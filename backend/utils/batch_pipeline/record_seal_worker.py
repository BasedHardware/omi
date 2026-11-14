"""CPU-only continuous seal slots, reusing the canonical isolated repair child."""

from collections import deque
from datetime import datetime, timezone
import json
import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from config import record_seal_repair as config
from database import record_seal_worker as claims
from utils.batch_pipeline import record_seal_cluster_repair as repair
from utils.batch_pipeline.record_seal_budget import SweepBudget, BudgetExhausted
from utils.observability.firestore_probe_export import register_probe_collectors


def enabled():
    # Reuse repair's existing control per Deployment, including in the child.
    return config.enabled()


class Metrics:
    def __init__(self, release, namespace):
        self.registry = CollectorRegistry()
        register_probe_collectors(self.registry)
        labels = ('worker_release', 'namespace')
        values = (release, namespace)

        def gauge(suffix, help_text):
            return Gauge('omi_record_seal_' + suffix, help_text, labels, registry=self.registry).labels(*values)

        self.backlog = gauge('backlog', 'Unsealed completed record_pending rows, including claims and backoff')
        self.oldest = Gauge(
            'omi_record_seal_oldest_age_seconds',
            'Oldest unsealed finish age in the completed sample',
            labels,
            registry=self.registry,
        ).labels(*values)
        self.invalid_clocks = gauge(
            'invalid_clock_rows', 'Unsealed rows with invalid finish clocks in the completed sample'
        )
        self.fresh = gauge('refreshed_at_seconds', 'Start time of the last fully completed sample')
        self.sealed = Counter(
            'omi_record_seal_sealed', 'Rows sealed by this slot', labels, registry=self.registry
        ).labels(*values)
        self.age = Histogram(
            'omi_record_seal_age_seconds',
            'Finish-to-seal age for successful attempts',
            labels,
            buckets=(60, 300, 600, 900, 1800, 3600, 7200, 14400, float('inf')),
            registry=self.registry,
        ).labels(*values)
        self.outcomes = Counter(
            'omi_record_seal_attempts', 'Closed-set row dispositions', (*labels, 'disposition'), registry=self.registry
        )
        self.labels = values
        self.invalid = Counter(
            'omi_record_seal_invalid_jobs', 'Malformed pending identities skipped', labels, registry=self.registry
        ).labels(*values)
        # An uninitialized gauge is not a successful empty sample.
        self.backlog.set(float('nan'))
        self.oldest.set(float('nan'))
        self.invalid_clocks.set(float('nan'))

    def sample(self, count, oldest, started, invalid_clock_rows):
        self.backlog.set(count)
        self.oldest.set(oldest)
        self.invalid_clocks.set(invalid_clock_rows)
        self.fresh.set(started)

    def outcome(self, disposition, age):
        self.outcomes.labels(*self.labels, disposition).inc()
        if disposition in {'sealed', 'sealed_registered', 'upload_failed_cleared'}:
            self.sealed.inc()
            if age is not None:
                self.age.observe(age)


class Scanner:
    """One bounded page at a time; publish only after the entire frozen pass.

    Each pod reports the same global debt; adapter max deduplicates replicas.
    Age/count include backoff debt; candidate selection excludes it. Private
    identifiers are only in memory/child stdin, never metrics or logs.
    """

    def __init__(self, client, namespace, metrics):
        self.client, self.namespace, self.metrics = client, namespace, metrics
        self.reset()

    def reset(self):
        self.after = None
        self.started = time.time()
        self.horizon = datetime.fromtimestamp(self.started, timezone.utc)
        self.count, self.oldest, self.invalid_clock_rows = 0, 0, 0

    def page(self, *, candidates=True):
        jobs, after = claims.pending_page(self.client, self.namespace, horizon=self.horizon, after=self.after)
        valid = []
        for job_id, job in jobs:
            try:
                valid.append((job_id, job, claims.conversation_ref(self.client, job)))
            except ValueError:
                self.metrics.invalid.inc()
        refs = [ref for _, _, ref in valid]
        rows = (
            {
                doc.reference.path: doc.to_dict() or {}
                for doc in self.client.get_all(refs, field_paths=list(claims.ROW_FIELDS), timeout=10, retry=None)
            }
            if refs
            else {}
        )
        now = time.time()
        selected = []
        # Do not mutate partial-pass counters/frontier until every read succeeds.
        count, oldest, invalid_clock_rows = 0, 0, 0
        for job_id, job, ref in valid:
            row = rows.get(ref.path, {})
            if claims.is_debt(row):
                count += 1
                stamp = row['finished_at'].timestamp()
                if repair.valid_metric_clock(stamp):
                    oldest = max(oldest, max(0, now - stamp))
                else:
                    invalid_clock_rows += 1
                if candidates and claims.ready(job.get('seal_claim') or {}, now):
                    selected.append(job_id)
        self.count += count
        self.invalid_clock_rows += invalid_clock_rows
        self.oldest = max(self.oldest, oldest)
        self.after = after
        complete = after is None
        if complete:
            # Timestamp the START: a long/incomplete pass cannot look fresh.
            self.metrics.sample(self.count, self.oldest, self.started, self.invalid_clock_rows)
            self.reset()
        return selected, complete


def row_result(process):
    try:
        payload = process.stdout.read(1025)
        value = json.loads(payload) if len(payload) <= 1024 else {}
        disposition = value.get('disposition')
        if process.returncode == 0 and disposition in repair.DISPOSITIONS:
            return disposition
    except Exception:
        pass
    return 'error'


class Worker:
    def __init__(self, client, namespace, metrics, *, launch=repair.launch_row, clock=time.monotonic):
        self.client, self.namespace, self.metrics = client, namespace, metrics
        self.scanner = Scanner(client, namespace, metrics)
        self.launch, self.clock = launch, clock
        self.pending = deque()
        self.active = None
        self.scan_at = 0

    def close(self, *, clear_pending=True, backoff=False):
        if self.active:
            process, _, claim = self.active
            # Reap FIRST. Preemption leaves the short claim to expire; only
            # completed attempts get refusal/budget backoff. Failed release
            # also leaves a safe expiring claim.
            try:
                repair.stop(process)
            finally:
                self.active = None
            if backoff:
                with SweepBudget(10).interrupt_io():
                    claims.release(self.client, self.namespace, claim)
        if clear_pending:
            self.pending.clear()

    def tick(self):
        if not enabled():
            self.close()
            return  # No discovery/claims/cloud access while disabled.
        if self.active:
            process, deadline, claim = self.active
            disposition = None
            if process.poll() is not None:
                disposition = row_result(process)
            elif self.clock() >= deadline:
                disposition = 'budget_exhausted'
            if disposition:
                stamp = claim['finished_at'].timestamp()
                age = max(0, time.time() - stamp) if repair.valid_metric_clock(stamp) else None
                self.metrics.outcome(disposition, age)
                self.close(clear_pending=False, backoff=True)
        # Sampling continues during the child walk. Bounded main-thread IO
        # adds at most 10s cleanup latency, still well inside the 360s claim.
        if self.clock() >= self.scan_at:
            with SweepBudget(10).interrupt_io():
                selected, complete = self.scanner.page(candidates=not self.active)
            self.pending.extend(selected)
            self.scan_at = self.clock() + (15 if complete else 0.5)
        if not self.active:
            while self.pending:
                job_id = self.pending.popleft()
                with SweepBudget(10).interrupt_io():
                    claim = claims.acquire(self.client, self.namespace, job_id)
                if claim is None:
                    continue
                # Keep the claim if launch is interrupted/ambiguous: expiry
                # is safer than releasing while an untracked child may exist.
                process = self.launch(claim['path'], 270, 'apply')
                self.active = (process, self.clock() + 270, claim)
                break


def run(release, namespace, *, pause=time.sleep, emit=lambda _: None):
    from prometheus_client import start_http_server

    if enabled():
        # Readiness is /metrics, so refuse policy before serving it: a pod with
        # an absent or invalid map crash-loops instead of reporting Ready idle.
        try:
            config.require_runtime()
            config.server_flags()
        except Exception:
            emit({'event': 'record_seal_worker', 'outcome': 'error', 'stage': 'policy'})
            raise SystemExit(1) from None
    metrics = Metrics(release, namespace)
    server, thread = start_http_server(8080, registry=metrics.registry)
    worker = None
    try:
        while True:
            try:
                if enabled() and worker is None:
                    from database._client import get_data_plane_firestore_client

                    worker = Worker(get_data_plane_firestore_client(), 'batch_pipeline_prod', metrics)
                if worker:
                    worker.tick()
            except (Exception, BudgetExhausted):
                # No provider payloads or private identifiers escape. Failed
                # samples retain their old timestamp; the adapter fails closed.
                if worker:
                    worker.pending.clear()
                emit({'event': 'record_seal_worker', 'outcome': 'error', 'stage': 'tick' if worker else 'startup'})
                pause(5)
            pause(0.1)
    finally:
        try:
            if worker:
                worker.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

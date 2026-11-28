"""Serving-side lease API. Authentication is at the router; all IO is lazy."""

import random
import asyncio
from functools import lru_cache
from datetime import datetime, timezone
import logging
import os
from threading import Lock
import time

from config import batch_pipeline_protected_share as protected_share
from config.batch_pipeline import (
    batch_held_dead_letter_enabled,
    held_partial_enabled,
    owner_chain_projection_enabled,
    recovered_merge_release_enabled,
    recovery_owner_only_enabled,
    recovery_dispatch_interval_seconds,
    projection_hold_recovery_enabled,
    projection_outbox_enabled,
    serving_metrics_min_refresh_seconds,
    serving_projection_sweep_enabled,
    serving_tick_seconds,
    projection_pump_enabled,
    projection_pump_sweep_pages,
    projection_pump_tick_seconds,
)
from database.privacy_check_metrics import BatchPrivacyPath, with_batch_privacy_path
from database.outbox import OutboxKind, outbox_for
from database.batch_privacy_attempt import batch_privacy_attempt, with_batch_privacy_attempt
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_shadow_hook import shadow_from_env
from database.batch_pipeline_staging import reap
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.live import drain_recordings
from utils.batch_pipeline.projection import HELD_PARTIAL_PAGE, Projector, error_type
from utils.batch_pipeline.projection_outbox import ProjectionOutbox
from utils.executors import db_executor, run_blocking, start_background_task, sync_executor
from utils.batch_pipeline.contracts import PoolCapacity, WorkResult
from config.batch_pipeline_leader import UPLOAD_COALESCING_SCAN, UPLOAD_COALESCING_SCAN_TTL
from utils.batch_pipeline.leader import (
    QUEUE_METRICS,
    SERVING_LEGACY_METRICS,
    SERVING_MAINTENANCE,
    LeaderLease,
)
from utils.batch_pipeline.held_dead_letter import HeldDeadLetter, ProjectionHeldDeadLetter
from utils.batch_pipeline.ready_discovery import ReadyDiscovery
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler
from database.batch_pipeline_recovery_discovery import RecoveryCaller
from utils.batch_pipeline.allowance_hold import AllowanceHolds, entitlement
from utils.batch_pipeline.retention import cleanup_completed_artifacts
from utils.sync.stage import current_stage
from utils.sync import reprocess

HELD_PARTIAL_INTERVAL_SECONDS = 300
# One maintenance tick chains held-partial pages into at most this much sweep
# time; a pass stopped by either budget keeps its cursor and resumes on the
# next supervisor tick instead of waiting out the interval above.
HELD_PARTIAL_TICK_SECONDS = 20.0
# Hourly read governor for the held sweep. The sweep charges its exact
# code-derived read count (one per examined document plus 5 per sibling and 7
# per attempted upload); this per-unit figure is only the pacing estimate for
# the page cap and the fallback for projector models that report no reads.
# 16 is the measured worst case for an upload per held unit (15 attempt reads
# + the query read; steady replays cost 14).
HELD_PARTIAL_READS_PER_HOUR = 120_000
HELD_PARTIAL_READS_PER_UNIT = 16
# One lookup and one normal CAS read per sweep segment. Charge retries after execution.
HELD_PARTIAL_CHECKPOINT_READ_RESERVE = 2
HELD_PARTIAL_WINDOW_SECONDS = 3600.0
# Re-examine landed targets at most once per minute on the maintenance leader.
# One page has its own inter-row time budget, so fresh projection resumes.
RELEASE_HELD_INTERVAL_SECONDS = 60.0
# Count keys of one held-partial pass, summed across its budget-resumed segments.
HELD_PASS_COUNT_KEYS = ('pages', 'units', 'partial', 'waiting', 'error', 'reads')


class Serving:
    def __init__(
        self,
        store,
        *,
        metrics=None,
        projector=None,
        cleanup=None,
        reap_staging=None,
        enrichment_sweep=None,
        recovery=None,
        leader=None,
        legacy_metrics_leader=None,
        outbox=None,
    ):
        self.store = store
        self.metrics = metrics
        # Bounded process state: retry cursors and small-pull share cadence
        # must survive queue() calls on the serving/maintenance plane too.
        self._queues = {pool: Scheduler(store, metrics=metrics, pool=pool) for pool in ('batch', 'live')}
        self.projector = projector
        self.outbox = outbox
        self.cleanup = cleanup
        self.reap_staging = reap_staging
        self.enrichment_sweep = enrichment_sweep
        self.recovery = recovery
        self.allowance_hold_due = 0.0
        # Optional single-owner lease for periodic maintenance (see reconcile).
        self.leader = leader
        # A non-serving legacy /metrics process still runs idempotent maintenance,
        # but must not hold the lease used by the serving supervisor.
        self.legacy_metrics_leader = legacy_metrics_leader
        self.held_dead_letter = HeldDeadLetter(store, metrics=metrics)
        self.projection_held_dead_letter = ProjectionHeldDeadLetter(store, metrics=metrics)
        self.merge = OrderedMerge(store, metrics=metrics)
        self.ready_discovery = ReadyDiscovery(store, 'serving')
        # Held units change only on a recovery or operator settle: scan them
        # at a slow cadence, not every maintenance pass.
        self.held_partial_due = 0.0
        # Restore redrives are rarer still: one bounded page per slow tick.
        self.release_held_due = 0.0
        # (monotonic instant, reads charged) pairs: the hourly read governor.
        # Per serving instance; the maintenance lease usually pins one leader.
        self.held_partial_reads: list[tuple[float, int]] = []
        # The held-partial pass across budget-resumed segments: the first
        # segment's monotonic start and its summed counts. A wrapped scan
        # (``more == 0``) closes it; deferred ticks and failed sweeps leave an
        # in-flight pass alone.
        self.held_pass_started: float | None = None
        self.held_pass_counts = dict.fromkeys(HELD_PASS_COUNT_KEYS, 0)
        self.held_pass_segments = 0

    def queue(self, pool='batch'):
        if not protected_share.enabled():
            return Scheduler(self.store, metrics=self.metrics, pool=pool)
        if pool not in self._queues:
            raise ValueError('pool must be batch or live')
        return self._queues[pool]

    @with_batch_privacy_path(BatchPrivacyPath.INTEGRATION_SERVING)
    def pull(self, limit: int, capacity: PoolCapacity, *, pool: str = 'batch'):
        return self.queue(pool).pull(time.time(), limit, capacity=capacity)

    @with_batch_privacy_path(BatchPrivacyPath.INTEGRATION_SERVING)
    def complete(self, result: WorkResult, token: str) -> bool:
        accepted = self.queue().complete(result, token, time.time())
        if accepted:
            job = self.store.run(lambda tx: tx.get('jobs', result.segment_id))
            if job:
                self.drain_owner(job['owner_id'])
        return accepted

    def drain_owner(self, owner_id: str, *, recovered: str | None = None):
        """Commit the owner's ready rows. ``recovered`` (a recovery wake) also
        releases that unit and its content's ready siblings past the head wait
        (the unit itself also past the catch-up depth hold)."""
        release = (
            self.merge.release_set(recovered) if recovered is not None and recovered_merge_release_enabled() else None
        )
        for _ in range(100):
            entry = self.merge.commit_next(owner_id, time.time(), release=release)
            if entry is None:
                break
            if self.outbox is not None:
                self.outbox.wake(entry)

    @with_batch_privacy_attempt
    async def drain_settled_async(self, owner_id: str) -> None:
        """A provider unit of ``owner_id`` settled: commit the owner's ready rows and walk its chain.

        The owner-only half of a recovery wake without a recovered unit, so no row skips the head
        wait or the catch-up depth hold. Global maintenance stays with the periodic owner.
        """
        priority = await run_blocking(sync_executor, self._reconcile_owner, owner_id, None)
        if self.projector:
            if priority:
                await self.projector.start_followups(priority, discover=False)
            if getattr(self.projector, 'owes_index', False) is True:
                self.projector.schedule_index_flush(owner_id)

    @with_batch_privacy_attempt
    async def reconcile_async(
        self,
        *,
        recover_quarantine=False,
        periodic=False,
        owner_id=None,
        recovered=None,
        owner_only=False,
        run_held_expiry=True,
    ):
        owner_only = owner_only and recovery_owner_only_enabled()
        priority = await run_blocking(
            sync_executor,
            self.reconcile,
            recover_quarantine=recover_quarantine,
            periodic=periodic,
            owner_id=owner_id,
            recovered=recovered,
            owner_only=owner_only,
            run_held_expiry=run_held_expiry,
        )
        # Walk-owed follow-ups keep the drain scheduled until they are queued.
        owes = getattr(self.projector, 'owes_followups', False) is True
        if self.projector:
            if owner_only:
                if priority:
                    await self.projector.start_followups(priority, discover=False)
            elif priority or self.projector.has_async_followups or owes:
                await self.projector.start_followups(priority or ())
        # A recovery wake may leave a durable owner continuation, but it must
        # not consume the process-wide queue of owners discovered by a sweep.
        # The periodic maintenance owner starts those drains on its next pass.
        if self.projector and not owner_only and getattr(self.projector, 'owes_drains', False) is True:
            self.projector.start_drains()
        # Deferred search/people-stats work left by walks converges off the chain.
        if self.projector and getattr(self.projector, 'owes_index', False) is True:
            self.projector.schedule_index_flush(owner_id if owner_only else None)

    def _leads(self, periodic: bool, *, leader=None) -> bool:
        # Explicit global RPC callers (POST /reconcile) always
        # run. Periodic ticks (supervisor, metrics scrape) run maintenance on
        # one serving instance per lease TTL; the lease fails open.
        lease = self.leader if leader is None else leader
        return not periodic or lease is None or lease.acquire()

    def _maintenance_leader(self, *, run_held_expiry: bool):
        # The held-expiry supervisor owns SERVING_MAINTENANCE. Any maintenance
        # pass that skips its inline expiry tick uses the separate lease.
        if not run_held_expiry and self.legacy_metrics_leader is not None:
            return self.legacy_metrics_leader
        return self.leader

    def refresh_serving_fresh_guard(self) -> bool:
        """Use the same lease as the serving loop, which leaves expiry to its supervisor."""
        return self.refresh_fresh_guard(leader=self._maintenance_leader(run_held_expiry=False))

    def _reconcile_owner(self, owner_id: str, recovered: str | None) -> list[str]:
        # The settled job remains result_ready/merge_pending until the fenced
        # commit; pending/persisted receipts then own projection/follow-up retry.
        # A failed request needs no in-memory callback to be rediscovered.
        try:
            self.drain_owner(owner_id, recovered=recovered)
            if self.projector and owner_chain_projection_enabled():
                return self.projector.project_owner(owner_id, recovered=recovered)
        except Exception as error:
            logging.getLogger(__name__).error(
                'event=batch_projection action=owner_chain outcome=retry exception_type=%s', error_type(error)
            )
        return []

    @with_batch_privacy_path(BatchPrivacyPath.INTEGRATION_SERVING)
    def reconcile(
        self,
        *,
        recover_quarantine=False,
        periodic=False,
        owner_id=None,
        recovered=None,
        owner_only=False,
        run_held_expiry=True,
    ) -> list[str]:
        """Returns async follow-ups an owner-chain wake wants run first."""
        if owner_only:
            if owner_id is None or recovered is None:
                raise ValueError('owner-only recovery requires an owner and recovered unit')
            return self._reconcile_owner(owner_id, recovered)
        # Metrics and explicit request paths may skip inline expiry. Keep their
        # maintenance on the separate lease so they cannot retain the
        # supervisor's expiry lease while omitting its tick.
        maintenance_leader = self._maintenance_leader(run_held_expiry=run_held_expiry)
        if self._leads(periodic, leader=maintenance_leader):
            maintenance_options = {}
            if maintenance_leader is not self.leader:
                maintenance_options['maintenance_leader'] = maintenance_leader
            self._maintain(
                recover_quarantine=recover_quarantine,
                recovery_caller=RecoveryCaller.SERVING if periodic else RecoveryCaller.RECONCILE,
                run_held_expiry=run_held_expiry,
                **maintenance_options,
            )
        elif self.metrics:
            self.metrics.fresh_guard.deactivate()
            self.metrics.delivered_share.deactivate()
        priority = []
        if owner_id is not None and self.projector and owner_chain_projection_enabled():
            # A settled recovery commits at this owner's log tail. Walk the
            # owner's chain now instead of waiting for the global cursor. The
            # wake is only a hint: on failure the generic sweep still runs.
            priority = self._reconcile_owner(owner_id, recovered)
        # Projection is throughput, ordered and fenced in its own transactions.
        # Metrics elect their own queue sampler; local samplers stay per instance.
        if self.projector and serving_projection_sweep_enabled():
            self.projector.sweep()
        # Catch-up rows this instance held for projection depth may now fit.
        for held_owner in list(self.merge.held_owners):
            try:
                self.drain_owner(held_owner)
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_merge action=held_drain outcome=retry exception_type=%s', type(error).__name__
                )
        if self.metrics:
            self.metrics.refresh(self.store, time.time())
        return priority

    def dispatch_recovery(self):
        """Dispatch-loop tick: quarantine recovery only, on the maintenance leader."""
        if self.recovery is None or not self._leads(True):
            return None
        return self.recovery.sweep()

    def sweep_held_dead_letters(self, *, periodic=False):
        if not batch_held_dead_letter_enabled() or not self._leads(periodic):
            return
        try:
            self.held_dead_letter.tick(time.time())
        except Exception as error:
            logging.getLogger(__name__).error(
                'event=batch_held_dead_letter outcome=retry exception_type=%s', type(error).__name__
            )

    def _charge_held_partial_reads(self, counts: dict) -> None:
        reads = counts.get('reads')
        if not isinstance(reads, int) or reads < 0:
            reads = counts.get('units', 0) * HELD_PARTIAL_READS_PER_UNIT
        if reads > 0:
            self.held_partial_reads.append((time.monotonic(), reads))

    def _held_partial_page_budget(self) -> int:
        """Full pages this tick may still examine under the hourly read governor."""
        now = time.monotonic()
        self.held_partial_reads = [
            charged for charged in self.held_partial_reads if now - charged[0] < HELD_PARTIAL_WINDOW_SECONDS
        ]
        spent = sum(reads for _, reads in self.held_partial_reads)
        remaining = max(0, HELD_PARTIAL_READS_PER_HOUR - spent - HELD_PARTIAL_CHECKPOINT_READ_RESERVE)
        return remaining // (HELD_PARTIAL_PAGE * HELD_PARTIAL_READS_PER_UNIT)

    def _log_held_partial_segment(self, counts: dict, segment_started: float, budget_pages: int) -> None:
        """One INFO line per sweep segment; a wrapped scan closes the pass with
        one summed line. Counts and durations only, never an id."""

        def count(key: str) -> int:
            value = counts.get(key)
            return value if isinstance(value, int) and value >= 0 else 0

        now = time.monotonic()
        if self.held_pass_started is None:
            self.held_pass_started = segment_started
            self.held_pass_segments = 0
            self.held_pass_counts = dict.fromkeys(HELD_PASS_COUNT_KEYS, 0)
        for key in HELD_PASS_COUNT_KEYS:
            self.held_pass_counts[key] += count(key)
        self.held_pass_segments += 1
        logging.getLogger(__name__).info(
            'event=batch_held_partial action=segment pages=%d units=%d partial=%d waiting=%d error=%d reads=%d '
            'more=%d elapsed_ms=%d budget_pages=%d',
            count('pages'),
            count('units'),
            count('partial'),
            count('waiting'),
            count('error'),
            count('reads'),
            1 if counts.get('more') else 0,
            int((now - segment_started) * 1000),
            budget_pages,
        )
        if not counts.get('more'):
            logging.getLogger(__name__).info(
                'event=batch_held_partial action=pass outcome=%s segments=%d pages=%d units=%d partial=%d '
                'waiting=%d error=%d reads=%d pass_seconds=%.1f',
                'cursor_unconfirmed' if counts.get('wrap_unconfirmed') else 'completed',
                self.held_pass_segments,
                self.held_pass_counts['pages'],
                self.held_pass_counts['units'],
                self.held_pass_counts['partial'],
                self.held_pass_counts['waiting'],
                self.held_pass_counts['error'],
                self.held_pass_counts['reads'],
                now - self.held_pass_started,
            )
            self.held_pass_started = None

    def refresh_fresh_guard(self, *, leader=None) -> bool:
        """Use the selected maintenance lease, including outside the potentially slow pass."""
        if not self.metrics:
            return False
        # Explicit reconcile bypasses the periodic lease; the guard never does.
        leads = self._leads(True, leader=leader)
        if leads:
            self.metrics.fresh_guard.refresh(self.store)
        else:
            self.metrics.fresh_guard.deactivate()
        return leads

    def _maintain(
        self,
        *,
        recover_quarantine: bool,
        recovery_caller=None,
        run_held_expiry=True,
        maintenance_leader=None,
    ):
        """Idempotent, transaction-fenced maintenance: cleanup, sweeps, discovery, recovery, drain."""
        leads = self.refresh_fresh_guard(leader=maintenance_leader)
        if self.metrics:
            if leads:
                self.metrics.delivered_share.refresh(self.store)
            else:
                self.metrics.delivered_share.deactivate()
        if self.cleanup:
            try:
                if self.reap_staging:
                    self.reap_staging(self.store, datetime.now(timezone.utc))
                self.cleanup(self.store, datetime.now(timezone.utc))
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_cleanup outcome=retry exception_type=%s', type(error).__name__
                )
        if self.enrichment_sweep:
            self.enrichment_sweep()
        if recover_quarantine and self.recovery:
            self.recovery.sweep()
        sweep_held = getattr(self.projector, 'sweep_held', None)
        if sweep_held is not None and time.monotonic() >= self.held_partial_due and held_partial_enabled():
            self.held_partial_due = time.monotonic() + HELD_PARTIAL_INTERVAL_SECONDS
            try:
                pages = self._held_partial_page_budget()
                if pages < 1:
                    # The hourly read governor is spent; rechecking it next tick
                    # costs no reads, and the backlog resumes as it refills.
                    self.held_partial_due = time.monotonic()
                else:
                    segment_started = time.monotonic()
                    counts = sweep_held(deadline=segment_started + HELD_PARTIAL_TICK_SECONDS, max_pages=pages)
                    if isinstance(counts, dict):
                        self._charge_held_partial_reads(counts)
                        self._log_held_partial_segment(counts, segment_started, pages)
                        if counts.get('more'):
                            # The tick or read budget stopped the pass mid-backlog.
                            self.held_partial_due = time.monotonic()
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_held_partial action=sweep outcome=retry exception_type=%s', type(error).__name__
                )
        release_held = getattr(self.projector, 'release_held_scan', None)
        if release_held is not None and time.monotonic() >= self.release_held_due:
            self.release_held_due = time.monotonic() + (
                RELEASE_HELD_INTERVAL_SECONDS if projection_hold_recovery_enabled() else 900.0
            )
            try:
                release_counts = release_held()
                if self.metrics is not None and isinstance(release_counts, dict):
                    self.metrics.held_expired.inc(release_counts.get('expired', 0))
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_projection action=release_held outcome=retry exception_type=%s', type(error).__name__
                )
        if run_held_expiry:
            self.sweep_held_dead_letters()
        try:
            self.projection_held_dead_letter.tick(time.time())
        except Exception as error:
            logging.getLogger(__name__).error(
                'event=batch_projection action=redrive_expired outcome=retry exception_type=%s', type(error).__name__
            )
        self.queue().recover(time.time(), caller=recovery_caller)
        if time.monotonic() >= self.allowance_hold_due and self._leads(True, leader=maintenance_leader):
            self.allowance_hold_due = time.monotonic() + 30
            AllowanceHolds(self.store, entitlement).tick(time.time())
        page = self.ready_discovery.page()
        if page is not None:
            for _, owner_id in self.ready_discovery.owners(page):
                try:
                    if owner_id:
                        self.drain_owner(owner_id)
                except Exception as error:
                    logging.getLogger(__name__).warning(
                        'event=batch_merge action=ready_drain outcome=retry exception_type=%s count=1',
                        type(error).__name__,
                    )
        if page is None or not self.ready_discovery.finish(page):
            self._drain_ready_page()
        # Held owners by durable marker: the page above can be all one held backlog.
        self.merge.reoffer_marked(self.drain_owner)

    def _drain_ready_page(self):
        owners = set()
        for segment in self.store.due('result_ready', time.time(), 100):
            job = self.store.run(lambda tx: tx.get('jobs', segment))
            if job and job['owner_id'] not in owners:
                owners.add(job['owner_id'])
                try:
                    self.drain_owner(job['owner_id'])
                except Exception as error:
                    # One fenced head must not stop the other owners or the held re-offer.
                    logging.getLogger(__name__).warning(
                        'event=batch_merge action=ready_drain outcome=retry exception_type=%s count=1',
                        type(error).__name__,
                    )


_serving_lock = Lock()


def serving_for_stage(stage: str) -> Serving:
    # Serving, the pump, and the outbox can cold-start in different executor workers.
    with _serving_lock:
        return _serving_for_stage(stage)


@lru_cache(maxsize=2)
def _serving_for_stage(stage: str) -> Serving:
    if stage != current_stage():
        raise ValueError('worker and serving stages must match')
    store = shadow_from_env(FirestoreStore(f'batch_pipeline_{stage}'))
    artifacts = artifacts_for(store)
    projector = Projector(store, artifacts.load_result, fetch_audio=artifacts.fetch_audio)
    from utils.batch_pipeline.quarantine_recovery import QuarantineRecovery

    metrics = _metrics()
    # Reuse the existing lease implementation, with a separate role so a slow
    # maintenance pass cannot strand metrics ownership. Default serving cadence
    # is 40s (30s reservation + 20s ticks); 20s TTL hands over within 60s.
    metrics.oldest_leader = LeaderLease(store, QUEUE_METRICS, ttl_seconds=20)
    return Serving(
        store,
        recovery=QuarantineRecovery(store, artifacts),
        metrics=metrics,
        projector=projector,
        outbox=ProjectionOutbox(store, projector, clock=time.time),
        cleanup=cleanup_completed_artifacts,
        reap_staging=reap,
        enrichment_sweep=reprocess.sweep,
        # Supervisor ticks every 20s; a lapsed holder hands over within 60s.
        leader=LeaderLease(store, SERVING_MAINTENANCE, ttl_seconds=60),
        legacy_metrics_leader=LeaderLease(store, SERVING_LEGACY_METRICS, ttl_seconds=60),
    )


@lru_cache(maxsize=1)
def _metrics() -> QueueMetrics:
    return QueueMetrics(min_refresh_seconds=serving_metrics_min_refresh_seconds())


async def _supervise_backlog_heartbeat(stop):
    from utils.batch_pipeline.backlog_heartbeat import HeartbeatAuthority, TICK_SECONDS

    authority = None
    while not stop.is_set():
        try:
            if authority is None:
                service = await run_blocking(db_executor, serving_for_stage, current_stage())
                authority = HeartbeatAuthority(service.store)
            await run_blocking(db_executor, authority.tick)
        except Exception as error:
            logging.getLogger(__name__).error(
                'event=batch_backlog_heartbeat outcome=stopped exception_type=%s', type(error).__name__
            )
            return  # Fail closed until restart, even for config/ambiguous-commit errors.
        try:
            await asyncio.wait_for(stop.wait(), timeout=TICK_SECONDS)
        except asyncio.TimeoutError:
            pass


async def _supervise_fresh_guard(stop):
    # General maintenance (and its sync executor) may be occupied for minutes.
    # Keep the same lease as the serving loop, but borrow a DB thread only for
    # this bounded count pair. FreshGuard coalesces overlaps and enforces 60s spacing.
    while not stop.is_set():
        try:
            service = await run_blocking(db_executor, serving_for_stage, current_stage())
            await run_blocking(db_executor, service.refresh_serving_fresh_guard)
        except Exception as error:
            logging.getLogger(__name__).error(
                'event=batch_fresh_guard outcome=retry exception_type=%s', type(error).__name__
            )
        try:
            await asyncio.wait_for(stop.wait(), timeout=20)
        except asyncio.TimeoutError:
            pass


async def _supervise_held_dead_letters(stop):
    # A slow or failed reconciliation (including quarantine discovery) must
    # still let the maintenance leader scan and expire dormant holds.
    while not stop.is_set():
        try:
            if batch_held_dead_letter_enabled():
                service = await run_blocking(db_executor, serving_for_stage, current_stage())
                with batch_privacy_attempt():
                    await run_blocking(db_executor, service.sweep_held_dead_letters, periodic=True)
        except Exception as error:
            logging.getLogger(__name__).error(
                'event=batch_held_dead_letter outcome=retry exception_type=%s', type(error).__name__
            )
        try:
            await asyncio.wait_for(stop.wait(), timeout=serving_tick_seconds())
        except asyncio.TimeoutError:
            pass


def start_serving_from_env():
    """Start projection consumers on the processes that own projection policy."""
    pump_enabled = projection_pump_enabled()
    serving_enabled = os.getenv('BATCH_PIPELINE_SERVING_ENABLED', 'false').strip().lower() == 'true'
    if not (pump_enabled or serving_enabled):
        return None
    outbox_enabled = projection_outbox_enabled()
    stop = asyncio.Event()

    async def projection_pump():
        # Dedicated instances only discover and drain owners. They never enter
        # reconcile or either leader-leased maintenance/recovery path.
        metrics = _metrics()
        while not stop.is_set():
            started = time.monotonic()
            sweeps = owners_requested = 0
            try:
                service = await run_blocking(sync_executor, serving_for_stage, current_stage())
                projector = service.projector
                if projector is None:
                    raise RuntimeError('projection pump requires a projector')
                for _ in range(projection_pump_sweep_pages()):
                    await run_blocking(sync_executor, projector.sweep)
                    sweeps += 1
                    if projector.has_async_followups or getattr(projector, 'owes_followups', False) is True:
                        await projector.start_followups(())
                    if getattr(projector, 'owes_index', False) is True:
                        projector.schedule_index_flush()
                if projector.owes_drains:
                    with projector.handoff:
                        owners_requested = len(projector.drain_requests)
                    projector.start_drains()
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_projection_pump outcome=retry exception_type=%s', type(error).__name__
                )
            else:
                metrics.projection_pump_last_success.set(time.time())
            finally:
                metrics.projection_pump_last_tick.set(time.time())
                logging.getLogger(__name__).info(
                    'event=batch_projection_pump outcome=tick sweeps=%d owners_requested=%d elapsed_seconds=%.3f',
                    sweeps,
                    owners_requested,
                    time.monotonic() - started,
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=projection_pump_tick_seconds())
            except asyncio.TimeoutError:
                pass

    async def supervise():
        while not stop.is_set():
            try:
                service = await run_blocking(sync_executor, serving_for_stage, current_stage())
                await service.reconcile_async(recover_quarantine=True, periodic=True, run_held_expiry=False)
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_serving outcome=retry exception_type=%s', type(error).__name__
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=serving_tick_seconds())
            except asyncio.TimeoutError:
                pass

    async def supervise_projection_outbox():
        while not stop.is_set():
            try:
                service = await run_blocking(sync_executor, serving_for_stage, current_stage())
                outbox = getattr(service, 'outbox', None)
                if outbox is not None:
                    await outbox.run(stop)
                    return
            except Exception as error:
                logging.getLogger(__name__).warning(
                    'event=batch_projection_outbox outcome=supervise_retry exception_type=%s', type(error).__name__
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=serving_tick_seconds())
            except TimeoutError:
                pass

    @with_batch_privacy_attempt
    async def drain_tick():
        service = await run_blocking(sync_executor, serving_for_stage, current_stage())
        return await drain_recordings(
            service.store,
            provider_outbox_factory=lambda: outbox_for(OutboxKind.PROVIDER_STT),
            metrics=getattr(service, 'metrics', None),
        )

    async def drain():
        # Record admission must not wait for a full reconciliation pass.
        while not stop.is_set():
            try:
                if await drain_tick():
                    # Keep draining a backlog without the idle poll delay, but
                    # always yield so shutdown and sibling loops can progress.
                    await asyncio.sleep(0)
                    continue
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_serving action=record_drain outcome=retry exception_type=%s', type(error).__name__
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=20)
            except asyncio.TimeoutError:
                pass

    async def dispatch_recovery():
        # Quarantine -> recovery start rode the whole serving pass plus its 20 s
        # sleep; this loop dispatches on its own short cadence.
        while not stop.is_set():
            interval = recovery_dispatch_interval_seconds()
            if interval > 0:
                try:
                    service = await run_blocking(sync_executor, serving_for_stage, current_stage())
                    await run_blocking(sync_executor, service.dispatch_recovery)
                except Exception as error:
                    logging.getLogger(__name__).error(
                        'event=batch_serving action=recovery_dispatch outcome=retry exception_type=%s',
                        type(error).__name__,
                    )
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval if interval > 0 else 20)
            except asyncio.TimeoutError:
                pass

    async def drain_upload_holds():
        from utils.batch_pipeline.upload_coalescing import drain as drain_uploads

        leader = None
        try:
            await asyncio.wait_for(stop.wait(), timeout=random.uniform(0, 2))
        except asyncio.TimeoutError:
            pass

        while not stop.is_set():
            try:
                service = await run_blocking(sync_executor, serving_for_stage, current_stage())
                if leader is None:
                    leader = LeaderLease(service.store, UPLOAD_COALESCING_SCAN, ttl_seconds=UPLOAD_COALESCING_SCAN_TTL)
                await drain_uploads(service.store, leader=leader)
            except Exception as error:
                logging.getLogger(__name__).warning(
                    'event=batch_coalescing outcome=scan_retry exception_type=%s', type(error).__name__
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    async def run():
        from utils.batch_pipeline.projection_drain import set_recurring_sweep

        # Owner drains hold live-target owners passively only while this loop
        # will sweep them again.
        set_recurring_sweep('pump' if pump_enabled else 'serving')
        try:
            if pump_enabled:
                loops = (projection_pump(), drain_upload_holds())
            else:
                loops = (
                    supervise(),
                    drain(),
                    dispatch_recovery(),
                    _supervise_held_dead_letters(stop),
                    drain_upload_holds(),
                    _supervise_fresh_guard(stop),
                    _supervise_backlog_heartbeat(stop),
                )
            if outbox_enabled:
                loops += (supervise_projection_outbox(),)
            await asyncio.gather(*loops)
        finally:
            set_recurring_sweep(None)

    supervisor_name = 'batch_projection_pump' if pump_enabled else 'batch_pipeline_serving'
    return stop, start_background_task(run(), name=supervisor_name)


async def stop_serving(runtime):
    if runtime is None:
        return
    stop, task = runtime
    stop.set()
    # Allow any transactional projection to finish; retries are durable if the
    # process shutdown budget ends first. Recovery may await a bounded legacy STT request; its durable started intent
    # prevents a replacement process from issuing it again.
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=5)
    except asyncio.TimeoutError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

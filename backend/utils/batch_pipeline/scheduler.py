"""Fenced, duration-fair pull scheduling over durable transactional documents."""

from dataclasses import asdict
import hashlib
import math
import logging
import uuid

from database.batch_pipeline_store import Store, Transaction
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from config.batch_pipeline import FRESH_CAPTURE_LAG_SECONDS, scheduler_control_key
from config.policy import resolve_batch_policy
from config.stt_cap_dispatch import offline_admission_enabled as cap_dispatch_enabled
from database.batch_pipeline_policy import stage_in_transaction, record_policy_observations
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import LeasedWork, Priority, WorkItem, WorkResult, PoolCapacity, attach_held_vad
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.control import read_control, activate, field, migrate_legacy
from utils.batch_pipeline.errors import validate_worker_failure
from utils.batch_pipeline.retry_policy import quarantine_job, expire_lease, observe_recovery

QUANTUM_SECONDS = 30.0
LEASE_SECONDS = 120.0
RETRY_BACKOFF_CAP_SECONDS = 600
MAX_ACTIVE_OWNERS = 1024
MAX_VISITS = 128
HEAD_OWNER_BUDGET = 64
logger = logging.getLogger(__name__)


def _admission_retry_delay(value: object, streak: int) -> float:
    minimum = min(300, 30 * 2 ** (streak - 1))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return minimum
    if isinstance(value, float) and not math.isfinite(value):
        return minimum
    return max(minimum, min(86400, value))


def owner_key(owner_id: str) -> str:
    return hashlib.sha256(owner_id.encode()).hexdigest()


def _append(tx: Transaction, control: dict, job: dict) -> None:
    queue_key = f"{job['priority']}_{job['owner_key']}"
    queue = tx.get('queues', queue_key) or {'head': '', 'tail': '', 'deficit': 0.0, 'continuing': False}
    ring = control['rings'][str(job['priority'])]
    if not queue['head']:
        if len(ring) >= MAX_ACTIVE_OWNERS:
            raise RuntimeError('active owner capacity exceeded; admission must retry')
        if queue_key not in ring:
            ring.append(queue_key)
        queue['head'] = job['segment_id']
        queue['deficit'] = 0.0
        queue['continuing'] = False
    else:
        tail = tx.get('jobs', queue['tail'])
        tail['next'] = job['segment_id']
        tx.put('jobs', tail['segment_id'], tail)
    queue['tail'] = job['segment_id']
    job['next'] = ''
    tx.put('queues', queue_key, queue)
    activate(tx, control, job['priority'], job['available_at'])
    tx.put('control', scheduler_control_key(job['owner_key']), control)


def _pool_allows(job: dict, max_seconds: float, shared_gpu: bool) -> bool:
    return job['duration_seconds'] <= max_seconds and not (
        shared_gpu and job.get('unit_kind', 'conversation') != 'capture_span'
    )


def _prefer_merge_head(
    tx: Transaction,
    queue: dict,
    job: dict,
    budget: list[int],
    observations: list,
    *,
    now: float,
    max_seconds: float,
    shared_gpu: bool,
    candidates=None,
) -> dict:
    """Promote an indexed capture head with O(1) queries, independent of FIFO depth.

    The budget bounds owners visited, not positions within an owner's backlog.
    An ordinary FIFO remains valid with head priority disabled. Compute can run
    concurrently for an owner; OrderedMerge alone enforces pending predecessors.
    """
    if budget[0] <= 0:
        observations.append(('budget_exhausted', None))
        return job
    budget[0] -= 1
    head = tx.first_pending(job['owner_key'])
    if not head:
        observations.append(('head_not_found', None))
        return job
    if head['state'] == 'ready':
        observations.append(('ready_age', max(0.0, now - head['available_at'])))
    if (
        head['segment_id'] == job['segment_id']
        or head['state'] != 'ready'
        or head['priority'] != job['priority']
        or not _pool_allows(head, max_seconds, shared_gpu)
    ):
        return job
    previous = tx.ready_predecessor(job['owner_key'], job['priority'], head['segment_id'])
    if not previous or previous.get('next') != head['segment_id']:
        observations.append(('head_not_found', None))
        return job
    try:
        for linked in (previous, head):
            tx.check_privacy(
                linked['owner_id'],
                (linked['conversation_id'],) if linked.get('conversation_id') else (),
                linked.get('privacy_generation'),
            )
    except BatchPrivacyBlocked:
        return job
    if not stage_in_transaction(tx, head, 'scheduler', observations=observations, candidates=candidates).head_priority:
        return job
    previous['next'] = head['next']
    tx.put('jobs', previous['segment_id'], previous)
    if queue['tail'] == head['segment_id']:
        queue['tail'] = previous['segment_id']
    head['next'] = queue['head']
    queue['head'] = head['segment_id']
    tx.put('jobs', head['segment_id'], head)
    return head


def owns_lease(job: dict, token: str, now: float) -> bool:
    return job.get('state') == 'leased' and job.get('token') == token and job['lease_until'] > now


def _defer(job: dict, now: float, reason: str) -> None:
    job.update(
        state='retry',
        available_at=now + min(RETRY_BACKOFF_CAP_SECONDS, 5 * 2 ** min(7, max(0, job['attempt'] - 1))),
        retry_started_at=job.get('retry_started_at', now),
        token='',
        lease_until=0.0,
        # Only bounded machine reason codes belong here, never provider errors/text.
        failure=reason,
    )


class Scheduler:
    def __init__(self, store: Store, *, metrics: QueueMetrics | None = None, pool: str = 'batch'):
        if pool not in {'batch', 'live'}:
            raise ValueError('pool must be batch or live')
        self.store = store
        self.metrics = metrics
        self.pool = pool

    def enqueue(self, item: WorkItem, now: float) -> bool:
        return self.store.run(lambda tx: self.enqueue_in_transaction(tx, item, now))

    @staticmethod
    def enqueue_in_transaction(tx: Transaction, item: WorkItem, now: float, *, policy=None) -> bool:
        if item.shadow:
            raise ValueError('shadow jobs may only use idle offers')
        previous = tx.get('jobs', item.segment_id)
        # Live jobs are never shadow; keep their documents free of the field.
        immutable = {key: value for key, value in asdict(item).items() if key != 'shadow'}
        immutable['priority'] = int(item.priority)
        if previous.get('state') == 'record_pending' and (
            previous.get('owner_id') != item.owner_id
            or previous.get('conversation_id') != item.conversation_id
            or previous.get('privacy_generation') != item.privacy_generation
        ):
            raise ValueError('pending recording owner cannot change')
        if previous and previous.get('state') != 'record_pending':
            if any(
                previous.get(key, {'unit_kind': 'conversation', 'requires_compute_admission': False}.get(key)) != value
                for key, value in immutable.items()
                if not (key == 'privacy_generation' and value is None)
            ):
                raise ValueError('segment ID reused with different immutable work')
            return False
        policy = policy or resolve_batch_policy(item.owner_id)
        key = owner_key(item.owner_id)
        owner = tx.get('owners', key)
        watermark = owner.get('watermark')
        control = read_control(tx, scheduler_control_key(key))
        job = {
            **immutable,
            'policy': policy.to_dict(),
            'policy_source': 'admission',
            'protocol_version': 1,
            'owner_key': key,
            'enqueued_at': now,
            'state': 'ready',
            'attempt': 0,
            'token': '',
            'lease_until': 0.0,
            'available_at': now,
            'merge_pending': True,
            'late_capture': bool(
                watermark and (item.capture_at, item.segment_id) <= (watermark['capture_at'], watermark['segment_id'])
            ),
            # Merge class only: fresh rows commit ahead of the owner's catch-up backlog.
            'fresh_capture': now - item.capture_at - item.duration_seconds <= FRESH_CAPTURE_LAG_SECONDS,
        }
        _append(tx, control, job)
        tx.put('jobs', item.segment_id, job)
        # Admission and merge serialize through this fence even for different classes.
        owner['revision'] = owner.get('revision', 0) + 1
        tx.put('owners', key, owner)
        return True

    def pull(self, now: float, limit: int = 1, *, capacity: PoolCapacity | None = None) -> list[LeasedWork]:
        if not 1 <= limit <= 32:
            raise ValueError('pull limit must be in [1, 32]')
        if self.pool == 'live' and (capacity is None or not capacity.shared_with_live):
            return []
        if self.pool == 'batch' and capacity is not None and capacity.shared_with_live:
            return []
        # No snapshot is the dedicated-batch worker contract only. Shared live
        # callers must supply a fresh exclusive-admission snapshot every pull.
        allow_backfill, max_seconds, backfill_budget = True, 7200.0, limit
        if capacity is not None:
            slots, allow_backfill, max_seconds = capacity.limits(now, shared_live_enabled=True)
            limit = min(limit, slots)
            backfill_budget = max(0, slots - capacity.reserved_fresh_slots)
        result = []
        for _ in range(limit):
            try:
                lease = self._pull_one(
                    now,
                    allow_backfill=allow_backfill and backfill_budget > 0,
                    max_seconds=max_seconds,
                    shared_gpu_id=capacity.gpu_id if capacity is not None and capacity.shared_with_live else None,
                )
            except Exception as error:
                if not result:
                    raise
                # Each earlier lease is its own committed transaction. Raising
                # would strand them leased until LEASE_SECONDS expiry and
                # charge a retry; hand them to the caller instead.
                logger.error(
                    'event=batch_pull outcome=partial leased=%d exception_type=%s', len(result), type(error).__name__
                )
                break
            if lease is None:
                break
            result.append(lease)
            if lease.item.priority != Priority.FRESH:
                backfill_budget -= 1
            if capacity is not None and capacity.shared_with_live:
                break  # One non-preemptible short item, never a mixed long batch.
        return result

    def _pull_one(
        self, now: float, *, allow_backfill: bool, max_seconds: float, shared_gpu_id: str | None = None
    ) -> LeasedWork | None:
        for priority in Priority:
            if priority != Priority.FRESH and not allow_backfill:
                break
            for _ in range(128):
                shard = self.store.control_candidate(int(priority), self.pool, now)
                if shard is None:
                    break
                receipt, eligible = self._pull_shard(now, shard, priority, max_seconds, shared_gpu_id)
                if receipt:
                    lease, enqueued_at = receipt
                    if self.metrics:
                        try:
                            self.metrics.record('leased', wait_seconds=now - enqueued_at)
                        except Exception:
                            pass  # Metrics cannot turn an issued lease into a failed pull.
                    return lease
                if eligible == 'reserved':
                    return None
                if eligible:
                    # Bounded deficit accrual must not bypass eligible fresh work.
                    continue
            else:
                return None
        return None

    def _pull_shard(self, now, shard, priority, max_seconds, shared_gpu_id):
        token = uuid.uuid4().hex
        candidates = {}

        def commit(tx):
            observations = []
            gpu_key = owner_key(shared_gpu_id) if shared_gpu_id is not None else ''
            gpu = tx.get('gpus', gpu_key) if gpu_key else {}
            if gpu.get('token'):
                return None, 'reserved', observations
            control = read_control(tx, shard)
            ring = control['rings'][str(int(priority))]
            eligible_queues, blocked = {}, set()
            owner_count = max(1, len(ring))
            head_budget = [HEAD_OWNER_BUDGET]
            for _ in range(MAX_VISITS):
                if not ring:
                    break
                queue_key = ring[0]
                queue = tx.get('queues', queue_key)
                job = tx.get('jobs', queue['head']) if queue.get('head') else {}
                if not job:
                    ring.pop(0)  # A completed purge may have removed this queue.
                    continue
                job.setdefault('unit_kind', 'conversation')
                if queue_key not in eligible_queues and queue_key not in blocked:
                    try:
                        tx.check_privacy(
                            job['owner_id'],
                            (job['conversation_id'],) if job.get('conversation_id') else (),
                            job.get('privacy_generation'),
                        )
                    except BatchPrivacyBlocked:
                        blocked.add(queue_key)
                    else:
                        privacy_checked_segment = job['segment_id']
                        policy = stage_in_transaction(
                            tx, job, 'scheduler', observations=observations, candidates=candidates
                        )
                        if policy.head_priority:
                            job = _prefer_merge_head(
                                tx,
                                queue,
                                job,
                                head_budget,
                                observations,
                                now=now,
                                max_seconds=max_seconds,
                                shared_gpu=bool(gpu_key),
                                candidates=candidates,
                            )
                        job.setdefault('unit_kind', 'conversation')
                        try:
                            if job['segment_id'] != privacy_checked_segment:
                                tx.check_privacy(
                                    job['owner_id'],
                                    (job['conversation_id'],) if job.get('conversation_id') else (),
                                    job.get('privacy_generation'),
                                )
                            policy = stage_in_transaction(tx, job, 'scheduler', candidates=candidates)
                            allowed = _pool_allows(job, max_seconds, bool(gpu_key)) and (
                                not gpu_key or policy.shared_live
                            )
                        except BatchPrivacyBlocked:
                            allowed = False
                        if allowed:
                            eligible_queues[queue_key] = job['duration_seconds']
                        else:
                            blocked.add(queue_key)
                if queue_key in blocked:
                    ring.append(ring.pop(0))
                    if len(blocked) == len(ring):
                        break
                    continue
                if not queue['continuing']:
                    queue['deficit'] += QUANTUM_SECONDS
                cost = job['duration_seconds']
                if cost > queue['deficit']:
                    queue['continuing'] = False
                    ring.append(ring.pop(0))
                    tx.put('queues', queue_key, queue)
                    # Skip empty DRR rounds in metadata, not repeated privacy IO.
                    if len(eligible_queues) + len(blocked) == len(ring):
                        rounds = min(
                            max(0, math.ceil((duration - tx.get('queues', key)['deficit']) / QUANTUM_SECONDS))
                            for key, duration in eligible_queues.items()
                        )
                        if rounds > 1:
                            for key in eligible_queues:
                                other = tx.get('queues', key)
                                other['deficit'] += (rounds - 1) * QUANTUM_SECONDS
                                tx.put('queues', key, other)
                    continue
                queue['deficit'] -= cost
                queue['head'] = job['next']
                queue['continuing'] = True
                if not queue['head']:
                    queue.update(tail='', deficit=0.0, continuing=False)
                    ring.pop(0)
                job.update(
                    state='leased',
                    token=token,
                    attempt=job['attempt'] + 1,
                    lease_until=now + LEASE_SECONDS,
                    shared_gpu_key=gpu_key,
                )
                if not job.get('requires_compute_admission') and not cap_dispatch_enabled(job['owner_id'], 'batch'):
                    # The pump dispatches this lease without admission, so it
                    # is a real commitment: a parked hold must not hide it.
                    job.pop('last_policy_hold', None)
                if gpu_key:
                    tx.put(
                        'gpus',
                        gpu_key,
                        {'token': token, 'segment_id': job['segment_id'], 'lease_until': job['lease_until']},
                    )
                tx.put('queues', queue_key, queue)
                tx.put('jobs', job['segment_id'], job)
                control[field(int(priority), 'active')] = bool(ring)
                control[field(int(priority), 'service')] += cost / owner_count
                tx.put('control', shard, control)
                item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
                return (
                    (LeasedWork(item, token, job['attempt'], job['lease_until']), job['enqueued_at']),
                    True,
                    observations,
                )
            control[field(int(priority), 'active')] = bool(ring)
            if not eligible_queues:
                control[field(int(priority), self.pool + '_available_at')] = now + 30
            tx.put('control', shard, control)
            return None, bool(eligible_queues), observations

        receipt, eligible, observations = self.store.run(commit)
        try:
            record_policy_observations(observations)
        except Exception:
            pass  # Telemetry after commit cannot drop the lease it just issued.
        # Only committed attempts emit telemetry; Firestore may retry callbacks.
        if self.metrics:
            for event, age in observations:
                if event in {'policy_fallback', 'policy_stage'}:
                    continue
                try:
                    self.metrics.record_head(event, priority, age=age)
                except Exception:
                    pass  # Metrics cannot turn an issued lease into a failed pull.
        return receipt, eligible

    def heartbeat(self, segment_id: str, token: str, now: float) -> bool:
        def commit(tx):
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return False
            gpu_key = job.get('shared_gpu_key')
            gpu = tx.get('gpus', gpu_key) if gpu_key else {}
            if gpu_key and gpu.get('token') != token:
                return False
            job['lease_until'] = max(job['lease_until'], now + LEASE_SECONDS)
            if gpu_key:
                gpu['lease_until'] = job['lease_until']
                tx.put('gpus', gpu_key, gpu)
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def complete(self, result: WorkResult, token: str, now: float) -> bool:
        def commit(tx):
            job = tx.get('jobs', result.segment_id)
            if job.get('state') in {'result_ready', 'committed'}:
                return job.get('result') == asdict(result) and job.get('token') == token, False
            if not owns_lease(job, token, now):
                return False, False
            if job.get('requires_compute_admission') and job.get('compute_admission_token') != token:
                return False, False
            job.update(state='result_ready', result=asdict(result), ready_at=now)
            job.pop('retry_started_at', None)
            job.pop('admission_refusals', None)
            tx.put('jobs', result.segment_id, job)
            return True, True

        accepted, changed = self.store.run(commit)
        if changed and self.metrics:
            self.metrics.record('completed')
        return accepted

    def fail(
        self,
        segment_id: str,
        token: str,
        now: float,
        *,
        quarantine: bool = False,
        padded_retry_empty: bool = False,
        padded_retry: str | None = None,
        worker_failure: dict | None = None,
        measured_held_vad_speech_seconds: float | None = None,
        worker_vad_receipt: dict | None = None,
    ) -> bool:
        if worker_failure is not None:
            validate_worker_failure(worker_failure)
        if padded_retry is None and padded_retry_empty:
            padded_retry = 'empty'
        elif padded_retry == 'empty' and not padded_retry_empty:
            padded_retry_empty = True
        if padded_retry not in {None, 'empty', 'skipped_oversize', 'skipped_long_speech'} or (
            padded_retry_empty and padded_retry != 'empty'
        ):
            raise ValueError('invalid padded retry evidence')

        candidates = {}
        observations = []

        def commit(tx):
            observations.clear()
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return None
            policy = stage_in_transaction(tx, job, 'scheduler', candidates=candidates, observations=observations)
            attach_held_vad(job, measured_held_vad_speech_seconds, worker_vad_receipt)
            if quarantine or worker_failure is not None or job['attempt'] >= policy.max_attempts:
                quarantine_job(tx, job, now, 'worker_failed')
                if quarantine and padded_retry in {'empty', 'skipped_oversize', 'skipped_long_speech'}:
                    job['worker_empty_evidence'] = {'padded_retry': padded_retry, 'version': 1}
                if worker_failure is not None:
                    job['worker_failure'] = dict(worker_failure)
            else:
                _defer(job, now, 'worker_failed')
            tx.put('jobs', segment_id, job)
            return job['state'], job['attempt'], job['duration_seconds']

        outcome = self.store.run(commit)
        record_policy_observations(observations)
        if outcome:
            state, attempt, seconds = outcome
            if state == 'quarantined':
                record_correctness('failed', seconds=seconds)
            # Best effort AFTER the transaction/exception scope: telemetry may
            # neither fail a sibling nor reveal a worker exception via handleError.
            if self.metrics:
                try:
                    self.metrics.record('quarantined' if state == 'quarantined' else 'retry')
                    if state == 'quarantined':
                        self.metrics.record('recovery_held')
                except Exception:
                    pass
            if state == 'quarantined':
                try:
                    logger.error(
                        'event=batch_quarantined reason=worker_failed attempt=%d recovery=held stage=%s worker_reason=%s',
                        attempt,
                        worker_failure['stage'] if worker_failure else 'unknown',
                        worker_failure['reason'] if worker_failure else 'unclassified',
                    )
                    logger.warning('event=batch_recovery outcome=held reason=awaiting_fenced_recovery')
                except Exception:
                    pass
        return bool(outcome)

    def defer(
        self,
        segment_id: str,
        token: str,
        now: float,
        retry_after: float = 30,
        *,
        held_reason: str | None = None,
        admission_refused: bool = False,
    ) -> bool:
        """Policy/capacity refusal is waiting, not a provider failure attempt.

        ``held_reason`` carries the bounded machine reason from the admission
        decision that caused the defer; it records the latest decision in the
        same transaction, so an outside reader can classify the wait without
        a second round-trip. Refund defers (shutdown, GPU abort) pass none and
        preserve the previously recorded decision. ``last_policy_hold`` keeps
        the latest hold across an unevaluated re-evaluation (which clears the
        decision to BLIND) until an allow is sealed or another hold replaces
        it, so the uncommitted-age proxy does not flap on a parked job.
        """

        def commit(tx):
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return False
            delay = retry_after
            if admission_refused:
                previous = job.get('admission_refusals', 0)
                previous = previous if type(previous) is int and 0 <= previous <= 5 else 0
                streak = min(previous + 1, 5)
                job['admission_refusals'] = streak
                # Bad/missing authority stays deferred; it never grants compute.
                delay = _admission_retry_delay(delay, streak)
                if not held_reason:
                    # A prior allow is not the latest decision when this RPC
                    # was unevaluated. Preserve BLIND instead of a false hold.
                    job.pop('compute_decision', None)
            job.update(
                state='retry',
                available_at=now + max(1, min(86400, delay)),
                attempt=max(0, job['attempt'] - 1),
                token='',
                lease_until=0.0,
            )
            if held_reason:
                job['compute_decision'] = {'reason': held_reason, 'outcome': 'held', 'at': now}
                job['last_policy_hold'] = {'reason': held_reason, 'at': now}
            tx.put('jobs', segment_id, job)
            return True

        deferred = self.store.run(commit)
        if deferred and admission_refused and self.metrics:
            try:
                self.metrics.record('admission_policy_deferred' if held_reason else 'admission_unevaluated_deferred')
            except Exception:
                pass  # Metrics cannot turn a committed defer into a retry.
        return deferred

    def release(self, segment_id: str, token: str, now: float) -> bool:
        """Expire a held lease now: the lease-expiry transition without the wait.

        For a holder that can no longer publish. The attempt stays charged and
        the retry backoff applies, exactly as ``recover`` would after expiry;
        a stale token is fenced like every other transition.
        """

        def commit(tx):
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return False
            _defer(job, now, 'lease_released')
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def recover(self, now: float, limit: int = 100) -> int:
        self.store.run(lambda tx: migrate_legacy(tx, now))
        recovered = 0
        candidates, observations = {}, []
        for state in ('leased', 'retry'):
            for segment_id in self.store.due(state, now, limit):

                def commit(tx: Transaction):
                    observations.clear()
                    job = tx.get('jobs', segment_id)
                    if job.get('state') == 'leased' and job['lease_until'] <= now:
                        outcome = expire_lease(
                            tx,
                            job,
                            now,
                            stage_policy=stage_in_transaction,
                            candidates=candidates,
                            observations=observations,
                            defer=_defer,
                        )
                    elif job.get('state') == 'retry' and job['available_at'] <= now:
                        control = read_control(tx, scheduler_control_key(job['owner_key']))
                        job['state'] = 'ready'
                        _append(tx, control, job)
                        outcome = ('retry', 0, None)
                    else:
                        return None
                    tx.put('jobs', segment_id, job)
                    return outcome

                try:
                    outcome = self.store.run(commit)
                    record_policy_observations(observations)
                except BatchPrivacyBlocked:
                    self.store.quarantine_fenced(segment_id, now)
                    continue
                if outcome:
                    recovered += 1
                    observe_recovery(outcome, self.metrics)
        return recovered

    @staticmethod
    def redrive_in_transaction(tx: Transaction, job: dict, now: float) -> bool:
        if job.get('state') != 'dead' or not job.get('merge_pending'):
            return False
        control = read_control(tx, scheduler_control_key(job['owner_key']))
        job.update(
            state='ready',
            available_at=now,
            failure='',
            token='',
            lease_until=0.0,
            retry_started_at=job.get('retry_started_at', now),
        )
        _append(tx, control, job)
        tx.put('jobs', job['segment_id'], job)
        return True

    def redrive_dead(self, segment_id: str, now: float) -> bool:
        """Authenticated recovery of historical dead records; never skips a gap."""
        return self.store.run(lambda tx: self.redrive_in_transaction(tx, tx.get('jobs', segment_id), now))

    def acknowledge_gpu_idle(self, gpu_id: str, token: str) -> bool:
        """Only the hardware admission owner may call this after GPU quiescence.

        Complete/fail/lease expiry never proves non-preemptible inference stopped.
        An orphaned shared reservation stays closed until that owner verifies idle.
        """
        if not gpu_id or len(gpu_id) > 128 or not token:
            raise ValueError('bounded GPU identity and current reservation token required')

        def commit(tx):
            key = owner_key(gpu_id)
            gpu = tx.get('gpus', key)
            if not gpu.get('token'):
                return gpu.get('released_token') == token
            if gpu['token'] != token:
                return False
            gpu.update(token='', lease_until=0.0, released_token=token)
            tx.put('gpus', key, gpu)
            return True

        return self.store.run(commit)

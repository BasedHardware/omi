"""Fenced, duration-fair pull scheduling over durable transactional documents."""

from dataclasses import asdict
import hashlib
import math
import logging
import uuid

from database.batch_pipeline_store import Store, Transaction
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from config.batch_pipeline import shared_live_enabled, scheduler_control_key, max_worker_attempts, head_priority_enabled
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import LeasedWork, Priority, WorkItem, WorkResult, PoolCapacity
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.control import read_control, activate, field, migrate_legacy

QUANTUM_SECONDS = 30.0
LEASE_SECONDS = 120.0
RETRY_BACKOFF_CAP_SECONDS = 600
MAX_ACTIVE_OWNERS = 1024
MAX_VISITS = 128
HEAD_LOOKAHEAD = 64
logger = logging.getLogger(__name__)


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
    tx: Transaction, queue: dict, job: dict, budget: list[int], *, max_seconds: float, shared_gpu: bool
) -> dict:
    """Splice the ready ordered head, sharing a 64-read budget across this shard.

    No new queue class, tombstones or lease takeover: rollback reads an ordinary
    FIFO. Priorities, DRR charges and pool/privacy checks still apply to the
    selected job. Quarantine is not merge_pending and is never selected here.
    """
    if budget[0] <= 0:
        return job
    budget[0] -= 1
    head = tx.first_pending(job['owner_key'])
    if (
        not head
        or head['segment_id'] == job['segment_id']
        or head['state'] != 'ready'
        or head['priority'] != job['priority']
        or not _pool_allows(head, max_seconds, shared_gpu)
    ):
        return job
    previous = job
    while budget[0] > 0:
        sid = previous.get('next')
        if not sid:
            break
        budget[0] -= 1
        candidate = tx.get('jobs', sid)
        if not candidate:
            break
        if sid == head['segment_id']:
            # Both link writes pass the same privacy boundary as leasing.
            # A fenced predecessor must not poison an otherwise unrelated
            # owner's pull transaction when buffered writes flush later.
            try:
                for linked in (previous, candidate):
                    tx.check_privacy(
                        linked['owner_id'],
                        (linked['conversation_id'],) if linked.get('conversation_id') else (),
                        linked.get('privacy_generation'),
                    )
            except BatchPrivacyBlocked:
                return job
            previous['next'] = candidate['next']
            tx.put('jobs', previous['segment_id'], previous)
            if queue['tail'] == sid:
                queue['tail'] = previous['segment_id']
            candidate['next'] = queue['head']
            queue['head'] = sid
            tx.put('jobs', sid, candidate)
            return candidate
        previous = candidate
    return job


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
        self.max_attempts = max_worker_attempts()

    def enqueue(self, item: WorkItem, now: float) -> bool:
        return self.store.run(lambda tx: self.enqueue_in_transaction(tx, item, now))

    @staticmethod
    def enqueue_in_transaction(tx: Transaction, item: WorkItem, now: float) -> bool:
        previous = tx.get('jobs', item.segment_id)
        immutable = {**asdict(item), 'priority': int(item.priority)}
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
        key = owner_key(item.owner_id)
        owner = tx.get('owners', key)
        watermark = owner.get('watermark')
        control = read_control(tx, scheduler_control_key(key))
        job = {
            **immutable,
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
            slots, allow_backfill, max_seconds = capacity.limits(now, shared_live_enabled=shared_live_enabled())
            limit = min(limit, slots)
            backfill_budget = max(0, slots - capacity.reserved_fresh_slots)
        result = []
        for _ in range(limit):
            lease = self._pull_one(
                now,
                allow_backfill=allow_backfill and backfill_budget > 0,
                max_seconds=max_seconds,
                shared_gpu_id=capacity.gpu_id if capacity is not None and capacity.shared_with_live else None,
            )
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
                        self.metrics.record('leased', wait_seconds=now - enqueued_at)
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

        def commit(tx):
            gpu_key = owner_key(shared_gpu_id) if shared_gpu_id is not None else ''
            gpu = tx.get('gpus', gpu_key) if gpu_key else {}
            if gpu.get('token'):
                return None, 'reserved'
            control = read_control(tx, shard)
            ring = control['rings'][str(int(priority))]
            eligible_queues, blocked = {}, set()
            owner_count = max(1, len(ring))
            head_budget = [HEAD_LOOKAHEAD]
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
                    if head_priority_enabled():
                        job = _prefer_merge_head(
                            tx, queue, job, head_budget, max_seconds=max_seconds, shared_gpu=bool(gpu_key)
                        )
                    job.setdefault('unit_kind', 'conversation')
                    try:
                        tx.check_privacy(
                            job['owner_id'],
                            (job['conversation_id'],) if job.get('conversation_id') else (),
                            job.get('privacy_generation'),
                        )
                        allowed = _pool_allows(job, max_seconds, bool(gpu_key))
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
                return (LeasedWork(item, token, job['attempt'], job['lease_until']), job['enqueued_at']), True
            control[field(int(priority), 'active')] = bool(ring)
            if not eligible_queues:
                control[field(int(priority), self.pool + '_available_at')] = now + 30
            tx.put('control', shard, control)
            return None, bool(eligible_queues)

        return self.store.run(commit)

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
            job.update(state='result_ready', result=asdict(result))
            job.pop('retry_started_at', None)
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
    ) -> bool:
        if padded_retry is None and padded_retry_empty:
            padded_retry = 'empty'
        elif padded_retry == 'empty' and not padded_retry_empty:
            padded_retry_empty = True
        if padded_retry not in {None, 'empty', 'skipped_oversize'} or (padded_retry_empty and padded_retry != 'empty'):
            raise ValueError('invalid padded retry evidence')

        def commit(tx):
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return None
            if quarantine or job['attempt'] >= self.max_attempts:
                # Serialize removal from the ordered pending set against merge
                # and admission. No success/silence result or cursor is invented.
                owner = tx.get('owners', job['owner_key'])
                owner['revision'] = owner.get('revision', 0) + 1
                job.update(
                    state='quarantined',
                    merge_pending=False,
                    token='',
                    lease_until=0.0,
                    failure='worker_failed',
                    quarantine_reason='worker_failed',
                    quarantined_at=now,
                    recovery_state='held',
                )
                if quarantine and padded_retry in {'empty', 'skipped_oversize'}:
                    job['worker_empty_evidence'] = {'padded_retry': padded_retry, 'version': 1}
                job.pop('retry_started_at', None)
                tx.put('owners', job['owner_key'], owner)
            else:
                _defer(job, now, 'worker_failed')
            tx.put('jobs', segment_id, job)
            return job['state'], job['attempt'], job['duration_seconds']

        outcome = self.store.run(commit)
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
                    logger.error('event=batch_quarantined reason=worker_failed attempt=%d recovery=held', attempt)
                    logger.warning('event=batch_recovery outcome=held reason=awaiting_fenced_recovery')
                except Exception:
                    pass
        return bool(outcome)

    def defer(self, segment_id: str, token: str, now: float, retry_after: float = 30) -> bool:
        """Policy/capacity refusal is waiting, not a provider failure attempt."""

        def commit(tx):
            job = tx.get('jobs', segment_id)
            if not owns_lease(job, token, now):
                return False
            job.update(
                state='retry',
                available_at=now + max(1, min(86400, retry_after)),
                attempt=max(0, job['attempt'] - 1),
                token='',
                lease_until=0.0,
            )
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def recover(self, now: float, limit: int = 100) -> int:
        self.store.run(lambda tx: migrate_legacy(tx, now))
        recovered = 0
        for state in ('leased', 'retry'):
            for segment_id in self.store.due(state, now, limit):

                def commit(tx: Transaction) -> str | None:
                    job = tx.get('jobs', segment_id)
                    if job.get('state') == 'leased' and job['lease_until'] <= now:
                        _defer(job, now, 'lease_expired')
                        event = 'lease_expired'
                    elif job.get('state') == 'retry' and job['available_at'] <= now:
                        control = read_control(tx, scheduler_control_key(job['owner_key']))
                        job['state'] = 'ready'
                        _append(tx, control, job)
                        event = 'retry'
                    else:
                        return None
                    tx.put('jobs', segment_id, job)
                    return event

                try:
                    event = self.store.run(commit)
                except BatchPrivacyBlocked:
                    self.store.quarantine_fenced(segment_id, now)
                    continue
                if event:
                    recovered += 1
                    if self.metrics:
                        self.metrics.record(event)
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

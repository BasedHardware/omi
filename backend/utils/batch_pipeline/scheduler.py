"""Fenced, duration-fair pull scheduling over durable transactional documents."""

from dataclasses import asdict
import hashlib
import uuid

from database.batch_pipeline_store import Store, Transaction
from utils.batch_pipeline.contracts import LeasedWork, Priority, WorkItem, WorkResult
from utils.batch_pipeline.metrics import QueueMetrics

QUANTUM_SECONDS = 30.0
LEASE_SECONDS = 120.0
MAX_ATTEMPTS = 5
MAX_ACTIVE_OWNERS = 1024
MAX_VISITS = 128


def owner_key(owner_id: str) -> str:
    return hashlib.sha256(owner_id.encode()).hexdigest()


def _control(tx: Transaction) -> dict:
    return tx.get('control', 'scheduler') or {'rings': {str(int(p)): [] for p in Priority}}


def _append(tx: Transaction, control: dict, job: dict) -> None:
    queue_key = f"{job['priority']}_{job['owner_key']}"
    queue = tx.get('queues', queue_key) or {'head': '', 'tail': '', 'deficit': 0.0, 'continuing': False}
    ring = control['rings'][str(job['priority'])]
    if not queue['head']:
        if len(ring) >= MAX_ACTIVE_OWNERS:
            raise RuntimeError('active owner capacity exceeded; admission must retry')
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
    tx.put('control', 'scheduler', control)


def _owns(job: dict, token: str, now: float) -> bool:
    return job.get('state') == 'leased' and job.get('token') == token and job['lease_until'] > now


def _defer(job: dict, now: float, reason: str) -> None:
    job.update(
        state='dead' if job['attempt'] >= MAX_ATTEMPTS else 'retry',
        available_at=now + min(3600, 5 * 2 ** (job['attempt'] - 1)),
        token='',
        lease_until=0.0,
        # Only bounded machine reason codes belong here, never provider errors/text.
        failure=reason,
    )


class Scheduler:
    def __init__(self, store: Store, *, metrics: QueueMetrics | None = None):
        self.store = store
        self.metrics = metrics

    def enqueue(self, item: WorkItem, now: float) -> bool:
        def commit(tx):
            previous = tx.get('jobs', item.segment_id)
            immutable = {**asdict(item), 'priority': int(item.priority)}
            if previous:
                if any(previous.get(key) != value for key, value in immutable.items()):
                    raise ValueError('segment ID reused with different immutable work')
                return False
            key = owner_key(item.owner_id)
            owner = tx.get('owners', key)
            watermark = owner.get('watermark')
            if watermark and (item.capture_at, item.segment_id) <= (watermark['capture_at'], watermark['segment_id']):
                raise ValueError('capture precedes committed watermark; explicit late-capture handling required')
            control = _control(tx)
            job = {
                **immutable,
                'owner_key': key,
                'enqueued_at': now,
                'state': 'ready',
                'attempt': 0,
                'token': '',
                'lease_until': 0.0,
                'available_at': now,
                'merge_pending': True,
            }
            _append(tx, control, job)
            tx.put('jobs', item.segment_id, job)
            # Admission and merge serialize through this fence even for different classes.
            owner['revision'] = owner.get('revision', 0) + 1
            tx.put('owners', key, owner)
            return True

        return self.store.run(commit)

    def pull(self, now: float, limit: int = 1) -> list[LeasedWork]:
        if not 1 <= limit <= 32:
            raise ValueError('pull limit must be in [1, 32]')
        result = []
        for _ in range(limit):
            lease = self._pull_one(now)
            if lease is None:
                break
            result.append(lease)
        return result

    def _pull_one(self, now: float) -> LeasedWork | None:
        token = uuid.uuid4().hex  # Stable across this transaction's retries.

        def commit(tx):
            control = _control(tx)
            ring = next((control['rings'][str(int(p))] for p in Priority if control['rings'][str(int(p))]), None)
            if not ring:
                return None
            # Budget bounded transactions; fresh deficits must accrue before backfill.
            for _ in range(MAX_VISITS):
                queue_key = ring[0]
                queue = tx.get('queues', queue_key)
                job = tx.get('jobs', queue['head'])
                if not queue['continuing']:
                    queue['deficit'] += QUANTUM_SECONDS
                cost = job['duration_seconds']
                if cost > queue['deficit']:
                    queue['continuing'] = False
                    ring.append(ring.pop(0))
                    tx.put('queues', queue_key, queue)
                    continue
                queue['deficit'] -= cost
                queue['head'] = job['next']
                queue['continuing'] = True
                if not queue['head']:
                    queue.update(tail='', deficit=0.0, continuing=False)
                    ring.pop(0)
                job.update(state='leased', token=token, attempt=job['attempt'] + 1, lease_until=now + LEASE_SECONDS)
                tx.put('queues', queue_key, queue)
                tx.put('jobs', job['segment_id'], job)
                tx.put('control', 'scheduler', control)
                item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__})
                return LeasedWork(item, token, job['attempt'], job['lease_until']), job['enqueued_at']
            tx.put('control', 'scheduler', control)
            return None

        receipt = self.store.run(commit)
        if receipt is None:
            return None
        lease, enqueued_at = receipt
        if self.metrics:
            self.metrics.record('leased', wait_seconds=now - enqueued_at)
        return lease

    def heartbeat(self, segment_id: str, token: str, now: float) -> bool:
        def commit(tx):
            job = tx.get('jobs', segment_id)
            if not _owns(job, token, now):
                return False
            job['lease_until'] = max(job['lease_until'], now + LEASE_SECONDS)
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def complete(self, result: WorkResult, token: str, now: float) -> bool:
        def commit(tx):
            job = tx.get('jobs', result.segment_id)
            if job.get('state') in {'result_ready', 'committed'}:
                return job.get('result') == asdict(result) and job.get('token') == token, False
            if not _owns(job, token, now):
                return False, False
            job.update(state='result_ready', result=asdict(result))
            tx.put('jobs', result.segment_id, job)
            return True, True

        accepted, changed = self.store.run(commit)
        if changed and self.metrics:
            self.metrics.record('completed')
        return accepted

    def fail(self, segment_id: str, token: str, now: float) -> bool:
        def commit(tx):
            job = tx.get('jobs', segment_id)
            if not _owns(job, token, now):
                return False
            _defer(job, now, 'worker_failed')
            tx.put('jobs', segment_id, job)
            return job['state']

        outcome = self.store.run(commit)
        if outcome and self.metrics:
            self.metrics.record('dead' if outcome == 'dead' else 'retry')
        return bool(outcome)

    def recover(self, now: float, limit: int = 100) -> int:
        recovered = 0
        for state in ('leased', 'retry'):
            for segment_id in self.store.due(state, now, limit):

                def commit(tx):
                    job = tx.get('jobs', segment_id)
                    if job.get('state') == 'leased' and job['lease_until'] <= now:
                        _defer(job, now, 'lease_expired')
                        event = 'dead' if job['state'] == 'dead' else 'lease_expired'
                    elif job.get('state') == 'retry' and job['available_at'] <= now:
                        control = _control(tx)
                        job['state'] = 'ready'
                        _append(tx, control, job)
                        event = 'retry'
                    else:
                        return False
                    tx.put('jobs', segment_id, job)
                    return event

                event = self.store.run(commit)
                if event:
                    recovered += 1
                    if self.metrics:
                        self.metrics.record(event)
        return recovered

    def redrive_dead(self, segment_id: str, now: float) -> bool:
        """Explicit operator action only; preserve capture position and immutable ID."""

        def commit(tx):
            job = tx.get('jobs', segment_id)
            if job.get('state') != 'dead':
                return False
            control = _control(tx)
            job.update(state='ready', attempt=0, available_at=now, failure='')
            _append(tx, control, job)
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

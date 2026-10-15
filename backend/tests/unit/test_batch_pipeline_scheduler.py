"""State-machine tests over an atomic snapshot store, not a Firestore emulator."""

from copy import deepcopy
from threading import RLock

import pytest

from config.batch_pipeline import admit_or_legacy, enabled_for, priority_for
from utils.batch_pipeline.contracts import Priority, WorkItem, WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler, LEASE_SECONDS


class MemoryTransaction:
    def __init__(self, rows):
        self.rows = rows

    def get(self, table, key):
        return deepcopy(self.rows.get((table, key), {}))

    def put(self, table, key, value):
        self.rows[(table, key)] = deepcopy(value)

    def first_pending(self, owner_key):
        jobs = [
            v
            for (table, _), v in self.rows.items()
            if table == 'jobs' and v['owner_key'] == owner_key and v['merge_pending']
        ]
        return min(jobs, key=lambda v: (v['capture_at'], v['segment_id'])) if jobs else None


class MemoryStore:
    def __init__(self):
        self.rows = {}
        self.lock = RLock()

    def run(self, body):
        with self.lock:
            snapshot = deepcopy(self.rows)
            result = body(MemoryTransaction(snapshot))
            self.rows = snapshot
            return result

    def due(self, state, now, limit):
        field = 'lease_until' if state == 'leased' else 'available_at'
        return [
            key for (table, key), v in self.rows.items() if table == 'jobs' and v['state'] == state and v[field] <= now
        ][:limit]

    def oldest(self, priority, *, ready_only):
        jobs = [
            v['enqueued_at']
            for (table, _), v in self.rows.items()
            if table == 'jobs'
            and v['priority'] == priority
            and (v['state'] == 'ready' if ready_only else v['merge_pending'])
        ]
        return min(jobs) if jobs else None


def item(segment, owner='heavy', capture=1, duration=30, priority=Priority.DEEP):
    return WorkItem(segment, owner, capture, f'gs://synthetic/{segment}', duration, priority)


def test_heavy_owner_does_not_starve_light_owner():
    queue = Scheduler(MemoryStore())
    for n in range(30):
        queue.enqueue(item(f'h{n}'), 0)
    queue.enqueue(item('light', owner='light'), 0)
    pulled = queue.pull(1, 3)
    assert [v.item.owner_id for v in pulled] == ['heavy', 'light', 'heavy']


def test_duration_deficit_round_robin():
    queue = Scheduler(MemoryStore())
    for n in range(9):
        queue.enqueue(item(f's{n}', owner='short', duration=10), 0)
    queue.enqueue(item('long', owner='long', duration=60), 0)
    pulled = queue.pull(1, 8)
    # Two 30s rounds give the long owner 60s and short owner six 10s items.
    assert sum(v.item.duration_seconds for v in pulled[:6]) == 60
    assert pulled[6].item.segment_id == 'long'


def test_strict_priority_and_parallel_owner_compute():
    queue = Scheduler(MemoryStore())
    queue.enqueue(item('deep'), 0)
    queue.enqueue(item('recent', priority=Priority.RECENT), 0)
    queue.enqueue(item('fresh', priority=Priority.FRESH), 0)
    assert [v.item.segment_id for v in queue.pull(1, 3)] == ['fresh', 'recent', 'deep']
    queue.enqueue(item('f2', priority=Priority.FRESH), 2)
    assert queue.pull(2)[0].item.segment_id == 'f2'


def test_maximum_duration_progress_without_backfill_bypass():
    queue = Scheduler(MemoryStore())
    queue.enqueue(item('long', duration=7200, priority=Priority.FRESH), 0)
    queue.enqueue(item('deep'), 0)
    assert queue.pull(1) == []  # Bounded first deficit-accumulation transaction.
    assert queue.pull(1)[0].item.segment_id == 'long'
    assert queue.pull(1)[0].item.segment_id == 'deep'


def test_lease_expiry_backoff_and_stale_result_fencing():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    first = queue.pull(0)[0]
    assert queue.heartbeat('a', first.token, 60)
    assert queue.recover(121) == 0
    assert not queue.complete(WorkResult('a', 'gs://results/a'), first.token, 181)
    assert not queue.heartbeat('a', first.token, 181)
    assert queue.recover(181) == 1
    assert queue.pull(185) == []
    assert queue.recover(186) == 1
    second = queue.pull(186)[0]
    assert second.attempt == 2 and second.token != first.token
    assert not queue.complete(WorkResult('a', 'gs://results/stale'), first.token, 187)
    assert queue.complete(WorkResult('a', 'gs://results/a'), second.token, 187)
    assert queue.complete(WorkResult('a', 'gs://results/a'), second.token, 999)
    assert not queue.complete(WorkResult('a', 'gs://results/changed'), second.token, 999)


def test_retries_end_in_dead_letter_and_block_merge():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    for attempt in range(1, 6):
        now = attempt * 1000
        queue.recover(now)
        lease = queue.pull(now)[0]
        assert lease.attempt == attempt
        assert queue.fail('a', lease.token, now + 1)
        assert not queue.fail('a', lease.token, now + 1)
    assert store.rows['jobs', 'a']['state'] == 'dead'
    assert queue.recover(99999) == 0
    assert OrderedMerge(store).commit_next('heavy', 99999) is None


def test_out_of_order_completion_and_idempotent_ordered_commit():
    store = MemoryStore()
    queue = Scheduler(store)
    merge = OrderedMerge(store)
    # Admission order differs from capture order; same owner computes in parallel.
    for key, capture in [('b', 2), ('a', 1), ('c', 2)]:
        queue.enqueue(item(key, capture=capture), 0)
    leases = {v.item.segment_id: v for v in queue.pull(0, 3)}
    for key in ('b', 'c'):
        assert queue.complete(WorkResult(key, f'gs://results/{key}'), leases[key].token, 1)
    assert merge.commit_next('heavy', 2) is None
    assert queue.complete(WorkResult('a', 'gs://results/a'), leases['a'].token, 2)
    assert [merge.commit_next('heavy', 3)['segment_id'] for _ in range(3)] == ['a', 'b', 'c']
    assert merge.commit_next('heavy', 3) is None
    assert merge.committed_result('a')['result']['result_uri'] == 'gs://results/a'
    assert not queue.enqueue(item('a', capture=1), 4)
    with pytest.raises(ValueError, match='different immutable'):
        queue.enqueue(item('a', capture=99), 4)
    with pytest.raises(ValueError, match='watermark'):
        queue.enqueue(item('late', capture=1), 4)


def test_flags_off_identity_and_cohort_validation(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_ENABLED', raising=False)
    sentinel = object()
    calls = []

    def legacy(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    def forbidden(*args, **kwargs):
        raise AssertionError('admission evaluated while disabled')

    assert admit_or_legacy('u', forbidden, legacy, sentinel, x=sentinel) is sentinel
    assert calls == [((sentinel,), {'x': sentinel})]
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')
    assert enabled_for('u') and not enabled_for('other')
    for invalid in ('nan', 'inf', 'bad', '101', '-1'):
        monkeypatch.setenv('BATCH_PIPELINE_PERCENT', invalid)
        assert not enabled_for('u')


def test_priority_respects_existing_lane():
    assert priority_for('fresh', None) == Priority.FRESH
    assert priority_for('backfill', 47 * 3600) == Priority.RECENT
    assert priority_for('backfill', None) == Priority.DEEP
    assert priority_for('backfill', 9 * 86400) == Priority.DEEP
    with pytest.raises(ValueError):
        priority_for('unknown', 1)


def test_expired_fifth_attempt_dead_letters_without_retry():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    for attempt in range(1, 6):
        now = attempt * 1000
        queue.recover(now)
        lease = queue.pull(now)[0]
        assert queue.recover(now + LEASE_SECONDS) == 1
        assert not queue.heartbeat('a', lease.token, now + LEASE_SECONDS)
    assert store.rows['jobs', 'a']['state'] == 'dead'


def test_dead_letter_redrive_preserves_order_and_identity():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    queue.enqueue(item('b', capture=2), 0)
    leases = queue.pull(0, 2)
    for lease in leases:
        if lease.item.segment_id == 'b':
            queue.complete(WorkResult('b', 'gs://results/b'), lease.token, 1)
        else:
            queue.fail('a', lease.token, 1)
    for attempt in range(2, 6):
        now = attempt * 1000
        queue.recover(now)
        lease = queue.pull(now)[0]
        queue.fail('a', lease.token, now + 1)
    merge = OrderedMerge(store)
    assert merge.commit_next('heavy', 9999) is None
    assert queue.redrive_dead('a', 9999)
    assert not queue.redrive_dead('a', 9999)
    lease = queue.pull(9999)[0]
    assert lease.attempt == 1
    queue.complete(WorkResult('a', 'gs://results/a'), lease.token, 10000)
    assert merge.commit_next('heavy', 10001)['segment_id'] == 'a'
    assert merge.commit_next('heavy', 10001)['segment_id'] == 'b'


def test_owner_capacity_fails_atomically_without_dropping_work(monkeypatch):
    from utils.batch_pipeline import scheduler

    monkeypatch.setattr(scheduler, 'MAX_ACTIVE_OWNERS', 1)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', owner='a'), 0)
    with pytest.raises(RuntimeError, match='capacity'):
        queue.enqueue(item('b', owner='b'), 0)
    assert ('jobs', 'b') not in store.rows
    assert queue.pull(1)[0].item.segment_id == 'a'


def test_store_stage_boundary_refuses_implicit_or_cross_stage_access(monkeypatch):
    from database.batch_pipeline_store import FirestoreStore

    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    with pytest.raises(RuntimeError, match='stage'):
        FirestoreStore('batch_pipeline_prod')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    with pytest.raises(RuntimeError, match='stage'):
        FirestoreStore('batch_pipeline_prod')
    assert FirestoreStore('batch_pipeline_dev').namespace == 'batch_pipeline_dev'
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    with pytest.raises(RuntimeError, match='loopback'):
        FirestoreStore('batch_pipeline_test_boundary')
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:18974')
    with pytest.raises(RuntimeError, match='injected'):
        FirestoreStore('batch_pipeline_test_boundary', firestore_client=object())


def test_capacity_reserves_fresh_slots_and_rejects_stale_slack():
    from utils.batch_pipeline.capacity import PoolCapacity

    queue = Scheduler(MemoryStore())
    queue.enqueue(item('deep'), 0)
    assert queue.pull(10, capacity=PoolCapacity(10, 1, reserved_fresh_slots=1)) == []
    queue.enqueue(item('fresh', priority=Priority.FRESH), 0)
    assert queue.pull(10, capacity=PoolCapacity(10, 1, reserved_fresh_slots=1))[0].item.segment_id == 'fresh'
    assert queue.pull(30, capacity=PoolCapacity(0, 1)) == []
    assert queue.pull(31, capacity=PoolCapacity(31, 1))[0].item.segment_id == 'deep'


def test_shared_live_requires_short_exclusive_slack_and_default_off_gate(monkeypatch):
    from utils.batch_pipeline.capacity import PoolCapacity

    queue = Scheduler(MemoryStore())
    queue.enqueue(item('long', duration=3600), 0)
    queue.enqueue(item('short', owner='short', duration=120), 0)
    capacity = PoolCapacity(10, 1, shared_with_live=True, memory_headroom_bytes=8 * 1024**3)
    monkeypatch.delenv('BATCH_PIPELINE_SHARED_LIVE_ENABLED', raising=False)
    assert queue.pull(10, capacity=capacity) == []
    monkeypatch.setenv('BATCH_PIPELINE_SHARED_LIVE_ENABLED', 'true')
    assert [v.item.segment_id for v in queue.pull(10, 32, capacity=capacity)] == ['short']
    assert queue.pull(10, capacity=capacity) == []
    from dataclasses import replace

    for unsafe in (
        replace(capacity, live_queue_age_seconds=1),
        replace(capacity, gpu_utilization=0.5),
        replace(capacity, memory_headroom_bytes=0),
        replace(capacity, available_slots=2),
    ):
        assert queue.pull(10, capacity=unsafe) == []


def test_capacity_never_spends_reserved_fresh_slots_on_multiple_backfill_items():
    from utils.batch_pipeline.contracts import PoolCapacity

    queue = Scheduler(MemoryStore())
    for n in range(3):
        queue.enqueue(item(f'backfill{n}'), 0)
    assert len(queue.pull(10, 3, capacity=PoolCapacity(10, 3, reserved_fresh_slots=2))) == 1

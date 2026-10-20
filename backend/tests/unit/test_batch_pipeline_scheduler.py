"""State-machine tests over an atomic snapshot store, not a Firestore emulator."""

from copy import deepcopy
from threading import RLock

import pytest

from config.batch_pipeline import admit_or_legacy, enabled_for, priority_for, scheduler_control_key
from utils.batch_pipeline.scheduler import owner_key
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

    def patch(self, table, key, fields):
        self.rows[(table, key)].update(deepcopy(fields))

    def service_frontier(self, priority):
        return max(
            (v.get(f'p{priority}_service', 0) for (table, _), v in self.rows.items() if table == 'control'), default=0.0
        )

    def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
        # This hermetic state-machine store models authorized synthetic accounts.
        return expected_generation or 0

    def first_pending(self, owner_key):
        jobs = [
            v
            for (table, _), v in self.rows.items()
            if table == 'jobs' and v['owner_key'] == owner_key and v['merge_pending']
        ]
        return min(jobs, key=lambda v: (v['capture_at'], v['segment_id'])) if jobs else None

    def first_ready_pending(self, owner_key):
        jobs = [
            v
            for (table, _), v in self.rows.items()
            if table == 'jobs' and v['owner_key'] == owner_key and v['merge_pending'] and v['state'] == 'result_ready'
        ]
        return min(jobs, key=lambda v: (v['capture_at'], v['segment_id'])) if jobs else None

    def ready_predecessor(self, owner_key, priority, segment_id):
        jobs = [
            v
            for (table, _), v in self.rows.items()
            if table == 'jobs'
            and v['owner_key'] == owner_key
            and v['priority'] == priority
            and v['state'] == 'ready'
            and v.get('next') == segment_id
        ]
        return deepcopy(jobs[0]) if len(jobs) == 1 else None


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

    def control_candidate(self, priority, pool, now):
        from utils.batch_pipeline.control import field

        candidates = [
            (v[field(priority, 'service')], v[field(priority, pool + '_available_at')], key)
            for (table, key), v in self.rows.items()
            if table == 'control'
            and v.get(field(priority, 'active'))
            and v[field(priority, pool + '_available_at')] <= now
        ]
        return min(candidates)[2] if candidates else None

    def oldest_retry(self, priority):
        values = [
            v['retry_started_at']
            for (table, _), v in self.rows.items()
            if table == 'jobs' and v.get('priority') == priority and 'retry_started_at' in v
        ]
        return min(values) if values else None

    def quarantine_fenced(self, segment_id, now):
        raise AssertionError('privacy isolation must use real emulator transactions')

    def longest_ready_pending(self, owner_key):
        jobs = [
            v
            for (table, _), v in self.rows.items()
            if table == 'jobs'
            and v['owner_key'] == owner_key
            and v['merge_pending']
            and v['state'] == 'result_ready'
            and 'ready_at' in v
        ]
        return deepcopy(min(jobs, key=lambda v: (v['ready_at'], v['segment_id']))) if jobs else None

    def fresh_pending(self, owner_key, limit):
        jobs = [
            v
            for (table, _), v in self.rows.items()
            if table == 'jobs' and v['owner_key'] == owner_key and v['merge_pending'] and v.get('fresh_capture') is True
        ]
        return deepcopy(sorted(jobs, key=lambda v: (v['capture_at'], v['segment_id']))[:limit])

    def held_merge_owners(self, limit, *, after=None):
        owners = []
        for (table, key), row in sorted(self.rows.items()):
            if table == 'merge_holds' and row.get('held') and (after is None or key > after) and len(owners) < limit:
                pending = [
                    v for (t, _), v in self.rows.items() if t == 'jobs' and v['owner_key'] == key and v['merge_pending']
                ]
                owners.append((key, pending[0]['owner_id'] if pending else None))
        return owners


def colliding_owner(owner):
    shard = scheduler_control_key(owner_key(owner))
    return next(str(n) for n in range(10000) if scheduler_control_key(owner_key(str(n))) == shard)


def item(segment, owner='heavy', capture=1, duration=30, priority=Priority.DEEP, unit_kind='conversation'):
    return WorkItem(segment, owner, capture, f'gs://synthetic/{segment}', duration, priority, unit_kind)


def test_heavy_owner_does_not_starve_light_owner():
    queue = Scheduler(MemoryStore())
    for n in range(30):
        queue.enqueue(item(f'h{n}'), 0)
    queue.enqueue(item('light', owner='light'), 0)
    pulled = queue.pull(1, 3)
    assert 'light' in [v.item.owner_id for v in pulled[:2]]
    assert len(pulled) == 3


def test_duration_deficit_round_robin():
    queue = Scheduler(MemoryStore())
    for n in range(9):
        queue.enqueue(item(f's{n}', owner='short', duration=10), 0)
    queue.enqueue(item('long', owner=colliding_owner('short'), duration=60), 0)
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


def test_failures_stop_at_default_ceiling_without_fabricating_result():
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
        job = store.rows['jobs', 'a']
        if attempt < 5:
            assert job['state'] == 'retry' and job['merge_pending']
            assert 0 < job['available_at'] - (now + 1) <= 600
            assert job['retry_started_at'] == 1001
    assert job['state'] == 'quarantined' and not job['merge_pending']
    assert job['quarantine_reason'] == 'worker_failed' and job['recovery_state'] == 'held'
    assert 'retry_started_at' not in job and 'result' not in job
    assert queue.recover(99999) == 0 and queue.pull(99999) == []
    assert not queue.redrive_dead('a', 99999)
    assert not queue.complete(WorkResult('a', 'gs://results/stale'), lease.token, 99999)
    assert OrderedMerge(store).commit_next('heavy', 99999) is None
    assert ('results', 'a') not in store.rows


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
    assert queue.enqueue(item('late', capture=1), 4)
    lease = queue.pull(4)[0]
    assert queue.complete(WorkResult('late', 'gs://results/late'), lease.token, 5)
    late = merge.commit_next('heavy', 6)
    assert late['previous_segment_id'] == 'c' and late['late_capture']
    assert late['capture_at'] == 1
    owner = store.rows['owners', owner_key('heavy')]
    assert owner['watermark'] == {'capture_at': 2, 'segment_id': 'c'}
    assert owner['log_tail'] == 'late'
    assert merge.commit_next('heavy', 7) is None


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


def test_catch_up_inside_the_fresh_lane_leases_after_fresh_uploads(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_FRESH_GPU_PRIORITY_ENABLED', raising=False)
    assert priority_for('fresh', 600) == Priority.FRESH
    assert priority_for('fresh', 601) == Priority.RECENT
    assert priority_for('fresh', 5 * 3600) == Priority.RECENT
    assert priority_for('fresh', float('nan')) == Priority.FRESH
    monkeypatch.setenv('BATCH_PIPELINE_FRESH_GPU_PRIORITY_ENABLED', 'false')
    assert priority_for('fresh', 5 * 3600) == Priority.FRESH


def test_fresh_upload_leases_ahead_of_the_same_owners_catch_up_fifo(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_FRESH_GPU_PRIORITY_ENABLED', raising=False)
    queue = Scheduler(MemoryStore())
    for n in range(20):
        queue.enqueue(item(f'c{n}', priority=priority_for('fresh', 3600)), 0)
    queue.enqueue(item('fresh', capture=2, priority=priority_for('fresh', 60)), 0)
    assert queue.pull(1, 1)[0].item.segment_id == 'fresh'


def test_admission_classifies_fresh_capture_by_capture_end():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('fresh', capture=1000, duration=60), 1000 + 60 + 600)
    queue.enqueue(item('catch_up', capture=1000, duration=60), 1000 + 60 + 601)
    assert store.rows['jobs', 'fresh']['fresh_capture'] is True
    assert store.rows['jobs', 'catch_up']['fresh_capture'] is False


def test_expired_leases_never_terminal_state_ordered_head():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    for attempt in range(1, 6):
        now = attempt * 1000
        queue.recover(now)
        lease = queue.pull(now)[0]
        assert queue.recover(now + LEASE_SECONDS) == 1
        assert not queue.heartbeat('a', lease.token, now + LEASE_SECONDS)
    assert store.rows['jobs', 'a']['state'] == 'retry'
    assert store.rows['jobs', 'a']['merge_pending']


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
    # A historical terminal job from the previous implementation.
    store.rows['jobs', 'a'].update(state='dead', available_at=0)
    # Strict order: the bounded head wait would release b past the dead head.
    merge = OrderedMerge(store, head_wait_seconds=0)
    assert merge.commit_next('heavy', 9999) is None
    assert queue.redrive_dead('a', 9999)
    assert not queue.redrive_dead('a', 9999)
    lease = queue.pull(9999)[0]
    assert lease.attempt == 2
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
        queue.enqueue(item('b', owner=colliding_owner('a')), 0)
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

    queue = Scheduler(MemoryStore(), pool='live')
    queue.enqueue(item('long', duration=3600), 0)
    queue.enqueue(item('over-boundary', owner='over-boundary', duration=120.001, unit_kind='capture_span'), 0)
    queue.enqueue(item('short', owner='short', duration=120, unit_kind='capture_span'), 0)
    capacity = PoolCapacity(10, 1, shared_with_live=True, memory_headroom_bytes=8 * 1024**3, gpu_id='gpu-test')
    monkeypatch.delenv('BATCH_PIPELINE_SHARED_LIVE_ENABLED', raising=False)
    assert queue.pull(10, capacity=capacity) == []
    monkeypatch.setenv('BATCH_PIPELINE_SHARED_LIVE_ENABLED', 'true')
    assert queue.pull(10, capacity=capacity) == []  # admitted policy remains off
    queue = Scheduler(MemoryStore(), pool='live')
    queue.enqueue(item('short', owner='short', duration=120, unit_kind='capture_span'), 0)
    assert [v.item.segment_id for v in queue.pull(10, 32, capacity=capacity)] == ['short']
    assert queue.pull(10, capacity=capacity) == []
    from dataclasses import replace

    for unsafe in (
        replace(capacity, live_queue_age_seconds=1),
        replace(capacity, gpu_utilization=0.5),
        replace(capacity, memory_headroom_bytes=0),
        replace(capacity, available_slots=2),
        replace(capacity, gpu_id=None),
    ):
        assert queue.pull(10, capacity=unsafe) == []


def test_capacity_never_spends_reserved_fresh_slots_on_multiple_backfill_items():
    from utils.batch_pipeline.contracts import PoolCapacity

    queue = Scheduler(MemoryStore())
    for n in range(3):
        queue.enqueue(item(f'backfill{n}'), 0)
    assert len(queue.pull(10, 3, capacity=PoolCapacity(10, 3, reserved_fresh_slots=2))) == 1


def test_per_pool_unit_ceiling_and_malformed_capacity_fail_closed():
    from utils.batch_pipeline.contracts import PoolCapacity

    queue = Scheduler(MemoryStore())
    queue.enqueue(item('long', duration=5400), 0)
    queue.enqueue(item('bounded', owner='bounded', duration=30), 0)
    assert queue.pull(10, capacity=PoolCapacity(10, 1, max_item_seconds=3600))[0].item.segment_id == 'bounded'
    assert queue.pull(10, capacity=PoolCapacity(10, 1, max_item_seconds=3600)) == []
    for capacity in (
        PoolCapacity(10, 1.5),
        PoolCapacity(10, 1, max_item_seconds=float('nan')),
        PoolCapacity(10, 1, max_item_seconds=0),
    ):
        assert queue.pull(10, capacity=capacity) == []


def test_shared_gpu_exclusivity_survives_completion_and_lease_expiry(monkeypatch):
    from utils.batch_pipeline.contracts import PoolCapacity

    monkeypatch.setenv('BATCH_PIPELINE_SHARED_LIVE_ENABLED', 'true')
    store = MemoryStore()
    first, second = Scheduler(store, pool='live'), Scheduler(store, pool='live')
    for name in ('a', 'b', 'c'):
        first.enqueue(item(name, owner=name, unit_kind='capture_span'), 0)

    def capacity(now):
        return PoolCapacity(now, 1, shared_with_live=True, memory_headroom_bytes=8 * 1024**3, gpu_id='same-gpu')

    lease = first.pull(1, capacity=capacity(1))[0]
    assert second.pull(1, capacity=capacity(1)) == []
    name = lease.item.segment_id
    assert first.heartbeat(name, lease.token, 60)
    assert first.complete(WorkResult(name, f'gs://results/{name}'), lease.token, 61)
    # Result completion alone cannot attest that asynchronous CUDA is idle.
    assert second.pull(61, capacity=capacity(61)) == []
    assert not first.acknowledge_gpu_idle('same-gpu', 'stale-token')
    assert first.acknowledge_gpu_idle('same-gpu', lease.token)
    assert first.acknowledge_gpu_idle('same-gpu', lease.token)
    next_lease = second.pull(61, capacity=capacity(61))[0]
    assert not first.acknowledge_gpu_idle('same-gpu', lease.token)
    assert first.recover(182) == 1
    # Expiry fences the old job, but never preempts/re-admits the physical GPU.
    assert first.pull(182, capacity=capacity(182)) == []
    assert second.acknowledge_gpu_idle('same-gpu', next_lease.token)
    assert first.pull(182, capacity=capacity(182))[0].item.segment_id not in {name, next_lease.item.segment_id}


def test_conversation_kind_never_runs_on_live_pool_even_when_short(monkeypatch):
    from utils.batch_pipeline.contracts import PoolCapacity

    monkeypatch.setenv('BATCH_PIPELINE_SHARED_LIVE_ENABLED', 'true')
    queue = Scheduler(MemoryStore(), pool='live')
    queue.enqueue(item('short-conversation', duration=30), 0)
    capacity = PoolCapacity(1, 1, shared_with_live=True, memory_headroom_bytes=8 * 1024**3, gpu_id='gpu-kind')
    assert queue.pull(1, capacity=capacity) == []
    assert queue.pull(1) == []
    assert queue.pull(1, capacity=PoolCapacity(1, 1)) == []
    assert Scheduler(queue.store).pull(1, capacity=capacity) == []
    assert Scheduler(queue.store).pull(1)[0].item.unit_kind == 'conversation'


def test_shards_weight_service_by_active_owner_count_and_preserve_global_priority():
    store = MemoryStore()
    queue = Scheduler(store)
    other = colliding_owner('heavy')
    assert scheduler_control_key(owner_key('light')) != scheduler_control_key(owner_key('heavy'))
    for owner in ('heavy', other, 'light'):
        for n in range(12):
            queue.enqueue(item(f'{owner}-{n}', owner=owner), 0)
    queue.enqueue(item('fresh-across-shards', owner='fresh', priority=Priority.FRESH), 0)
    assert queue.pull(1)[0].item.segment_id == 'fresh-across-shards'
    pulled = queue.pull(1, 18)
    counts = {uid: sum(v.item.owner_id == uid for v in pulled) for uid in ('heavy', other, 'light')}
    assert set(counts.values()) == {6}
    assert ('control', 'scheduler') not in store.rows
    assert len([key for table, key in store.rows if table == 'control']) >= 2


def test_legacy_ring_migration_preserves_pending_work():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('legacy'), 0)
    key = scheduler_control_key(owner_key('heavy'))
    store.rows['control', 'scheduler'] = {'rings': store.rows.pop(('control', key))['rings']}
    assert queue.pull(1) == []
    queue.recover(1)
    assert queue.pull(1)[0].item.segment_id == 'legacy'
    assert store.rows['control', 'scheduler']['rings']['2'] == []


def test_idle_shards_rejoin_at_frontier_without_history_penalty_or_credit_reset():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('old-heavy', duration=3600), 0)
    queue.pull(1)
    heavy_key = scheduler_control_key(owner_key('heavy'))
    light_key = scheduler_control_key(owner_key('light'))
    assert store.rows['control', heavy_key]['p2_service'] == 3600
    queue.enqueue(item('light', owner='light'), 2)
    assert store.rows['control', light_key]['p2_service'] == 3600
    queue.enqueue(item('heavy-again'), 2)
    assert {v.item.owner_id for v in queue.pull(2, 2)} == {'heavy', 'light'}
    frontier = max(v.get('p2_service', 0) for (table, _), v in store.rows.items() if table == 'control')
    queue.enqueue(item('heavy-rejoin'), 3)
    assert store.rows['control', heavy_key]['p2_service'] == frontier


@pytest.mark.parametrize('enabled', [False, True])
def test_capture_head_priority_resolves_ready_head_before_later_compute(monkeypatch, enabled):
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', str(enabled).lower())
    store = MemoryStore()
    queue = Scheduler(store)
    # Upload order differs from capture order, as in the incident. The later
    # recovered unit cannot commit until the older ready unit is computed.
    for sid, capture in [('later', 20), ('head', 10), ('tail', 30)]:
        queue.enqueue(item(sid, capture=capture), 0)
    first = queue.pull(1)[0]
    assert first.item.segment_id == ('head' if enabled else 'later')
    assert queue.complete(WorkResult(first.item.segment_id, 'gs://synthetic/result'), first.token, 2)
    entry = OrderedMerge(store).commit_next('heavy', 3)
    assert (entry is not None) == enabled
    if enabled:
        assert entry['segment_id'] == 'head'
        # The splice left an ordinary FIFO, including its original tail. A
        # rollback neither duplicates nor loses a lease.
        monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'false')
        assert [v.item.segment_id for v in queue.pull(4, 2)] == ['later', 'tail']


def test_slow_leased_head_is_never_stolen_or_overtaken(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('head', capture=10), 0)
    slow = queue.pull(1)[0]
    queue.enqueue(item('recovered', capture=20), 2)
    later = queue.pull(3)[0]
    assert queue.complete(WorkResult('recovered', 'gs://synthetic/recovered'), later.token, 4)
    merge = OrderedMerge(store)
    assert merge.commit_next('heavy', 5) is None
    assert queue.heartbeat('head', slow.token, 60)
    assert store.rows['jobs', 'head']['token'] == slow.token
    assert queue.complete(WorkResult('head', 'gs://synthetic/head'), slow.token, 61)
    assert merge.commit_next('heavy', 62)['segment_id'] == 'head'
    later_entry = merge.commit_next('heavy', 63)
    assert later_entry['segment_id'] == 'recovered'
    assert later_entry['previous_segment_id'] == 'head'


def test_head_priority_splices_tail_and_leaves_priority_capacity_and_fairness_intact(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    queue = Scheduler(MemoryStore())
    queue.enqueue(item('newer', capture=20), 0)
    queue.enqueue(item('head', capture=10), 0)
    queue.enqueue(item('fresh', owner='fresh', priority=Priority.FRESH), 0)
    assert queue.pull(1)[0].item.segment_id == 'fresh'
    assert queue.pull(2)[0].item.segment_id == 'head'
    queue.enqueue(item('after', capture=30), 3)
    assert [v.item.segment_id for v in queue.pull(4, 2)] == ['newer', 'after']


def test_head_owner_budget_is_bounded_and_default_off_adds_no_pending_query(monkeypatch):
    from utils.batch_pipeline import scheduler

    store = MemoryStore()
    queue = Scheduler(store)
    for sid, capture in [('new', 20), ('middle', 30), ('head', 10)]:
        queue.enqueue(item(sid, capture=capture), 0)
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    monkeypatch.setattr(scheduler, 'HEAD_OWNER_BUDGET', 0)
    assert queue.pull(1)[0].item.segment_id == 'new'
    monkeypatch.delenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED')
    monkeypatch.setattr(MemoryTransaction, 'first_pending', lambda *_: pytest.fail('dark priority queried head'))
    assert queue.pull(2)[0].item.segment_id == 'middle'


def test_head_promotion_never_buffers_link_writes_for_privacy_fenced_job(monkeypatch):
    from dataclasses import replace
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('newer', capture=20), 0)
    queue.enqueue(replace(item('head', capture=10), conversation_id='deleted'), 0)
    check = MemoryTransaction.check_privacy

    def privacy(tx, uid, conversation_ids=(), expected_generation=None):
        if 'deleted' in conversation_ids:
            raise BatchPrivacyBlocked('synthetic deletion')
        return check(tx, uid, conversation_ids, expected_generation)

    monkeypatch.setattr(MemoryTransaction, 'check_privacy', privacy)
    assert queue.pull(1)[0].item.segment_id == 'newer'
    assert store.rows['jobs', 'head']['state'] == 'ready'
    assert store.rows['jobs', 'head']['next'] == ''
    assert queue.pull(2) == []


def test_head_lookup_budget_is_shared_by_all_visited_owners(monkeypatch):
    from utils.batch_pipeline import scheduler

    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    monkeypatch.setattr(scheduler, 'HEAD_OWNER_BUDGET', 1)
    store = MemoryStore()
    queue = Scheduler(store)
    other = colliding_owner('heavy')
    for owner in ('heavy', other):
        queue.enqueue(item('new-' + owner, owner=owner, capture=20, duration=100), 0)
        queue.enqueue(item('head-' + owner, owner=owner, capture=10), 0)
    calls = []
    first = MemoryTransaction.first_pending

    def count(tx, key):
        calls.append(key)
        return first(tx, key)

    monkeypatch.setattr(MemoryTransaction, 'first_pending', count)
    assert queue.pull(1)
    assert len(calls) == 1


@pytest.mark.parametrize(
    'pool,kind,duration', [('batch', 'capture_span', 121), ('live', 'capture_span', 121), ('live', 'conversation', 10)]
)
def test_unleasable_merge_head_never_splices_ahead_of_eligible_fifo(monkeypatch, pool, kind, duration):
    from dataclasses import replace
    from utils.batch_pipeline.contracts import PoolCapacity

    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_SHARED_LIVE_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store, pool=pool)
    queue.enqueue(replace(item('fifo', capture=20, duration=10), unit_kind='capture_span'), 0)
    queue.enqueue(replace(item('head', capture=10, duration=duration), unit_kind=kind), 0)
    queue.enqueue(replace(item('tail', capture=30, duration=10), unit_kind='capture_span'), 0)
    capacity = PoolCapacity(
        1,
        1,
        max_item_seconds=120,
        shared_with_live=pool == 'live',
        memory_headroom_bytes=8 * 1024**3,
        gpu_id='head-priority-gpu',
    )
    lease = queue.pull(1, capacity=capacity)[0]
    assert lease.item.segment_id == 'fifo'
    key = f'{int(Priority.DEEP)}_{owner_key("heavy")}'
    assert store.rows['queues', key]['head'] == 'head'
    assert store.rows['queues', key]['tail'] == 'tail'
    assert store.rows['jobs', 'head']['next'] == 'tail'
    assert store.rows['jobs', 'head']['state'] == 'ready'
    assert queue.complete(WorkResult('fifo', 'gs://synthetic/result'), lease.token, 2)
    assert OrderedMerge(store).commit_next('heavy', 3) is None
    # The ordinary batch pool can still lease the skipped ordered head.
    assert Scheduler(store).pull(3)[0].item.segment_id == 'head'


@pytest.fixture
def reverse_capture_run(monkeypatch):
    # Execute the snapshot-store workload in setup, as the virtual-clock suite
    # does; the fast-unit call-phase budget measures the ordering assertions.
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    for n in reversed(range(160)):
        queue.enqueue(item(f's{n:03}', capture=n), 0)
    merge = OrderedMerge(store)
    receipts = []
    for n in range(160):
        lease = queue.pull(10 + n)[0]
        accepted = queue.complete(WorkResult(lease.item.segment_id, 'gs://synthetic/result'), lease.token, 10 + n)
        entry = merge.commit_next('heavy', 10 + n)
        receipts.append((lease.item.segment_id, accepted, entry))
    return receipts, queue.pull(1000)


def test_indexed_head_beyond_64_preserves_all_links_and_order(reverse_capture_run):
    receipts, remaining = reverse_capture_run
    assert len(receipts) == 160
    for n, (segment_id, accepted, entry) in enumerate(receipts):
        assert segment_id == f's{n:03}'
        assert accepted
        assert entry['segment_id'] == segment_id
        assert entry['previous_segment_id'] == (f's{n-1:03}' if n else None)
    assert remaining == []


def test_head_metrics_and_missing_predecessor_fail_closed(monkeypatch):
    from prometheus_client import CollectorRegistry
    from utils.batch_pipeline.metrics import QueueMetrics
    from utils.batch_pipeline import scheduler

    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    queue = Scheduler(store, metrics=metrics)
    queue.enqueue(item('later', capture=20), 0)
    queue.enqueue(item('head', capture=10), 0)
    monkeypatch.setattr(MemoryTransaction, 'ready_predecessor', lambda *_: None)
    assert queue.pull(20)[0].item.segment_id == 'later'
    labels = {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'}
    assert registry.get_sample_value('omi_batch_pipeline_head_not_found_total', labels) == 1
    assert registry.get_sample_value('omi_batch_pipeline_predecessor_ready_age_seconds_sum', labels) == 20
    monkeypatch.setattr(scheduler, 'HEAD_OWNER_BUDGET', 0)
    assert queue.pull(21)[0].item.segment_id == 'head'
    assert registry.get_sample_value('omi_batch_pipeline_head_budget_exhausted_total', labels) == 1


def test_ready_predecessor_ignores_stale_leased_links(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('leased', capture=0), 0)
    queue.enqueue(item('fifo', capture=20), 0)
    slow = queue.pull(1)[0]
    queue.enqueue(item('head', capture=10), 2)
    # A prior lease can retain the same next link; it must never be rewritten.
    store.rows['jobs', 'leased']['next'] = 'head'
    assert queue.complete(WorkResult('leased', 'gs://synthetic/result'), slow.token, 3)
    assert OrderedMerge(store).commit_next('heavy', 3)
    assert queue.pull(4)[0].item.segment_id == 'head'
    assert store.rows['jobs', 'leased']['next'] == 'head'
    assert queue.pull(4)[0].item.segment_id == 'fifo'


def _fail_on_call(queue, monkeypatch, failing_call, error):
    original, calls = queue._pull_one, [0]

    def pull_one(*args, **kwargs):
        calls[0] += 1
        if calls[0] == failing_call:
            raise error
        return original(*args, **kwargs)

    monkeypatch.setattr(queue, '_pull_one', pull_one)


def test_partial_pull_failure_hands_back_committed_leases_instead_of_stranding_them(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    for n, owner in enumerate(('a', 'b', 'c')):
        queue.enqueue(item(owner, owner=owner, capture=n), 0)
    _fail_on_call(queue, monkeypatch, 3, RuntimeError('synthetic Aborted on lease 3'))
    pulled = queue.pull(1, 3)
    assert len(pulled) == 2
    for lease in pulled:
        job = store.rows['jobs', lease.item.segment_id]
        assert job['state'] == 'leased' and job['token'] == lease.token and job['attempt'] == 1
        assert queue.complete(WorkResult(lease.item.segment_id, 'gs://results/x'), lease.token, 2)
    # Lease 3 never committed: its job is still ready and claimable at once.
    (rest,) = [v for v in ('a', 'b', 'c') if v not in {lease.item.segment_id for lease in pulled}]
    assert store.rows['jobs', rest]['state'] == 'ready'
    monkeypatch.undo()
    assert [v.item.segment_id for v in queue.pull(2, 3)] == [rest]


def test_first_lease_failure_still_raises_with_nothing_leased(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    _fail_on_call(queue, monkeypatch, 1, ValueError('synthetic'))
    with pytest.raises(ValueError):
        queue.pull(1, 3)
    assert store.rows['jobs', 'a']['state'] == 'ready'


def test_post_commit_telemetry_failure_never_drops_an_issued_lease(monkeypatch):
    from utils.batch_pipeline import scheduler as module

    class BrokenMetrics:
        def record(self, *args, **kwargs):
            raise RuntimeError('metrics down')

        def record_head(self, *args, **kwargs):
            raise RuntimeError('metrics down')

    def broken_observations(observations):
        raise RuntimeError('policy telemetry down')

    monkeypatch.setattr(module, 'record_policy_observations', broken_observations)
    store = MemoryStore()
    queue = Scheduler(store, metrics=BrokenMetrics())
    queue.enqueue(item('a'), 0)
    queue.enqueue(item('b', capture=2), 0)
    pulled = queue.pull(1, 2)
    assert [v.item.segment_id for v in pulled] == ['a', 'b']
    assert all(store.rows['jobs', v.item.segment_id]['token'] == v.token for v in pulled)


def test_release_expires_lease_now_with_expiry_semantics_and_fences_stale_tokens():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    first = queue.pull(1)[0]
    assert not queue.release('a', 'stale-token', 2)
    assert queue.release('a', first.token, 2)
    job = store.rows['jobs', 'a']
    # Same transition recover() applies after LEASE_SECONDS, without the wait.
    assert job['state'] == 'retry' and job['attempt'] == 1 and job['token'] == ''
    assert job['available_at'] == 2 + 5 < 1 + LEASE_SECONDS
    assert not queue.release('a', first.token, 3)
    assert queue.recover(7) == 1
    second = queue.pull(7)[0]
    assert second.attempt == 2 and second.token != first.token
    assert not queue.release('a', first.token, 8)
    assert not queue.complete(WorkResult('a', 'gs://results/stale'), first.token, 8)
    assert queue.complete(WorkResult('a', 'gs://results/a'), second.token, 8)
    assert not queue.release('a', second.token, 9)  # Published work is never released.
    assert store.rows['jobs', 'a']['state'] == 'result_ready'

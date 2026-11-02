"""Bounded cross-owner publication and one ordered drain per owner per flight."""

import asyncio
import threading
import time

import pytest

from config.batch_pipeline import DEFAULT_PUBLISH_CONCURRENCY, publish_concurrency
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import PoolCapacity, RecoveryWork, WorkResult
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler


class Worker:
    """Returns results in reverse lease order so completion order != capture order."""

    def __init__(self, recover=()):
        self.recover = set(recover)

    def process_batch(self, items):
        return [
            (
                RecoveryWork(v.segment_id)
                if v.segment_id in self.recover
                else WorkResult(v.segment_id, f'gs://r/{v.segment_id}')
            )
            for v in reversed(items)
        ]


def build(concurrency, segments, worker=None):
    store = MemoryStore()
    queue = Scheduler(store)
    for segment, owner, capture in segments:
        queue.enqueue(item(segment, owner=owner, capture=capture), time.time())
    pump = Pump(
        queue,
        worker or Worker(),
        capacity=lambda: PoolCapacity(time.time(), 8),
        publish_concurrency=concurrency,
    )
    return store, queue, pump


# Two owners, captures enqueued out of capture order.
MIXED = [('a3', 'alice', 3), ('b2', 'bob', 2), ('a1', 'alice', 1), ('b1', 'bob', 1), ('a2', 'alice', 2)]


def count_commit_calls(pump):
    calls = {}
    original = pump.merge.commit_next

    def commit_next(owner_id, now):
        calls[owner_id] = calls.get(owner_id, 0) + 1
        return original(owner_id, now)

    pump.merge.commit_next = commit_next
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize('concurrency', [1, DEFAULT_PUBLISH_CONCURRENCY, 16])
async def test_each_owner_commits_in_capture_order_whatever_the_concurrency(concurrency):
    store, _, pump = build(concurrency, MIXED)
    committed = []
    pump.on_committed = lambda entry: committed.append((entry['owner_id'], entry['segment_id']))
    assert await pump.run_once() == 5
    assert [s for o, s in committed if o == 'alice'] == ['a1', 'a2', 'a3']
    assert [s for o, s in committed if o == 'bob'] == ['b1', 'b2']
    assert store.rows['results', 'a2']['previous_segment_id'] == 'a1'
    assert store.rows['results', 'a3']['previous_segment_id'] == 'a2'
    assert store.rows['results', 'a3']['log_sequence'] == 3
    assert store.rows['results', 'b2']['previous_segment_id'] == 'b1'


@pytest.mark.asyncio
async def test_one_drain_per_owner_per_flight_and_kill_switch_restores_per_transition_drains():
    _, _, pump = build(DEFAULT_PUBLISH_CONCURRENCY, MIXED)
    calls = count_commit_calls(pump)
    await pump.run_once()
    # One drain each: every commit plus a single empty probe.
    assert calls == {'alice': 4, 'bob': 3}

    _, _, legacy = build(1, MIXED)
    legacy_calls = count_commit_calls(legacy)
    await legacy.run_once()
    # Legacy drains after every accepted transition: one probe per transition.
    assert legacy_calls == {'alice': 6, 'bob': 4}


@pytest.mark.asyncio
async def test_transitions_are_bounded_and_overlap_across_owners():
    segments = [(f's{n}', f'owner{n}', 1) for n in range(8)]
    _, queue, pump = build(3, segments)
    active, peak, lock = [0], [0], threading.Lock()
    original = queue.complete

    def complete(result, token, now):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        try:
            time.sleep(0.01)
            return original(result, token, now)
        finally:
            with lock:
                active[0] -= 1

    queue.complete = complete
    assert await pump.run_once() == 8
    assert 1 < peak[0] <= 3


@pytest.mark.asyncio
async def test_same_owner_drains_never_overlap():
    _, _, pump = build(DEFAULT_PUBLISH_CONCURRENCY, MIXED)
    original = pump.merge.commit_next
    active, overlap, lock = {}, [], threading.Lock()

    def commit_next(owner_id, now):
        with lock:
            active[owner_id] = active.get(owner_id, 0) + 1
            if active[owner_id] > 1:
                overlap.append(owner_id)
        try:
            time.sleep(0.005)
            return original(owner_id, now)
        finally:
            with lock:
                active[owner_id] -= 1

    pump.merge.commit_next = commit_next
    await pump.run_once()
    # Maintenance and post-flight drains for the same owner race here on purpose.
    await asyncio.gather(*(pump.drain_owner('alice') for _ in range(4)), pump.drain_owner('bob'))
    assert overlap == []
    assert pump._owner_locks == {}


@pytest.mark.asyncio
async def test_lost_lease_is_fenced_and_does_not_block_other_owners(monkeypatch):
    store, queue, pump = build(DEFAULT_PUBLISH_CONCURRENCY, MIXED)
    original = queue.complete

    def complete(result, token, now):
        if result.segment_id == 'b1':
            # Another worker took the lease: the token no longer owns the job.
            store.rows['jobs', 'b1']['token'] = 'stolen'
        return original(result, token, now)

    queue.complete = complete
    assert await pump.run_once() == 5
    assert store.rows['jobs', 'b1']['state'] == 'leased'
    assert ('results', 'b1') not in store.rows
    # b2 is result_ready but must wait behind its uncommitted predecessor.
    assert store.rows['jobs', 'b2']['state'] == 'result_ready'
    assert ('results', 'b2') not in store.rows
    assert all(store.rows['jobs', s]['state'] == 'committed' for s in ('a1', 'a2', 'a3'))


@pytest.mark.asyncio
async def test_privacy_fence_on_one_owner_merge_does_not_suppress_others():
    store, _, pump = build(DEFAULT_PUBLISH_CONCURRENCY, MIXED)
    original = pump.merge.commit_next

    def commit_next(owner_id, now):
        if owner_id == 'bob':
            raise BatchPrivacyBlocked('synthetic deletion fence')
        return original(owner_id, now)

    pump.merge.commit_next = commit_next
    assert await pump.run_once() == 5
    assert all(store.rows['jobs', s]['state'] == 'committed' for s in ('a1', 'a2', 'a3'))
    assert all(('results', s) not in store.rows for s in ('b1', 'b2'))
    assert all(store.rows['jobs', s]['state'] == 'result_ready' for s in ('b1', 'b2'))


@pytest.mark.asyncio
async def test_privacy_fence_on_one_transition_does_not_suppress_siblings():
    store, queue, pump = build(DEFAULT_PUBLISH_CONCURRENCY, MIXED)
    original = queue.complete

    def complete(result, token, now):
        if result.segment_id == 'a2':
            raise BatchPrivacyBlocked('synthetic revoked owner')
        return original(result, token, now)

    queue.complete = complete
    assert await pump.run_once() == 5
    assert store.rows['jobs', 'a1']['state'] == 'committed'
    assert ('results', 'a2') not in store.rows and ('results', 'a3') not in store.rows
    assert store.rows['jobs', 'b2']['state'] == 'committed'


@pytest.mark.asyncio
async def test_duplicate_publication_is_idempotent():
    store, queue, pump = build(DEFAULT_PUBLISH_CONCURRENCY, MIXED, worker=Worker(recover={'b2'}))
    leases = queue.pull(time.time(), 8)
    results = {v.segment_id: v for v in pump.worker.process_batch([lease.item for lease in leases])}
    committed = []
    pump.on_committed = lambda entry: committed.append(entry['segment_id'])
    await pump._publish_flight(leases, results, set())
    before = {key: dict(value) for key, value in store.rows.items() if key[0] in {'jobs', 'results', 'owners'}}
    # Same lease tokens, same results, delivered again (lost reply + retry).
    await pump._publish_flight(leases, results, set())
    after = {key: dict(value) for key, value in store.rows.items() if key[0] in {'jobs', 'results', 'owners'}}
    assert after == before
    assert sorted(committed) == ['a1', 'a2', 'a3', 'b1']
    # The quarantine is held once; the paid-recovery intent is created downstream from it.
    assert store.rows['jobs', 'b2']['state'] == 'quarantined'
    assert store.rows['jobs', 'b2']['recovery_state'] == 'held'


@pytest.mark.asyncio
@pytest.mark.parametrize('concurrency, expected_reads', [(DEFAULT_PUBLISH_CONCURRENCY, 2), (1, 6)])
async def test_maintenance_does_not_reread_blocked_result_ready_jobs_every_sweep(concurrency, expected_reads):
    store, queue, pump = build(concurrency, MIXED)
    leases = {lease.item.segment_id: lease for lease in queue.pull(time.time(), 8)}
    # a1 stays leased (the blocked ordered head); its successors wait result_ready.
    for segment in ('a2', 'a3'):
        queue.complete(WorkResult(segment, 'gs://r'), leases[segment].token, time.time())
    owner_reads = []
    original = store.run

    def run(body):
        if 'owner_of' in getattr(body, '__qualname__', ''):
            owner_reads.append(body)
        return original(body)

    store.run = run
    calls = count_commit_calls(pump)
    for _ in range(3):
        pump._last_recovery = float('-inf')
        assert await pump.run_once() == 0
    assert len(owner_reads) == expected_reads  # memo: read once, not once per sweep
    assert calls['alice'] == 3  # one fenced probe per sweep; nothing commits past the head
    assert all(store.rows['jobs', s]['state'] == 'result_ready' for s in ('a2', 'a3'))


@pytest.mark.asyncio
async def test_maintenance_drains_each_ready_owner_once():
    store, queue, pump = build(DEFAULT_PUBLISH_CONCURRENCY, MIXED)
    for lease in queue.pull(time.time(), 8):
        queue.complete(WorkResult(lease.item.segment_id, 'gs://r'), lease.token, time.time())
    calls = count_commit_calls(pump)
    assert await pump.run_once() == 0
    assert calls == {'alice': 4, 'bob': 3}
    assert all(store.rows['jobs', s]['state'] == 'committed' for s, _, _ in MIXED)


def test_publish_concurrency_is_ship_on_with_a_kill_switch(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_PUBLISH_CONCURRENCY', raising=False)
    assert publish_concurrency() == DEFAULT_PUBLISH_CONCURRENCY > 1
    for raw, expected in (('1', 1), ('8', 8), ('16', 16), ('0', 1), ('17', 1), ('x', 1), ('', 1)):
        monkeypatch.setenv('BATCH_PIPELINE_PUBLISH_CONCURRENCY', raw)
        assert publish_concurrency() == expected
    for bad in (0, 17):
        with pytest.raises(ValueError):
            Pump(Scheduler(MemoryStore()), Worker(), publish_concurrency=bad)

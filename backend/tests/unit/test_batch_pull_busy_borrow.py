"""A pump's non-first lanes borrow backfill past claimed fresh shards; lane 0 stays fresh-first."""

import asyncio
import time

import pytest

from config.batch_pipeline import pull_busy_borrow_enabled
from tests.unit.test_batch_pipeline_pump import Worker
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import PoolCapacity, Priority
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler


class HintStore(MemoryStore):
    """Fresh candidates are all claimed by other pullers; deep has one free shard."""

    def control_candidates(self, priority, pool, now, *, worker_id='', fanout=None):
        if priority == int(Priority.FRESH):
            return ['fresh-a', 'fresh-b']
        if priority == int(Priority.DEEP):
            return ['deep-a']
        return []


def fake_pull_shard(visited, receipt):
    def pull(now, shard, *args):
        visited.append(shard)
        return ([(receipt, 0, False)], True) if shard.startswith('deep') else (None, 'busy')

    return pull


@pytest.mark.parametrize('raw, expected', [(None, True), ('true', True), (' FALSE ', False), ('false', False)])
def test_busy_borrow_ships_on_with_a_kill_switch(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv('BATCH_PULL_BUSY_BORROW_ENABLED', raising=False)
    else:
        monkeypatch.setenv('BATCH_PULL_BUSY_BORROW_ENABLED', raw)
    assert pull_busy_borrow_enabled() is expected


def test_first_lane_never_borrows_past_claimed_fresh_shards(monkeypatch):
    queue = Scheduler(HintStore())
    visited = []
    monkeypatch.setattr(queue, '_pull_shard', fake_pull_shard(visited, object()))
    assert queue._pull_one(1, allow_backfill=True, max_seconds=3600) == []
    assert visited == ['fresh-a', 'fresh-b']


def test_borrowing_lane_leases_backfill_when_every_fresh_shard_is_claimed(monkeypatch):
    queue = Scheduler(HintStore())
    visited = []
    receipt = object()
    monkeypatch.setattr(queue, '_pull_shard', fake_pull_shard(visited, receipt))
    assert queue._pull_one(1, allow_backfill=True, max_seconds=3600, borrow_when_fresh_busy=True) == [receipt]
    assert visited == ['fresh-a', 'fresh-b', 'deep-a']


def test_borrowing_still_respects_disallowed_backfill(monkeypatch):
    queue = Scheduler(HintStore())
    visited = []
    monkeypatch.setattr(queue, '_pull_shard', fake_pull_shard(visited, object()))
    assert queue._pull_one(1, allow_backfill=False, max_seconds=3600, borrow_when_fresh_busy=True) == []
    assert visited == ['fresh-a', 'fresh-b']


def claimed_fresh_and_ready_deep():
    """Real store: one fresh unit whose shard another worker has claimed, one deep unit elsewhere."""
    from config.batch_pipeline import scheduler_control_key
    from utils.batch_pipeline.scheduler import owner_key

    store = MemoryStore()
    queue = Scheduler(store)
    shards = {}
    for n in range(10000):
        owner = f'synthetic-owner-{n}'
        shards.setdefault(scheduler_control_key(owner_key(owner)), owner)
        if len(shards) == 2:
            break
    (fresh_shard, fresh_owner), (_, deep_owner) = sorted(shards.items())
    queue.enqueue(item('fresh-unit', owner=fresh_owner, priority=Priority.FRESH), 0)
    queue.enqueue(item('deep-unit', owner=deep_owner, priority=Priority.DEEP), 0)
    store.rows['pull_claims', fresh_shard] = {'token': 'another-worker', 'expires_at': 100}
    return store, queue


def test_pull_borrows_deep_work_while_the_fresh_shard_is_claimed_elsewhere():
    store, queue = claimed_fresh_and_ready_deep()
    assert queue.pull(1, 8) == []  # Lane 0: strict fresh-first.
    leases = queue.pull(1, 8, borrow_when_fresh_busy=True)
    assert [lease.item.segment_id for lease in leases] == ['deep-unit']
    assert store.rows['jobs', 'fresh-unit']['state'] == 'ready'  # Left to its claimant.


def test_kill_switch_restores_strict_fresh_first_on_every_lane(monkeypatch):
    monkeypatch.setenv('BATCH_PULL_BUSY_BORROW_ENABLED', 'false')
    store, queue = claimed_fresh_and_ready_deep()
    assert queue.pull(1, 8, borrow_when_fresh_busy=True) == []
    assert store.rows['jobs', 'deep-unit']['state'] == 'ready'


@pytest.mark.parametrize('shared, expected', [(False, [True]), (True, [False])])
def test_shared_live_gpu_never_borrows(monkeypatch, shared, expected):
    queue = Scheduler(MemoryStore())
    seen = []

    def pull_one(now, **kwargs):
        seen.append(kwargs['borrow_when_fresh_busy'])
        return []

    monkeypatch.setattr(queue, '_pull_one', pull_one)
    if shared:
        queue.pool = 'live'
        capacity = PoolCapacity(1, 1, shared_with_live=True, gpu_id='synthetic-gpu')
    else:
        capacity = PoolCapacity(1, 8)
    monkeypatch.setattr(
        PoolCapacity, 'limits', lambda self, now, shared_live_enabled: (self.available_slots, True, 7200.0)
    )
    queue.pull(1, 8, capacity=capacity, borrow_when_fresh_busy=True)
    assert seen == expected


@pytest.mark.asyncio
async def test_only_lanes_after_the_first_ask_to_borrow(monkeypatch):
    queue = Scheduler(MemoryStore())
    pump = Pump(queue, Worker(), capacity=lambda: PoolCapacity(time.time(), 8), flights=3)
    calls = []

    def pull(now, limit, *, capacity=None, borrow_when_fresh_busy=False):
        calls.append(borrow_when_fresh_busy)
        return []

    monkeypatch.setattr(queue, 'pull', pull)
    stop = asyncio.Event()
    running = asyncio.create_task(pump.run(stop))
    while len(calls) < 3:
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(running, 10)
    assert sorted(calls[:3]) == [False, True, True]

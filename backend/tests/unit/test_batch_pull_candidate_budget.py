"""Bound hint RPCs while preserving busy exclusion and fresh priority."""

from collections import Counter

import pytest

from config.batch_pipeline import control_candidate_fanout
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler


@pytest.mark.parametrize('raw, expected', [(None, 16), ('bad', 16), ('0', 1), ('999', 64), ('64', 64), ('1', 1)])
def test_candidate_budget_clamps_and_legacy_width(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv('BATCH_CONTROL_CANDIDATE_FANOUT', raising=False)
    else:
        monkeypatch.setenv('BATCH_CONTROL_CANDIDATE_FANOUT', raw)
    assert control_candidate_fanout() == expected


class HintStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.queries = Counter()

    def control_candidates(self, priority, pool, now, *, worker_id='', fanout=None):
        self.queries[priority] += 1
        return ['busy-a', 'busy-b', 'head', 'tail'] if priority == 0 else []


def test_busy_claims_reuse_one_hint_list_and_find_an_unclaimed_shard(monkeypatch):
    store = HintStore()
    queue = Scheduler(store)
    receipt = object()
    visited = []

    def pull(now, shard, *args):
        visited.append(shard)
        return ([(receipt, 0, False)], True) if shard == 'head' else (None, 'busy')

    monkeypatch.setattr(queue, '_pull_shard', pull)
    assert queue._pull_one(1, allow_backfill=True, max_seconds=3600) == [receipt]
    assert visited == ['busy-a', 'busy-b', 'head']
    assert store.queries == {0: 1}


def test_deficit_rounds_refresh_at_most_once_and_do_not_skip_eligible_head(monkeypatch):
    store = HintStore()
    queue = Scheduler(store)
    visited = []
    receipt = object()

    def pull(now, shard, *args):
        visited.append(shard)
        if shard.startswith('busy'):
            return None, 'busy'
        return ([(receipt, 0, False)], True) if visited.count('head') == 4 else (None, True)

    monkeypatch.setattr(queue, '_pull_shard', pull)
    assert queue._pull_one(1, allow_backfill=True, max_seconds=3600) == [receipt]
    assert visited == ['busy-a', 'busy-b', 'head', 'head', 'head', 'head']
    assert store.queries == {0: 2}


def test_busy_fresh_candidates_never_borrow_backfill(monkeypatch):
    store = HintStore()
    queue = Scheduler(store)
    monkeypatch.setattr(queue, '_pull_shard', lambda *args: (None, 'busy'))
    assert queue._pull_one(1, allow_backfill=True, max_seconds=3600) == []
    assert store.queries == {int(Priority.FRESH): 1}


class BudgetStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.widths = []
        self.claims = Counter()

    def control_candidates(self, priority, pool, now, *, worker_id='', fanout=None):
        self.widths.append(control_candidate_fanout(fanout))
        return super().control_candidates(priority, pool, now, worker_id=worker_id, fanout=fanout)

    def acquire_pull_claim(self, shard, token, now, ttl):
        self.claims[shard] += 1
        return super().acquire_pull_claim(shard, token, now, ttl)


@pytest.mark.parametrize('busy_count, expected_widths', [(0, [16]), (16, [16, 64])])
def test_full_window_only_refills_when_all_sixteen_candidates_are_busy(monkeypatch, busy_count, expected_widths):
    from config.batch_pipeline import scheduler_control_key
    from tests.unit.test_batch_pipeline_scheduler import item
    from utils.batch_pipeline.scheduler import owner_key

    monkeypatch.setenv('BATCH_CONTROL_CANDIDATE_FANOUT', '16')
    store = BudgetStore()
    queue = Scheduler(store)
    owners = {}
    for n in range(10000):
        owner = f'synthetic-owner-{n}'
        owners.setdefault(scheduler_control_key(owner_key(owner)), owner)
        if len(owners) == 17:
            break
    assert len(owners) == 17
    for shard, owner in owners.items():
        queue.enqueue(item(f'unit-{shard}', owner=owner, priority=Priority.FRESH), 0)
    shards = sorted(owners)
    for shard in shards[:busy_count]:
        store.rows['pull_claims', shard] = {'token': 'another-worker', 'expires_at': 100}

    leases = queue.pull(1)

    assert len(leases) == 1
    assert leases[0].item.segment_id not in {f'unit-{shard}' for shard in shards[:busy_count]}
    if busy_count:
        assert leases[0].item.segment_id == f'unit-{shards[16]}'
    assert store.widths == expected_widths
    assert len(store.claims) == busy_count + 1 and all(count == 1 for count in store.claims.values())
    assert all(store.rows['jobs', f'unit-{shard}']['state'] == 'ready' for shard in shards[:busy_count])


@pytest.mark.parametrize('fanout, expected_widths', [(16, [16, 64]), (64, [64])])
def test_saturated_busy_refill_is_bounded_and_never_bypasses_fresh(monkeypatch, fanout, expected_widths):
    monkeypatch.setenv('BATCH_CONTROL_CANDIDATE_FANOUT', str(fanout))
    store = MemoryStore()
    queue = Scheduler(store)
    widths, visited = [], []

    def candidates(priority, pool, now, *, worker_id='', fanout=None):
        assert priority == int(Priority.FRESH), 'busy fresh must prevent backfill queries'
        widths.append(fanout)
        return [f'shard-{n}' for n in range(fanout)]

    def pull(now, shard, *args):
        visited.append(shard)
        return None, 'busy'

    monkeypatch.setattr(store, 'control_candidates', candidates)
    monkeypatch.setattr(queue, '_pull_shard', pull)
    assert queue._pull_one(1, allow_backfill=True, max_seconds=3600) == []
    assert widths == expected_widths
    assert len(visited) == len(set(visited)) == 64

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

    def control_candidates(self, priority, pool, now, *, worker_id=''):
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

from copy import deepcopy

import pytest

from config import conversation_smart_merge as config
from config import merge_ancestry
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
from tests.unit.test_conversation_smart_merge import UID, World
from tests.unit.test_conversation_smart_merge_flatten import (
    _absorb_attempts,
    _assign,
    _flattened_world,
    _path,
    _seed_index,
    _sync_chunk,
    _tombstone,
)
from utils.sync.assignment_errors import SyncAssignmentConflict


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'off')
    monkeypatch.delenv(config.SMART_MERGE_UID_ALLOWLIST_ENV, raising=False)
    monkeypatch.delenv(config.SMART_MERGE_AUDIT_ENV, raising=False)
    monkeypatch.delenv(config.SMART_MERGE_FLATTEN_ENV, raising=False)
    return World(monkeypatch)


@pytest.fixture
def reads(monkeypatch):
    log = []
    real = StrictFirestoreDocument.get

    def get(self, transaction=None, **kwargs):
        if transaction is not None:
            log.append((transaction, self.path))
        return real(self, transaction, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    return log


def _live_pair(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.raw('n')['sync_content_revision'] = 7
    world.raw('p')['sync_content_revision'] = 2


def _bridge(world, cid, start_min, *, merged_into, nested=None, marker=False, minutes=4):
    world.add(cid, start_min, minutes)
    extra = {}
    if nested is not None:
        extra['sync_merged_from'] = nested
    if marker:
        extra['smart_merge'] = {'role': 'donor', 'survivor_id': merged_into}
    _tombstone(world, cid, merged_into=merged_into, **extra)


def _assert_absorb_rejected_clean(world, reads, before):
    assert world.finish('n') is False
    assert world.raw('n')['smart_merge_decision']['reason'] == merge_ancestry.INVALID
    absorbs = _absorb_attempts(world, reads)
    assert absorbs
    assert all(not txn.has_written for txn in absorbs)
    after = deepcopy(world.store.rows)
    after[_path('n')].pop('smart_merge_decision', None)
    assert after == before


def test_survivor_ancestor_hidden_descendant_rejects_without_reading_it(world, reads):
    _live_pair(world)
    _bridge(world, 'g1', 5, merged_into='p', nested=['g2'])
    _bridge(world, 'g2', 4, merged_into='g1')
    world.raw('p')['sync_merged_from'] = ['g1']
    before = deepcopy(world.store.rows)
    _assert_absorb_rejected_clean(world, reads, before)
    assert all(path != _path('g2') for _, path in reads)


@pytest.mark.parametrize(
    'nested',
    ['zz', [''], ['a' * 129], [f'z{i}' for i in range(12)]],
    ids=['non_list', 'invalid_id', 'long_id', 'oversized'],
)
@pytest.mark.parametrize('marker', [False, True], ids=['plain', 'smart_donor_marker'])
def test_survivor_ancestor_malformed_nested_list_rejects(world, reads, nested, marker):
    _live_pair(world)
    _bridge(world, 'g1', 5, merged_into='p', nested=nested, marker=marker)
    world.raw('p')['sync_merged_from'] = ['g1']
    before = deepcopy(world.store.rows)
    _assert_absorb_rejected_clean(world, reads, before)


@pytest.mark.parametrize('marker', [False, True], ids=['plain', 'smart_donor_marker'])
def test_survivor_ancestor_self_cycle_rejects(world, reads, marker):
    _live_pair(world)
    _bridge(world, 'g1', 5, merged_into='p', nested=['g1'], marker=marker)
    world.raw('p')['sync_merged_from'] = ['g1']
    before = deepcopy(world.store.rows)
    _assert_absorb_rejected_clean(world, reads, before)


@pytest.mark.parametrize('marker', [False, True], ids=['plain', 'smart_donor_marker'])
def test_survivor_ancestor_two_node_cycle_rejects(world, reads, marker):
    _live_pair(world)
    _bridge(world, 'g1', 5, merged_into='p', nested=['g2'])
    _bridge(world, 'g2', 4, merged_into='p', nested=['g1'], marker=marker)
    world.raw('p')['sync_merged_from'] = ['g1', 'g2']
    before = deepcopy(world.store.rows)
    _assert_absorb_rejected_clean(world, reads, before)


def test_survivor_ancestor_three_node_cycle_rejects(world, reads):
    _live_pair(world)
    _bridge(world, 'g1', 5, merged_into='p', nested=['g2'])
    _bridge(world, 'g2', 4, merged_into='p', nested=['g3'])
    _bridge(world, 'g3', 3, merged_into='p', nested=['g1'])
    world.raw('p')['sync_merged_from'] = ['g1', 'g2', 'g3']
    before = deepcopy(world.store.rows)
    _assert_absorb_rejected_clean(world, reads, before)


def test_survivor_ancestor_transitive_hidden_descendant_rejects(world, reads):
    _live_pair(world)
    _bridge(world, 'g1', 5, merged_into='p', nested=['g2'])
    _bridge(world, 'g2', 4, merged_into='p', nested=['h'])
    _bridge(world, 'h', 3, merged_into='g2')
    world.raw('p')['sync_merged_from'] = ['g1', 'g2']
    before = deepcopy(world.store.rows)
    _assert_absorb_rejected_clean(world, reads, before)
    assert all(path != _path('h') for _, path in reads)


@pytest.mark.parametrize('marker', [False, True], ids=['plain', 'smart_donor_marker'])
def test_valid_closed_survivor_ancestry_absorbs_unmodified(world, reads, marker):
    _live_pair(world)
    _bridge(world, 'g1', 5, merged_into='p', nested=['g2'], marker=marker)
    _bridge(world, 'g2', 4, merged_into='p')
    world.raw('p')['sync_merged_from'] = ['g1', 'g2']
    g1_before, g2_before = deepcopy(world.raw('g1')), deepcopy(world.raw('g2'))
    assert world.finish('n') is True
    assert world.raw('g1') == g1_before
    assert world.raw('g2') == g2_before
    assert sorted(world.raw('p')['sync_merged_from']) == ['g1', 'g2', 'n']
    assert world.raw('n')['sync_merged_into'] == 'p'


def test_donor_ancestor_two_node_cycle_rejects(world, reads):
    _live_pair(world)
    _bridge(world, 'g1', 5, merged_into='n', nested=['g2'])
    _bridge(world, 'g2', 4, merged_into='n', nested=['g1'])
    world.raw('n')['sync_merged_from'] = ['g1', 'g2']
    before = deepcopy(world.store.rows)
    _assert_absorb_rejected_clean(world, reads, before)


def test_donor_ancestor_three_node_cycle_rejects(world, reads):
    _live_pair(world)
    _bridge(world, 'g1', 5, merged_into='n', nested=['g2'])
    _bridge(world, 'g2', 4, merged_into='n', nested=['g3'])
    _bridge(world, 'g3', 3, merged_into='n', nested=['g1'])
    world.raw('n')['sync_merged_from'] = ['g1', 'g2', 'g3']
    before = deepcopy(world.store.rows)
    _assert_absorb_rejected_clean(world, reads, before)


def test_sync_assign_into_smart_survivor_rejects_hidden_grand_donor(world, reads):
    _flattened_world(world)
    world.add('d', 20, 8, sync_content_revision=1)
    _bridge(world, 'g3', 19, merged_into='d', nested=['zz'], minutes=2)
    _bridge(world, 'zz', 18, merged_into='g3', minutes=2)
    world.raw('d')['sync_merged_from'] = ['g3']
    _seed_index(world, 'd')
    before = deepcopy(world.store.rows)
    reads.clear()
    with pytest.raises(SyncAssignmentConflict):
        _assign(world, _sync_chunk('wal-gd', 21, minutes=6), target_id='n')
    assert world.store.rows == before
    assert all(path != _path('zz') for _, path in reads)


def test_sync_assign_into_smart_survivor_rejects_existing_survivor_hidden_descendant(world, reads):
    _flattened_world(world)
    world.raw('g1')['sync_merged_from'] = ['hidden']
    _bridge(world, 'hidden', 3, merged_into='g1', minutes=2)
    world.add('d', 20, 8, sync_content_revision=1)
    _seed_index(world, 'd')
    before = deepcopy(world.store.rows)
    reads.clear()
    with pytest.raises(SyncAssignmentConflict):
        _assign(world, _sync_chunk('wal-sh', 21, minutes=6), target_id='n')
    assert world.store.rows == before
    assign_txns = {txn for txn, _ in reads}
    assert assign_txns
    assert all(not txn.has_written for txn in assign_txns)
    assert all(path != _path('hidden') for _, path in reads)


def test_sync_assign_into_smart_survivor_rejects_grand_donor_cycle(world):
    _flattened_world(world)
    world.add('d', 20, 8, sync_content_revision=1)
    _bridge(world, 'g3', 19, merged_into='d', nested=['g4'], minutes=2)
    _bridge(world, 'g4', 18, merged_into='d', nested=['g3'], minutes=2)
    world.raw('d')['sync_merged_from'] = ['g3', 'g4']
    _seed_index(world, 'd')
    before = deepcopy(world.store.rows)
    with pytest.raises(SyncAssignmentConflict):
        _assign(world, _sync_chunk('wal-gc', 21, minutes=6), target_id='n')
    assert world.store.rows == before

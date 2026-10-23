"""Ordinary sync absorbs leave multi-hop lineage; a smart-survivor flatten must accept it.

An ordinary (non-smart) sync absorb re-points only the rows it matched, and the
canonical's ``sync_merged_from`` is cumulative. When an earlier row later absorbs
a row that had itself absorbed others, the inherited ancestors still redirect to
the intermediate hop. Backfill chunks that land on a smart-merge survivor and
match such a row used to reject the whole assignment as
``ancestry_flatten_rejected`` after STT had already been paid for.
"""

from copy import deepcopy

import pytest

from config import conversation_smart_merge as config
from config import merge_ancestry
from tests.unit.test_conversation_smart_merge import UID, World
from tests.unit.test_conversation_smart_merge_flatten import (
    _assign,
    _decoded,
    _flattened_world,
    _segment_ids,
    _seed_index,
    _sync_chunk,
    _visible,
)
from utils.sync.assignment_errors import SyncAssignmentConflict


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'off')
    monkeypatch.delenv(config.SMART_MERGE_AUDIT_ENV, raising=False)
    monkeypatch.delenv(config.SMART_MERGE_FLATTEN_ENV, raising=False)
    return World(monkeypatch)


def _ordinary_chain(world):
    """Build e <- h <- g with real ordinary sync intakes (no smart state)."""
    world.add('h', 33, 2, sync_content_revision=1)
    world.add('g', 36, 2, sync_content_revision=1)
    _seed_index(world, 'h', 'g')
    result, _, _ = _assign(world, _sync_chunk('wal-hg', 34, minutes=3))
    assert result['id'] == 'h'
    assert world.raw('g')['sync_merged_into'] == 'h'
    world.add('e', 29, 2, sync_content_revision=1)
    _seed_index(world, 'e')
    result, _, _ = _assign(world, _sync_chunk('wal-eh', 30, minutes=4))
    assert result['id'] == 'e'
    # The ordinary path re-points only matched rows: g still redirects to h.
    assert world.raw('h')['sync_merged_into'] == 'e'
    assert world.raw('g')['sync_merged_into'] == 'h'
    assert sorted(_decoded(world, 'e')['sync_merged_from']) == ['g', 'h']


def test_ordinary_sync_absorbs_leave_a_multihop_chain(world):
    _ordinary_chain(world)


def test_backfill_into_smart_survivor_flattens_an_ordinary_multihop_donor(world):
    _flattened_world(world)
    _ordinary_chain(world)
    incoming = _sync_chunk('wal-bf', 24, minutes=7)
    result, created, _ = _assign(world, incoming, target_id='n')
    assert result['id'] == 'p' and not created
    for cid in ('e', 'h', 'g'):
        assert world.raw(cid)['sync_merged_into'] == 'p', cid
    assert sorted(_decoded(world, 'p')['sync_merged_from']) == ['e', 'g', 'g1', 'g2', 'h', 'n']
    assert _visible(world) == ['p']
    ids = _segment_ids(world, 'p')
    assert len(ids) == len(set(ids))


def test_chain_repair_off_restores_the_strict_rejection(world, monkeypatch):
    monkeypatch.setenv(config.SMART_MERGE_FLATTEN_CHAIN_REPAIR_ENV, 'off')
    _flattened_world(world)
    _ordinary_chain(world)
    before = deepcopy(world.store.rows)
    with pytest.raises(SyncAssignmentConflict) as exc_info:
        _assign(world, _sync_chunk('wal-bf', 24, minutes=7), target_id='n')
    assert exc_info.value.subtype == 'ancestry_flatten_rejected'
    assert world.store.rows == before


@pytest.mark.parametrize(('raw', 'enabled'), [(None, True), ('', True), ('on', True), ('off', False), ('typo', False)])
def test_chain_repair_flag_is_a_kill_switch(monkeypatch, raw, enabled):
    if raw is None:
        monkeypatch.delenv(config.SMART_MERGE_FLATTEN_CHAIN_REPAIR_ENV, raising=False)
    else:
        monkeypatch.setenv(config.SMART_MERGE_FLATTEN_CHAIN_REPAIR_ENV, raw)
    assert config.smart_merge_flatten_chain_repair_enabled() is enabled


# --------------------------------------------------------------------------- pure planner


def _tomb(merged_into, *, nested=(), revision=3, **extra):
    row = {
        'deleted': True,
        'discarded': True,
        'sync_merged_into': merged_into,
        'sync_content_revision': revision,
    }
    if nested:
        row['sync_merged_from'] = list(nested)
    row.update(extra)
    return row


def _plan(survivor_ancestry, donor_ancestry, rows, *, chain_repair=True):
    return merge_ancestry.flatten_updates(
        {'id': 'p', 'sync_merged_from': list(survivor_ancestry)},
        {'e': {'id': 'e', 'sync_merged_from': list(donor_ancestry)}},
        rows,
        user_managed=lambda row: bool(row.get('starred')),
        chain_repair=chain_repair,
    )


def test_donor_chain_inside_its_lineage_repoints_every_hop():
    rows = {'h': _tomb('e', nested=['g']), 'g': _tomb('h', sync_bridge_cleaned_revision=3)}
    reason, union, updates = _plan([], ['g', 'h'], rows)
    assert reason is None and union == ['e', 'g', 'h']
    assert updates == {
        'g': {'sync_merged_into': 'p', 'sync_content_revision': 4, 'sync_bridge_cleaned_revision': 4},
        'h': {'sync_merged_into': 'p', 'sync_content_revision': 4},
    }


def test_donor_chain_is_rejected_without_repair():
    rows = {'h': _tomb('e', nested=['g']), 'g': _tomb('h')}
    assert _plan([], ['g', 'h'], rows, chain_repair=False)[0] == merge_ancestry.INVALID


@pytest.mark.parametrize(
    'rows',
    [
        # A hop that leaves the donor's declared lineage.
        {'h': _tomb('elsewhere'), 'g': _tomb('h')},
        # A redirect cycle that never reaches the donor.
        {'h': _tomb('g'), 'g': _tomb('h')},
        # An intermediate hop that is not a tombstone.
        {'h': dict(_tomb('e'), deleted=False), 'g': _tomb('h')},
        # A hop carrying smart-merge state.
        {'h': _tomb('e'), 'g': _tomb('h', smart_merge={'role': 'donor', 'survivor_id': 'h'})},
    ],
)
def test_donor_chain_repair_still_rejects_broken_chains(rows):
    assert _plan([], ['g', 'h'], rows)[0] == merge_ancestry.INVALID


def test_user_managed_hop_still_refuses():
    rows = {'h': _tomb('e'), 'g': _tomb('h', starred=True)}
    assert _plan([], ['g', 'h'], rows)[0] == merge_ancestry.USER_MANAGED


def test_survivor_own_chain_is_repaired_and_direct_ancestors_untouched():
    rows = {'a': _tomb('p'), 'b': _tomb('a'), 'h': _tomb('e')}
    reason, union, updates = _plan(['a', 'b'], ['h'], rows)
    assert reason is None and union == ['a', 'b', 'e', 'h']
    assert sorted(updates) == ['b', 'h']
    assert updates['b']['sync_merged_into'] == 'p'


def test_survivor_own_chain_leaving_lineage_rejects():
    rows = {'a': _tomb('p'), 'b': _tomb('x'), 'h': _tomb('e')}
    assert _plan(['a', 'b'], ['h'], rows)[0] == merge_ancestry.INVALID


# --------------------------------------------------------------------------- bridge


def _defect(rows, lineage, source_id):
    from utils.sync.bridge import _bridge_source_defect

    return _bridge_source_defect(rows.get(source_id), 'p', lineage, rows.get)


def test_bridge_accepts_a_chain_inside_the_survivor_lineage():
    rows = {'e': _tomb('p'), 'h': _tomb('e'), 'g': _tomb('h')}
    assert [_defect(rows, ['e', 'g', 'h'], cid) for cid in ('e', 'g', 'h')] == [None, None, None]


def test_bridge_chain_kinds(monkeypatch):
    rows = {'e': _tomb('p'), 'h': _tomb('e'), 'g': _tomb('h'), 'x': _tomb('q'), 'c1': _tomb('c2'), 'c2': _tomb('c1')}
    assert _defect(rows, ['x'], 'x') == 'redirect_elsewhere'
    assert _defect(rows, ['c1', 'c2'], 'c1') == 'chain_broken'
    assert _defect(rows, ['g', 'h'], 'g') == 'chain_broken'  # e is outside the lineage
    monkeypatch.setenv(config.SMART_MERGE_FLATTEN_CHAIN_REPAIR_ENV, 'off')
    assert _defect(rows, ['e', 'g', 'h'], 'g') == 'chain'


@pytest.mark.parametrize(
    'bad',
    [
        {'discarded': False},
        {'sync_content_revision': 0},
        {'smart_merge': {'role': 'donor', 'survivor_id': 'h'}},
        {'starred': True},
        {'has_photos': True},
    ],
)
@pytest.mark.parametrize('where', ['source', 'hop'])
def test_bridge_chain_requires_the_planners_plain_tombstone(bad, where):
    # Finalize must never retract a chain row the flatten planner would refuse.
    rows = {'e': _tomb('p'), 'h': _tomb('e'), 'g': _tomb('h')}
    rows['g' if where == 'source' else 'h'].update(bad)
    assert _defect(rows, ['e', 'g', 'h'], 'g') == 'chain_broken'

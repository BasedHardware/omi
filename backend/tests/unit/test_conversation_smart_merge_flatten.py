"""Smart-merge ancestry flatten (CONVERSATION_SMART_MERGE_FLATTEN_ENABLED).

A live new-side donor that already absorbed sync-bridge tombstones may merge:
the absorb transaction re-points every inherited tombstone one hop at the
survivor, unions the ancestry under the fragment budget, and records a bounded
count on the donor marker and content-free audit. Flag off restores the legacy
eligibility and writes byte-for-byte.

All tests run the real absorb/assignment transactions against the shared
``World`` fixture (strict in-memory Firestore, production conversation codec,
faked Jev/processing seams). All text is synthetic.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import conversation_smart_merge as config
from config import merge_ancestry
from database import conversations as conversations_db
from database.legal_holds import DestructiveOperationInProgress
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
from tests.unit.test_conversation_smart_merge import T0, UID, World
from tests.unit.test_sync_lineage_dedupe_replay import prove
from utils import metrics
from utils.conversations import smart_merge
from utils.conversations.smart_merge_policy import absorb_payloads, fragment_of, user_managed
from utils.sync.assignment import assign_in_transaction
from utils.sync.assignment_errors import SyncAssignmentConflict, SyncAssignmentSuperseded
from utils.sync.recording_lineage import select_segment_targets


def _path(cid):
    return ('users', UID, 'conversations', cid)


def _audit_path(cid):
    return ('users', UID, 'smart_merge_audit', cid)


def _decoded(world, cid):
    return world.get(UID, cid)


def _rows_without_decision(world):
    rows = {}
    for cid in ('p', 'n', 'g1', 'g2', 'old', 'd'):
        if world.raw(cid) is None:
            continue
        row = _decoded(world, cid)
        row.pop('smart_merge_decision', None)
        rows[cid] = row
    return rows


def _absorb_attempts(world, reads):
    """Transactions that read both pair rows inside one attempt (the absorb)."""
    by_txn = {}
    for txn, path in reads:
        if path[:3] == _path('x')[:3]:
            by_txn.setdefault(txn, set()).add(path[-1])
    return [txn for txn, ids in by_txn.items() if 'p' in ids and 'n' in ids]


def _tombstone(world, cid, *, merged_into, revision=3, **extra):
    world.raw(cid).update(
        {
            'deleted': True,
            'discarded': True,
            'sync_merged_into': merged_into,
            'sync_content_revision': revision,
        }
    )
    world.raw(cid).update(extra)


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


def _setup_pair(world, ancestors=('g1', 'g2')):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    for gid in ancestors:
        world.add(gid, 5, 5)
        _tombstone(world, gid, merged_into='n')
    world.raw('n')['sync_merged_from'] = sorted(ancestors)
    world.raw('n')['sync_content_revision'] = 7
    world.raw('p')['sync_content_revision'] = 2


def _sync_chunk(cid, start_min, minutes=10, text=None):
    start = T0 + timedelta(minutes=start_min)
    return {
        'id': cid,
        'started_at': start,
        'finished_at': start + timedelta(minutes=minutes),
        'source': 'omi',
        'client_device_id': 'pendant-1',
        'discarded': False,
        'status': 'completed',
        'data_protection_level': 'enhanced',
        'transcript_segments': [
            {
                'id': f'{cid}-seg',
                'start': 0.0,
                'end': min(9.5, minutes * 60.0),
                'text': text or f'A synthetic {cid} line of captured speech.',
                'speaker_id': 0,
                'is_user': False,
            }
        ],
    }


def _assign(world, incoming, *, candidate_id=None, target_id=None):
    """The production intake transaction against the world's store and codec."""
    with world.store.lock:
        return assign_in_transaction(
            world.store.transaction(),
            world.store.collection('users').document(UID),
            incoming,
            candidate_id=candidate_id,
            target_id=target_id,
            decode=lambda raw: world.get(UID, raw['id']),
            encode=lambda row: conversations_db.encode_conversation_for_write(UID, row, 'enhanced'),
            invalidate=lambda payload: None,
        )


def _index_row(world, cid):
    """Sync-assignment day-bucket entries for a row (what a real intake wrote)."""
    row = _decoded(world, cid)
    return {key: row.get(key) for key in ('id', 'started_at', 'finished_at', 'source', 'client_device_id', 'is_locked')}


def _seed_index(world, *cids):
    day = T0.date().isoformat()
    key = ('users', UID, 'sync_assignment', day)
    doc = world.store.rows.setdefault(key, {'entries': []})
    doc['entries'] += [_index_row(world, cid) for cid in cids]


def _visible(world):
    return sorted(
        key[-1] for key, row in world.store.rows.items() if key[:3] == _path('x')[:3] and not row.get('deleted')
    )


def _segment_ids(world, cid):
    return [segment['id'] for segment in world.transcript(cid)]


# --------------------------------------------------------------------------- flag


@pytest.mark.parametrize('raw', ['', '   ', 'true', 'ON', '1', ' yes '])
def test_flatten_flag_on_values(monkeypatch, raw):
    monkeypatch.setenv(config.SMART_MERGE_FLATTEN_ENV, raw)
    assert config.smart_merge_flatten_enabled() is True


@pytest.mark.parametrize('raw', ['off', 'false', '0', 'of', 'bogus', 'disabled'])
def test_flatten_flag_off_values(monkeypatch, raw):
    monkeypatch.setenv(config.SMART_MERGE_FLATTEN_ENV, raw)
    assert config.smart_merge_flatten_enabled() is False


def test_flatten_flag_unset_is_on(monkeypatch):
    monkeypatch.delenv(config.SMART_MERGE_FLATTEN_ENV, raising=False)
    assert config.smart_merge_flatten_enabled() is True


# --------------------------------------------------------------------------- helper


def _survivor(ancestry=()):
    return {'id': 'p', 'sync_merged_from': list(ancestry)}


def _donor(ancestry):
    return {'id': 'n', 'sync_merged_from': list(ancestry)}


def _ancestor(merged_into='n', **extra):
    row = {
        'id': 'g',
        'deleted': True,
        'discarded': True,
        'sync_merged_into': merged_into,
        'sync_content_revision': 3,
    }
    row.update(extra)
    return row


def test_ancestry_ids_rejects_malformed_lists():
    for value in ('g1', 123, [''], ['a' * 129], ['has/slash'], [1]):
        reason, _ = merge_ancestry.ancestry_ids({'sync_merged_from': value})
        assert reason == merge_ancestry.INVALID, value
    reason, ids = merge_ancestry.ancestry_ids({'sync_merged_from': None})
    assert reason is None and ids == []


def test_ancestry_ids_dedupes_sorts_and_caps_before_reads():
    reason, ids = merge_ancestry.ancestry_ids({'sync_merged_from': ['b', 'a', 'b']})
    assert reason is None and ids == ['a', 'b']
    for raw in (['x'] * 12, [str(i) for i in range(12)]):
        reason, _ = merge_ancestry.ancestry_ids({'sync_merged_from': raw})
        assert reason == merge_ancestry.CAP, raw


def test_flatten_updates_happy_path_advances_closed_receipt():
    g = _ancestor(sync_bridge_cleaned_revision=3)
    reason, union, updates = merge_ancestry.flatten_updates(
        _survivor(), {'n': _donor(['g'])}, {'g': g}, user_managed=user_managed
    )
    assert reason is None and union == ['g', 'n']
    assert updates['g']['sync_merged_into'] == 'p'
    assert updates['g']['sync_content_revision'] == 4
    assert updates['g']['sync_bridge_cleaned_revision'] == 4


def test_flatten_updates_leaves_pending_receipt_open():
    reason, union, updates = merge_ancestry.flatten_updates(
        _survivor(), {'n': _donor(['g'])}, {'g': _ancestor()}, user_managed=user_managed
    )
    assert reason is None and 'sync_bridge_cleaned_revision' not in updates['g']


@pytest.mark.parametrize(
    'row',
    [
        None,
        _ancestor(deleted=False),
        _ancestor(discarded=False),
        _ancestor(merged_into='other'),
        _ancestor(sync_content_revision=0),
        _ancestor(sync_content_revision=-1),
        _ancestor(sync_content_revision=True),
        _ancestor(sync_content_revision='3'),
        _ancestor(sync_merged_from=['h']),
        _ancestor(smart_merge={'role': 'donor'}),
    ],
    ids=[
        'missing',
        'live',
        'not_discarded',
        'foreign_redirect',
        'zero_revision',
        'negative_revision',
        'bool_revision',
        'string_revision',
        'undeclared_descendant',
        'smart_merge_state',
    ],
)
def test_flatten_updates_rejects_each_invalid_ancestor(row):
    reason, union, updates = merge_ancestry.flatten_updates(
        _survivor(), {'n': _donor(['g'])}, {'g': row}, user_managed=user_managed
    )
    assert reason == merge_ancestry.INVALID and union == [] and updates == {}


@pytest.mark.parametrize(
    'field,value',
    [
        ('user_title', 'Mine'),
        ('starred', True),
        ('folder_user_set', True),
        ('sync_relevance_user_kept', True),
        ('has_photos', True),
        ('is_locked', True),
        ('manual_speaker_assignments', {'x': 1}),
        ('capture_group', 'g'),
        ('visibility', 'shared'),
        ('external_data', {'duplicate_capture_of': 'x'}),
    ],
)
def test_flatten_updates_rejects_every_user_managed_field(field, value):
    reason, union, updates = merge_ancestry.flatten_updates(
        _survivor(), {'n': _donor(['g'])}, {'g': _ancestor(**{field: value})}, user_managed=user_managed
    )
    assert reason == merge_ancestry.USER_MANAGED and updates == {}


def test_flatten_updates_rejects_survivor_cycle_and_donor_self_cycle():
    reason, _, _ = merge_ancestry.flatten_updates(
        _survivor(), {'n': _donor(['p'])}, {'p': _ancestor()}, user_managed=user_managed
    )
    assert reason == merge_ancestry.INVALID
    reason, _, _ = merge_ancestry.flatten_updates(_survivor(), {'n': _donor(['n'])}, {}, user_managed=user_managed)
    assert reason == merge_ancestry.INVALID


def test_flatten_updates_rejects_donor_overlap_with_survivor_ancestry():
    reason, _, _ = merge_ancestry.flatten_updates(
        _survivor(ancestry=['old']),
        {'n': _donor(['old', 'g'])},
        {'old': _ancestor(merged_into='p'), 'g': _ancestor()},
        user_managed=user_managed,
    )
    assert reason == merge_ancestry.INVALID


def test_flatten_updates_rejects_shared_ancestor_declared_by_two_donors():
    reason, _, _ = merge_ancestry.flatten_updates(
        _survivor(),
        {'n': _donor(['g']), 'd': _donor(['g'])},
        {'g': _ancestor()},
        user_managed=user_managed,
    )
    assert reason == merge_ancestry.INVALID


def test_flatten_updates_union_cap_boundary():
    ancestors = [f'g{i}' for i in range(10)]
    reason, union, updates = merge_ancestry.flatten_updates(
        _survivor(),
        {'n': _donor(ancestors)},
        {gid: _ancestor() for gid in ancestors},
        user_managed=user_managed,
    )
    assert reason is None and len(union) == 11 and len(updates) == 10
    reason, union, updates = merge_ancestry.flatten_updates(
        _survivor(ancestry=['h']),
        {'n': _donor(ancestors)},
        {gid: _ancestor() for gid in ancestors},
        user_managed=user_managed,
    )
    assert reason == merge_ancestry.CAP


def test_flatten_updates_retains_validated_survivor_ancestry_without_rewrite():
    reason, union, updates = merge_ancestry.flatten_updates(
        _survivor(ancestry=['old']),
        {'n': _donor(['g'])},
        {'old': _ancestor(merged_into='p'), 'g': _ancestor()},
        user_managed=user_managed,
    )
    assert reason is None and sorted(union) == ['g', 'n', 'old']
    assert sorted(updates) == ['g']


@pytest.mark.parametrize(
    'state',
    [
        {'role': 'survivor'},
        {'role': 'donor', 'survivor_id': 'other'},
        {'role': 'donor'},
    ],
    ids=['survivor_role', 'foreign_donor', 'missing_survivor'],
)
def test_flatten_updates_rejects_foreign_smart_state_on_existing_ancestor(state):
    reason, _, _ = merge_ancestry.flatten_updates(
        _survivor(ancestry=['old']),
        {'n': _donor(['g'])},
        {'old': _ancestor(merged_into='p', smart_merge=state), 'g': _ancestor()},
        user_managed=user_managed,
    )
    assert reason == merge_ancestry.INVALID


def test_flatten_updates_allows_smart_donor_row_already_pointing_at_survivor():
    reason, union, updates = merge_ancestry.flatten_updates(
        _survivor(ancestry=['old']),
        {'n': _donor(['g'])},
        {
            'old': _ancestor(merged_into='p', smart_merge={'role': 'donor', 'survivor_id': 'p'}),
            'g': _ancestor(),
        },
        user_managed=user_managed,
    )
    assert reason is None and sorted(union) == ['g', 'n', 'old']
    assert sorted(updates) == ['g']


def test_flatten_updates_accepts_declared_one_hop_descendants():
    donors = {'n': _donor(['g', 'h'])}
    rows = {'g': _ancestor(sync_merged_from=['h']), 'h': _ancestor()}
    reason, union, updates = merge_ancestry.flatten_updates(_survivor(), donors, rows, user_managed=user_managed)
    assert reason is None and sorted(union) == ['g', 'h', 'n']
    assert sorted(updates) == ['g', 'h']


def test_flatten_updates_rejects_descendant_redirected_elsewhere():
    donors = {'n': _donor(['g', 'h'])}
    rows = {'g': _ancestor(sync_merged_from=['h']), 'h': _ancestor(merged_into='other')}
    reason, _, _ = merge_ancestry.flatten_updates(_survivor(), donors, rows, user_managed=user_managed)
    assert reason == merge_ancestry.INVALID


# --------------------------------------------------------------------------- merge


def test_flatten_merge_repoints_ancestry_and_audits_count(world):
    _setup_pair(world)
    assert world.finish('n') is True
    survivor = world.raw('p')
    assert sorted(survivor['sync_merged_from']) == ['g1', 'g2', 'n']
    for gid in ('g1', 'g2'):
        assert world.raw(gid)['sync_merged_into'] == 'p'
        assert world.raw(gid)['sync_content_revision'] == 4
    assert world.raw('n')['sync_merged_into'] == 'p'
    assert world.raw('n')['deleted'] is True
    assert world.raw('n')['smart_merge']['flattened_ancestor_count'] == 2
    text = ' '.join(segment['text'] for segment in world.transcript('p'))
    assert 'g1' not in text and 'g2' not in text
    ids = _segment_ids(world, 'p')
    assert len(ids) == len(set(ids)) == 4
    audit = world.store.rows[_audit_path('n')]
    assert audit['flattened_ancestor_count'] == 2
    assert sorted(world.retracted) == ['g1', 'g2', 'n']


def test_absorb_writes_ancestor_updates_in_the_same_transaction(world):
    _setup_pair(world)
    assert world.finish('n') is True
    absorb = next(
        txn
        for txn in reversed(world.store.transactions)
        if {_path('p'), _path('n')} <= {path for path, _ in txn.updates}
    )
    written = {path[-1] for path, _ in absorb.updates}
    assert {'p', 'n', 'g1', 'g2'} <= written
    assert next(patch for path, patch in absorb.updates if path[-1] == 'g1')['sync_merged_into'] == 'p'


def test_flatten_replay_does_not_duplicate_cleanup(world):
    _setup_pair(world)
    assert world.finish('n') is True
    retracted, copied, processed = list(world.retracted), list(world.copied), list(world.processed)
    smart_merge.finish_absorb(UID, 'n', owner='job', resumed=True)
    assert world.retracted == retracted
    assert world.copied == copied
    assert world.processed == processed
    audits = [path for txn in world.store.transactions for path, _ in txn.sets if path == _audit_path('n')]
    assert audits == [_audit_path('n')]


def test_flatten_off_donor_with_ancestry_is_ineligible(world, reads):
    _setup_pair(world)
    before = _rows_without_decision(world)
    world.monkeypatch.setenv(config.SMART_MERGE_FLATTEN_ENV, 'off')
    assert world.finish('n') is False
    assert _rows_without_decision(world) == before
    assert not world.raw('n').get('deleted')
    assert not any(path[-1] in ('g1', 'g2') for _, path in reads)


def test_flatten_off_plain_pair_keeps_baseline_write_shape(world, reads):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.raw('n')['sync_content_revision'] = 7
    world.raw('p')['sync_content_revision'] = 2
    world.monkeypatch.setenv(config.SMART_MERGE_FLATTEN_ENV, 'off')
    assert world.finish('n') is True
    absorb = next(
        txn
        for txn in reversed(world.store.transactions)
        if {_path('p'), _path('n')} <= {path for path, _ in txn.updates}
    )
    donor_patch = next(patch for path, patch in absorb.updates if path[-1] == 'n')
    assert set(donor_patch) == {
        'deleted',
        'discarded',
        'sync_merged_into',
        'sync_content_revision',
        'smart_merge',
        'smart_merge_decision',
    }
    survivor_patch = next(patch for path, patch in absorb.updates if path[-1] == 'p')
    assert survivor_patch['sync_merged_from'] == ['n']
    absorb_reads = {path for txn, path in reads if txn is absorb}
    assert {path for path in absorb_reads if path[:3] == _path('x')[:3]} == {_path('p'), _path('n')}
    assert 'flattened_ancestor_count' not in world.raw('n')['smart_merge']
    assert 'flattened_ancestor_count' not in world.store.rows[_audit_path('n')]


def test_flatten_off_persisted_patches_equal_absorb_payloads_output(world, monkeypatch):
    """OFF writes exactly the unchanged absorb_payloads output (helper untouched vs origin/main).

    Encryption makes stored bytes random; this compares the decoded persisted
    patches — every field value, including transcript times, revisions, roles,
    fragments, and the donor decision — against what the baseline helper emits
    on the same decoded inputs, with ``merged_at`` and ``decision`` read back
    from the persisted marker so the comparison pins the values the code wrote.
    """
    monkeypatch.setenv(config.SMART_MERGE_FLATTEN_ENV, 'off')
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.raw('n')['sync_content_revision'] = 7
    world.raw('p')['sync_content_revision'] = 2
    survivor_in = deepcopy(world.get(UID, 'p'))
    donor_in = deepcopy(world.get(UID, 'n'))
    assert world.finish('n') is True
    absorb = next(
        txn
        for txn in reversed(world.store.transactions)
        if {_path('p'), _path('n')} <= {path for path, _ in txn.updates}
    )
    survivor_patch = next(patch for path, patch in absorb.updates if path[-1] == 'p')
    donor_patch = next(patch for path, patch in absorb.updates if path[-1] == 'n')
    expected_survivor, expected_donor = absorb_payloads(
        dict(survivor_in),
        survivor_in['transcript_segments'],
        dict(donor_in),
        donor_in['transcript_segments'],
        merged_at=world.raw('n')['smart_merge']['merged_at'],
        decision=world.raw('n')['smart_merge_decision'],
    )
    decoded_patch = dict(survivor_patch)
    decoded_patch['transcript_segments'] = conversations_db._decode_transcript_segments_strict(
        UID, survivor_patch['transcript_segments'], bool(survivor_patch.get('transcript_segments_compressed'))
    )
    decoded_patch.pop('transcript_segments_compressed', None)
    assert decoded_patch == expected_survivor
    assert donor_patch == expected_donor
    audit = world.store.rows[_audit_path('n')]
    assert 'flattened_ancestor_count' not in audit
    assert 'flattened_ancestor_count' not in world.raw('n')['smart_merge']


def test_committed_flatten_cleanup_finishes_after_flag_off(world):
    _setup_pair(world)
    world.retract_error = DestructiveOperationInProgress('gate busy')
    with pytest.raises(Exception):
        world.finish('n')
    assert world.raw('n')['sync_merged_into'] == 'p'
    assert world.raw('g1')['sync_merged_into'] == 'p'
    world.monkeypatch.setenv(config.SMART_MERGE_FLATTEN_ENV, 'off')
    world.retract_error = None
    smart_merge.finish_absorb(UID, 'n', owner='job', resumed=True)
    assert sorted(world.retracted) == ['g1', 'g2', 'n']
    for gid in ('g1', 'g2'):
        assert world.raw(gid)['sync_bridge_cleaned_revision'] == 4


@pytest.mark.parametrize('state', [{'role': 'survivor', 'revision': 1}, {'role': 'donor', 'survivor_id': 'p'}])
def test_smart_state_new_side_with_ancestry_still_refused(world, state):
    _setup_pair(world)
    world.raw('n')['smart_merge'] = dict(state)
    before = _rows_without_decision(world)
    assert world.finish('n') is False
    assert _rows_without_decision(world) == before


# --------------------------------------------------------------------------- rejection fences


_REJECT_MUTATIONS = {
    'missing': lambda world: world.store.rows.pop(_path('g1')),
    'foreign_redirect': lambda world: world.raw('g1').update(sync_merged_into='other'),
    'curated': lambda world: world.raw('g1').update(user_title='Mine'),
    'smart_state': lambda world: world.raw('g1').update(smart_merge={'role': 'donor', 'survivor_id': 'x'}),
    'nested_chain': lambda world: world.raw('g1').update(sync_merged_from=['zz']),
    'donor_self_cycle': lambda world: world.raw('n').update(sync_merged_from=['n', 'g1', 'g2']),
    'survivor_overlap': lambda world: (
        world.raw('n').update(sync_merged_from=['g1', 'g2', 'old']),
        _tombstone(world, 'old', merged_into='p'),
        world.raw('p').update(sync_merged_from=['old']),
    ),
}


@pytest.mark.parametrize('case', sorted(_REJECT_MUTATIONS))
def test_rejected_flatten_absorb_writes_nothing(world, reads, case):
    _setup_pair(world)
    if case == 'survivor_overlap':
        world.add('old', 3, 2)
    _REJECT_MUTATIONS[case](world)
    before = _rows_without_decision(world)
    assert world.finish('n') is False
    assert _rows_without_decision(world) == before
    absorbs = _absorb_attempts(world, reads)
    assert absorbs
    assert all(not txn.has_written for txn in absorbs)


def test_stale_sync_revision_fences_the_absorb(world, reads):
    """A real stale snapshot: a competing sync write lands between decide and commit."""
    _setup_pair(world)

    def competing_append():
        world.raw('n')['sync_content_revision'] = 9

    world.on_ask = competing_append
    assert world.finish('n') is False
    assert world.raw('n')['sync_content_revision'] == 9
    assert not world.raw('n').get('deleted')
    assert not world.raw('p').get('sync_merged_from')
    absorbs = _absorb_attempts(world, reads)
    assert absorbs and all(not txn.has_written for txn in absorbs)
    # Replaying the job re-plans against the newer revision and converges.
    assert world.finish('n') is True
    assert world.raw('n')['sync_merged_into'] == 'p'


def test_union_over_budget_rejects_before_ancestor_reads(world, reads):
    _setup_pair(world, ancestors=tuple(f'g{i}' for i in range(12)))
    assert world.finish('n') is False
    absorbs = _absorb_attempts(world, reads)
    assert absorbs and all(not txn.has_written for txn in absorbs)
    assert not any(path[:3] == _path('x')[:3] and path[-1].startswith('g') for _, path in reads)


def test_flattened_ancestor_count_is_bounded_in_audit(world):
    _setup_pair(world)
    assert world.finish('n') is True
    audit = world.store.rows[_audit_path('n')]
    assert 0 <= audit['flattened_ancestor_count'] <= merge_ancestry.MAX_UNION_ANCESTORS


# --------------------------------------------------------------------------- telemetry


def _flatten_labels(monkeypatch):
    from utils import metrics

    seen = []
    monkeypatch.setattr(
        metrics.OMI_CONVERSATION_SMART_MERGE_FLATTEN_TOTAL,
        'labels',
        lambda **labels: SimpleNamespace(inc=lambda amount=1: seen.append(labels)),
    )
    return seen


def test_flatten_counter_labels_absorbed(world, monkeypatch):
    seen = _flatten_labels(monkeypatch)
    _setup_pair(world)
    assert world.finish('n') is True
    assert seen == [{'outcome': 'absorbed', 'reason': 'none'}]


@pytest.mark.parametrize(
    'mutate,expected',
    [
        (lambda world: world.raw('g1').update(user_title='curated'), 'flatten_ancestor_user_managed'),
        (lambda world: world.raw('g1').update(sync_merged_into='other'), 'flatten_ancestor_invalid'),
    ],
)
def test_flatten_counter_labels_bounded_rejection(world, monkeypatch, mutate, expected):
    seen = _flatten_labels(monkeypatch)
    _setup_pair(world)
    mutate(world)
    assert world.finish('n') is False
    assert seen == [{'outcome': 'rejected', 'reason': expected}]


def test_metrics_smart_merge_survives_module_reload():
    import importlib

    from utils import metrics, metrics_smart_merge

    before = metrics_smart_merge.OMI_CONVERSATION_SMART_MERGE_FLATTEN_TOTAL
    reloaded = importlib.reload(metrics_smart_merge)
    assert reloaded.OMI_CONVERSATION_SMART_MERGE_FLATTEN_TOTAL is before
    reloaded.record_smart_merge_flatten('absorbed', 'none')
    assert metrics.OMI_CONVERSATION_SMART_MERGE_FLATTEN_TOTAL is before


# --------------------------------------------------------------------------- late sync assignment


def _flattened_world(world):
    _setup_pair(world)
    assert world.finish('n') is True
    return world


def test_late_upload_targeting_donor_resolves_to_survivor(world):
    _flattened_world(world)
    result, created, _ = _assign(world, _sync_chunk('wal-1', 26), target_id='n')
    assert result['id'] == 'p' and not created
    assert _visible(world) == ['p']


def test_late_upload_targeting_flattened_ancestor_resolves_to_survivor(world):
    _flattened_world(world)
    result, created, _ = _assign(world, _sync_chunk('wal-2', 26), target_id='g1')
    assert result['id'] == 'p' and not created


def test_late_upload_to_deleted_survivor_supersedes_without_new_row(world):
    _flattened_world(world)
    world.raw('p')['deleted'] = True
    before = deepcopy(world.store.rows)
    with pytest.raises(SyncAssignmentSuperseded):
        _assign(world, _sync_chunk('wal-3', 26), target_id='n')
    assert world.store.rows == before


def test_late_upload_to_discarded_survivor_supersedes_without_new_row(world):
    _flattened_world(world)
    world.raw('p')['discarded'] = True
    before = deepcopy(world.store.rows)
    with pytest.raises(SyncAssignmentSuperseded):
        _assign(world, _sync_chunk('wal-3b', 26), target_id='g1')
    assert world.store.rows == before


def test_two_hop_explicit_target_fails_closed(world):
    _flattened_world(world)
    world.raw('g1')['sync_merged_into'] = 'n'
    before = deepcopy(world.store.rows)
    with pytest.raises(SyncAssignmentConflict):
        _assign(world, _sync_chunk('wal-4', 26), target_id='g1')
    assert world.store.rows == before


def test_two_hop_own_id_retry_fails_closed(world, reads):
    _flattened_world(world)
    world.raw('g1')['sync_merged_into'] = 'n'
    before = deepcopy(world.store.rows)
    reads.clear()
    with pytest.raises(SyncAssignmentConflict):
        _assign(world, _sync_chunk('g1', 26))
    assert world.store.rows == before
    assert _path('p') not in [path for _, path in reads]


def test_smart_donor_tombstone_without_redirect_conflicts(world):
    _flattened_world(world)
    del world.raw('n')['sync_merged_into']
    before = deepcopy(world.store.rows)
    with pytest.raises(SyncAssignmentConflict):
        _assign(world, _sync_chunk('wal-5', 26), target_id='n')
    assert world.store.rows == before


def test_off_keeps_sync_donor_temporal_fallback(world):
    world.monkeypatch.setenv(config.SMART_MERGE_FLATTEN_ENV, 'off')
    world.add('d', 0, 10)
    _tombstone(world, 'd', merged_into='p')
    result, created, _ = _assign(world, _sync_chunk('wal-6', 26), target_id='d')
    assert result['id'] != 'p'


# --------------------------------------------------------------------------- both orderings


def test_sync_absorb_then_smart_merge_flattens_one_hop(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10, sync_content_revision=2)
    world.add('g', 14, 2, sync_content_revision=1)
    _seed_index(world, 'n', 'g')
    start_ids = {seg['id'] for cid in ('p', 'n', 'g') for seg in world.transcript(cid)}
    result, _, _ = _assign(world, _sync_chunk('wal-7', 15, minutes=2), target_id='n')
    assert result['id'] == 'n'
    assert world.raw('g')['sync_merged_into'] == 'n'
    assert _decoded(world, 'n')['sync_merged_from'] == ['g']
    assert world.finish('n') is True
    assert _visible(world) == ['p']
    assert world.raw('n')['sync_merged_into'] == 'p'
    assert world.raw('g')['sync_merged_into'] == 'p'
    ids = _segment_ids(world, 'p')
    expected = start_ids | {'wal-7-seg'}
    assert set(ids) == expected
    assert len(ids) == len(expected)


def test_smart_merge_then_sync_absorb_flattens_new_donor_ancestry(world):
    _flattened_world(world)
    world.add('d', 20, 8, sync_content_revision=1)
    world.add('g3', 19, 2)
    _tombstone(world, 'g3', merged_into='d')
    world.raw('d')['sync_merged_from'] = ['g3']
    _seed_index(world, 'd')
    incoming = _sync_chunk('wal-8', 21, minutes=6)
    result, created, _ = _assign(world, incoming, target_id='n')
    assert result['id'] == 'p' and not created
    assert world.raw('d')['sync_merged_into'] == 'p'
    assert world.raw('g3')['sync_merged_into'] == 'p'
    assert sorted(_decoded(world, 'p')['sync_merged_from']) == ['d', 'g1', 'g2', 'g3', 'n']
    ids = _segment_ids(world, 'p')
    assert len(ids) == len(set(ids))
    segment_count = len(ids)
    prove(incoming, world.raw('p'))
    result2, _, survivors = _assign(world, incoming, target_id='n')
    assert result2['id'] == 'p' and len(survivors) == len(incoming['transcript_segments'])
    assert len(_segment_ids(world, 'p')) == segment_count + len(survivors)
    assert _visible(world) == ['p']


def test_invalid_grand_donor_blocks_the_whole_assignment(world):
    _flattened_world(world)
    world.add('d', 20, 8, sync_content_revision=1)
    world.raw('d')['sync_merged_from'] = ['missing-ancestor']
    _seed_index(world, 'd')
    before = deepcopy(world.store.rows)
    with pytest.raises(SyncAssignmentConflict):
        _assign(world, _sync_chunk('wal-9', 21, minutes=6), target_id='n')
    assert world.store.rows == before


def test_size_rollover_abandons_the_flatten_plan_without_ancestor_writes(world, monkeypatch):
    from utils.sync import assignment

    _flattened_world(world)
    world.add('d', 24, 8, sync_content_revision=1)
    world.add('g3', 23, 2)
    _tombstone(world, 'g3', merged_into='d')
    world.raw('d')['sync_merged_from'] = ['g3']
    _seed_index(world, 'd')
    before_p = deepcopy(world.raw('p'))
    real_estimate = assignment._stored_document_bytes

    def estimate(reference, payload, current, invalidate):
        if reference.path[-1] == 'p':
            return assignment.SYNC_CONVERSATION_BYTE_BUDGET + 1
        return real_estimate(reference, payload, current, invalidate)

    monkeypatch.setattr(assignment, '_stored_document_bytes', estimate)
    result, created, _ = _assign(world, _sync_chunk('wal-r', 26, minutes=2), target_id='n')
    assert result['id'] == 'd' and not created
    assert world.raw('p') == before_p
    assert world.raw('g3')['sync_merged_into'] == 'd'
    assert _decoded(world, 'd')['sync_merged_from'] == ['g3']
    assert 'wal-r-seg' in _segment_ids(world, 'd')
    assert _visible(world) == ['d', 'p']


def test_over_cap_sync_donor_ancestry_conflicts_before_grand_reads(world, reads):
    _flattened_world(world)
    world.add('d', 20, 8, sync_content_revision=1)
    world.raw('d')['sync_merged_from'] = [f'zz{i}' for i in range(12)]
    _seed_index(world, 'd')
    before = deepcopy(world.store.rows)
    reads.clear()
    with pytest.raises(SyncAssignmentConflict):
        _assign(world, _sync_chunk('wal-9b', 21, minutes=6), target_id='n')
    assert world.store.rows == before
    assert not any(path[-1].startswith('zz') for _, path in reads)


@pytest.mark.parametrize('bad', [[{'a': 1}], 'notalist', 42], ids=['unhashable', 'non_list', 'non_string'])
def test_malformed_sync_donor_ancestry_conflicts_without_typeerror(world, bad):
    _flattened_world(world)
    world.add('d', 20, 8, sync_content_revision=1)
    world.raw('d')['sync_merged_from'] = bad
    _seed_index(world, 'd')
    before = deepcopy(world.store.rows)
    with pytest.raises(SyncAssignmentConflict):
        _assign(world, _sync_chunk('wal-9c', 21, minutes=6), target_id='n')
    assert world.store.rows == before


def test_ordinary_sync_merge_keeps_no_flatten_cap(world):
    """A normal sync intake with many fragments stays under the old behavior."""
    for i in range(12):
        world.add(f'f{i}', 0, 10, sync_content_revision=1)
    _seed_index(world, *(f'f{i}' for i in range(12)))
    result, created, _ = _assign(world, _sync_chunk('wal-10', 2, minutes=6), target_id='f0')
    assert not created
    assert len(result['sync_merged_from']) == 11
    assert _visible(world) == [result['id']]


# --------------------------------------------------------------------------- lineage


def test_lineage_donor_only_match_returns_donor_then_redirects(world):
    _setup_pair(world)
    world.raw('n')['external_data'] = {'recording_origin_id': 'origin-1'}
    assert world.finish('n') is True
    rows = [_decoded(world, 'n'), _decoded(world, 'p')]
    start = (T0 + timedelta(minutes=15)).timestamp()
    plan = select_segment_targets(
        rows,
        'origin-1',
        {'seg-1': (start, start + 5.0)},
        stamped_target=None,
        source='omi',
        client_device_id='pendant-1',
        is_locked=False,
    )
    assert plan.targets['seg-1'] == 'n'
    incoming = _sync_chunk('seg-1', 15)
    result, created, _ = _assign(world, incoming, target_id=plan.targets['seg-1'])
    assert result['id'] == 'p' and not created


# --------------------------------------------------------------------------- cleanup tasks


def test_flatten_cleanup_transfers_donor_and_ancestor_tasks(world, monkeypatch):
    from utils.conversations import action_item_refresh as flow
    from utils.conversations import process_conversation as pc
    from utils.conversations.processing_trigger import ProcessingTrigger

    monkeypatch.setenv('ACTION_ITEM_REFRESH_PRESERVE_ENABLED', 'true')
    tasks = ('users', UID, 'action_items')
    donor_task = {
        'description': 'Call vendor',
        'conversation_id': 'n',
        'completed': False,
        'exported': True,
        'edited': True,
        'provenance': [{'kind': 'conversation', 'id': 'n'}],
    }
    grand_task = {
        'description': 'Grand task',
        'conversation_id': 'g1',
        'completed': True,
        'exported': True,
        'edited': True,
    }
    world.store.rows[(*tasks, 'n-task')] = deepcopy(donor_task)
    world.store.rows[(*tasks, 'g-task')] = deepcopy(grand_task)

    def real_retract(uid, cid):
        world.retract(uid, cid)
        residual = [
            key for key, row in world.store.rows.items() if key[:3] == tasks and row.get('conversation_id') == cid
        ]
        for key in residual:
            del world.store.rows[key]

    monkeypatch.setattr(smart_merge, 'retract_sync_bridge_source', real_retract)
    monkeypatch.setattr(pc.conversation_capture, 'canonical_conversation_fields', lambda *a: {})
    monkeypatch.setattr(pc, 'upsert_action_item_vectors_batch', lambda *a: None)
    queue, external = [], []
    monkeypatch.setattr(flow, 'submit_with_context', lambda executor, fn, *args: queue.append(lambda: fn(*args)))

    async def export(uid, rows):
        for row in rows:
            external.append(row['id'])
            world.store.rows[(*tasks, row['id'])]['exported'] = True

    monkeypatch.setattr(flow, 'auto_sync_action_items_batch', export)

    def write(trigger):
        row = world.get(UID, 'p')
        items = [
            SimpleNamespace(
                description=text,
                completed=False,
                created_at=T0,
                updated_at=T0,
                due_at=None,
                completed_at=None,
            )
            for text in ['Call vendor', 'Grand task', 'Book room']
        ]
        conversation = SimpleNamespace(
            id='p',
            is_locked=False,
            sync_content_revision=row['sync_content_revision'],
            structured=SimpleNamespace(action_items=items),
        )
        pc._write_action_items(UID, conversation, trigger)
        while queue:
            queue.pop(0)()

    def process(*args, **kwargs):
        result = world.process(*args, **kwargs)
        write(ProcessingTrigger.SMART_MERGE)
        return result

    monkeypatch.setattr(smart_merge, 'process_conversation', process)
    _setup_pair(world)
    assert world.finish('n') is True
    assert world.store.rows[(*tasks, 'n-task')] == {**donor_task, 'conversation_id': 'p'}
    assert world.store.rows[(*tasks, 'g-task')] == {**grand_task, 'conversation_id': 'p'}
    assert sorted(world.retracted) == ['g1', 'g2', 'n']
    assert not any(
        row.get('conversation_id') in ('n', 'g1', 'g2') for key, row in world.store.rows.items() if key[:3] == tasks
    )
    fresh = [key for key, row in world.store.rows.items() if key[:3] == tasks and row.get('description') == 'Book room']
    assert len(fresh) == 1
    assert external == [fresh[0][-1]]
    assert world.store.rows[fresh[0]]['exported'] is True
    exports, snapshot = list(external), deepcopy(world.store.rows[(*tasks, 'n-task')])
    smart_merge.finish_absorb(UID, 'n', owner='job', resumed=True)
    assert world.store.rows[(*tasks, 'n-task')] == snapshot
    assert world.store.rows[(*tasks, 'g-task')] == {**grand_task, 'conversation_id': 'p'}
    assert external == exports
    assert world.processed and world.processed[-1][0] == 'p'


def test_flatten_cleanup_missing_source_raises_bounded_incomplete(world):
    _setup_pair(world)
    assert world.finish('n') is True
    del world.store.rows[_path('g1')]
    with pytest.raises(smart_merge.SmartMergeIncomplete) as error:
        smart_merge.finish_absorb(UID, 'n', owner='job', resumed=True)
    assert error.value.args[0] == 'flatten_cleanup_source_invalid'


def test_flatten_cleanup_terminates_with_deleted_survivor(world):
    _setup_pair(world)
    assert world.finish('n') is True
    world.raw('p')['deleted'] = True
    world.retracted.clear()
    smart_merge.finish_absorb(UID, 'n', owner='job', resumed=True)
    assert world.retracted == []


# --------------------------------------------------------------------------- shared audio dedup


def test_flatten_cleanup_copies_donor_and_ancestor_audio_once(world, monkeypatch):
    """Flattened cleanup copies each source's audio; absolute filenames dedupe objects."""
    from contextlib import nullcontext

    from utils.conversations import merge_conversations

    blobs = {}
    copied_paths = []

    class _Blob:
        def __init__(self, name):
            self.name = name

    class _Bucket:
        def blob(self, name):
            return _Blob(name)

        def copy_blob(self, source_blob, bucket, new_path):
            copied_paths.append(new_path)
            blobs[new_path] = True

        def list_blobs(self, prefix=''):
            return [_Blob(name) for name in list(blobs) if name.startswith(prefix)]

    class _AudioFile:
        def __init__(self, path, uid, cid):
            self._path = path
            self._ts = path.rsplit('/', 1)[-1].removesuffix('.bin')
            self._uid = uid
            self._cid = cid

        def dict(self):
            return {
                'id': f'af-{self._ts}',
                'uid': self._uid,
                'conversation_id': self._cid,
                'path': self._path,
                'chunk_timestamps': [float(self._ts)],
                'duration': 1.0,
                'created_at': T0,
            }

    chunk_map = {
        'n': ('chunks/%s/n/100.0.bin', 'chunks/%s/n/200.0.bin'),
        'g1': ('chunks/%s/g1/100.0.bin',),
        'g2': ('chunks/%s/g2/300.0.bin',),
    }
    monkeypatch.setattr(merge_conversations, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda n: _Bucket()))
    monkeypatch.setattr(merge_conversations, 'owner_storage_write_gate', lambda uid, bucket=None: nullcontext())
    monkeypatch.setattr(
        merge_conversations,
        'list_audio_chunks',
        lambda uid, cid: [
            {'path': path % uid, 'timestamp': float(path.rsplit('/', 1)[-1].removesuffix('.bin'))}
            for path in chunk_map.get(cid, ())
        ],
    )

    def create_files(uid, cid):
        return [_AudioFile(name, uid, cid) for name in sorted(blobs) if name.startswith(f'chunks/{uid}/{cid}/')]

    monkeypatch.setattr(conversations_db, 'create_audio_files_from_chunks', create_files)
    monkeypatch.setattr(
        conversations_db,
        'update_conversation',
        lambda uid, cid, payload: world.raw(cid).update(payload) or True,
    )
    monkeypatch.setattr(smart_merge, 'copy_sync_bridge_audio', merge_conversations.copy_sync_bridge_audio)
    _setup_pair(world)
    for cid in ('p', 'n', 'g1', 'g2'):
        world.raw(cid)['private_cloud_sync_enabled'] = True
    # The donor carries the already-copied ancestor audio under the same absolute
    # filename; g1's chunk and n's first chunk are the same capture.
    assert world.finish('n') is True
    assert set(blobs) == {
        f'chunks/{UID}/p/100.0.bin',
        f'chunks/{UID}/p/200.0.bin',
        f'chunks/{UID}/p/300.0.bin',
    }
    assert sorted(blobs) == sorted(set(copied_paths))
    refs = world.raw('p')['audio_files']
    assert {ref['path'] for ref in refs} == set(blobs)
    copied, files = list(copied_paths), deepcopy(refs)
    smart_merge.finish_absorb(UID, 'n', owner='job', resumed=True)
    assert copied_paths == copied
    assert world.raw('p')['audio_files'] == files


@pytest.fixture(params=['span_cap', 'segment_cap', 'fragment_cap'])
def capped_pair(request, world):
    _setup_pair(world)
    if request.param == 'span_cap':
        world.add('p', 0, 170)
        world.add('n', 175, 10)
        world.raw('n')['sync_merged_from'] = ['g1', 'g2']
        world.raw('n')['sync_content_revision'] = 7
        world.raw('p')['sync_content_revision'] = 2
    elif request.param == 'segment_cap':
        row = _decoded(world, 'p')
        segments = row['transcript_segments']
        row['transcript_segments'] = [
            dict(segments[i % len(segments)], id=f'p-many-{i}', text='synthetic') for i in range(3999)
        ]
        world.store.rows[_path('p')] = conversations_db.encode_conversation_for_write(UID, row, 'enhanced')
    else:
        entry = fragment_of(_decoded(world, 'p')).as_ledger_entry()
        world.raw('p')['smart_merge'] = {
            'role': 'survivor',
            'revision': 11,
            'refreshed_revision': 11,
            'fragments': [dict(entry, id=f'f{i}') for i in range(11)] + [entry],
        }
    return SimpleNamespace(world=world, expected=request.param, snapshot=deepcopy(world.store.rows))


def test_default_caps_refuse_a_flatten_eligible_pair(capped_pair, monkeypatch):
    world = capped_pair.world
    seen = []
    monkeypatch.setattr(
        metrics.CONVERSATION_SMART_MERGE_DECISION_TOTAL,
        'labels',
        lambda **labels: SimpleNamespace(inc=lambda amount=1: seen.append(labels)),
    )
    assert world.finish('n') is False
    assert world.jev_calls == []
    assert world.raw('n').get('smart_merge_decision') is None
    assert len(seen) == 1
    assert {key: seen[0][key] for key in ('mode', 'decision', 'reason')} == {
        'mode': 'merge',
        'decision': 'skip',
        'reason': capped_pair.expected,
    }
    assert world.store.rows == capped_pair.snapshot
    for gid in ('g1', 'g2'):
        assert world.raw(gid)['sync_merged_into'] == 'n'
    assert not world.raw('n').get('deleted')
    assert 'sync_merged_into' not in world.raw('n')


# --------------------------------------------------------------------------- privacy delete


def test_flattened_lineage_delete_purges_every_source(world, monkeypatch):
    from tests.unit.test_delete_conversation_cascade import _FakeFirestore
    from utils.conversations import merge_conversations
    from utils.other import storage
    import database.action_items as action_items_db
    import database.conversations as conv_db

    _setup_pair(world)
    assert world.finish('n') is True

    store = _FakeFirestore()
    blobs = {f'chunks/{UID}/p/{ts}.bin': True for ts in (100.0, 200.0)} | {
        f'chunks/{UID}/{cid}/{ts}.bin': True for cid in ('n', 'g1', 'g2') for ts in (100.0,)
    }

    class _Blob:
        def __init__(self, name):
            self.name = name

        def delete(self):
            blobs.pop(self.name, None)

    class _Bucket:
        def list_blobs(self, prefix=''):
            return [_Blob(name) for name in list(blobs) if name.startswith(prefix)]

    for cid in ('p', 'n', 'g1', 'g2'):
        doc = store.collection('users').document(UID).collection('conversations').document(cid)
        doc.data = {
            'id': cid,
            'sync_merged_from': list(_decoded(world, 'p')['sync_merged_from']) if cid == 'p' else [],
            'audio_files': [{'path': f'chunks/{UID}/{cid}/100.0.bin'}],
        }
        doc.collection('photos').document('ph').data = {'url': 'synthetic'}
        doc.collection('deepgram_streaming').document('seg').data = {'text': 'synthetic'}

    memory_map = {f'{cid}-mem': {'conversation_id': cid, 'text': 'synthetic'} for cid in ('p', 'n', 'g1', 'g2')}
    task_map = {
        f'{cid}-task': {'id': f'{cid}-task', 'conversation_id': cid, 'description': 'synthetic'}
        for cid in ('p', 'n', 'g1', 'g2')
    }

    class FakeMemoryService:
        def __init__(self, db_client=None):
            pass

        def retract_conversation_memories(self, uid, cid, **kwargs):
            for key in [key for key, row in memory_map.items() if row['conversation_id'] == cid]:
                del memory_map[key]

    calls = {'vector': [], 'index': [], 'survivor': []}
    monkeypatch.setattr(merge_conversations, 'firestore_db', store)
    monkeypatch.setattr(merge_conversations, 'MemoryService', FakeMemoryService)
    monkeypatch.setattr(merge_conversations, 'retraction_can_be_skipped', lambda *a, **k: False)
    monkeypatch.setattr(merge_conversations, 'delete_vector', lambda uid, cid: calls['vector'].append(cid))
    monkeypatch.setattr(merge_conversations, '_cancel_open_dated_task_reminders', lambda uid, items: None)
    monkeypatch.setattr(
        merge_conversations, 'record_survivor_deleted', lambda uid, cid, row: calls['survivor'].append(cid)
    )
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda n: _Bucket()))
    monkeypatch.setattr(
        action_items_db,
        'get_action_items_by_conversation',
        lambda uid, cid: [row for row in task_map.values() if row['conversation_id'] == cid],
    )
    monkeypatch.setattr(
        action_items_db,
        'delete_action_items_for_conversation',
        lambda uid, cid: [
            task_map.pop(key) for key in [key for key, row in task_map.items() if row['conversation_id'] == cid]
        ],
    )
    monkeypatch.setattr(conv_db, 'db', store)
    monkeypatch.setattr(conv_db, 'leave_capture_group', lambda *a, **k: None)
    monkeypatch.setattr(conv_db, '_delete_conversation_search_index', lambda uid, cid: calls['index'].append(cid))
    monkeypatch.setattr(
        conv_db,
        'get_conversation',
        lambda uid, cid, **k: (
            dict(
                store.collection('users').document(uid).collection('conversations').document(cid).to_dict(),
                id=cid,
            )
            if store.collection('users').document(uid).collection('conversations').document(cid).exists
            else None
        ),
    )

    merge_conversations._delete_conversation_and_related_data(UID, 'p')

    deleted = set(store.deleted)
    for cid in ('p', 'n', 'g1', 'g2'):
        assert f'users/{UID}/conversations/{cid}' in deleted
        assert f'users/{UID}/conversations/{cid}/photos/ph' in deleted
        assert f'users/{UID}/conversations/{cid}/deepgram_streaming/seg' in deleted
        assert cid in calls['vector']
    assert calls['survivor'] == ['p']
    assert not memory_map
    assert not task_map
    assert not blobs


def _ordinary_chain(world):
    world.add('p', 0, 10, sync_content_revision=2)
    world.add('n', 15, 10)
    world.add('g1', 5, 2)
    _tombstone(world, 'n', merged_into='p')
    _tombstone(world, 'g1', merged_into='n')
    world.raw('n')['sync_merged_from'] = ['g1']
    world.raw('p')['sync_merged_from'] = ['n', 'g1']


@pytest.mark.parametrize('discarded', [False, True])
def test_ordinary_retry_follows_a_multihop_chain(world, discarded):
    _ordinary_chain(world)
    world.raw('p')['discarded'] = discarded
    result, created, _ = _assign(world, _sync_chunk('g1', 5, minutes=1))
    assert result['id'] == 'p'
    assert created is False
    assert world.raw('p').get('discarded') is False
    assert not world.raw('p').get('deleted')
    for cid, merged_into in (('g1', 'n'), ('n', 'p')):
        assert world.raw(cid)['deleted']
        assert world.raw(cid)['sync_merged_into'] == merged_into
    ids = [segment['id'] for segment in world.transcript('p')]
    assert len(ids) == len(set(ids))


def test_ordinary_target_hint_falls_back_without_chain_checks(world):
    _ordinary_chain(world)
    result, created, _ = _assign(world, _sync_chunk('wal-legacy', 60, minutes=1), target_id='g1')
    assert result['id'] == 'wal-legacy'
    assert created is True
    assert world.raw('g1')['sync_merged_into'] == 'n'
    assert world.raw('n')['sync_merged_into'] == 'p'

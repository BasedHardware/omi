"""Sync/live admission through the production assignment transaction."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import chunk, conversations
from utils.sync.assignment import assign_in_transaction
from utils.sync.live_overlap import choose_live_overlap, live_overlap_enabled
from utils.sync.assignment_errors import SyncAssignmentSuperseded


@pytest.fixture(scope='module', autouse=True)
def dependencies():
    from database import conversations as db


@pytest.fixture(autouse=True)
def merge_mode(monkeypatch):
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'off')
    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'off')
    monkeypatch.setenv('SYNC_LIVE_OVERLAP_ENABLED', 'true')


def live_row(status='completed'):
    row = chunk('live', 1000)
    row.update(has_content=True, capture_evidence={'origin': 'live'}, status=status, data_protection_level='standard')
    return row


def assign(store, incoming, candidates=('live',), **kwargs):
    return assign_in_transaction(
        store.transaction(),
        store.collection('users').document('u'),
        incoming,
        live_candidate_ids=candidates,
        decode=deepcopy,
        encode=deepcopy,
        invalidate=lambda payload: None,
        **kwargs,
    )


def seeded(row=None):
    store = StrictFirestore()
    row = row or live_row()
    store.rows[('users', 'u', 'conversations', row['id'])] = deepcopy(row)
    return store


@pytest.mark.parametrize('status', ['completed', 'in_progress'])
def test_overlap_keeps_live_identity_words_and_lifecycle(status):
    store = seeded(live_row(status))
    incoming = dict(chunk('wal', 1000), data_protection_level='standard')
    row, created, survivors = assign(store, incoming)
    assert not created and row['id'] == 'live' and row['status'] == status
    assert row['sync_live_target'] and not row['discarded']
    assert len(row['transcript_segments']) == 1 and not survivors
    assert len(conversations(store)) == 1
    again, created, survivors = assign(store, incoming)
    assert not created and not survivors and len(again['transcript_segments']) == 1


def test_discovered_tombstoned_live_row_is_not_adopted_without_batch_validator():
    store = seeded()
    store.rows[('users', 'u', 'deleted_conversations', 'live')] = {'deleted': True}
    before = deepcopy(store.rows[('users', 'u', 'conversations', 'live')])
    row, created, survivors = assign(store, chunk('wal', 1000, text='New retained speech.'))
    assert created and row['id'] == 'wal' and survivors
    assert row['sync_merged_from'] == []
    assert store.rows[('users', 'u', 'conversations', 'live')] == before


def test_redirect_to_tombstoned_live_survivor_cannot_receive_speech():
    store = seeded()
    store.rows[('users', 'u', 'deleted_conversations', 'live')] = {'deleted': True}
    store.rows[('users', 'u', 'conversations', 'donor')] = {
        'id': 'donor',
        'deleted': True,
        'sync_merged_into': 'live',
        'smart_merge': {'role': 'donor'},
    }
    before = deepcopy(store.rows)
    with pytest.raises(SyncAssignmentSuperseded):
        assign(store, chunk('wal', 1000), target_id='donor')
    assert store.rows == before


@pytest.mark.parametrize('start', [900, 1009.5, 1120])
def test_non_overlap_and_touching_boundary_create_normal_sync(start):
    store = seeded()
    original = deepcopy(store.rows)
    row, created, _ = assign(store, dict(chunk('wal', start), data_protection_level='standard'))
    assert created and row['id'] == 'wal'
    assert store.rows[('users', 'u', 'conversations', 'live')] == original[('users', 'u', 'conversations', 'live')]


@pytest.mark.parametrize('start', [995, 1005])
@pytest.mark.parametrize('timeline', [None, {'version': 2}])
@pytest.mark.parametrize('explicit_target', [False, True])
def test_partial_overlap_keeps_all_new_speech_and_live_origin(start, timeline, explicit_target):
    live = live_row('in_progress')
    if timeline is not None:
        live['audio_timeline'] = timeline
    store = seeded(live)
    incoming = dict(
        chunk('wal', start, text='New speech outside the existing live transcript.'), data_protection_level='standard'
    )
    row, created, _ = assign(store, incoming, target_id='live' if explicit_target else None)
    assert not created and row['id'] == 'live'
    assert row['started_at'] == live['started_at']
    assert {s['text'] for s in row['transcript_segments']} == {
        live['transcript_segments'][0]['text'],
        incoming['transcript_segments'][0]['text'],
    }
    assert sorted(s['start'] for s in row['transcript_segments']) == sorted([0, start - 1000])


@pytest.mark.parametrize('status', ['completed', 'in_progress'])
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_adoption_outside_lineage_allowlist_keeps_cached_origin_and_fences_late_live(monkeypatch, status, level):
    from config.sync_lineage import sync_lineage_resolve_active_for
    from database import conversations as db

    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', 'another-synthetic-owner')
    assert not sync_lineage_resolve_active_for('u')
    live = live_row(status)
    assert 'audio_timeline' not in live
    cached_origin = live['started_at']
    store = StrictFirestore()
    path = ('users', 'u', 'conversations', 'live')
    store.rows[path] = db._prepare_conversation_for_write(live, 'u', level)
    monkeypatch.setattr(db, 'find_sync_live_overlap_candidates', lambda *a, **kw: ('live',))
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(db, 'db', store)
    # Keep storage codecs and the read-before-write transaction boundary real.
    incoming = dict(chunk('wal', 995, text='Earlier retained sync speech.'), data_protection_level=level)
    stale, created, _ = db.assign_sync_conversation('u', incoming, firestore_client=store)
    assert not created and stale['id'] == 'live' and stale['sync_live_target']
    assert stale['started_at'] == cached_origin
    early = next(s for s in stale['transcript_segments'] if s['text'] == 'Earlier retained sync speech.')
    assert early['start'] == -5 and early['audio_alignment'] == 'unplaced'
    assert stale['sync_content_revision'] == 1

    # The listener's 30-second cache still computes offsets from the old origin.
    late = dict(
        id='late', start=12, end=14, text='Delayed live final.', speaker='SPEAKER_01', speaker_id=1, is_user=True
    )
    for _ in range(2):  # an unchanged live retry must not advance the fence
        db.update_conversation_segments('u', 'live', [], live_segments=[late], firestore_client=store)
        assert store.rows[path]['sync_content_revision'] == 2
    stale['status'] = 'completed'
    writes_before = sum(len(t.sets) + len(t.updates) for t in store.transactions)
    assert not db.persist_processing_result_with_lifecycle('u', stale)
    assert sum(len(t.sets) + len(t.updates) for t in store.transactions) == writes_before
    saved = deepcopy(store.rows[path])
    saved['transcript_segments'] = db._decode_transcript_segments_strict(
        'u', saved['transcript_segments'], bool(saved.get('transcript_segments_compressed'))
    )
    assert saved['started_at'] == cached_origin
    final = next(s for s in saved['transcript_segments'] if s.get('id') == 'late')
    assert saved['started_at'] + timedelta(seconds=final['start']) == cached_origin + timedelta(seconds=12)
    assert {s['text'] for s in saved['transcript_segments']} == {
        live['transcript_segments'][0]['text'],
        'Earlier retained sync speech.',
        'Delayed live final.',
    }


@pytest.mark.parametrize(
    'field,value',
    [
        ('client_device_id', 'other'),
        ('client_device_id', None),
        ('source', 'desktop'),
        ('is_locked', True),
        ('deleted', True),
        ('has_content', False),
        ('status', 'processing'),
    ],
)
def test_incompatible_deleted_and_empty_stubs_are_not_adopted(field, value):
    live = live_row()
    live[field] = value
    store = seeded(live)
    row, created, _ = assign(store, dict(chunk('wal', 1000), data_protection_level='standard'))
    assert created and row['id'] == 'wal'


def test_candidate_deleted_after_discovery_uses_next_overlapping_live():
    store = seeded(dict(live_row(), deleted=True))
    other = dict(live_row(), id='other')
    store.rows[('users', 'u', 'conversations', 'other')] = other
    row, created, _ = assign(
        store, dict(chunk('wal', 1000), data_protection_level='standard'), candidates=('live', 'other')
    )
    assert row['id'] == 'other' and not created


def test_merge_size_failure_publishes_immediately_without_hidden_pending_row(monkeypatch):
    from utils.sync import assignment

    store = seeded()
    # Keep room for a new encoded row; only the existing live row is full.
    store.rows[('users', 'u', 'conversations', 'live')]['structured'] = {'overview': 'x' * 8192}
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', 4096)
    incoming = dict(
        chunk('wal', 1005, text='Speech that is not already in the live conversation.'),
        data_protection_level='standard',
    )
    row, created, _ = assign(store, incoming)
    assert created and row['id'] == 'wal' and not row['discarded']
    assert row['transcript_segments'][0]['text'] == incoming['transcript_segments'][0]['text']
    assert len(conversations(store)) == 2
    assert not store.rows[('users', 'u', 'conversations', 'live')].get('sync_content_revision')
    retried, created, survivors = assign(store, incoming)
    assert not created and not survivors and retried['id'] == 'wal'


def test_lookup_failure_is_immediate_visible_fallback(monkeypatch):
    from database import sync_live_overlap as db

    user = MagicMock()
    user.collection.side_effect = RuntimeError('unavailable')
    fallback = MagicMock()
    monkeypatch.setattr(db, 'record_fallback', fallback)
    assert db.find_sync_live_overlap_candidates(user, chunk('wal', 1000)) == ()
    fallback.assert_called_once()
    row, created, _ = assign(seeded(), dict(chunk('wal', 1000), data_protection_level='standard'), candidates=())
    assert created and row['id'] == 'wal' and not row['discarded']


def test_kill_switch_restores_old_assignment(monkeypatch):
    monkeypatch.delenv('SYNC_LIVE_OVERLAP_ENABLED', raising=False)
    assert live_overlap_enabled()
    monkeypatch.setenv('SYNC_LIVE_OVERLAP_ENABLED', 'false')
    assert not live_overlap_enabled()
    row, created, _ = assign(seeded(), dict(chunk('wal', 1000), data_protection_level='standard'))
    assert created and row['id'] == 'wal'


def test_maximum_overlap_wins_without_merging_live_identities():
    first = live_row()
    longer = dict(live_row(), id='longer', finished_at=first['finished_at'] + timedelta(seconds=10))
    assert choose_live_overlap([first, longer], chunk('wal', 1005)) == 'longer'


def test_discovery_returns_empty_stub_so_transaction_reads_and_fences_it():
    # A same-device stub that has not written its first transcript yet must be a
    # discovery hint, so the assignment transaction reads that document and
    # Firestore commit contention can fence a listen writer adding content
    # concurrently. The stub itself is still not adopted while it stays empty:
    # eligibility stays authoritative in the transaction, never in discovery.
    stub = live_row()
    stub.pop('capture_evidence')
    stub['has_content'] = False
    stub['transcript_segments'] = []
    from utils.sync.live_overlap import discoverable_live_overlap

    assert discoverable_live_overlap(stub, chunk('wal', 1002))
    assert choose_live_overlap([stub], chunk('wal', 1002)) is None
    store = seeded(stub)
    incoming = dict(chunk('wal', 1002), data_protection_level='standard')
    row, created, _ = assign(store, incoming)
    assert created and row['id'] == 'wal'
    assert store.rows[('users', 'u', 'conversations', 'live')]['has_content'] is False


def test_stub_becoming_eligible_is_adopted_by_the_transactional_revalidation():
    # Same race one step later: discovery saw an empty stub, the listen writer
    # landed its first transcript (with live capture provenance, as the
    # production writer does) before the transaction re-read it. The
    # in-transaction eligibility check is the authority, so the upload appends
    # into the live row instead of publishing a twin.
    stub = live_row('in_progress')
    stub.pop('capture_evidence')
    stub['has_content'] = False
    stub['transcript_segments'] = []
    store = seeded(stub)
    landed = live_row('in_progress')
    store.rows[('users', 'u', 'conversations', 'live')].update(
        has_content=True,
        capture_evidence=landed['capture_evidence'],
        transcript_segments=deepcopy(landed['transcript_segments']),
    )
    incoming = dict(chunk('wal', 1002), data_protection_level='standard')
    row, created, _ = assign(store, incoming)
    assert not created and row['id'] == 'live' and row['has_content']


def test_discovery_excludes_other_partitions_and_off_lifecycle_rows():
    stub = live_row()
    stub.pop('capture_evidence')
    stub['has_content'] = False
    from utils.sync.live_overlap import discoverable_live_overlap

    assert discoverable_live_overlap(stub, chunk('wal', 1002))
    assert not discoverable_live_overlap(dict(stub, deleted=True), chunk('wal', 1002))
    assert not discoverable_live_overlap(dict(stub, status='processing'), chunk('wal', 1002))
    assert not discoverable_live_overlap(dict(stub, client_device_id='other'), chunk('wal', 1002))
    assert not discoverable_live_overlap(dict(stub, finished_at=stub['started_at']), chunk('wal', 1002))


@pytest.mark.parametrize('fleet,lineage', [('off', 'on'), ('on', 'on'), ('off', 'off')])
def test_same_transcript_as_explicit_target_for_each_existing_merge_mode(monkeypatch, fleet, lineage):
    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', fleet)
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', lineage)
    incoming = dict(chunk('wal', 1000), data_protection_level='standard')
    temporal, _, _ = assign(seeded(), incoming)
    explicit, _, _ = assign(seeded(), incoming, candidates=(), target_id='live')
    assert temporal['transcript_segments'] == explicit['transcript_segments']


def test_proven_exact_retry_drops_and_new_words_survive_with_default_lineage(monkeypatch):
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'on')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'on')
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', raising=False)
    live = live_row()
    live['transcript_segments'][0]['speaker_id_scope'] = 'sync:original-chunk'
    incoming = dict(chunk('wal', 1000), data_protection_level='standard')
    incoming['transcript_segments'][0]['speaker_id_scope'] = 'sync:original-chunk'
    incoming['transcript_segments'].append(
        dict(start=10, end=15, text='Fresh words that the live row did not have.', speaker_id=0)
    )
    incoming['finished_at'] += timedelta(seconds=5.5)
    row, created, survivors = assign(seeded(live), incoming)
    assert not created and row['id'] == live['id']
    assert [s['text'] for s in row['transcript_segments']] == [
        live['transcript_segments'][0]['text'],
        incoming['transcript_segments'][1]['text'],
    ]
    assert [s['text'] for s in survivors] == [incoming['transcript_segments'][1]['text']]


def test_metadata_discovery_uses_existing_index_and_bounded_deadline():
    from database import conversations as db

    user = MagicMock()
    query = user.collection.return_value
    query.where.return_value = query
    query.order_by.return_value = query
    query.select.return_value = query
    query.limit.return_value = query
    snapshot = MagicMock(id='live')
    snapshot.to_dict.return_value = live_row()
    query.stream.return_value = iter([snapshot])
    assert db.find_sync_live_overlap_candidates(user, chunk('wal', 1000)) == ('live',)
    query.stream.assert_called_once_with(timeout=10)
    fields = query.select.call_args.args[0]
    assert 'transcript_segments' not in fields and 'structured' not in fields


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_database_adapter_discovers_and_appends_with_real_storage_codecs(monkeypatch, level):
    from database import conversations as db

    store = StrictFirestore()
    live = live_row('in_progress')
    store.rows[('users', 'u', 'conversations', 'live')] = db._prepare_conversation_for_write(live, 'u', level)
    discover = MagicMock(return_value=('live',))
    monkeypatch.setattr(db, 'find_sync_live_overlap_candidates', discover)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *a: None)
    incoming = dict(
        chunk('wal', 1005, text='Distinct new speech for the live conversation.'), data_protection_level=level
    )
    row, created, _ = db.assign_sync_conversation('u', incoming, firestore_client=store)
    assert not created and row['id'] == 'live' and row['status'] == 'in_progress'
    assert len(row['transcript_segments']) == 2
    discover.assert_called_once()


def test_capture_mode_discovers_no_device_open_target_and_projection_keeps_its_key(monkeypatch):
    from database import conversations as db

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    capture = {'capture_root': 'synthetic-root', 'channel': 'mono', 'clock_epoch': 0}
    live = live_row('in_progress')
    live.update(client_device_id=None, capture_evidence={'origin': 'live', **capture})
    incoming = dict(
        chunk('wal', 1005),
        client_device_id=None,
        capture_evidence={'origin': 'sync', **capture},
        data_protection_level='standard',
    )
    store = StrictFirestore()
    store.rows[('users', 'u', 'conversations', 'live')] = db._prepare_conversation_for_write(live, 'u', 'standard')
    discover = MagicMock(return_value=('live',))
    monkeypatch.setattr(db, 'find_sync_live_overlap_candidates', discover)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *args: None)
    row, created, _ = db.assign_sync_conversation('u', incoming, firestore_client=store)
    discover.assert_called_once()
    assert not created and row['id'] == 'live' and row['status'] == 'in_progress'

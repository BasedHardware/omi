"""Real protected rows round-trip through assignment and protection migration."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
import zlib

import pytest

from database import conversations as db
from models.conversation import Conversation
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreCollection
from tests.support.dream_firestore import DreamFirestore
from tests.unit.test_sync_cross_job_assignment import chunk
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD as MARKER
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_FIELD as FIELD

EXTRACTIONS = {'version': 1, 'delegated_by_user': [], 'commitments_by_others': [], 'observed_issue_or_blocker': None}


@pytest.fixture(autouse=True)
def assignment_seams(monkeypatch):
    monkeypatch.setenv('SYNC_LIVE_OVERLAP_ENABLED', 'false')
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    monkeypatch.setattr(db, 'index_sync_assignment', lambda *args: None)


def path(key):
    return ('users', 'u', 'conversations', key)


def seed(store, key, start, level, **extra):
    logical = dict(
        chunk(key, start),
        structured={'title': 'Synthetic'},
        data_protection_level=level,
        sync_content_revision=1,
        **extra
    )
    store.rows[path(key)] = db.encode_conversation_for_write('u', logical, level)
    return deepcopy(store.rows[path(key)])


def assert_retained(raw, level, expected=EXTRACTIONS):
    assert raw[MARKER] is True
    assert isinstance(raw[FIELD], bytes if level == 'standard' else str)
    assert db.decode_open_loop_extractions('u', raw[FIELD], raw[MARKER]) == expected


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_sync_append_and_retry_preserve_encoded_extractions(level):
    store = StrictFirestore()
    seed(store, 'existing', 1000, level, **{FIELD: EXTRACTIONS})
    incoming = dict(chunk('append', 1060), data_protection_level=level)
    for _ in range(2):
        row, created, _ = db.assign_sync_conversation('u', incoming, candidate_id='existing', firestore_client=store)
        assert not created and row['id'] == 'existing'
        raw = store.rows[path('existing')]
        assert_retained(raw, level)
        segments = db._decode_transcript_segments_strict('u', raw['transcript_segments'], True)
        assert len(segments) == 2
        # The strict fixture retains DELETE_FIELD literally, unlike Firestore.
        wire = Conversation.model_validate(dict(row, created_at=row['started_at'], client_processing=None)).model_dump(
            mode='json'
        )
        assert FIELD not in wire and MARKER not in wire


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_sync_assignment_same_level_never_decodes_and_writes_blob_byte_identical(monkeypatch, level):
    store = StrictFirestore()
    before = seed(store, 'existing', 1000, level, **{FIELD: EXTRACTIONS})
    decode_calls = []
    real_decode = db.decode_open_loop_extractions

    def counting_decode(uid, raw, compressed):
        decode_calls.append((raw, compressed))
        return real_decode(uid, raw, compressed)

    monkeypatch.setattr(db, 'decode_open_loop_extractions', counting_decode)
    incoming = dict(chunk('append', 1060), data_protection_level=level)
    for _ in range(2):
        row, created, _ = db.assign_sync_conversation('u', incoming, candidate_id='existing', firestore_client=store)
        assert not created and row['id'] == 'existing'
        # A replayed transaction body must not pay decrypt/decompress either.
        assert decode_calls == []
    raw = store.rows[path('existing')]
    assert raw[FIELD] == before[FIELD] and raw[MARKER] == before[MARKER]
    assert_retained(raw, level)


def test_sync_assignment_level_change_reprotects_retained_extractions(monkeypatch):
    store = StrictFirestore()
    before = seed(store, 'existing', 1000, 'standard', **{FIELD: EXTRACTIONS})
    decode_calls = []
    real_decode = db.decode_open_loop_extractions

    def counting_decode(uid, raw, compressed):
        decode_calls.append((raw, compressed))
        return real_decode(uid, raw, compressed)

    monkeypatch.setattr(db, 'decode_open_loop_extractions', counting_decode)
    row, created, _ = db.assign_sync_conversation(
        'u',
        dict(chunk('append', 1060), data_protection_level='enhanced'),
        candidate_id='existing',
        firestore_client=store,
    )
    assert not created and row['id'] == 'existing'
    assert len(decode_calls) == 1 and decode_calls[0][0] == before[FIELD]
    raw = store.rows[path('existing')]
    assert raw['data_protection_level'] == 'enhanced'
    assert raw[FIELD] != before[FIELD]
    assert_retained(raw, 'enhanced')


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('upgrade', [False, True])
def test_sync_donor_merge_preserves_both_rows_and_stronger_protection(level, upgrade):
    store = StrictFirestore()
    seed(store, 'survivor', 1000, level, **{FIELD: EXTRACTIONS})
    donor_value = dict(EXTRACTIONS, version=2)
    donor_level = 'enhanced' if upgrade else level
    before_donor = seed(store, 'donor', 1060, donor_level, **{FIELD: donor_value})
    incoming = dict(chunk('append', 1030), data_protection_level=level)
    row, created, _ = db.assign_sync_conversation(
        'u', incoming, target_id='survivor', candidate_id='donor', firestore_client=store
    )
    assert not created and row['id'] == 'survivor'
    assert_retained(store.rows[path('survivor')], donor_level)
    donor = store.rows[path('donor')]
    assert donor['deleted'] and donor['sync_merged_into'] == 'survivor'
    assert donor[FIELD] == before_donor[FIELD] and donor[MARKER] == before_donor[MARKER]
    assert_retained(donor, donor_level, donor_value)


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('state', ['absent', 'null', 'object'])
def test_new_row_encodes_logical_extractions_and_keeps_absent_null_controls(level, state):
    store = StrictFirestore()
    incoming = dict(chunk('new', 1000), data_protection_level=level)
    if state != 'absent':
        incoming[FIELD] = EXTRACTIONS if state == 'object' else None
    _, created, _ = db.assign_sync_conversation('u', incoming, firestore_client=store)
    assert created
    raw = store.rows[path('new')]
    if state == 'object':
        assert_retained(raw, level)
    elif state == 'null':
        assert raw[FIELD] is None and raw[MARKER] is None
    else:
        assert FIELD not in raw and MARKER not in raw


@pytest.mark.parametrize('bad', [b'not compressed', ['not an object']])
def test_unreadable_existing_extractions_abort_a_reprotecting_write(bad):
    # Only a protection-level change must read the stored blob; an unreadable
    # one then aborts before any transaction write instead of being emptied.
    store = StrictFirestore()
    seed(store, 'existing', 1000, 'standard', **{FIELD: EXTRACTIONS})
    store.rows[path('existing')][FIELD] = bad
    before = deepcopy(store.rows)
    with pytest.raises((ValueError, zlib.error)):
        db.assign_sync_conversation(
            'u',
            dict(chunk('append', 1060), data_protection_level='enhanced'),
            candidate_id='existing',
            firestore_client=store,
        )
    assert store.rows == before


@pytest.mark.parametrize('bad', [b'not compressed', ['not an object']])
def test_unreadable_existing_extractions_at_unchanged_level_are_carried_untouched(bad):
    # The same-level write never decodes the blob, so it cannot be blocked by
    # one either: the corrupt bytes ride along verbatim for the tolerant read
    # path to handle, and the append itself still lands.
    store = StrictFirestore()
    seed(store, 'existing', 1000, 'standard', **{FIELD: EXTRACTIONS})
    store.rows[path('existing')][FIELD] = bad
    row, created, _ = db.assign_sync_conversation(
        'u',
        dict(chunk('append', 1060), data_protection_level='standard'),
        candidate_id='existing',
        firestore_client=store,
    )
    assert not created and row['id'] == 'existing'
    raw = store.rows[path('existing')]
    assert raw[FIELD] == bad and raw[MARKER] is True
    segments = db._decode_transcript_segments_strict('u', raw['transcript_segments'], True)
    assert len(segments) == 2


@pytest.mark.parametrize('source,target', [('standard', 'enhanced'), ('enhanced', 'standard')])
def test_protection_migration_round_trips_extractions_atomically(monkeypatch, source, target):
    store = StrictFirestore()
    seed(store, 'existing', 1000, source, **{FIELD: EXTRACTIONS})
    ref = store.collection('users').document('u').collection('conversations').document('existing')
    monkeypatch.setattr(
        store, 'get_all', lambda *args, **kwargs: [SimpleNamespace(exists=True, reference=ref)], raising=False
    )
    monkeypatch.setattr(store, 'batch', MagicMock, raising=False)
    monkeypatch.setattr(
        StrictFirestoreCollection, 'select', lambda *args: SimpleNamespace(stream=lambda: []), raising=False
    )
    monkeypatch.setattr(db, 'db', store)
    db.migrate_conversations_level_batch('u', ['existing'], target)
    raw = store.rows[path('existing')]
    assert raw['data_protection_level'] == target
    assert_retained(raw, target)
    before = deepcopy(raw)
    db.migrate_conversations_level_batch('u', ['existing'], target)
    assert store.rows[path('existing')] == before


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_reprocess_without_fresh_extractions_preserves_stored_blob(monkeypatch, level):
    store = DreamFirestore()  # Existing strict extension with witnessed set(merge=True).
    before = seed(store, 'existing', 1000, level, **{FIELD: EXTRACTIONS})
    monkeypatch.setattr(db, 'db', store)
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *args: None)
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda *args: None)
    incoming = dict(
        chunk('existing', 1000),
        structured={'title': 'Reprocessed'},
        data_protection_level=level,
        sync_content_revision=1,
    )
    assert db.persist_processing_result_with_lifecycle('u', incoming)
    raw = store.rows[path('existing')]
    assert raw[FIELD] == before[FIELD] and raw[MARKER] == before[MARKER]


@pytest.mark.parametrize('source,target', [('standard', 'enhanced'), ('enhanced', 'standard')])
@pytest.mark.parametrize('has_transcript', [False, True])
def test_processor_output_reprotected_when_migration_wins(monkeypatch, source, target, has_transcript):
    store = DreamFirestore()
    seed(store, 'existing', 1000, target, **{FIELD: EXTRACTIONS})
    monkeypatch.setattr(db, 'db', store)
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *args: None)
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda *args: None)
    incoming = dict(
        chunk('existing', 1000),
        structured={'title': 'Reprocessed'},
        data_protection_level=source,
        sync_content_revision=1,
        **{FIELD: EXTRACTIONS}
    )
    if not has_transcript:
        incoming.pop('transcript_segments')
    assert db.persist_processing_result_with_lifecycle('u', incoming)
    assert_retained(store.rows[path('existing')], target)
    assert store.rows[path('existing')]['data_protection_level'] == target

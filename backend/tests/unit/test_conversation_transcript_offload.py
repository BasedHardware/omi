"""Pointer-mode domain refusals, reader surfaces and C1 review follow-ups."""

from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import inspect
import json
from types import SimpleNamespace
from unittest.mock import Mock
import zlib

from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists
from pydantic import ValidationError
import pytest

from database import conversations as db, transcript_pointer as pointer
from database import (
    owner_confirmation,
    review_overlay_merge,
    review_store,
    episodes,
    speaker_resolution_updates,
    review_transcript_changes,
    speaker_learning_jobs,
)
from database import smart_merge, recurring_voice_privacy, review_changes
from database import recording_sessions, conversation_finalization_jobs as jobs, users, speaker_auto_enroll as auto
from database import episode_attach_memo as memo, episode_timeline as timeline, episode_recorded_components
from utils.speakers import auto_enroll as policy
from utils.conversations.episode_attach_key import content_key
from utils.sync.assignment import assign_in_transaction
from utils.sync.assignment_errors import SyncAssignmentSuperseded
from models.review import ReviewChange, ChangeRef
from utils.conversations import transcript_chunks
from utils.conversations.transcript_hash import transcript_sha256_for_binding
from models.conversation import Conversation
from models.transcript_segment import TranscriptSegment
from tests.support.dream_firestore import DreamFirestore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument, StrictFirestoreCollection
from tests.unit.test_transcript_pointer import lake_world, UID, CID, PATH, encode, speech, pointer_doc
from utils.other import object_lake as lake, space_keys
from utils.other.local_storage import LocalBlob
from utils.person_evidence_backfill import backfill_person
from utils.speaker_tag_prompts.owner_confirmation import StaleOwnerConfirmation

NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    'failure,display,content',
    [
        (lake.LakeFetchError, pointer.TranscriptPointerFetchError, pointer.TranscriptPointerFetchError),
        (lake.LakeObjectAbsent, None, False),
        (space_keys.SpaceKeyDestroyed, pointer.TranscriptShredded, False),
        (lake.LakeObjectCorrupt, [], True),
    ],
)
def test_decode_state_display_and_content_contract(lake_world, monkeypatch, failure, display, content):
    doc = pointer_doc(lake_world)
    doc['has_content'] = True  # cached inline hints cannot bypass lake failure states
    monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    if isinstance(display, type):
        with pytest.raises(display):
            db.prepare_conversation_for_read(doc, UID)
    else:
        rendered = db.prepare_conversation_for_read(doc, UID)
        assert rendered is None if display is None else rendered['transcript_segments'] == display
    if isinstance(content, type):
        with pytest.raises(content):
            db.raw_conversation_has_content(UID, doc)
    else:
        assert db.raw_conversation_has_content(UID, doc) is content


@pytest.mark.parametrize('enhanced', [False, True])
def test_display_decoder_decrypts_lake_independent_of_level(lake_world, enhanced):
    doc = pointer_doc(lake_world)
    doc['data_protection_level'] = 'enhanced' if enhanced else 'standard'
    assert db.prepare_conversation_for_read(doc, UID)['transcript_segments'] == speech()
    assert db._decrypt_conversation_data(doc, UID)['transcript_segments'] == speech()
    assert lake_world.calls['get'] == 1


def test_public_chat_rejects_pointer_and_wire_model_fails_loud(lake_world):
    doc = pointer_doc(lake_world)
    with pytest.raises(ValueError):
        db._decode_public_transcript_segments_bounded(UID, doc['transcript_segments'], compressed=True)
    with pytest.raises(ValidationError):
        Conversation.model_validate(doc)
    assert lake_world.calls['get'] == 0


def test_oversize_inline_transcript_fits_after_offload(lake_world):
    segments = speech(1100000)
    assert len(zlib.compress(json.dumps(segments).encode())) > 900 * 1024
    doc = encode(segments)
    assert isinstance(doc['transcript_segments'], dict)
    assert len(json.dumps(doc)) < 1024
    assert db.decode_transcript_segments_verified(UID, doc['transcript_segments'], True) == segments


@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_live_update_cold_pointer_domain_mapping(lake_world, monkeypatch, state):
    doc = pointer_doc(lake_world)
    monkeypatch.setattr(db, 'get_firestore_client', lambda: lake_world.store)
    if state != 'present':
        failure = {
            'absent': lake.LakeObjectAbsent,
            'shredded': space_keys.SpaceKeyDestroyed,
            'outage': lake.LakeFetchError,
        }[state]
        monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    operation = lambda: db.update_conversation_segments(
        UID, CID, speech(), preserve_unseen=True, firestore_client=lake_world.store
    )
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
    else:
        result = operation()
        assert bool(result) is (state == 'present')
    if state != 'present':
        assert lake_world.store.rows[PATH] == doc


@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_owner_confirmation_cold_pointer_refusal(lake_world, monkeypatch, state):
    pointer_doc(lake_world)
    if state != 'present':
        failure = {
            'absent': lake.LakeObjectAbsent,
            'shredded': space_keys.SpaceKeyDestroyed,
            'outage': lake.LakeFetchError,
        }[state]
        monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    # An invalid binding still reaches strict transcript decode before refusing.
    with pytest.raises(pointer.TranscriptPointerFetchError if state == 'outage' else StaleOwnerConfirmation):
        owner_confirmation.record(
            UID, CID, 'claim', {'prompt_id': 'invalid', 'evidence_id': 'invalid'}, firestore_client=lake_world.store
        )
    if state == 'present':
        assert lake_world.calls['get'] == 1


@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_review_merge_cold_pointer_mapping(lake_world, monkeypatch, state):
    pointer_doc(lake_world)
    if state != 'present':
        failure = {
            'absent': lake.LakeObjectAbsent,
            'shredded': space_keys.SpaceKeyDestroyed,
            'outage': lake.LakeFetchError,
        }[state]
        monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    with pytest.raises(pointer.TranscriptPointerFetchError if state == 'outage' else review_store.ReviewConflict):
        review_overlay_merge.transfer(UID, [], CID, firestore_client=lake_world.store)
    if state == 'present':
        assert lake_world.calls['get'] == 1


@pytest.mark.parametrize('failure', [lake.LakeObjectAbsent, space_keys.SpaceKeyDestroyed])
def test_episode_retained_bounds_skips_deleted_blob(lake_world, monkeypatch, failure):
    pointer_doc(lake_world)
    monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    raw = {'conversation_ids': [CID], 'started_at': NOW}
    merged = deepcopy(raw)
    pointer.run_preloaded_transactional(
        lake_world.store, lambda txn: episodes.retained_bounds(txn, lake_world.store, UID, raw, merged)
    )
    assert merged['discarded_conversation_ids'] == [CID]


@pytest.mark.parametrize('failure', [lake.LakeObjectAbsent, space_keys.SpaceKeyDestroyed])
def test_evidence_backfill_skips_deleted_blob(lake_world, monkeypatch, failure):
    pointer_doc(lake_world)
    lake_world.store.rows[('users', UID, 'people', 'p')] = {'name': 'Synthetic'}
    monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    assert backfill_person(lake_world.store, UID, 'p', [CID], NOW, apply=True) is None


def test_deleted_owner_fence_prevents_key_resurrection(lake_world):
    space_keys.destroy_space_keys(UID)
    assert lake_world.store.rows[('space_keys', UID)]['state'] == 'destroyed'
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        space_keys.get_or_create_space_key(UID)
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        encode()
    assert lake_world.calls['put'] == 0


def test_destroy_racing_upload_removes_late_object(lake_world, monkeypatch):
    original = LocalBlob.upload_from_string

    def upload(blob, *args, **kwargs):
        space_keys.destroy_space_keys(UID)
        return original(blob, *args, **kwargs)

    monkeypatch.setattr(LocalBlob, 'upload_from_string', upload)
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        encode()
    assert list(lake_world.bucket.list_blobs(prefix=f'v1/spaces/{UID}/')) == []
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        space_keys.get_or_create_space_key(UID)


def test_destroy_racing_first_key_creation_observes_tombstone(lake_world, monkeypatch):
    original = StrictFirestoreDocument.create

    def create(ref, data):
        space_keys.destroy_space_keys(UID)
        raise AlreadyExists('concurrent tombstone won')

    monkeypatch.setattr(StrictFirestoreDocument, 'create', create)
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        encode()
    assert lake_world.calls['put'] == 0


@pytest.mark.parametrize('malformation', ['wrapped', 'versions', 'algo', 'version', 'false_tombstone'])
def test_malformed_key_rows_are_retryable_even_after_cache_hit(lake_world, malformation):
    encode()
    doc = lake_world.store.rows[('space_keys', UID)]
    if malformation == 'wrapped':
        doc['versions'][0]['wrapped'] = ''
    elif malformation == 'versions':
        doc['versions'] = []
    elif malformation == 'algo':
        doc['algo'] = 'unknown'
    elif malformation == 'false_tombstone':
        doc['state'] = 'destroyed'  # wrapped material still present: retryable corruption
    else:
        doc['versions'][0]['version'] = True
    with pytest.raises(space_keys.SpaceKeyUnavailable):
        space_keys.unwrap_space_dek(UID, 1)
    with pytest.raises(space_keys.SpaceKeyUnavailable):
        space_keys.get_or_create_space_key(UID)


def test_key_document_read_budget(lake_world, monkeypatch):
    reads = []
    original = StrictFirestoreDocument.get

    def get(ref, *args, **kwargs):
        if ref.path[0] == 'space_keys':
            reads.append(ref.path)
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    first = lake.put_space_object(UID, 'transcript', CID, b'synthetic')
    assert len(reads) == 2  # pre-encryption + post-upload authority
    reads.clear()
    space_keys.unwrap_space_dek(UID, 1)
    assert len(reads) == 1  # KMS cache never caches destruction authority
    reads.clear()
    assert lake.put_space_object(UID, 'transcript', CID, b'synthetic') == first
    assert len(reads) == 2  # idempotent put has the same authority budget


def test_data_class_limits_bound_decompression_and_admission(lake_world, monkeypatch):
    ref = lake.put_space_object(UID, 'transcript', CID, b'a' * 10000)
    monkeypatch.setitem(lake.MAX_PLAINTEXT_BYTES, 'transcript', 9999)
    with pytest.raises(lake.LakeObjectCorrupt, match='limit'):
        lake.get_space_object(ref)
    with pytest.raises(lake.LakeObjectCorrupt, match='limit'):
        lake.put_space_object(UID, 'transcript', CID, b'a' * 10000)


@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
@pytest.mark.parametrize('site', ['projection', 'translation', 'speaker_assignment', 'speaker_resolution'])
def test_remaining_domain_transactions_use_preload(lake_world, monkeypatch, site, state):

    pointer_doc(lake_world)
    original_get = StrictFirestoreDocument.get

    def get(ref, *args, **kwargs):
        snap = original_get(ref, *args, **kwargs)
        snap.update_time = NOW
        return snap

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    monkeypatch.setattr(speaker_resolution_updates, 'get_firestore_client', lambda: lake_world.store)
    if state != 'present':
        failure = {
            'absent': lake.LakeObjectAbsent,
            'shredded': space_keys.SpaceKeyDestroyed,
            'outage': lake.LakeFetchError,
        }[state]
        monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    digest = transcript_sha256_for_binding(speech())
    projection = {'client_processing': {'schema_version': 1, 'transcript_sha256': digest}}
    if site == 'projection':
        operation = lambda: db.bind_client_processing(UID, CID, projection, firestore_client=lake_world.store)
    elif site == 'translation':
        operation = lambda: db.materialize_translation(
            UID, CID, 'segment-1', speech()[0]['text'], 'es', 'Synthetic translation', firestore_client=lake_world.store
        )
    elif site == 'speaker_assignment':
        operation = lambda: db.assign_conversation_speaker(
            UID, CID, is_user=True, segment_ids=['segment-1'], firestore_client=lake_world.store
        )
    else:
        operation = lambda: speaker_resolution_updates.persist_speaker_resolution_if_current(
            UID,
            {'id': CID, 'transcript_segments': speech()},
            expected_updated_at=NOW,
            on_committed_identity=lambda *args: None,
        )
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
    elif state != 'present' and site == 'speaker_assignment':
        with pytest.raises(LookupError):
            operation()
    elif state != 'present' and site == 'speaker_resolution':
        with pytest.raises((pointer.TranscriptBlobAbsent, pointer.TranscriptShredded)):
            operation()
    else:
        result = operation()
        assert bool(result) is (state == 'present')
    if state == 'present':
        assert lake_world.calls['get'] == 1


class _ReadSurface:
    """Small read-only query transport; domain transactions use StrictFirestore."""

    def __init__(self, world):
        self.world = world

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def start_after(self, *args, **kwargs):
        return self

    def get_all(self, refs, **kwargs):
        return self.stream()

    def get(self, **kwargs):
        return next(self.stream())

    def stream(self, **kwargs):
        doc = deepcopy(self.world.store.rows[PATH])
        yield SimpleNamespace(id=CID, exists=True, update_time=NOW, to_dict=lambda: deepcopy(doc))


@pytest.mark.parametrize('surface', ['detail', 'list', 'mcp', 'export', 'search', 'notifications'])
def test_reader_surfaces_resolve_pointers(lake_world, monkeypatch, surface):

    doc = pointer_doc(lake_world)
    doc.update(
        discarded=False,
        has_photos=False,
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
        structured={'title': 'Synthetic'},
    )
    lake_world.store.rows[PATH] = doc
    transport = _ReadSurface(lake_world)
    monkeypatch.setattr(db, 'db', transport)
    # Query selection is already covered by the repository's query-driver suite;
    # this isolates the actual list/notification decoder from pagination storage.
    monkeypatch.setattr(db, '_collect_visible_conversation_page', lambda *args, **kwargs: [deepcopy(doc)])
    if surface == 'detail':
        rows = [db.get_conversation(UID, CID)]
    elif surface in ('list', 'notifications'):
        rows = db.get_conversations(UID)
    elif surface == 'mcp':
        rows = db.get_mcp_conversations_by_id(UID, [CID], include_transcript=True, firestore_client=transport)
    elif surface == 'export':
        rows = list(db.iter_all_conversations(UID))
    else:
        rows = transcript_chunks.hydrate_chunk_texts(UID, [{'conversation_id': CID, 'chunk_index': 0}])
        assert speech()[0]['text'] in rows[0]['text']
        assert lake_world.calls['get'] == 1
        return
    assert rows[0]['transcript_segments'] == speech()
    assert lake_world.calls['get'] == 1


def test_export_skips_absent_pointer(lake_world, monkeypatch):
    pointer_doc(lake_world)
    monkeypatch.setattr(db, 'db', _ReadSurface(lake_world))
    monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=lake.LakeObjectAbsent('synthetic')))
    assert list(db.iter_all_conversations(UID)) == []


@pytest.mark.parametrize('status', ['pending_deletion', 'pending', 'wiping', 'completed', 'unknown', None])
def test_durable_account_deletion_marker_fences_put_before_key_creation(lake_world, status):
    lake_world.store.rows[('account_deletions', UID)] = {'wipe_status': status}
    with pytest.raises(lake.LakeWriteFenced):
        encode()
    assert ('space_keys', UID) not in lake_world.store.rows
    assert lake_world.calls['put'] == 0


@pytest.mark.parametrize('status', ['cancelled', 'billing_failed'])
def test_explicitly_restored_account_can_put(lake_world, status):
    lake_world.store.rows[('account_deletions', UID)] = {'wipe_status': status}
    assert isinstance(encode()['transcript_segments'], dict)


def test_owner_deletion_during_upload_cleans_object(lake_world, monkeypatch):
    original = LocalBlob.upload_from_string

    def upload(blob, *args, **kwargs):
        lake_world.store.rows[('account_deletions', UID)] = {'wipe_status': 'wiping'}
        return original(blob, *args, **kwargs)

    monkeypatch.setattr(LocalBlob, 'upload_from_string', upload)
    with pytest.raises(lake.LakeWriteFenced):
        encode()
    assert list(lake_world.bucket.list_blobs(prefix=f'v1/spaces/{UID}/')) == []


def test_unavailable_owner_authority_fails_closed(lake_world, monkeypatch):
    original = StrictFirestoreDocument.get

    def get(ref, *args, **kwargs):
        if ref.path[0] == 'account_deletions':
            raise TimeoutError('synthetic')
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    with pytest.raises(lake.LakeFetchError, match='authority'):
        encode()
    assert lake_world.calls['put'] == 0


def test_review_overlay_apply_and_undo_preload_cold_pointers(lake_world, monkeypatch):

    doc = pointer_doc(lake_world)
    monkeypatch.setattr(review_store, 'get_firestore_client', lambda: lake_world.store)
    monkeypatch.setattr(review_transcript_changes, 'sync_conversations', lambda *args, **kwargs: None)
    monkeypatch.setattr(review_transcript_changes, 'sync_transcript_chunks', lambda *args, **kwargs: None)
    change = ReviewChange(
        change_id='synthetic-change',
        kind='other',
        title='Synthetic spelling',
        created_at=NOW,
        refs=[ChangeRef(type='conversation', id=CID, label='Synthetic')],
    )
    correction = dict(
        segment_id='segment-1',
        conversation_id=CID,
        segment_index=0,
        start=0.0,
        before=speech()[0]['text'],
        after='synthetic',
        kind='transcript',
        source='user',
        change_id=change.change_id,
        created_at=NOW,
        undone=False,
    )
    review_transcript_changes.record_change(
        UID,
        change,
        {},
        [correction],
        edit_key='synthetic-edit',
        expected_records={},
        expected_document=doc,
        authority='user',
        firestore_client=lake_world.store,
    )
    assert lake_world.calls['get'] == 1
    pointer.clear_memo()
    review_transcript_changes.set_undone(UID, change.change_id, True)
    assert lake_world.calls['get'] == 2


@pytest.mark.parametrize('site', ['legacy_learning', 'ensure_learning'])
@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_learning_ledger_transactions_preload(lake_world, monkeypatch, site, state):

    doc = pointer_doc(lake_world)
    doc['manual_speaker_assignments'] = {
        'generation': 1,
        'speakers': {'0': {'person_id': 'p', 'generation': 1, 'is_user': False}},
    }
    lake_world.store.rows[PATH] = doc
    lake_world.store.rows[('users', UID)] = {'save_other_voice_profiles': True}
    lake_world.store.rows[('users', UID, 'people', 'p')] = {'id': 'p', 'name': 'Synthetic'}
    if state != 'present':
        failure = {
            'absent': lake.LakeObjectAbsent,
            'shredded': space_keys.SpaceKeyDestroyed,
            'outage': lake.LakeFetchError,
        }[state]
        monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    if site == 'legacy_learning':
        operation = lambda: speaker_learning_jobs.claim_next_job(UID, CID, now=NOW, firestore_client=lake_world.store)
    else:
        operation = lambda: speaker_learning_jobs.ensure_job(
            UID, CID, person_id='p', segment_ids=['segment-1'], now=NOW, firestore_client=lake_world.store
        )
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
    else:
        operation()
    if state == 'present':
        assert lake_world.calls['get'] == 1


def test_nontransactional_update_offloads_without_id_in_patch(lake_world, monkeypatch):
    lake_world.store.rows[PATH] = {'id': CID, 'data_protection_level': 'standard', 'status': 'completed'}
    monkeypatch.setattr(db, 'db', lake_world.store)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *args: None)

    def update(ref, payload):
        assert isinstance(payload['transcript_segments'], dict)
        assert lake_world.calls['put'] == 1  # upload completed before the doc write
        lake_world.store.rows[ref.path].update(deepcopy(payload))

    monkeypatch.setattr(StrictFirestoreDocument, 'update', update, raising=False)
    assert db.update_conversation.__wrapped__(UID, CID, {'transcript_segments': speech()})
    assert (
        db.decode_transcript_segments_verified(UID, lake_world.store.rows[PATH]['transcript_segments'], True)
        == speech()
    )


def test_translation_drains_deferred_offload_for_the_document_id(lake_world, monkeypatch):
    pointer_doc(lake_world)
    drain = Mock(return_value=True)
    monkeypatch.setattr(pointer, 'offload_inline_transcript', drain)
    assert db.materialize_translation(
        UID, CID, 'segment-1', speech()[0]['text'], 'es', 'Synthetic translation', firestore_client=lake_world.store
    )
    drain.assert_called_once()
    assert drain.call_args.args == (UID, CID)
    assert drain.call_args.kwargs['firestore_client'] is lake_world.store
    assert len(drain.call_args.kwargs['expected_sha256']) == 64


def test_create_if_absent_preloads_and_drains_notes_identity_reencode(lake_world, monkeypatch):
    doc = encode()
    doc.update(data_protection_level='standard', status='completed', created_at=NOW, _notes_identity={})
    pointer.clear_memo()
    monkeypatch.setattr(db, 'db', lake_world.store)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *args: None)
    drain = Mock(return_value=True)
    monkeypatch.setattr(pointer, 'offload_inline_transcript', drain)

    def stage(transaction, user_ref, data, existing):
        assert pointer._client.in_transaction_body()
        segments = db.decode_transcript_segments_verified(UID, data['transcript_segments'], True)
        segments[0]['is_user'] = True
        data.update(
            db._prepare_conversation_for_write({'transcript_segments': segments}, UID, 'standard', conversation_id=CID)
        )
        data.pop('_notes_identity', None)

    monkeypatch.setattr(db, '_stage_notes_identity', stage)
    # Payload is already protected exactly as the write decorator supplies it;
    # the transaction owner and identity callback are the real product path.
    assert inspect.unwrap(db.create_conversation_if_absent_with_lifecycle)(UID, doc)
    assert lake_world.calls == {'get': 1, 'put': 1}
    assert isinstance(lake_world.store.rows[PATH]['transcript_segments'], bytes)
    drain.assert_called_once()
    assert drain.call_args.args == (UID, CID)


@pytest.mark.parametrize('writer', ['upsert', 'persist'])
@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_processing_owners_preload_existing_transcript(lake_world, monkeypatch, writer, state):
    doc = pointer_doc(lake_world)
    doc.update(status='processing', has_transcript_corrections=True, discarded=False)
    client = DreamFirestore()
    client.rows[PATH] = deepcopy(doc)
    payload = dict(doc, status='completed')
    monkeypatch.setattr(db, 'db', client)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *args: None)
    monkeypatch.setattr(db, 'stop_quiet_check_for_conversation', lambda *args, **kwargs: None)
    if state != 'present':
        failure = {
            'absent': lake.LakeObjectAbsent,
            'shredded': space_keys.SpaceKeyDestroyed,
            'outage': lake.LakeFetchError,
        }[state]
        monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    fn = db.upsert_conversation_with_lifecycle if writer == 'upsert' else db.persist_processing_result_with_lifecycle
    operation = lambda: inspect.unwrap(fn)(UID, deepcopy(payload))
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
    elif state != 'present' and writer == 'upsert':
        with pytest.raises((pointer.TranscriptBlobAbsent, pointer.TranscriptShredded)):
            operation()
    else:
        result = operation()
        if writer == 'persist':
            assert result is (state == 'present')
    if state == 'present':
        assert lake_world.calls['get'] == 1
    else:
        assert client.rows[PATH] == doc


def test_level_migration_keeps_lake_envelope_without_fetch(lake_world, monkeypatch):
    doc = pointer_doc(lake_world)
    ref = lake_world.store.collection('users').document(UID).collection('conversations').document(CID)
    snapshot = ref.get()
    snapshot.reference, snapshot.id = ref, CID
    monkeypatch.setattr(lake_world.store, 'get_all', lambda *args, **kwargs: [snapshot])
    # No photos in this transcript-only case; any batch update is a test failure.
    monkeypatch.setattr(
        lake_world.store,
        'batch',
        lambda: SimpleNamespace(update=Mock(side_effect=AssertionError('unexpected photo write')), commit=Mock()),
        raising=False,
    )
    original = StrictFirestoreDocument.collection

    def collection(document, name):
        if name == 'photos':
            return SimpleNamespace(select=lambda fields: SimpleNamespace(stream=lambda: iter(())))
        return original(document, name)

    monkeypatch.setattr(StrictFirestoreDocument, 'collection', collection)
    monkeypatch.setattr(db, 'db', lake_world.store)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *args: None)
    db.migrate_conversations_level_batch(UID, [CID], 'enhanced')
    assert lake_world.store.rows[PATH]['transcript_segments'] == doc['transcript_segments']
    assert lake_world.store.rows[PATH]['data_protection_level'] == 'enhanced'
    assert lake_world.calls == {'get': 0, 'put': 1}


@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_final_pass_transaction_preloads(lake_world, monkeypatch, state):
    pointer_doc(lake_world)
    original = StrictFirestoreDocument.get

    def get(ref, *args, **kwargs):
        snapshot = original(ref, *args, **kwargs)
        snapshot.update_time = NOW
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    monkeypatch.setattr(db, 'authoritative_for', lambda uid: True)
    monkeypatch.setattr(pointer, 'offload_inline_transcript', lambda *args, **kwargs: True)
    if state != 'present':
        failure = {
            'absent': lake.LakeObjectAbsent,
            'shredded': space_keys.SpaceKeyDestroyed,
            'outage': lake.LakeFetchError,
        }[state]
        monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    candidate = TranscriptSegment(**dict(speech()[0], id='candidate', speaker_id=1, is_user=False))
    operation = lambda: db.promote_final_pass_if_current(
        UID, CID, [candidate], expected_updated_at=NOW, clock_offset=0, firestore_client=lake_world.store
    )
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
    else:
        assert operation() is (state == 'present')
    if state == 'present':
        assert lake_world.calls['get'] == 1


@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_smart_merge_transaction_preloads_both_rows(lake_world, monkeypatch, state):
    pointer_doc(lake_world)
    donor = db.encode_conversation_for_write(UID, {'id': 'donor', 'transcript_segments': speech(21000)})
    donor['status'] = 'completed'
    lake_world.store.rows[('users', UID, 'conversations', 'donor')] = donor
    pointer.clear_memo()
    monkeypatch.setattr(smart_merge, 'smart_merge_flatten_enabled', lambda: False)
    if state != 'present':
        failure = {
            'absent': lake.LakeObjectAbsent,
            'shredded': space_keys.SpaceKeyDestroyed,
            'outage': lake.LakeFetchError,
        }[state]
        monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    operation = lambda: smart_merge.absorb_conversation(
        UID,
        CID,
        'donor',
        expected_revision=0,
        plan=lambda *args: ('synthetic_stop', None, None, None),
        firestore_client=lake_world.store,
    )
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
    else:
        result = operation()
        assert result.outcome == 'rejected'
        assert result.reason == ('synthetic_stop' if state == 'present' else 'conversation_not_eligible')
    if state == 'present':
        assert lake_world.calls['get'] == 2


@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_privacy_scrub_transaction_resolves_pointer_but_writes_inline(lake_world, monkeypatch, state):
    segments = speech()
    segments[0]['recurring_voice_id'] = 'expired'
    doc = pointer_doc(lake_world, segments)
    store = DreamFirestore()
    store.rows[PATH] = deepcopy(doc)
    if state != 'present':
        failure = {
            'absent': lake.LakeObjectAbsent,
            'shredded': space_keys.SpaceKeyDestroyed,
            'outage': lake.LakeFetchError,
        }[state]
        monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            recurring_voice_privacy.scrub_transcripts(UID, firestore_client=store)
    else:
        recurring_voice_privacy.scrub_transcripts(UID, firestore_client=store)
    if state == 'present':
        raw = store.rows[PATH]['transcript_segments']
        assert isinstance(raw, bytes)
        assert 'recurring_voice_id' not in pointer.decode_stored_transcript(UID, raw, True)[0]
        assert lake_world.calls['get'] == 1
    else:
        assert store.rows[PATH] == doc


@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_legacy_review_undo_preloads_pointer_field_states(lake_world, monkeypatch, state):
    before = encode()
    after = db.encode_conversation_for_write(UID, {'id': CID, 'transcript_segments': speech(21000)})
    after.update(data_protection_level='standard', status='completed', has_transcript_corrections=True)
    lake_world.store.rows[PATH] = after
    change = ReviewChange(change_id='legacy-change', kind='other', title='Synthetic', created_at=NOW)
    journal = {
        'change': change.model_dump(mode='python'),
        'created_at': NOW,
        'edit_key': 'legacy-key',
        'edits': [
            {
                'collection': 'conversations',
                'document_id': CID,
                'before': {'transcript_segments': {'present': True, 'value': before['transcript_segments']}},
                'after': {'transcript_segments': {'present': True, 'value': after['transcript_segments']}},
            }
        ],
    }
    lake_world.store.rows[('users', UID, 'review_changes', review_store.safe_id('legacy-change'))] = (
        review_store.encode_doc(UID, journal)
    )
    lake_world.store.rows[('users', UID, 'transcript_corrections', CID)] = review_store.encode_doc(UID, {'source': []})
    pointer.clear_memo()
    monkeypatch.setattr(review_store, 'get_firestore_client', lambda: lake_world.store)
    monkeypatch.setattr(review_changes, 'sync_conversations', lambda *args, **kwargs: None)
    monkeypatch.setattr(review_changes, 'record_undo', lambda *args: None)
    if state != 'present':
        failure = {
            'absent': lake.LakeObjectAbsent,
            'shredded': space_keys.SpaceKeyDestroyed,
            'outage': lake.LakeFetchError,
        }[state]
        monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    operation = lambda: review_changes.set_undone(UID, 'legacy-change', True, now=NOW)
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
    elif state != 'present':
        with pytest.raises(review_store.ReviewConflict):
            operation()
    else:
        assert operation().undone
        assert lake_world.calls['get'] == 2


def test_explicit_document_identity_wins_over_payload_identity(lake_world):
    encoded = db._prepare_conversation_for_write(
        {'id': 'payload-alias', 'transcript_segments': speech()}, UID, 'standard', conversation_id=CID
    )
    assert f'/transcript/{CID}/' in encoded['transcript_segments']['key']
    assert lake_world.calls['put'] == 1


def _pointer_failure(monkeypatch, state):
    if state != 'present':
        failure = {
            'absent': lake.LakeObjectAbsent,
            'shredded': space_keys.SpaceKeyDestroyed,
            'outage': lake.LakeFetchError,
        }[state]

        def fail(ref):
            assert not pointer._client.in_transaction_body()
            raise failure('synthetic')

        monkeypatch.setattr(lake, 'get_space_object', fail)


@pytest.mark.parametrize('surface', ['list', 'mcp'])
def test_absent_pointer_is_filtered_from_collections(lake_world, monkeypatch, surface):
    doc = pointer_doc(lake_world)
    doc.update(discarded=False, has_photos=False, created_at=NOW, started_at=NOW, finished_at=NOW)
    lake_world.store.rows[PATH] = doc
    transport = _ReadSurface(lake_world)
    monkeypatch.setattr(db, 'db', transport)
    monkeypatch.setattr(db, '_collect_visible_conversation_page', lambda *a, **kw: [deepcopy(doc)])
    _pointer_failure(monkeypatch, 'absent')
    rows = (
        db.get_conversations(UID)
        if surface == 'list'
        else db.get_mcp_conversations_by_id(UID, [CID], include_transcript=True, firestore_client=transport)
    )
    assert rows == []


@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_empty_recording_cleanup_preloads_and_refuses_unknown_content(lake_world, monkeypatch, state):
    doc = pointer_doc(lake_world)
    doc['status'] = 'in_progress'
    lake_world.store.rows[PATH] = doc
    monkeypatch.setattr(recording_sessions, 'stop_quiet_check_for_conversation', lambda *a, **kw: None)
    monkeypatch.setattr(recording_sessions, 'invalidate_people_stats_cache', lambda *a: None)
    _pointer_failure(monkeypatch, state)
    operation = lambda: recording_sessions.tombstone_and_delete_empty_conversation(
        UID, CID, None, firestore_client=lake_world.store
    )
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
        assert lake_world.store.rows[PATH] == doc
    else:
        assert operation() is (state in {'absent', 'shredded'})
        assert (PATH in lake_world.store.rows) is (state == 'present')
    if state == 'present':
        assert lake_world.calls['get'] == 1


@pytest.mark.parametrize('trigger', ['capture_end', 'server_recovery'])
@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_finalization_admission_preloads_before_outbox_writes(lake_world, monkeypatch, state, trigger):
    doc = pointer_doc(lake_world)
    doc.update(status='in_progress', source='omi', finished_at=NOW, last_speech_at=NOW, has_photos=False)
    lake_world.store.rows[PATH] = doc

    # StrictFirestore intentionally has no photo-query model; this boundary
    # returns the empty legacy photo probe, enforcing its transaction ordering.
    def limit(collection, count):
        assert collection._path[-1] == 'photos' and count == 1

        def stream(transaction):
            transaction._assert_read_allowed()
            return iter(())

        return SimpleNamespace(stream=stream)

    monkeypatch.setattr(StrictFirestoreCollection, 'limit', limit, raising=False)
    # Projection transforms have their own tests; keep this fake focused on
    # admission snapshot reads and durable outbox writes.
    monkeypatch.setattr(jobs, '_record_projection_delta', lambda *a, **kw: None)
    monkeypatch.setattr(jobs, 'quiet_finalization_enabled', lambda: False)
    monkeypatch.setattr(jobs, 'stop_quiet_check_for_conversation', lambda *a, **kw: None)
    monkeypatch.setattr(jobs, 'invalidate_people_stats_cache', lambda *a: None)
    _pointer_failure(monkeypatch, state)
    operation = lambda: jobs.create_or_get_finalization_intent(
        UID,
        CID,
        requires_byok=False,
        finalization_admission=lambda row: dict(accepted=True, terminal=False, reason='accepted', fanout_key='test'),
        trigger=jobs.ProcessingTrigger(trigger),
        recovery_cutoff=NOW + timedelta(days=1),
        firestore_client=lake_world.store,
    )
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
        assert lake_world.store.rows[PATH] == doc
        assert not any(key[0] == jobs.FINALIZATION_JOBS_COLLECTION for key in lake_world.store.rows)
    else:
        result = operation()
        assert result['created'] is (state == 'present')
        if state == 'present':
            assert lake_world.calls['get'] == 1


@pytest.mark.parametrize('site', ['memo_check', 'memo_finish', 'timeline'])
@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_episode_memo_owners_preload(lake_world, monkeypatch, site, state):
    doc = pointer_doc(lake_world)
    doc.update(source='omi', started_at=NOW, finished_at=NOW + timedelta(seconds=12), episode_id='episode')
    lake_world.store.rows[PATH] = doc
    row = {**doc, 'transcript_segments': speech()}
    key = content_key(row)
    assert key
    link_path = ('users', UID, 'episode_links', CID)
    lake_world.store.rows[link_path] = dict(
        episode_id='episode',
        attach_owner_id='episode',
        attach_revision=key,
        attach_completed=key if site == 'memo_check' else None,
    )
    monkeypatch.setattr(memo, 'content_gate_enabled', lambda: True)
    monkeypatch.setattr(timeline, 'content_gate_enabled', lambda: True)
    monkeypatch.setattr(episode_recorded_components, 'attach', lambda *a, **kw: {'id': 'episode'})
    _pointer_failure(monkeypatch, state)
    if site == 'memo_check':
        operation = lambda: memo.matches(UID, CID, row, firestore_client=lake_world.store)
    elif site == 'memo_finish':
        operation = lambda: memo.complete(UID, CID, row, {'id': 'episode'}, firestore_client=lake_world.store)
    else:
        operation = lambda: timeline.attach_recorded(
            UID,
            CID,
            'omi',
            NOW,
            NOW + timedelta(seconds=12),
            choose=lambda *a: None,
            new_episode={},
            attach_row=row,
            firestore_client=lake_world.store,
        )
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
    else:
        result = operation()
        if site == 'memo_check':
            assert result is (state == 'present')
        else:
            assert (lake_world.store.rows[link_path].get('attach_completed') == key) is (
                state == 'present' and site == 'memo_finish'
            )
    if state == 'present':
        assert lake_world.calls['get'] == 1


@pytest.mark.parametrize('site', ['profile', 'auto_enroll'])
@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_speaker_publication_owners_preload(lake_world, monkeypatch, site, state):
    doc = pointer_doc(lake_world, [dict(speech()[0], person_id='p', is_user=False)])
    doc['manual_speaker_assignments'] = {'generation': 1}
    doc['private_cloud_sync_enabled'] = True
    lake_world.store.rows[PATH] = doc
    lake_world.store.rows[('users', UID)] = dict(save_other_voice_profiles=True, private_cloud_sync_enabled=True)
    lake_world.store.rows[('users', UID, 'people', 'p')] = {'id': 'p', 'updated_at': NOW}
    monkeypatch.setattr(users, 'db', lake_world.store)
    monkeypatch.setattr(users, 'shadow_profile', lambda *a: None)
    monkeypatch.setattr(policy, 'enabled', lambda: True)
    monkeypatch.setattr(policy, 'retained', lambda row: True)
    # Stop after real current-source authorization; policy scoring is unrelated
    # to whether a cold pointer is resolved by the publication owner.
    candidate = Mock(return_value=None)
    monkeypatch.setattr(policy, 'candidate', candidate)
    _pointer_failure(monkeypatch, state)
    if site == 'profile':
        operation = lambda: users.replace_person_speech_profile(
            UID, 'p', NOW, 'sample', 'text', [0.1], CID, ['segment-1'], expected_receipt_generation=1
        )
    else:
        operation = lambda: auto.publish(UID, 'p', CID, ['segment-1'], {}, NOW, 1, firestore_client=lake_world.store)
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
        assert lake_world.store.rows[('users', UID, 'people', 'p')]['updated_at'] == NOW
    else:
        result = operation()
        if site == 'profile':
            assert (result == []) is (state == 'present')
        else:
            assert result is False
            assert candidate.called is (state == 'present')
    if state == 'present':
        assert lake_world.calls['get'] == 1


@pytest.mark.parametrize('role', ['candidate', 'canonical', 'target'])
@pytest.mark.parametrize('state', ['present', 'absent', 'shredded', 'outage'])
def test_sync_load_validates_pointer_before_selection(lake_world, monkeypatch, role, state):
    doc = pointer_doc(lake_world)
    doc.update(
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=12),
        source='omi',
        client_device_id='pendant',
        sync_content_revision=1,
        sync_merged_from=[],
        discarded=False,
    )
    lake_world.store.rows[PATH] = deepcopy(doc)
    incoming = dict(
        id=CID if role == 'canonical' else 'new',
        started_at=NOW + timedelta(seconds=12),
        finished_at=NOW + timedelta(seconds=24),
        source='omi',
        client_device_id='pendant',
        status='completed',
        discarded=False,
        transcript_segments=[dict(speech(100)[0], id='new-segment')],
    )
    _pointer_failure(monkeypatch, state)

    def decode(row):
        return {
            **row,
            'transcript_segments': db.decode_transcript_segments_verified(
                UID, row.get('transcript_segments', []), bool(row.get('transcript_segments_compressed'))
            ),
        }

    def body(transaction):
        return assign_in_transaction(
            transaction,
            lake_world.store.collection('users').document(UID),
            incoming,
            candidate_id=CID if role == 'candidate' else None,
            target_id=CID if role == 'target' else None,
            decode=decode,
            encode=deepcopy,
            invalidate=lambda row: None,
        )

    operation = lambda: pointer.run_preloaded_transactional(lake_world.store, body)
    if state == 'outage':
        with pytest.raises(pointer.TranscriptPointerFetchError):
            operation()
        assert lake_world.store.rows[PATH] == doc
    elif state in {'absent', 'shredded'} and role == 'canonical':
        with pytest.raises(SyncAssignmentSuperseded):
            operation()
        assert lake_world.store.rows[PATH] == doc
    else:
        result, created, _ = operation()
        assert result['id'] == ('new' if state != 'present' else CID)
        assert created is (state != 'present')
        if state != 'present':
            assert lake_world.store.rows[PATH] == doc
    if state == 'present':
        assert lake_world.calls['get'] == 1

"""Pointer-mode domain refusals, reader surfaces and C1 review follow-ups."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock
import zlib

from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists
from pydantic import ValidationError
import pytest

from database import conversations as db, transcript_pointer as pointer
from database import owner_confirmation, review_overlay_merge, review_store, episodes
from models.conversation import Conversation
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
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


@pytest.mark.parametrize('malformation', ['wrapped', 'versions', 'algo', 'version'])
def test_malformed_key_rows_are_retryable_even_after_cache_hit(lake_world, malformation):
    encode()
    doc = lake_world.store.rows[('space_keys', UID)]
    if malformation == 'wrapped':
        doc['versions'][0]['wrapped'] = ''
    elif malformation == 'versions':
        doc['versions'] = []
    elif malformation == 'algo':
        doc['algo'] = 'unknown'
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
    from database import speaker_resolution_updates
    from utils.conversations.transcript_hash import transcript_sha256_for_binding

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
    from utils.conversations import transcript_chunks

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
    from database import review_transcript_changes, memory_ledger
    from models.review import ReviewChange, ChangeRef

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
    from database import speaker_learning_jobs

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

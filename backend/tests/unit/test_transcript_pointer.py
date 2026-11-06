"""Hermetic codec, guard and deferred-CAS contracts, using real lake envelopes."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import random
from types import SimpleNamespace
from unittest.mock import Mock
import zlib

from google.api_core.exceptions import FailedPrecondition
import pytest

from database import _client, conversations as conversations_db, transcript_pointer as pointer
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils import encryption
from utils.other import object_lake as lake, space_keys
from utils.other.local_storage import LocalStorageClient, LocalBlob

UID = 'lake-owner'
CID = 'lake-conversation'
PATH = ('users', UID, 'conversations', CID)


def speech(size=18000):
    return [
        {'id': 'segment-1', 'text': random.Random(71).randbytes(size).hex(), 'start': 0.0, 'end': 12.0, 'speaker_id': 0}
    ]


@pytest.fixture
def lake_world(tmp_path, monkeypatch):
    for name, value in {
        'BUCKET_OBJECT_LAKE': 'test-transcript-lake',
        'OBJECT_LAKE_WRITE_ENABLED': 'true',
        'OBJECT_LAKE_WRITE_PERCENT': '100',
        'OBJECT_LAKE_RELEASE': 'v1',
        'OBJECT_LAKE_READ_ENABLED': 'true',
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv('OBJECT_LAKE_KMS_KEY', raising=False)
    monkeypatch.delenv('OBJECT_LAKE_KMS_FAKE_SECRET', raising=False)
    monkeypatch.delenv('OBJECT_LAKE_INLINE_MAX_BYTES', raising=False)
    store = StrictFirestore()
    bucket = LocalStorageClient(tmp_path).bucket('test-transcript-lake')
    monkeypatch.setattr(lake, '_lake_bucket', lambda: bucket)
    monkeypatch.setattr(
        space_keys, 'space_key_firestore_client', lambda client=None: store if client is None else client
    )
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(_client, 'get_data_plane_firestore_client', lambda: store)
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda uid: None)
    calls = {'get': 0, 'put': 0}
    for attr, kind in [('download_as_bytes', 'get'), ('upload_from_string', 'put')]:
        original = getattr(LocalBlob, attr)

        def counted(self, *args, _original=original, _kind=kind, **kwargs):
            assert not _client.in_transaction_body(), 'lake IO inside transaction'
            calls[_kind] += 1
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(LocalBlob, attr, counted)
    pointer.clear_memo()
    space_keys.clear_space_key_cache()
    yield SimpleNamespace(store=store, bucket=bucket, calls=calls)
    pointer.clear_memo()
    space_keys.clear_space_key_cache()


def encode(segments=None, level='standard'):
    return conversations_db.encode_conversation_for_write(
        UID, {'id': CID, 'transcript_segments': segments or speech()}, level
    )


def pointer_doc(world, segments=None):
    doc = encode(segments)
    doc.update(status='completed', data_protection_level='standard')
    world.store.rows[PATH] = deepcopy(doc)
    pointer.clear_memo()
    return doc


def test_round_trip_single_field_and_path(lake_world):
    doc = encode()
    ref = lake.LakeObjectRef.from_pointer_dict(doc['transcript_segments'])
    assert ref.key == f'v1/spaces/{UID}/transcript/{CID}/{ref.sha256}'
    assert doc['transcript_segments_compressed'] is True
    assert conversations_db.decode_transcript_segments_verified(UID, doc['transcript_segments'], True) == speech()
    assert lake_world.calls == {'get': 0, 'put': 1}
    pointer.clear_memo()
    assert conversations_db.decode_transcript_segments_verified(UID, doc['transcript_segments'], True) == speech()
    assert lake_world.calls == {'get': 1, 'put': 1}


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_flag_off_golden_encoding(lake_world, monkeypatch, level):
    monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'false')
    # Pin pre-C2 zlib+JSON bytes; enhanced encryption's randomness is replaced
    # at its existing seam so the full emitted document can be compared.
    monkeypatch.setattr(encryption, 'encrypt', lambda value, uid: 'encrypted:' + value)
    segments = speech()
    compressed = zlib.compress(json.dumps(segments).encode())
    expected = compressed if level == 'standard' else 'encrypted:' + compressed.hex()
    doc = encode(segments, level)
    assert doc == {
        'id': CID,
        'transcript_segments': expected,
        'transcript_segments_compressed': True,
        'recording_speaker_scopes': [],
    }
    assert lake_world.calls == {'get': 0, 'put': 0}


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_threshold_uses_compressed_bytes(lake_world, monkeypatch, level):
    segments = speech(50)
    size = len(zlib.compress(json.dumps(segments).encode()))
    monkeypatch.setenv('OBJECT_LAKE_INLINE_MAX_BYTES', str(size))
    assert not isinstance(encode(segments, level)['transcript_segments'], dict)
    monkeypatch.setenv('OBJECT_LAKE_INLINE_MAX_BYTES', str(size - 1))
    assert isinstance(encode(segments, level)['transcript_segments'], dict)


def test_cold_transaction_reloads_outside_body(lake_world):
    doc = pointer_doc(lake_world)
    attempts = []

    def body(transaction):
        assert _client.in_transaction_body()
        attempts.append(1)
        return pointer.decode_stored_transcript(UID, doc['transcript_segments'], True)

    assert pointer.run_preloaded_transactional(lake_world.store, body) == speech()
    assert len(attempts) == 2
    assert lake_world.calls['get'] == 1
    assert pointer._MEMO.get() is None


def test_direct_transaction_guard_cold_read_and_deferred_encode(lake_world):
    doc = pointer_doc(lake_world)

    def body(transaction):
        with pytest.raises(pointer.TranscriptPointerUnloaded):
            pointer.resolve_pointer(UID, doc['transcript_segments'])
        result = encode(speech(22000))
        assert isinstance(result['transcript_segments'], bytes)
        assert pointer._memo().deferred

    _client.run_transactional(lake_world.store, body)
    assert lake_world.calls['get'] == 0
    assert lake_world.calls['put'] == 1
    assert not _client.in_transaction_body()


def test_changed_pointer_preloads_again(lake_world):
    first = pointer_doc(lake_world)
    second = encode(speech(21000))
    pointer.clear_memo()
    attempts = []

    def body(transaction):
        attempts.append(1)
        raw = first if len(attempts) == 1 else second
        return pointer.resolve_pointer(UID, raw['transcript_segments'])

    assert pointer.run_preloaded_transactional(lake_world.store, body) == speech(21000)
    assert len(attempts) == 3
    assert lake_world.calls['get'] == 2


def test_preload_churn_is_bounded_and_typed(lake_world):
    docs = [encode(speech(n)) for n in [18000, 19000, 20000]]
    pointer.clear_memo()
    attempts = []

    def body(transaction):
        raw = docs[len(attempts)]
        attempts.append(1)
        return pointer.resolve_pointer(UID, raw['transcript_segments'])

    with pytest.raises(pointer.TranscriptPointerFetchError, match='bounded'):
        pointer.run_preloaded_transactional(lake_world.store, body)
    assert len(attempts) == 3


@pytest.mark.parametrize(
    'failure,expected',
    [
        (lake.LakeFetchError, pointer.TranscriptPointerFetchError),
        (space_keys.SpaceKeyUnavailable, pointer.TranscriptPointerFetchError),
        (lake.ObjectLakeNotConfigured, pointer.TranscriptPointerFetchError),
        (lake.LakeObjectAbsent, pointer.TranscriptBlobAbsent),
        (space_keys.SpaceKeyDestroyed, pointer.TranscriptShredded),
        (lake.LakeObjectCorrupt, pointer.TranscriptSegmentsDecodeError),
    ],
)
def test_error_taxonomy_inside_and_outside_transactions(lake_world, monkeypatch, failure, expected):
    doc = pointer_doc(lake_world)
    monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=failure('synthetic')))
    for transactional in [False, True]:
        pointer.clear_memo()

        def body(*args):
            return conversations_db.decode_transcript_segments_verified(UID, doc['transcript_segments'], True)

        with pytest.raises(expected):
            pointer.run_preloaded_transactional(lake_world.store, body) if transactional else body()


def test_read_disabled_even_on_warm_memo(lake_world, monkeypatch):
    doc = encode()
    monkeypatch.setenv('OBJECT_LAKE_READ_ENABLED', 'false')
    with pytest.raises(pointer.TranscriptPointerFetchError):
        pointer.resolve_pointer(UID, doc['transcript_segments'])


def test_memo_eviction_and_uploaded_reuse(lake_world):
    first = encode()
    assert encode() == first
    assert lake_world.calls['put'] == 1
    memo = pointer._memo()
    for n in range(33):
        memo.decoded[('synthetic', n)] = []
    assert len(memo.decoded) == 32
    assert (
        pointer._memo_key(UID, lake.LakeObjectRef.from_pointer_dict(first['transcript_segments'])) not in memo.decoded
    )
    pointer.clear_memo()
    assert not pointer._memo().decoded


def test_memo_validates_full_pointer_and_owner(lake_world):
    doc = encode()
    ref = doc['transcript_segments']
    with pytest.raises(pointer.TranscriptSegmentsDecodeError):
        pointer.decode_stored_transcript('different-owner', ref, True)
    altered = dict(ref, bytes=ref['bytes'] + 1)
    with pytest.raises(pointer.TranscriptSegmentsDecodeError):
        pointer.decode_stored_transcript(UID, altered, True)


@pytest.mark.parametrize('opt_in,expected', [(True, 'opt_in'), (False, 'opt_out'), (None, 'unknown')])
def test_ingest_consent(lake_world, opt_in, expected):
    lake_world.store.rows[('users', UID)] = {} if opt_in is None else {'training_data_opt_in': opt_in}
    doc = encode()
    blob = lake_world.bucket.blob(doc['transcript_segments']['key'])
    blob.reload()
    assert blob.metadata['consent'] == expected


@pytest.mark.parametrize('state', ['completed', 'in_progress', 'deleted', 'pointer', 'conflict', 'changed'])
def test_deferred_swap_cas_and_skip_policy(lake_world, monkeypatch, state):
    segments = speech()
    monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'false')
    doc = encode(segments)
    doc['status'] = 'in_progress' if state == 'in_progress' else 'completed'
    doc['deleted'] = state == 'deleted'
    monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'true')
    if state == 'pointer':
        doc = encode(segments)
    lake_world.store.rows[PATH] = deepcopy(doc)
    original_get = StrictFirestoreDocument.get

    def get(ref, *args, **kwargs):
        snapshot = original_get(ref, *args, **kwargs)
        snapshot.update_time = 'revision-7'
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    monkeypatch.setattr(lake_world.store, 'write_option', lambda **kw: kw, raising=False)

    def update(ref, patch, option):
        assert option == {'last_update_time': 'revision-7'}
        assert lake_world.calls['put'] == 1  # upload precedes pointer commit
        if state == 'conflict':
            raise FailedPrecondition('concurrent change')
        lake_world.store.rows[ref.path].update(deepcopy(patch))

    monkeypatch.setattr(StrictFirestoreDocument, 'update', update, raising=False)
    expected = hashlib.sha256(json.dumps(segments).encode()).hexdigest() if state != 'changed' else '0' * 64
    result = pointer.offload_inline_transcript(UID, CID, firestore_client=lake_world.store, expected_sha256=expected)
    assert result is (state == 'completed')
    if result:
        assert isinstance(lake_world.store.rows[PATH]['transcript_segments'], dict)
        assert not pointer.offload_inline_transcript(UID, CID, firestore_client=lake_world.store)
    elif state != 'pointer':
        assert isinstance(lake_world.store.rows[PATH]['transcript_segments'], bytes)

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
from cachetools import TTLCache

from database import _client, conversations as conversations_db, transcript_pointer as pointer
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
from tests.unit.fixtures.lake_firestore import LakeFirestore as StrictFirestore
from tests.unit.memory_import_isolation import make_database_client_stub
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
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')  # FakeKMS is admitted only offline
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
        UID,
        {'id': CID, 'transcript_segments': segments or speech()},
        level,
        conversation_state={'visibility': 'shared'},
    )


def pointer_doc(world, segments=None, *, visibility=None):
    doc = encode(segments)
    # Existing pointers remain readable at any visibility, including historical
    # private rows; only tests exercising new uploads opt into shared visibility.
    doc.update(status='completed', data_protection_level='standard')
    if visibility is not None:
        doc['visibility'] = visibility
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
    assert not pointer._memo().resolved  # ordinary readers do not retain attempt bookkeeping


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


@pytest.mark.parametrize('binding', ['BUCKET_OBJECT_LAKE', 'OBJECT_LAKE_RELEASE'])
@pytest.mark.parametrize('value', [None, '', '   '])
def test_incomplete_lake_bindings_close_write_admission(lake_world, monkeypatch, binding, value):
    if value is None:
        monkeypatch.delenv(binding)
    else:
        monkeypatch.setenv(binding, value)
    if binding == 'OBJECT_LAKE_RELEASE' and value is None:
        assert pointer.config.write_admitted(UID)  # release defaults to v1
        return
    assert not pointer.config.write_admitted(UID)
    put = Mock(side_effect=AssertionError('put attempted without lake bindings'))
    monkeypatch.setattr(lake, 'put_space_object', put)
    assert isinstance(encode()['transcript_segments'], bytes)
    put.assert_not_called()


@pytest.mark.parametrize('stage', ['', 'dev', 'prod'])
def test_deployed_stage_without_kms_key_closes_write_admission(lake_world, monkeypatch, stage):
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    assert not pointer.config.write_admitted(UID)
    put = Mock(side_effect=AssertionError('put attempted under FakeKMS on a deployed stage'))
    monkeypatch.setattr(lake, 'put_space_object', put)
    assert isinstance(encode()['transcript_segments'], bytes)
    put.assert_not_called()
    monkeypatch.setenv('OBJECT_LAKE_KMS_KEY', 'projects/p/locations/l/keyRings/r/cryptoKeys/k')
    # Per-object DEKs lift the cryptographic stage fence for dev. Production and
    # unknown stages stay refused at runtime and in deployment validation until C4.
    assert pointer.config.write_admitted(UID) == (stage == 'dev')
    assert bool(pointer.config.validate_write_settings(stage, 'true', '100')) == (stage != 'dev')


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


def test_direct_transaction_guard_cold_read_and_candidate_upload(lake_world):
    doc = pointer_doc(lake_world)

    def body(transaction):
        with pytest.raises(pointer.TranscriptPointerUnloaded):
            pointer.resolve_pointer(UID, doc['transcript_segments'])
        with pytest.raises(pointer.TranscriptUploadRequired):
            encode(speech(22000))

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
    docs = [encode(speech(n)) for n in range(18000, 18005)]
    pointer.clear_memo()
    attempts = []

    def body(transaction):
        raw = docs[len(attempts)]
        attempts.append(1)
        return pointer.resolve_pointer(UID, raw['transcript_segments'])

    with pytest.raises(pointer.TranscriptPointerFetchError, match='bounded'):
        pointer.run_preloaded_transactional(lake_world.store, body)
    assert len(attempts) == 5
    assert lake_world.calls['get'] == 4


def test_candidate_upload_churn_is_bounded_and_never_commits(lake_world):
    attempts = []

    def body(transaction):
        attempts.append(1)
        result = encode(speech(18000 + len(attempts)))
        transaction.set(
            lake_world.store.collection('users').document(UID).collection('conversations').document(CID), result
        )

    with pytest.raises(pointer.TranscriptPointerFetchError, match='bounded upload retries'):
        pointer.run_preloaded_transactional(lake_world.store, body)
    assert len(attempts) == 5
    assert lake_world.calls['put'] == 4
    assert PATH not in lake_world.store.rows
    assert pointer._MEMO.get() is None
    assert_all_uploads_recorded(lake_world, expected=4)


def assert_all_uploads_recorded(world, *, expected):
    blobs = list(world.bucket.list_blobs(prefix=f'v1/spaces/{UID}/transcript/'))
    assert len(blobs) == expected
    for blob in blobs:
        candidate_id = hashlib.sha256(f'{world.bucket.name}/{blob.name}'.encode()).hexdigest()
        candidate = world.store.rows[('lake_upload_candidates', candidate_id)]
        assert candidate['bucket'] == world.bucket.name
        assert candidate['key'] == blob.name


@pytest.mark.parametrize(
    'refusal', ['private', 'deleted', 'locked', 'kill_switch', 'protect_kill_switch', 'protect_empty', 'small', 'empty']
)
def test_replay_inline_refusal_retains_sweep_candidate(lake_world, monkeypatch, refusal):
    attempts = []

    def body(transaction):
        attempts.append(1)
        replay = len(attempts) > 1
        state = {
            'visibility': 'private' if replay and refusal == 'private' else 'shared',
            'deleted': replay and refusal == 'deleted',
            'is_locked': replay and refusal == 'locked',
        }
        if replay and refusal == 'kill_switch':
            monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'false')

        def protect(segments):
            if replay and refusal == 'protect_kill_switch':
                monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'false')
            if replay and refusal == 'protect_empty':
                segments.clear()
            return zlib.compress(json.dumps(segments).encode())

        segments = [] if replay and refusal == 'empty' else speech(10 if replay and refusal == 'small' else 18000)
        raw = pointer.offload_or_inline(UID, CID, segments, protect, conversation_state=state)
        transaction.set(
            lake_world.store.collection('users').document(UID).collection('conversations').document(CID),
            {'transcript_segments': raw},
        )
        return raw

    assert isinstance(pointer.run_preloaded_transactional(lake_world.store, body), bytes)
    assert len(attempts) == 2 and lake_world.calls['put'] == 1
    assert isinstance(lake_world.store.rows[PATH]['transcript_segments'], bytes)
    assert_all_uploads_recorded(lake_world, expected=1)


@pytest.mark.parametrize('refusal', ['return_false', 'exception', 'preload_limit', 'upload_limit'])
def test_replay_boundary_refusal_retains_sweep_candidate(lake_world, monkeypatch, refusal):
    attempts = []

    def body(transaction):
        attempts.append(1)
        if len(attempts) == 1:
            return encode()
        if refusal == 'return_false':
            return False
        if refusal == 'exception':
            raise ValueError('domain replay refused')
        if refusal == 'preload_limit':
            # Changing an unresolved reference repeatedly exhausts the bounded
            # preload retry budget after the first candidate was uploaded.
            ref = lake.LakeObjectRef.from_pointer_dict(encode()['transcript_segments'])
            raise pointer.TranscriptPointerUnloaded(UID, ref.to_pointer_dict())
        raise pointer.TranscriptUploadRequired(UID, f'other-{len(attempts)}', b'[]', 'source')

    if refusal == 'preload_limit':
        # Force no resolution progress: all 68 attempts still leave the
        # original upload covered when the final preload attempt refuses.
        monkeypatch.setattr(pointer, 'preload_pointer', lambda *args: None)
    if refusal == 'return_false':
        assert pointer.run_preloaded_transactional(lake_world.store, body) is False
    else:
        expected = ValueError if refusal == 'exception' else pointer.TranscriptPointerFetchError
        with pytest.raises(expected):
            pointer.run_preloaded_transactional(lake_world.store, body)
    assert PATH not in lake_world.store.rows
    assert_all_uploads_recorded(lake_world, expected=32 if refusal == 'upload_limit' else 1)


def test_refused_replay_never_deletes_an_already_referenced_digest(lake_world):
    doc = pointer_doc(lake_world)
    attempts = []

    def body(transaction):
        attempts.append(1)
        if len(attempts) == 1:
            return encode()
        return False

    assert pointer.run_preloaded_transactional(lake_world.store, body) is False
    assert lake_world.store.rows[PATH] == doc
    assert lake.get_space_object(lake.LakeObjectRef.from_pointer_dict(doc['transcript_segments']))
    assert_all_uploads_recorded(lake_world, expected=1)


def test_candidate_upload_failure_aborts_without_inline_write(lake_world, monkeypatch):
    doc = {'status': 'in_progress', 'transcript_segments': [], 'visibility': 'shared'}
    lake_world.store.rows[PATH] = deepcopy(doc)
    monkeypatch.setattr(lake, 'put_space_object', Mock(side_effect=lake.LakeFetchError('synthetic')))
    with pytest.raises(lake.LakeFetchError):
        conversations_db.update_conversation_segments(UID, CID, speech(), firestore_client=lake_world.store)
    assert lake_world.store.rows[PATH] == doc
    assert pointer._MEMO.get() is None


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


@pytest.mark.parametrize(
    'opt_in,expected',
    [('approved', 'opt_in'), ('rejected', 'opt_out'), ('pending_review', 'unknown'), (None, 'unknown')],
)
def test_ingest_consent(lake_world, opt_in, expected):
    lake_world.store.rows[('users', UID)] = (
        {} if opt_in is None else {'training_data_opt_in': {'status': opt_in, 'requested_at': '2026-11-06T00:00:00Z'}}
    )
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
    doc['visibility'] = 'shared'
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
    if state == 'conflict':
        assert_all_uploads_recorded(lake_world, expected=1)


def test_memo_ttl_expires_plaintext(lake_world):
    doc = encode()
    pointer.clear_memo()
    clock = [0]
    pointer._memo().decoded = TTLCache(maxsize=32, ttl=120, timer=lambda: clock[0])
    assert pointer.resolve_pointer(UID, doc['transcript_segments']) == speech()
    assert lake_world.calls['get'] == 1
    clock[0] = 121
    assert pointer.resolve_pointer(UID, doc['transcript_segments']) == speech()
    assert lake_world.calls['get'] == 2


def test_explicit_preload_cannot_fetch_inside_transaction(lake_world):
    doc = pointer_doc(lake_world)
    with pytest.raises(pointer.TranscriptPointerUnloaded):
        _client.run_transactional(
            lake_world.store, lambda txn: pointer.preload_pointer(UID, doc['transcript_segments'])
        )
    assert lake_world.calls['get'] == 0


def test_nested_runner_leaves_io_to_outer_boundary(lake_world):
    doc = pointer_doc(lake_world)
    with _client.transaction_body():
        assert pointer.run_preloaded_operation(lambda: 'nested') == 'nested'
        with pytest.raises(pointer.TranscriptUploadRequired):
            pointer.run_preloaded_operation(lambda: encode(speech(21000)))
        with pytest.raises(pointer.TranscriptPointerUnloaded):
            pointer.run_preloaded_operation(lambda: pointer.resolve_pointer(UID, doc['transcript_segments']))
    assert lake_world.calls['get'] == 0


def test_decoded_memo_aggregate_byte_budget_is_retryable(lake_world, monkeypatch):
    first = encode(speech(18000))
    second = encode(speech(18001))
    pointer.clear_memo()
    # Exercise the production aggregate accounting without allocating 64 MiB.
    monkeypatch.setattr(pointer, 'MAX_MEMO_DECODED_BYTES', 2 * pointer._decoded_bytes(speech(18000)) - 1)
    attempts = []

    def body(transaction):
        attempts.append(1)
        for doc in (first, second):
            pointer.resolve_pointer(UID, doc['transcript_segments'])

    with pytest.raises(pointer.TranscriptMemoBudgetExceeded, match='byte budget') as failure:
        pointer.run_preloaded_transactional(lake_world.store, body)
    assert isinstance(failure.value, pointer.TranscriptPointerFetchError)
    assert len(attempts) == 2
    assert lake_world.calls['get'] == 2
    assert pointer._MEMO.get() is None


def test_decoded_memo_replacement_and_expiry_release_byte_budget(lake_world, monkeypatch):
    monkeypatch.setattr(pointer, 'MAX_MEMO_DECODED_BYTES', pointer._decoded_bytes(speech(100)))
    memo = pointer._memo().decoded
    memo['same'] = speech(100)
    memo['same'] = speech(100)
    assert memo.currsize == memo.maxsize
    memo.pop('same')
    memo['next'] = speech(100)
    memo.expire(memo.timer() + 121)
    assert memo.currsize == 0
    memo['after-expiry'] = speech(100)


def test_cached_failure_does_not_retain_caller_tracebacks(lake_world, monkeypatch):
    doc = pointer_doc(lake_world)
    monkeypatch.setattr(lake, 'get_space_object', Mock(side_effect=lake.LakeObjectAbsent('synthetic')))
    errors = []
    for _ in range(2):
        with pytest.raises(pointer.TranscriptBlobAbsent) as error:
            pointer.resolve_pointer(UID, doc['transcript_segments'])
        errors.append(error.value)
    assert errors[0] is not errors[1]
    assert all(value.__traceback__ is None for value in pointer._memo().decoded.values())


def test_malformed_pointer_remains_corrupt_without_bucket_configuration(lake_world, monkeypatch):
    doc = encode()
    pointer.clear_memo()
    monkeypatch.delenv('BUCKET_OBJECT_LAKE')
    with pytest.raises(pointer.TranscriptSegmentsDecodeError):
        pointer.decode_stored_transcript(UID, {'not': 'a pointer'}, True)
    with pytest.raises(pointer.TranscriptPointerFetchError):
        pointer.decode_stored_transcript(UID, doc['transcript_segments'], True)
    assert lake_world.calls['get'] == 0


def test_expiry_during_cache_lookup_is_a_transactional_miss(lake_world):
    doc = encode()
    key = pointer._memo_key(UID, lake.LakeObjectRef.from_pointer_dict(doc['transcript_segments']))

    class ExpiringCache(TTLCache):
        armed = False

        def __getitem__(self, cache_key):
            if self.armed:
                self.armed = False
                del self[cache_key]
                raise KeyError(cache_key)
            return super().__getitem__(cache_key)

    cache = ExpiringCache(maxsize=32, ttl=120)
    cache[key] = speech()
    cache.armed = True
    pointer._memo().decoded = cache
    with pytest.raises(pointer.TranscriptPointerUnloaded):
        _client.run_transactional(
            lake_world.store, lambda txn: pointer.resolve_pointer(UID, doc['transcript_segments'])
        )
    assert lake_world.calls['get'] == 0
    assert pointer.resolve_pointer(UID, doc['transcript_segments']) == speech()
    assert lake_world.calls['get'] == 1


@pytest.mark.parametrize('count', [3, 32, 33])
def test_distinct_cold_documents_have_separate_bounded_budget(lake_world, monkeypatch, count):
    base = pointer_doc(lake_world)['transcript_segments']
    refs = [{**base, 'key': base['key'].replace(f'/{CID}/', f'/conversation-{i}/')} for i in range(count)]
    fetch = Mock(return_value=json.dumps(speech()).encode())
    monkeypatch.setattr(lake, 'get_space_object', fetch)
    attempts = []

    def body(transaction):
        attempts.append(1)
        return [pointer.resolve_pointer(UID, ref) for ref in refs]

    if count > 32:
        with pytest.raises(pointer.TranscriptPointerFetchError, match='bounded'):
            pointer.run_preloaded_transactional(lake_world.store, body)
        assert len(attempts) == 33
        assert fetch.call_count == 32
    else:
        assert pointer.run_preloaded_transactional(lake_world.store, body) == [speech()] * count
        assert len(attempts) == count + 1
        assert fetch.call_count == count


def test_superseded_versions_do_not_evict_other_cold_documents(lake_world, monkeypatch):
    docs = [encode(speech(n))['transcript_segments'] for n in range(18000, 18004)]
    others = [{**docs[0], 'key': docs[0]['key'].replace(f'/{CID}/', f'/other-{i}/')} for i in range(31)]
    pointer.clear_memo()
    monkeypatch.setattr(lake, 'get_space_object', lambda ref: json.dumps(speech()).encode())
    attempts = []

    def body(transaction):
        # Each version is actually observed before advancing the simulated
        # concurrent writer; then the remaining 31 distinct documents go cold.
        attempt = len(attempts)
        attempts.append(1)
        current = docs[min(attempt, 3)]
        result = pointer.resolve_pointer(UID, current)
        return result, [pointer.resolve_pointer(UID, ref) for ref in others]

    result, rest = pointer.run_preloaded_transactional(lake_world.store, body)
    assert result == speech() and len(rest) == 31
    assert len(attempts) == 36


def test_transaction_can_read_multiple_historical_versions_of_one_document(lake_world):
    versions = [encode(speech(n))['transcript_segments'] for n in range(18000, 18003)]
    pointer.clear_memo()
    attempts = []

    def body(transaction):
        attempts.append(1)
        return [pointer.resolve_pointer(UID, ref) for ref in versions]

    assert pointer.run_preloaded_transactional(lake_world.store, body) == [speech(n) for n in range(18000, 18003)]
    assert len(attempts) == 4
    assert lake_world.calls['get'] == 3


def test_legacy_memory_client_stub_preserves_pointer_transaction_guard(lake_world, monkeypatch):
    doc = pointer_doc(lake_world)
    client = make_database_client_stub()
    monkeypatch.setattr(pointer, '_client', client)

    def body(transaction):
        assert client.in_transaction_body()
        with pytest.raises(pointer.TranscriptPointerUnloaded):
            pointer.resolve_pointer(UID, doc['transcript_segments'])

    client.run_transactional(lake_world.store, body)
    assert not client.in_transaction_body()
    assert lake_world.calls['get'] == 0


@pytest.mark.parametrize(
    'state',
    [
        {'visibility': 'private'},
        {},
        {'visibility': 'unknown'},
        {'visibility': 'shared', 'deleted': True},
        {'visibility': 'public', 'is_locked': True},
    ],
)
def test_privacy_policy_precedes_codec_and_backfill_upload(lake_world, monkeypatch, state):
    doc = {'id': CID, 'transcript_segments': speech(), **state}
    encoded = conversations_db.encode_conversation_for_write(UID, doc)
    assert isinstance(encoded['transcript_segments'], bytes)
    lake_world.store.rows[PATH] = {**encoded, 'status': 'completed'}
    assert not pointer.offload_inline_transcript(UID, CID, firestore_client=lake_world.store)
    assert lake_world.calls == {'get': 0, 'put': 0}
    assert ('space_keys', UID) not in lake_world.store.rows


@pytest.mark.parametrize('visibility', ['shared', 'public'])
def test_privacy_policy_permits_explicit_shared_visibility(lake_world, visibility):
    doc = conversations_db.encode_conversation_for_write(
        UID, {'id': CID, 'visibility': visibility, 'transcript_segments': speech()}
    )
    assert isinstance(doc['transcript_segments'], dict)
    assert lake_world.calls['put'] == 1


@pytest.mark.parametrize(
    'current,patch',
    [
        ({'visibility': 'private'}, {'visibility': 'shared'}),
        ({'visibility': 'shared'}, {'visibility': 'private'}),
        ({'visibility': 'shared', 'deleted': True}, {'deleted': False}),
        ({'visibility': 'shared'}, {'deleted': True}),
    ],
)
def test_stale_or_partial_payload_cannot_bypass_current_privacy(lake_world, current, patch):
    encoded = conversations_db.encode_conversation_for_write(
        UID, {'id': CID, 'transcript_segments': speech(), **patch}, conversation_state=current
    )
    assert isinstance(encoded['transcript_segments'], bytes)
    assert lake_world.calls == {'get': 0, 'put': 0}

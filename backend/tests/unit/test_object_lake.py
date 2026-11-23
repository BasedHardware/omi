"""Real AES-GCM plus filesystem storage, with no cloud/service access."""

from dataclasses import replace
import hashlib
import time
import zlib
from unittest.mock import Mock, patch

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.keywrap import aes_key_unwrap
from google.api_core.exceptions import FailedPrecondition

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument, StrictFirestoreTransaction
from tests.unit.fixtures.lake_firestore import LakeFirestore as StrictFirestore
from utils.other import object_lake as lake, space_keys
from utils.other.local_storage import LocalStorageClient, LocalBlob


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv('BUCKET_OBJECT_LAKE', 'lake-test')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'true')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_PERCENT', '100')
    monkeypatch.setenv('OBJECT_LAKE_RELEASE', 'v1')
    monkeypatch.delenv('OBJECT_LAKE_KMS_KEY', raising=False)
    monkeypatch.delenv('OBJECT_LAKE_KMS_FAKE_SECRET', raising=False)
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')  # FakeKMS is admitted only offline
    store = StrictFirestore()
    space_keys.clear_space_key_cache()
    monkeypatch.setattr(
        space_keys, 'space_key_firestore_client', lambda client=None: store if client is None else client
    )
    storage_client = LocalStorageClient(tmp_path)
    monkeypatch.setattr(lake, 'create_storage_client', lambda: storage_client)
    bucket = storage_client.bucket('lake-test')
    with patch.object(lake, '_lake_bucket', return_value=bucket):
        yield bucket, store
    space_keys.clear_space_key_cache()


def put(data=b'private transcript: the meeting is at nine' * 10, **kwargs):
    return lake.put_space_object('s', 'transcript', 'c', data, **kwargs)


def test_roundtrip_and_unconditional_encryption(storage, monkeypatch):
    bucket, _ = storage
    monkeypatch.setenv('DATA_PROTECTION_LEVEL', 'standard')
    plaintext = b'private transcript: the meeting is at nine' * 10
    ref = put(plaintext)
    digest = hashlib.sha256(plaintext).hexdigest()
    assert ref.key == f'v1/spaces/s/transcript/c/{digest}'
    assert ref.bucket == bucket.name and ref.dek_version == 1 and ref.data_class == 'transcript'
    payload = bucket.blob(ref.key).download_as_bytes()
    assert ref.bytes == len(payload)
    assert payload[:9] == b'OLK1\x02\x00\x00\x00\x01'
    assert lake._HEADER_V2.size == 61
    assert ref.bytes == 61 + len(zlib.compress(plaintext, level=6)) + 16
    assert plaintext[:20] not in payload and zlib.compress(plaintext)[:12] not in payload
    assert lake.get_space_object(ref) == plaintext
    assert lake.LakeObjectRef.from_pointer_dict(ref.to_pointer_dict()) == ref
    assert ref.to_pointer_dict()['class'] == 'transcript'


def test_empty_plaintext(storage):
    assert lake.get_space_object(put(b'')) == b''


def test_upload_intent_precedes_blob_and_survives_retries(storage, monkeypatch):
    bucket, store = storage
    upload = LocalBlob.upload_from_string

    def checked_upload(blob, *args, **kwargs):
        assert kwargs['retry'] is None
        assert all(0 < value < lake.config.put_deadline_seconds() for value in kwargs['timeout'])
        assert sum(kwargs['timeout']) <= lake.config.put_deadline_seconds()
        candidate_id = hashlib.sha256(f'{bucket.name}/{blob.name}'.encode()).hexdigest()
        row = store.rows[('lake_upload_candidates', candidate_id)]
        assert set(row) == {'bucket', 'key', 'created_at', 'admitted_at', 'in_flight', 'settled'}
        assert row['settled'] is False and len(row['in_flight']) == 1
        assert all(
            value['admitted_at'].tzinfo is not None and value['session'] and value['size'] > 0
            for value in row['in_flight'].values()
        )
        assert row['bucket'] == bucket.name and row['key'] == blob.name
        assert row['created_at'].tzinfo is not None
        return upload(blob, *args, **kwargs)

    monkeypatch.setattr(LocalBlob, 'upload_from_string', checked_upload)
    first = put()
    candidates = {path: row.copy() for path, row in store.rows.items() if path[0] == 'lake_upload_candidates'}
    assert put() == first
    for path, previous in candidates.items():
        row = store.rows[path]
        assert row['created_at'] == previous['created_at']
        assert row['admitted_at'] >= previous['admitted_at']
        assert row['settled'] is True and row['in_flight'] == {}


@pytest.mark.parametrize('replay', [False, True])
def test_put_exceeding_deadline_cannot_return_pointer(storage, monkeypatch, replay):
    bucket, store = storage
    ref = put() if replay else None
    clock = Mock(monotonic=Mock(return_value=10.0))
    monkeypatch.setattr(lake, 'time', clock)
    original = LocalBlob.reload if replay else LocalBlob.upload_from_string

    def slow_operation(blob, *args, **kwargs):
        assert kwargs['retry'] is None
        original(blob, *args, **kwargs)
        clock.monotonic.return_value += lake.config.put_deadline_seconds()

    monkeypatch.setattr(LocalBlob, 'reload' if replay else 'upload_from_string', slow_operation)
    with pytest.raises(lake.LakeWriteDeadlineExceeded, match='deadline exceeded'):
        put()
    monkeypatch.setattr(LocalBlob, 'reload' if replay else 'upload_from_string', original)
    # Deadline expiry is not a deletion fence. Another writer may already have
    # referenced the create-only name, even when this attempt created it.
    assert len(list(bucket.list_blobs())) == 1
    if replay:
        assert bucket.blob(ref.key).exists()  # A reused referenced generation is never self-deleted.
    assert any(path[0] == 'lake_upload_candidates' for path in store.rows)


def test_expired_candidate_admission_never_starts_put(storage, monkeypatch):
    bucket, store = storage
    clock = Mock(monotonic=Mock(return_value=10.0))
    monkeypatch.setattr(lake, 'time', clock)
    record = lake._record_upload_candidate

    def delayed_record(*args):
        attempt = record(*args)
        clock.monotonic.return_value += lake.config.put_deadline_seconds()
        return attempt

    monkeypatch.setattr(lake, '_record_upload_candidate', delayed_record)
    forbidden = Mock(side_effect=AssertionError('expired put started upload'))
    monkeypatch.setattr(LocalBlob, 'upload_from_string', forbidden)
    with pytest.raises(lake.LakeWriteDeadlineExceeded):
        put()
    forbidden.assert_not_called()
    assert not list(bucket.list_blobs())
    assert any(path[0] == 'lake_upload_candidates' for path in store.rows)


def test_deadline_checked_after_post_put_authority(storage, monkeypatch):
    bucket, _ = storage
    clock = Mock(monotonic=Mock(return_value=10.0))
    monkeypatch.setattr(lake, 'time', clock)
    authority = space_keys.get_space_keys
    upload = LocalBlob.upload_from_string

    def slow_authority(*args, **kwargs):
        keys = authority(*args, **kwargs)
        clock.monotonic.return_value += lake.config.put_deadline_seconds()
        return keys

    def uploaded(blob, *args, **kwargs):
        upload(blob, *args, **kwargs)
        monkeypatch.setattr(space_keys, 'get_space_keys', slow_authority)

    monkeypatch.setattr(LocalBlob, 'upload_from_string', uploaded)
    with pytest.raises(lake.LakeWriteDeadlineExceeded):
        put()
    assert len(list(bucket.list_blobs())) == 1


@pytest.mark.parametrize('operation', ['get', 'create'])
def test_candidate_record_failure_prevents_upload(storage, monkeypatch, operation):
    bucket, _ = storage
    cls = StrictFirestoreDocument if operation == 'get' else StrictFirestoreTransaction
    original = getattr(cls, operation)

    def fail_candidate(target, *args, **kwargs):
        document = target if operation == 'get' else args[0]
        if document.path[0] == 'lake_upload_candidates':
            raise RuntimeError('synthetic candidate store failure')
        return original(target, *args, **kwargs)

    monkeypatch.setattr(cls, operation, fail_candidate)
    with pytest.raises(lake.LakeFetchError, match='upload unavailable'):
        put()
    assert not list(bucket.list_blobs(prefix='v1/spaces/'))


def test_ambiguous_upload_retains_durable_candidate(storage, monkeypatch):
    bucket, store = storage
    upload = LocalBlob.upload_from_string

    def lost_response(blob, *args, **kwargs):
        upload(blob, *args, **kwargs)
        raise RuntimeError('response lost after upload')

    monkeypatch.setattr(LocalBlob, 'upload_from_string', lost_response)
    with pytest.raises(lake.LakeFetchError):
        put()
    blobs = list(bucket.list_blobs(prefix='v1/spaces/'))
    assert len(blobs) == 1
    assert any(
        row.get('key') == blobs[0].name for path, row in store.rows.items() if path[0] == 'lake_upload_candidates'
    )


@pytest.mark.parametrize('field', ['bucket', 'key', 'created_at'])
def test_invalid_existing_candidate_refuses_upload(storage, monkeypatch, field):
    bucket, store = storage
    record_candidate(bucket.name, 'v1/spaces/s/transcript/c/' + hashlib.sha256(b'new').hexdigest())
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    row[field] = None
    with pytest.raises(lake.LakeObjectConflict, match='candidate is invalid'):
        put(b'new')
    assert not list(bucket.list_blobs(prefix='v1/spaces/'))


def legacy_object(bucket, plaintext=b'legacy transcript'):
    digest = hashlib.sha256(plaintext).hexdigest()
    key = f'v1/spaces/s/transcript/c/{digest}'
    nonce = b'0' * 12
    dek = space_keys.unwrap_space_dek('s', 1)
    payload = lake._HEADER.pack(b'OLK1', 1, 1, nonce) + lake.AESGCM(dek).encrypt(
        nonce, zlib.compress(plaintext), key.encode()
    )
    blob = bucket.blob(key)
    blob.metadata = {'plaintext_sha256': digest, 'space_id': 's', 'data_class': 'transcript', 'dek_version': '1'}
    blob.upload_from_string(payload, if_generation_match=0)
    return lake.LakeObjectRef(bucket.name, key, digest, len(payload), 'transcript', 1)


def test_legacy_v1_roundtrip_and_retry_preserves_envelope(storage):
    bucket, store = storage
    space_keys.get_or_create_space_key('s', firestore_client=store)
    ref = legacy_object(bucket)
    original = bucket.blob(ref.key).download_as_bytes()
    assert lake.get_space_object(ref) == b'legacy transcript'
    assert put(b'legacy transcript') == ref
    assert bucket.blob(ref.key).download_as_bytes() == original


def test_object_deks_are_independent(storage):
    bucket, _ = storage
    one, two = put(b'first object'), put(b'second object')
    first = bucket.blob(one.key).download_as_bytes()
    second = bucket.blob(two.key).download_as_bytes()
    _, _, _, nonce, wrap_one = lake._HEADER_V2.unpack_from(first)
    wrap_two = lake._HEADER_V2.unpack_from(second)[4]
    assert len(wrap_one) == len(wrap_two) == 40
    assert wrap_one != wrap_two
    kek = space_keys.unwrap_space_dek('s', 1)
    dek_one, dek_two = aes_key_unwrap(kek, wrap_one), aes_key_unwrap(kek, wrap_two)
    assert len(dek_one) == len(dek_two) == 32 and dek_one != dek_two
    with pytest.raises(InvalidTag):
        lake.AESGCM(dek_two).decrypt(nonce, first[61:], one.key.encode())


def test_repeated_nonce_is_safe_with_independent_object_deks(storage, monkeypatch):
    bucket, store = storage
    # Provision the parent before fixing only the object nonce, not DEK randomness.
    space_keys.get_or_create_space_key('s', firestore_client=store)
    random_bytes = lake.os.urandom
    monkeypatch.setattr(lake.os, 'urandom', lambda size: b'n' * 12 if size == 12 else random_bytes(size))
    one, two = put(b'first object'), put(b'second object')
    first = bucket.blob(one.key).download_as_bytes()
    second = bucket.blob(two.key).download_as_bytes()
    assert lake._HEADER_V2.unpack_from(first)[3] == lake._HEADER_V2.unpack_from(second)[3] == b'n' * 12
    assert first[21:61] != second[21:61] and first[61:] != second[61:]
    assert lake.get_space_object(one) == b'first object'
    assert lake.get_space_object(two) == b'second object'


def test_object_wraps_add_no_kms_decrypts(storage):
    _, store = storage
    kms = space_keys.FakeKMS()
    with patch.object(space_keys, '_kms', return_value=kms), patch.object(kms, 'decrypt', wraps=kms.decrypt) as decrypt:
        one, two = put(b'first object'), put(b'second object')
        assert lake.get_space_object(one) == b'first object'
        assert lake.get_space_object(two) == b'second object'
        assert decrypt.call_count == 1
        space_keys.rotate_space_key('s', firestore_client=store)
        three = put(b'after rotation')
        assert lake.get_space_object(three) == b'after rotation'
        assert lake.get_space_object(one) == b'first object'
        assert decrypt.call_count == 2


def test_create_only_retry_and_retry_after_rotation(storage):
    bucket, store = storage
    first = put()
    original = bucket.blob(first.key).download_as_bytes()
    assert put() == first
    space_keys.rotate_space_key('s', firestore_client=store)
    assert put() == first
    assert bucket.blob(first.key).download_as_bytes() == original
    second = put(b'different plaintext')
    assert second.dek_version == 2
    assert lake.get_space_object(first).startswith(b'private transcript')
    assert lake.get_space_object(second) == b'different plaintext'


@pytest.mark.parametrize('field', ['plaintext_sha256', 'space_id', 'data_class', 'dek_version'])
def test_create_only_conflict(storage, field):
    bucket, _ = storage
    ref = put()
    blob = bucket.blob(ref.key)
    blob.reload()
    blob.metadata[field] = 'wrong'
    blob.patch()
    with pytest.raises(lake.LakeObjectConflict):
        put()


@pytest.mark.parametrize('consent', [None, lake.ConsentStamp('opt_in', 'policy-7', '2026-11-06T01:00:00Z')])
def test_consent_metadata(storage, consent):
    bucket, _ = storage
    ref = put(consent=consent)
    blob = bucket.blob(ref.key)
    blob.reload()
    stamp = blob.metadata
    assert set(stamp) == {
        'space_id',
        'data_class',
        'dek_version',
        'plaintext_sha256',
        'created_day',
        'consent',
        'consent_policy_version',
        'consented_at',
    }
    assert all(isinstance(v, str) for v in stamp.values())
    assert stamp['space_id'] == 's' and stamp['data_class'] == 'transcript'
    assert stamp['plaintext_sha256'] == ref.sha256 and stamp['dek_version'] == '1'
    assert stamp['consent'] == ('opt_in' if consent else 'unknown')
    assert stamp['consent_policy_version'] == ('policy-7' if consent else '')
    assert stamp['consented_at'] == (consent.consented_at if consent else '')
    assert len(stamp['created_day']) == 10


def test_absent_is_distinct_from_empty(storage):
    bucket, _ = storage
    ref = put()
    bucket.blob(ref.key).delete()
    with pytest.raises(lake.LakeObjectAbsent):
        lake.get_space_object(ref)


@pytest.mark.parametrize(
    'change',
    [
        'ciphertext',
        'header',
        'truncated',
        'digest',
        'aad',
        'size',
        'version',
        'env',
        'v2_floor',
        'wrap_bit',
        'wrap_swap',
    ],
)
def test_corruption_fails_closed(storage, change):
    bucket, _ = storage
    ref = put()
    blob = bucket.blob(ref.key)
    payload = blob.download_as_bytes()
    if change == 'ciphertext':
        blob.upload_from_string(payload[:-1] + bytes([payload[-1] ^ 1]))
    elif change == 'header':
        blob.upload_from_string(b'BAD!' + payload[4:])
    elif change == 'truncated':
        blob.upload_from_string(payload[:8])
    elif change == 'env':
        blob.upload_from_string(payload[:4] + b'\x03' + payload[5:])
    elif change == 'v2_floor':
        blob.upload_from_string(payload[:61])
        ref = replace(ref, bytes=61)
    elif change == 'wrap_bit':
        blob.upload_from_string(payload[:21] + bytes([payload[21] ^ 1]) + payload[22:])
    elif change == 'wrap_swap':
        other = put(b'another object')
        wrapped = bucket.blob(other.key).download_as_bytes()[21:61]
        blob.upload_from_string(payload[:21] + wrapped + payload[61:])
    elif change == 'digest':
        ref = replace(ref, sha256='0' * 64)
    elif change == 'size':
        ref = replace(ref, bytes=ref.bytes + 1)
    elif change == 'version':
        ref = replace(ref, dek_version=2)
    elif change == 'aad':
        swapped = ref.key.replace('/c/', '/other-entity/')
        bucket.blob(swapped).upload_from_string(payload)
        ref = replace(ref, key=swapped)
    with pytest.raises(lake.LakeObjectCorrupt):
        lake.get_space_object(ref)


def test_hash_is_verified_after_authenticated_decryption(storage):
    bucket, _ = storage
    ref = put()
    digest = hashlib.sha256(b'different').hexdigest()
    key = ref.key.rsplit('/', 1)[0] + '/' + digest
    nonce = b'0' * 12
    dek = space_keys.unwrap_space_dek('s', 1)
    payload = lake._HEADER.pack(b'OLK1', 1, 1, nonce) + lake.AESGCM(dek).encrypt(
        nonce, zlib.compress(b'wrong plaintext'), key.encode()
    )
    bucket.blob(key).upload_from_string(payload)
    with pytest.raises(lake.LakeObjectCorrupt, match='digest'):
        lake.get_space_object(replace(ref, key=key, sha256=digest, bytes=len(payload)))


def test_transport_failure_never_returns_fallback(storage):
    ref = put()
    with patch.object(LocalBlob, 'download_as_bytes', side_effect=Exception('transport body with secrets')):
        with pytest.raises(lake.LakeFetchError) as error:
            lake.get_space_object(ref)
        assert 'secrets' not in str(error.value)
    with patch.object(LocalBlob, 'upload_from_string', side_effect=Exception('transport')):
        with pytest.raises(lake.LakeFetchError):
            put(b'new object')


def test_delete_is_idempotent_and_prefix_is_space_scoped(storage):
    bucket, _ = storage
    ref = put()
    assert lake.delete_space_object(ref) is True
    assert lake.delete_space_object(ref) is False
    one = put()
    two = lake.put_space_object('s', 'transcript', 'second', b'2')
    neighbor = lake.put_space_object('ss', 'transcript', 'c', b'3')
    assert lake.delete_space_prefix('s', data_class='transcript', entity_id='c') == 1
    assert not bucket.blob(one.key).exists() and bucket.blob(two.key).exists()
    assert lake.delete_space_prefix('s') == 1
    assert lake.delete_space_prefix('s') == 0
    assert bucket.blob(neighbor.key).exists()


def test_prefix_requires_verified_absence(storage):
    bucket, _ = storage
    put()
    original_delete = LocalBlob.delete

    def resurrect(blob):
        payload = blob.download_as_bytes()
        original_delete(blob)
        blob.upload_from_string(payload, if_generation_match=0)

    with patch.object(LocalBlob, 'delete', resurrect):
        with pytest.raises(lake.LakePurgeIncomplete, match='left objects'):
            lake.delete_space_prefix('s')
    assert list(bucket.list_blobs())


def test_verify_shallow_and_deep(storage):
    bucket, _ = storage
    ref = put()
    assert lake.verify_space_object(ref) and lake.verify_space_object(ref, deep=True)
    assert not lake.verify_space_object(replace(ref, bytes=ref.bytes + 1))
    blob = bucket.blob(ref.key)
    blob.reload()
    payload = blob.download_as_bytes()
    blob.upload_from_string(payload[:-1] + bytes([payload[-1] ^ 1]))
    # Size and stamp unchanged; deep verification is required to find tag damage.
    assert lake.verify_space_object(ref)
    assert not lake.verify_space_object(ref, deep=True)
    blob.delete()
    assert not lake.verify_space_object(ref) and not lake.verify_space_object(ref, deep=True)


def test_destroyed_and_unavailable_keys_propagate(storage):
    bucket, store = storage
    ref = put()
    legacy = legacy_object(bucket)
    lake.get_space_object(ref)  # Warm the unwrap cache before destroy.
    lake.get_space_object(legacy)
    space_keys.destroy_space_keys('s', firestore_client=store)
    for pointer in (legacy, ref):
        with pytest.raises(space_keys.SpaceKeyDestroyed):
            lake.get_space_object(pointer)
    with patch.object(space_keys, 'unwrap_space_dek', side_effect=space_keys.SpaceKeyUnavailable('retry')):
        with pytest.raises(space_keys.SpaceKeyUnavailable):
            lake.get_space_object(ref)


def test_not_configured_and_not_admitted(storage, monkeypatch):
    ref = put()
    monkeypatch.delenv('BUCKET_OBJECT_LAKE')
    with pytest.raises(lake.ObjectLakeNotConfigured):
        put()
    with pytest.raises(lake.ObjectLakeNotConfigured):
        lake.get_space_object(ref)
    monkeypatch.setenv('BUCKET_OBJECT_LAKE', 'lake-test')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_PERCENT', '0')
    with patch.object(space_keys, 'get_or_create_space_key') as key_create:
        with pytest.raises(lake.ObjectLakeNotConfigured):
            put()
        key_create.assert_not_called()


@pytest.mark.parametrize('identifier', ['', '../neighbor', 's/other', '..'])
def test_unsafe_identifiers_never_reach_storage(storage, identifier):
    with pytest.raises(ValueError):
        lake.delete_space_prefix(identifier)


def test_wrong_bucket_and_malformed_pointer_are_rejected(storage):
    ref = put()
    with pytest.raises(lake.LakeObjectCorrupt):
        lake.get_space_object(replace(ref, bucket='foreign-bucket'))
    with pytest.raises(lake.LakeObjectCorrupt):
        lake.LakeObjectRef.from_pointer_dict({'key': 'garbage'})


def test_bucket_client_is_lazy_and_reused(monkeypatch):
    monkeypatch.setenv('BUCKET_OBJECT_LAKE', 'lazy-lake')
    monkeypatch.setattr(lake, '_bucket_instance', None)
    monkeypatch.setattr(lake, '_bucket_name', None)
    with patch.object(lake, 'create_storage_client') as create:
        expected = create.return_value.bucket.return_value
        assert lake._lake_bucket() is expected
        assert lake._lake_bucket() is expected
        create.assert_called_once_with()
        create.return_value.bucket.assert_called_once_with('lazy-lake')


def test_delete_space_entity_scopes_all_classes_and_is_idempotent(storage, monkeypatch):
    bucket, _ = storage
    put()
    lake.put_space_object('s', 'transcript', 'c-sibling', b'sibling')
    lake.put_space_object('other', 'transcript', 'c', b'other owner')
    # Exercise every registered class, including a future class without admitting
    # it to put_space_object's codec. Prefix deletion must cover it too.
    monkeypatch.setattr(lake, 'DATA_CLASSES', ('transcript', 'future'))
    bucket.blob('v1/spaces/s/future/c/digest').upload_from_string(b'synthetic')
    assert lake.delete_space_entity('s', 'c') == 2
    assert lake.delete_space_entity('s', 'c') == 0
    assert len(list(bucket.list_blobs())) == 2
    assert all('/c/' not in blob.name or '/other/' in blob.name for blob in bucket.list_blobs())


def test_delete_space_entity_verifies_absence(storage, monkeypatch):
    put()
    monkeypatch.setattr(LocalBlob, 'delete', lambda self: None)
    with pytest.raises(lake.LakePurgeIncomplete, match='left objects behind'):
        lake.delete_space_entity('s', 'c')


def test_delete_space_entity_transport_failure_is_retryable(storage, monkeypatch):
    bucket, _ = storage
    monkeypatch.setattr(bucket, 'list_blobs', lambda **kwargs: (_ for _ in ()).throw(OSError('down')))
    with pytest.raises(lake.LakeFetchError):
        lake.delete_space_entity('s', 'c')


@pytest.mark.parametrize('envelope_version', [1, 2])
def test_shredded_key_wins_over_purged_blob(storage, envelope_version):
    bucket, store = storage
    space_keys.get_or_create_space_key('s', firestore_client=store)
    ref = legacy_object(bucket) if envelope_version == 1 else put()
    lake.delete_space_prefix('s')
    space_keys.destroy_space_keys('s')
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        lake.get_space_object(ref)


def test_disabled_kms_key_with_live_authority_remains_shredded(storage, monkeypatch):
    ref = put()
    space_keys.clear_space_key_cache()
    kms = Mock()
    kms.decrypt.side_effect = FailedPrecondition('key disabled')
    monkeypatch.setattr(space_keys, '_kms', lambda: kms)
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        lake.get_space_object(ref)


def test_conversation_fence_refuses_put_before_storage_or_keys(storage, monkeypatch):
    _, store = storage
    store.collection('users').document('s').collection('deleted_conversations').document('c').create({})
    with patch.object(space_keys, 'active_space_dek') as keys, patch.object(lake, '_lake_bucket') as bucket:
        with pytest.raises(lake.LakeWriteFenced, match='Conversation'):
            put()
    keys.assert_not_called()
    bucket.assert_not_called()


def test_create_only_retry_does_not_delete_reused_referenced_object(storage, monkeypatch):
    bucket, store = storage
    ref = put()
    store.collection('users').document('s').collection('conversations').document('c').create(
        {'transcript_segments': ref.to_pointer_dict()}
    )
    original = LocalBlob.reload

    def fence_during_retry(blob, *args, **kwargs):
        original(blob, *args, **kwargs)
        store.collection('users').document('s').collection('deleted_conversations').document('c').create({})

    monkeypatch.setattr(LocalBlob, 'reload', fence_during_retry)
    with pytest.raises(lake.LakeWriteFenced):
        put()
    monkeypatch.setattr(LocalBlob, 'reload', original)
    assert bucket.blob(ref.key).exists()
    assert any(path[0] == 'lake_upload_candidates' for path in store.rows)
    # The deleting orchestrator, rather than the retry, owns referenced content.
    assert lake.delete_space_entity('s', 'c') == 1


def test_conversation_fence_failure_never_lists_or_purges(storage, monkeypatch):
    from utils.other import lake_wipe

    bucket, _ = storage
    monkeypatch.setattr(space_keys, 'space_key_firestore_client', Mock(side_effect=OSError('unavailable')))
    listing = Mock(side_effect=AssertionError('listed before fence'))
    monkeypatch.setattr(bucket, 'list_blobs', listing)
    with pytest.raises(lake.LakeFetchError, match='fence unavailable'):
        lake_wipe.purge_conversation_lake_objects('s', 'c')
    listing.assert_not_called()


def test_conversation_fences_all_donors_and_preserves_existing_bindings(storage):
    from utils.other import lake_wipe

    _, store = storage
    row = {'conversation_id': 'c', 'client_session_id': 'session', 'created_at': 'original'}
    ref = store.collection('users').document('s').collection('deleted_conversations').document('c')
    ref.create(row)
    assert lake_wipe.purge_conversation_lake_objects('s', 'c', ['c', 'donor', 'donor', '']) == 0
    assert ref.get().to_dict() == row
    assert store.collection('users').document('s').collection('deleted_conversations').document('donor').get().exists


def test_delayed_candidate_creation_refused_after_owner_purge(storage, monkeypatch):
    from utils.other import lake_wipe

    bucket, store = storage
    record = lake._record_upload_candidate

    def record_after_purge(bucket_name, key, session, size):
        store.collection('account_deletions').document('s').create({'wipe_status': 'running'})
        monkeypatch.setattr(lake_wipe.users_db, 'get_user_deletion_wipe_status', lambda uid: 'running')
        assert lake_wipe.purge_owner_lake_content('s')['status'] == 'purged'
        record(bucket_name, key, session, size)

    monkeypatch.setattr(lake, '_record_upload_candidate', record_after_purge)
    with pytest.raises(lake.LakeWriteFenced):
        put()
    assert not list(bucket.list_blobs())
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)


def test_candidate_absence_verification_failure_is_retryable(storage, monkeypatch):
    _, store = storage
    put()
    monkeypatch.setattr(StrictFirestoreTransaction, 'delete', lambda self, ref: None)
    store.collection('account_deletions').document('s').create({'wipe_status': 'running'})
    with pytest.raises(lake.LakeFetchError, match='remain after purge'):
        lake.delete_space_upload_candidates('s')


def test_settlement_of_one_same_key_request_leaves_other_inflight(storage):
    bucket, store = storage
    key = 'v1/spaces/s/transcript/c/' + hashlib.sha256(b'new').hexdigest()
    one = record_candidate(bucket.name, key)
    two = record_candidate(bucket.name, key)
    lake._settle_upload_candidate(bucket.name, key, two)
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    assert set(row['in_flight']) == {one} and row['settled'] is False
    lake.assert_space_uploads_quiescent('s')
    lake._settle_upload_candidate(bucket.name, key, one)
    lake.assert_space_uploads_quiescent('s')
    store.collection('account_deletions').document('s').create({'wipe_status': 'running'})
    assert lake.delete_space_upload_candidates('s') == 1
    lake._settle_upload_candidate(bucket.name, key, one)
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)


def test_failed_put_keeps_ambiguous_request_in_flight(storage, monkeypatch):
    # A raised transport error can still commit server-side: only the
    # storage session fence, never elapsed time, may release the attempt.
    _, store = storage
    monkeypatch.setattr(LocalBlob, 'upload_from_string', Mock(side_effect=RuntimeError('transport failed')))
    with pytest.raises(lake.LakeFetchError):
        put()
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    assert row['settled'] is not True and len(row['in_flight']) == 1


def test_settlement_store_failure_retains_inflight_discovery(storage, monkeypatch):
    bucket, store = storage
    settle = Mock(side_effect=RuntimeError('settlement unavailable'))
    monkeypatch.setattr(lake, '_settle_upload_candidate', settle)
    with pytest.raises(lake.LakeFetchError):
        put()
    assert len(list(bucket.list_blobs())) == 1
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    assert row['settled'] is False and len(row['in_flight']) == 1


def test_large_payload_refuses_resumable_upload_before_admission(storage, monkeypatch):
    bucket, store = storage
    monkeypatch.setattr(lake, '_MAX_SINGLE_REQUEST_BYTES', 1)
    forbidden = Mock(side_effect=AssertionError('resumable upload admitted'))
    monkeypatch.setattr(LocalBlob, 'upload_from_string', forbidden)
    with pytest.raises(lake.LakeObjectCorrupt, match='single-request upload limit'):
        put(b'content')
    forbidden.assert_not_called()
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)


def test_deletion_after_post_put_check_fails_the_put(storage, monkeypatch):
    # The tombstone lands after the post-upload authority check but before
    # settlement; settlement purges the object, so the put must not return it.
    bucket, store = storage
    original = lake._settle_upload_candidate

    def tombstone_then_settle(*args, **kwargs):
        store.collection('users').document('s').collection('deleted_conversations').document('c').create({})
        return original(*args, **kwargs)

    monkeypatch.setattr(lake, '_settle_upload_candidate', tombstone_then_settle)
    with pytest.raises(lake.LakeWriteFenced, match='fenced the upload'):
        put()
    assert not list(bucket.list_blobs())


def test_deletion_between_settlement_preread_and_transaction_fails_the_put(storage, monkeypatch):
    # The tombstone lands after settlement's non-transactional pre-read but
    # before its transaction; the transaction must see it, purge, and refuse.
    bucket, store = storage
    original_client = lake.space_keys.space_key_firestore_client
    original_settle = lake._settle_upload_candidate

    class _FenceOnFirstTransaction:
        def __init__(self, inner):
            self._inner, self._armed = inner, True

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def transaction(self, *args, **kwargs):
            if self._armed:
                self._armed = False
                store.collection('users').document('s').collection('deleted_conversations').document('c').create({})
            return self._inner.transaction(*args, **kwargs)

    def fence_inside_settle(*args, **kwargs):
        client = _FenceOnFirstTransaction(original_client())
        with monkeypatch.context() as scoped:
            scoped.setattr(lake.space_keys, 'space_key_firestore_client', lambda: client)
            return original_settle(*args, **kwargs)

    monkeypatch.setattr(lake, '_settle_upload_candidate', fence_inside_settle)
    with pytest.raises(lake.LakeWriteFenced, match='fenced the upload'):
        put()
    assert not list(bucket.list_blobs())
    assert [doc.to_dict() for doc in store.collection('lake_upload_candidates').stream()] == []


def test_account_wipe_marker_before_settlement_fails_the_put(storage, monkeypatch):
    # The account wipe marker lands after the put's authority check but before
    # settlement; settlement must purge the object and refuse the reference.
    bucket, store = storage
    original = lake._settle_upload_candidate

    def mark_then_settle(*args, **kwargs):
        store.collection('account_deletions').document('s').create({'wipe_status': 'running'})
        return original(*args, **kwargs)

    monkeypatch.setattr(lake, '_settle_upload_candidate', mark_then_settle)
    with pytest.raises(lake.LakeWriteFenced, match='fenced the upload'):
        put()
    assert not list(bucket.list_blobs())
    # The account wipe, not settlement, owns erasing discovery rows.
    rows = [doc.to_dict() for doc in store.collection('lake_upload_candidates').stream()]
    assert len(rows) == 1 and rows[0]['in_flight'] == {} and rows[0]['settled'] is True


def record_candidate(bucket, key):
    blob = lake.create_storage_client().bucket(bucket).blob(key)
    session = blob.create_resumable_upload_session(
        content_type='application/octet-stream', size=9, if_generation_match=0, timeout=(1, 1), retry=None
    )
    return lake._record_upload_candidate(bucket, key, session, 9)


def test_record_fenced_after_session_creation_cancels_empty_session(storage, monkeypatch):
    bucket, store = storage
    create = LocalBlob.create_resumable_upload_session
    sessions = []

    def fence_after_create(blob, **kwargs):
        session = create(blob, **kwargs)
        sessions.append(session)
        store.collection('users').document('s').collection('deleted_conversations').document('c').create({})
        return session

    monkeypatch.setattr(LocalBlob, 'create_resumable_upload_session', fence_after_create)
    with pytest.raises(lake.LakeWriteFenced):
        put()
    assert not list(bucket.list_blobs())
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)
    assert lake._UploadSession.status(bucket.client, sessions[0], 1) == 499


@pytest.mark.parametrize('operation', ['create', 'put'])
def test_session_errors_and_pointer_never_expose_capability(storage, monkeypatch, caplog, operation):
    bucket, store = storage
    ref = put()
    assert 'session' not in repr(ref) and 'session' not in repr(ref.to_pointer_dict())
    secret = 'https://storage.googleapis.com/upload?upload_id=secret-capability'
    if operation == 'create':
        monkeypatch.setattr(LocalBlob, 'create_resumable_upload_session', Mock(side_effect=OSError(secret)))
    else:

        def fail(*args):
            raise OSError(secret)

        bucket.client._http.before_request = fail
    with pytest.raises(lake.LakeFetchError) as error:
        put(b'other plaintext')
    assert secret not in str(error.value) and secret not in caplog.text
    assert error.value.__suppress_context__


@pytest.mark.parametrize('precondition_stage', ['none', 'initiation', 'finalize'])
def test_real_gcs_session_seam_uses_one_put_and_generation_zero(storage, monkeypatch, precondition_stage):
    from google.api_core.exceptions import PreconditionFailed
    from google.cloud.storage import Blob, Client
    from google.auth.credentials import AnonymousCredentials

    put()  # Existing candidate authority for the initiation replay case.
    session = 'https://storage.googleapis.com/upload?upload_id=secret-capability'
    client = Client(project='demo-pgf-c4', credentials=AnonymousCredentials())
    blob = client.bucket('lake-test').blob('v1/spaces/s/transcript/c/' + hashlib.sha256(b'real seam').hexdigest())
    create = Mock(return_value=session)
    if precondition_stage == 'initiation':
        create.side_effect = PreconditionFailed(session)
    monkeypatch.setattr(Blob, 'create_resumable_upload_session', create)
    response = Mock(
        status_code=412 if precondition_stage == 'finalize' else 200,
        json=Mock(return_value={'generation': '17', 'size': '7'}),
    )
    http = Mock(request=Mock(return_value=response))
    client._http_internal = http
    blob.metadata = {'space_id': 's', 'data_class': 'transcript', 'plaintext_sha256': 'digest'}
    response.json.return_value['metadata'] = blob.metadata
    try:
        if precondition_stage == 'initiation':
            with pytest.raises(PreconditionFailed) as error:
                lake._UploadSession.create(blob, b'payload', 'application/octet-stream', lake.time.monotonic() + 5)
            assert session not in str(error.value)
            http.request.assert_not_called()
        else:
            assert (
                lake._UploadSession.create(blob, b'payload', 'application/octet-stream', lake.time.monotonic() + 5)
                == session
            )
            if precondition_stage == 'finalize':
                with pytest.raises(PreconditionFailed) as error:
                    lake._UploadSession.put_all(client, session, b'payload', lake.time.monotonic() + 5, blob=blob)
                assert session not in str(error.value)
            else:
                lake._UploadSession.put_all(client, session, b'payload', lake.time.monotonic() + 5, blob=blob)
            if precondition_stage == 'none':
                assert blob.generation == 17
            http.request.assert_called_once()
            args, kwargs = http.request.call_args
            assert args == ('PUT', session) and kwargs['data'] == b'payload'
            assert kwargs['headers'] == {'Content-Length': '7', 'Content-Range': 'bytes 0-6/7'}
            assert kwargs['allow_redirects'] is False
        assert create.call_args.kwargs['size'] == 7
        assert create.call_args.kwargs['if_generation_match'] == 0
        assert create.call_args.kwargs['retry'] is None
        assert blob.metadata['space_id'] == 's'
    finally:
        client.close()


def test_initiation_precondition_replay_records_discovery_and_returns_existing_ref(storage, monkeypatch):
    from google.api_core.exceptions import PreconditionFailed

    bucket, store = storage
    ref = put()
    # Even an existing object without discovery gains settled discovery before
    # the replay returns; no new session capable of committing was issued.
    for path in list(store.rows):
        if path[0] == 'lake_upload_candidates':
            del store.rows[path]
    monkeypatch.setattr(LocalBlob, 'create_resumable_upload_session', Mock(side_effect=PreconditionFailed('exists')))
    assert put() == ref
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    assert row['settled'] is True and not row['in_flight']


def test_expired_creator_preserves_concurrently_published_pointer(storage, monkeypatch):
    bucket, store = storage
    clock = Mock(monotonic=Mock(return_value=10.0))
    monkeypatch.setattr(lake, 'time', clock)
    published = []

    def publish_before_expiry(method, uri, data, headers, response):
        if method == 'PUT' and not str(headers.get('Content-Range', '')).startswith('bytes */'):
            bucket.client._http.after_request = None
            published.append(put())
            clock.monotonic.return_value += lake.config.put_deadline_seconds()

    bucket.client._http.after_request = publish_before_expiry
    with pytest.raises(lake.LakeWriteDeadlineExceeded):
        put()
    assert len(list(bucket.list_blobs())) == 1
    assert lake.get_space_object(published[0]).startswith(b'private transcript')
    assert any(path[0] == 'lake_upload_candidates' for path in store.rows)


@pytest.mark.parametrize(
    'status', [200, 201, 404, 410, 412, 499, 400, 401, 403, 407, 408, 409, 425, 429, 308, 503, 302, 202, 0]
)
def test_fence_requires_terminal_storage_status(storage, monkeypatch, status):
    bucket, store = storage
    session = 'local-session://' + 'a' * 32
    calls = []
    monkeypatch.setattr(lake._UploadSession, 'cancel', lambda client, uri: calls.append(('DELETE', uri)))
    monkeypatch.setattr(
        lake._UploadSession, 'status', lambda client, uri, size: calls.append(('status', uri, size)) or status
    )
    # Allowlist only: finalized, cancelled (499), sticky finalize refusal (412) or
    # unknown to the service (404/410). A 400, auth, throttling or other code is not proof.
    if status in (200, 201, 404, 410, 412, 499):
        lake._fence_upload_attempt({'session': session, 'size': 7})
    else:
        with pytest.raises(lake.LakeFetchError):
            lake._fence_upload_attempt({'session': session, 'size': 7})
    assert calls == [('DELETE', session), ('status', session, 7)]


def test_status_query_names_the_declared_size(storage):
    bucket, store = storage
    seen = []
    client = bucket.client
    client._http.before_request = lambda method, uri, data, headers: seen.append((method, dict(headers or {})))
    blob = bucket.blob('rel/spaces/u/transcript/c/' + 'd' * 64)
    session = lake._UploadSession.create(blob, b'payload', 'application/octet-stream', time.monotonic() + 30)
    assert lake._UploadSession.status(client, session, 7) == 308
    lake._UploadSession.cancel(client, session)
    assert lake._UploadSession.status(client, session, 7) == 499
    assert seen[0] == ('PUT', {'Content-Length': '0', 'Content-Range': 'bytes */7'})


def _candidate_rows(store):
    return [row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates']


def test_finalize_412_replay_fences_its_session_before_settling(storage, monkeypatch):
    bucket, store = storage
    first = put()
    calls = []
    status = lake._UploadSession.status
    monkeypatch.setattr(
        lake._UploadSession,
        'status',
        lambda client, uri, size: calls.append(size) or status(client, uri, size),
    )
    # Same plaintext, same key: GCS evaluates generation 0 at finalize and refuses.
    assert put() == first
    assert calls and all(size > 0 for size in calls)
    [row] = _candidate_rows(store)
    assert row['settled'] is True and row['in_flight'] == {}


def test_finalize_412_with_unproven_session_keeps_it_discoverable(storage, monkeypatch):
    bucket, store = storage
    put()
    monkeypatch.setattr(lake._UploadSession, 'status', lambda client, uri, size: 503)
    with pytest.raises(lake.LakeFetchError):
        put()
    [row] = _candidate_rows(store)
    [attempt] = row['in_flight'].values()
    assert row['settled'] is False and attempt['session'] and attempt['size'] > 0

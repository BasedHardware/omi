"""Real AES-GCM plus filesystem storage, with no cloud/service access."""

from dataclasses import replace
import hashlib
import zlib
from unittest.mock import patch

import pytest
from google.api_core.exceptions import AlreadyExists
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.keywrap import aes_key_unwrap

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
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
    bucket = LocalStorageClient(tmp_path).bucket('lake-test')
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
        candidate_id = hashlib.sha256(f'{bucket.name}/{blob.name}'.encode()).hexdigest()
        row = store.rows[('lake_upload_candidates', candidate_id)]
        assert set(row) == {'bucket', 'key', 'created_at'}
        assert row['bucket'] == bucket.name and row['key'] == blob.name
        assert row['created_at'].tzinfo is not None
        return upload(blob, *args, **kwargs)

    monkeypatch.setattr(LocalBlob, 'upload_from_string', checked_upload)
    first = put()
    candidates = {path: row.copy() for path, row in store.rows.items() if path[0] == 'lake_upload_candidates'}
    assert put() == first
    assert {path: row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates'} == candidates


@pytest.mark.parametrize('operation', ['get', 'create'])
def test_candidate_record_failure_prevents_upload(storage, monkeypatch, operation):
    bucket, _ = storage
    original = getattr(StrictFirestoreDocument, operation)

    def fail_candidate(document, *args, **kwargs):
        if document.path[0] == 'lake_upload_candidates':
            raise RuntimeError('synthetic candidate store failure')
        return original(document, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, operation, fail_candidate)
    with pytest.raises(lake.LakeFetchError, match='upload unavailable'):
        put()
    assert not list(bucket.list_blobs(prefix='v1/spaces/'))


def test_concurrent_candidate_create_is_idempotent(storage, monkeypatch):
    _, store = storage
    original = StrictFirestoreDocument.create

    def concurrent_create(document, data):
        original(document, data)
        if document.path[0] == 'lake_upload_candidates':
            raise AlreadyExists('concurrent intent already committed')

    monkeypatch.setattr(StrictFirestoreDocument, 'create', concurrent_create)
    ref = put()
    assert lake.get_space_object(ref)
    assert len([path for path in store.rows if path[0] == 'lake_upload_candidates']) == 1


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
    lake._record_upload_candidate(bucket.name, 'v1/spaces/s/transcript/c/' + hashlib.sha256(b'new').hexdigest())
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
        with pytest.raises(RuntimeError, match='left objects'):
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


def test_strict_dict_bucket_retry_uses_existing_metadata(storage):
    """GCS-shaped fake rejects writes without an explicit create precondition."""
    from google.api_core.exceptions import PreconditionFailed

    rows = {}

    class Blob:
        def __init__(self, name):
            self.name = name
            self.metadata = None
            self.size = None

        def upload_from_string(self, data, *, content_type, if_generation_match):
            assert if_generation_match == 0
            if self.name in rows:
                raise PreconditionFailed('exists')
            rows[self.name] = (data, dict(self.metadata))

        def reload(self):
            data, self.metadata = rows[self.name]
            self.size = len(data)

        def download_as_bytes(self):
            return rows[self.name][0]

    class Bucket:
        def blob(self, name):
            return Blob(name)

    with patch.object(lake, '_lake_bucket', return_value=Bucket()):
        ref = put(b'dictionary storage')
        assert put(b'dictionary storage') == ref
        assert lake.get_space_object(ref) == b'dictionary storage'


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

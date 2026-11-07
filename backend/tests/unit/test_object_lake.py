"""Real AES-GCM plus filesystem storage, with no cloud/service access."""

from dataclasses import replace
import hashlib
import zlib
from unittest.mock import patch

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
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
    store = StrictFirestore()
    space_keys.clear_space_key_cache()
    monkeypatch.setattr(space_keys, '_client', lambda client: store if client is None else client)
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
    assert payload[:9] == b'OLK1\x01\x00\x00\x00\x01'
    assert plaintext[:20] not in payload and zlib.compress(plaintext)[:12] not in payload
    assert lake.get_space_object(ref) == plaintext
    assert lake.LakeObjectRef.from_pointer_dict(ref.to_pointer_dict()) == ref
    assert ref.to_pointer_dict()['class'] == 'transcript'


def test_empty_plaintext(storage):
    assert lake.get_space_object(put(b'')) == b''


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


@pytest.mark.parametrize('change', ['ciphertext', 'header', 'truncated', 'digest', 'aad', 'size', 'version'])
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
    _, store = storage
    ref = put()
    lake.get_space_object(ref)  # Warm the unwrap cache before destroy.
    space_keys.destroy_space_keys('s', firestore_client=store)
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        lake.get_space_object(ref)
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

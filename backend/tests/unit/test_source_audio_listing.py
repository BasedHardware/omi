"""Listed metadata saves RPCs without relaxing retained-source integrity."""

import hashlib
import struct
from types import SimpleNamespace
from unittest.mock import Mock

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
import pytest

from utils.batch_pipeline import live, source_audio as source, record_seal_profile
from utils.other import storage


def reader(raw, *, path='chunks/u/c/100.batch.bin', metadata=None):
    blob = SimpleNamespace(
        size=len(raw), metadata=metadata or {}, reload=Mock(), download_as_bytes=Mock(return_value=raw)
    )
    bucket = SimpleNamespace(blob=Mock(return_value=blob))
    client = SimpleNamespace(bucket=Mock(return_value=bucket))
    ref = {'path': path, 'bucket': 'synthetic', 'generation': 7}
    return client, bucket, blob, ref


@pytest.mark.parametrize('missing', [None, 'size', 'metadata', 'metageneration'])
def test_listing_skips_only_redundant_metadata_get(missing):
    client, bucket, blob, ref = reader(b'\x01\x00' * 10, metadata={'record_sample_rate': '8000'})
    listing = {'size': 20, 'metadata': dict(blob.metadata), 'metageneration': 3}
    if missing:
        listing.pop(missing)
    if missing == 'metageneration':
        blob.metadata = {'record_sample_rate': '16000'}  # Stale unversioned listing must reload.
    profile = record_seal_profile.RowProfile(0)
    with profile.install():
        pcm = source.read_reference(
            client, ref, 'u', 'c', {'synthetic'}, b'x' * 32, source_metadata=True, listed_source=listing
        )
    assert pcm and ref['sample_rate'] == (16000 if missing == 'metageneration' else 8000)
    assert ref['metadata'] == blob.metadata
    assert blob.reload.call_count == (1 if missing else 0)
    if missing:
        blob.reload.assert_called_once_with(if_generation_match=7, timeout=30, retry=None)
    bucket.blob.assert_called_once_with(ref['path'], generation=7)
    blob.download_as_bytes.assert_called_once_with(
        if_generation_match=7,
        timeout=60,
        retry=None,
        **({} if missing else {'if_metageneration_match': 3}),
    )
    assert profile.chunks == 1 and profile.bytes == 20
    assert profile.metadata_reloads == (1 if missing else 0)


@pytest.mark.parametrize('size', [0, source.MAX_SOURCE_BYTES + 1])
def test_listed_size_still_fences_download(size):
    client, _, blob, ref = reader(b'\x01\x00')
    with pytest.raises(ValueError, match='size budget'):
        source.read_reference(
            client,
            ref,
            'u',
            'c',
            {'synthetic'},
            b'x' * 32,
            source_metadata=True,
            listed_source={'size': size, 'metadata': {}, 'metageneration': 3},
        )
    blob.reload.assert_not_called()
    blob.download_as_bytes.assert_not_called()


def test_listed_metadata_keeps_decrypt_authentication_and_raw_sha256(monkeypatch):
    key, raw = b'x' * 32, b'\x01\x00' * 10
    nonce = b'n' * 12
    ciphertext = nonce + AESGCM(key).encrypt(nonce, raw, None)
    encrypted = struct.pack('>I', len(ciphertext)) + ciphertext
    metadata = {'encrypted': 'true', 'sha256': hashlib.sha256(raw).hexdigest()}
    client, _, blob, ref = reader(encrypted, path='raw-live/u/c/100.enc', metadata=metadata)
    monkeypatch.setattr(source, 'decode_capture', lambda raw, *a: raw)
    listing = {'size': len(encrypted), 'metadata': metadata, 'metageneration': 3}
    assert (
        source.read_reference(client, ref, 'u', 'c', {'synthetic'}, key, source_metadata=True, listed_source=listing)
        == raw
    )
    metadata['sha256'] = 'wrong'
    with pytest.raises(ValueError, match='checksum mismatch'):
        source.read_reference(client, ref, 'u', 'c', {'synthetic'}, key, source_metadata=True, listed_source=listing)
    blob.download_as_bytes.return_value = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
    with pytest.raises(InvalidTag):
        source.read_reference(client, ref, 'u', 'c', {'synthetic'}, key, source_metadata=True, listed_source=listing)
    blob.reload.assert_not_called()


def test_listing_to_walk_keeps_identical_references_without_reload(monkeypatch):
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', 'synthetic')
    monkeypatch.setattr(live, 'private_cloud_sync_bucket', 'synthetic')
    pcm = b'\x01\x00' * 16000
    blobs = [
        SimpleNamespace(
            name=f'chunks/u/c/{timestamp}.batch.bin',
            generation=7,
            metageneration=3,
            size=len(pcm),
            metadata={'record_sample_rate': '16000'},
            reload=Mock(),
            download_as_bytes=Mock(return_value=pcm),
        )
        for timestamp in (100, 101)
    ]
    bucket = SimpleNamespace(
        name='synthetic',
        list_blobs=lambda **kw: iter(blobs),
        blob=lambda path, **kw: next(blob for blob in blobs if blob.name == path),
    )
    client = SimpleNamespace(bucket=lambda _: bucket)
    chunks = storage.list_audio_chunks('u', 'c', client=client, source_metadata=True, include_archive=False)
    profile = record_seal_profile.RowProfile(0)
    with profile.install():
        listed_units = list(live.retained_record_units('u', 'c', chunks, client, b'x' * 32))
    assert profile.chunks == 2 and profile.bytes == 64000 and profile.metadata_reloads == 0
    assert all(not blob.reload.called for blob in blobs)
    for blob in blobs:
        blob.download_as_bytes.assert_called_once_with(
            if_generation_match=7, if_metageneration_match=3, timeout=60, retry=None
        )
    for chunk in chunks:
        chunk.pop('metadata')
    legacy_units = list(live.retained_record_units('u', 'c', chunks, client, b'x' * 32))
    assert listed_units == legacy_units
    assert all(blob.reload.call_count == 1 for blob in blobs)

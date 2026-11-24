"""Listed metadata saves RPCs without relaxing retained-source integrity."""

import hashlib
import json
import struct
import time
from types import SimpleNamespace
from unittest.mock import Mock

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from google.api_core.exceptions import PreconditionFailed
import pytest

from utils.batch_pipeline import live, source_audio as source, record_seal_profile
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget
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

    # Existing operator and partial-plan identities retain their prior shape.
    assert all('source_metageneration' not in ref for _, _, refs in legacy_units for ref in refs)
    worker_units = list(live.retained_record_units('u', 'c', chunks, client, b'x' * 32, record_source_proof=True))
    assert all(
        ref['source_metageneration'] == 3 and ref['source_size'] == len(pcm)
        for _, _, refs in worker_units
        for ref in refs
    )


def test_disabled_metadata_reuse_reloads_even_with_a_complete_listing(monkeypatch):
    monkeypatch.setenv('BATCH_SOURCE_VERIFIED_METADATA_REUSE_ENABLED', 'false')
    raw = b'\x01\x00' * 10
    client, bucket, blob, ref = reader(raw, metadata={'record_sample_rate': '16000'})
    blob.metageneration = 4
    listing = {'size': len(raw), 'metadata': {'record_sample_rate': '8000'}, 'metageneration': 3}
    pcm = source.read_reference(
        client,
        ref,
        'u',
        'c',
        {'synthetic'},
        b'x' * 32,
        source_metadata=True,
        listed_source=listing,
        record_source_proof=True,
        retry_stale_metadata=True,
    )
    assert pcm == raw
    assert ref['sample_rate'] == 16000
    assert 'source_metageneration' not in ref
    bucket.blob.assert_called_once_with(ref['path'], generation=7)
    blob.reload.assert_called_once_with(if_generation_match=7, timeout=30, retry=None)
    blob.download_as_bytes.assert_called_once_with(if_generation_match=7, timeout=60, retry=None)


def test_stale_source_metadata_reloads_the_same_data_generation():
    raw = b'\x01\x00' * 10
    client, _, blob, ref = reader(raw, metadata={'record_sample_rate': '16000'})
    blob.metageneration = 4
    blob.download_as_bytes.side_effect = [PreconditionFailed('metadata changed'), raw]
    listing = {'size': len(raw), 'metadata': {'record_sample_rate': '8000'}, 'metageneration': 3}
    with pytest.raises(PreconditionFailed):
        source.read_reference(
            client, ref, 'u', 'c', {'synthetic'}, b'x' * 32, source_metadata=True, listed_source=listing
        )
    assert blob.reload.call_count == 0
    blob.download_as_bytes.reset_mock()
    blob.download_as_bytes.side_effect = [PreconditionFailed('metadata changed'), raw]
    budget = ArtifactReadBudget(time.monotonic() + 30, len(raw), 1)
    pcm = source.read_reference(
        client,
        ref,
        'u',
        'c',
        {'synthetic'},
        b'x' * 32,
        source_metadata=True,
        listed_source=listing,
        retry_stale_metadata=True,
        read_budget=budget,
    )
    assert budget.downloaded_bytes == budget.received_bytes == len(raw)
    assert pcm == raw
    assert blob.reload.call_args.kwargs['if_generation_match'] == 7
    assert [call.kwargs['if_metageneration_match'] for call in blob.download_as_bytes.call_args_list] == [3, 4]
    assert all(call.kwargs['if_generation_match'] == 7 for call in blob.download_as_bytes.call_args_list)


def test_materialization_reuses_a_verified_non_adjacent_pack_only_with_equal_decoder_settings(monkeypatch):
    audio = b'\x01\x00' * 3
    item = SimpleNamespace(owner_id='u', conversation_id='c', capture_at=100, duration_seconds=1)
    fetch = Mock(return_value=audio)
    identities = [('first', 16000), ('other', 16000), ('first', 16000), ('first', 8000)]
    references = [
        dict(
            bucket='synthetic',
            path=f'chunks/u/c/{path}',
            generation=7,
            source_metageneration=1,
            pcm_sha256=hashlib.sha256(audio).hexdigest(),
            start_frame=i,
            offset_frame=i % 3,
            frames=1,
            sample_rate=rate,
        )
        for i, (path, rate) in enumerate(identities)
    ]
    body = (
        source.MAGIC
        + json.dumps(
            dict(owner_id='u', conversation_id='c', capture_at=100, references=references, context={})
        ).encode()
    )
    memo_output = source.materialize(body, item, fetch)
    assert [(call.args[0]['path'], call.args[0]['sample_rate']) for call in fetch.call_args_list] == [
        ('chunks/u/c/first', 16000),
        ('chunks/u/c/other', 16000),
        ('chunks/u/c/first', 8000),
    ]
    monkeypatch.setenv('PRIVATE_SYNC_REQUEST_READ_MEMO_ENABLED', 'false')
    fetch.reset_mock()
    assert source.materialize(body, item, fetch) == memo_output
    assert fetch.call_count == 3  # Legacy adjacent reuse only.

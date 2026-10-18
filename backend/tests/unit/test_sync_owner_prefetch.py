"""Exercise bounded speculative I/O and real generation-checked consumption."""

from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import MagicMock

import pytest
from google.cloud.exceptions import NotFound

from config import sync_owner_concurrency as config
from utils.other import storage
from utils.sync import owner_prefetch
from utils.sync import staged_prefetch as cache_module
from utils.sync.staged_prefetch import MAX_FILE_BYTES, StagedBytes, StagedPrefetch


@pytest.fixture(autouse=True)
def preparation(monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', 'on')
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY', '4')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    cache = StagedPrefetch()
    monkeypatch.setattr(owner_prefetch, 'staged_prefetch', cache)
    monkeypatch.setattr(storage, 'staged_prefetch', cache)
    return cache


def test_width_is_conservative_and_kill_switch_is_serial(monkeypatch):
    monkeypatch.delenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED')
    monkeypatch.delenv('SYNC_BACKFILL_OWNER_CONCURRENCY')
    assert config.preparation_width() == 2
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY', '99')
    assert config.preparation_width() == 4
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY', 'bad')
    assert config.preparation_width() == 1
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', 'off')
    assert config.preparation_width() == 1


def test_two_owners_get_preparation_and_duplicate_owner_cannot_take_both_slots(preparation, monkeypatch):
    entered = threading.Barrier(3)
    release = threading.Event()
    calls = []
    monkeypatch.setattr(
        owner_prefetch.registry,
        'preparation_candidates',
        lambda uid, job, epoch: [{'job_id': 'next', 'payload': {'raw_blob_paths': [f'syncing/{uid}/next/audio']}}],
    )

    def download(path):
        calls.append(path)
        entered.wait(timeout=5)
        assert release.wait(timeout=5)
        return StagedBytes(b'audio', 'staged', 1)

    monkeypatch.setattr(owner_prefetch, 'prefetch_syncing_temporal_file', download)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(owner_prefetch.warm_owner, uid, 'head', 1) for uid in ('heavy', 'light')]
        try:
            entered.wait(timeout=5)
            owner_prefetch.warm_owner('heavy', 'head', 1)
            owner_prefetch.warm_owner('third', 'head', 1)
            assert len(calls) == 2
        finally:
            release.set()
        for future in futures:
            future.result(timeout=5)
    assert preparation.take('syncing/heavy/next/audio').data == b'audio'
    assert preparation.take('syncing/light/next/audio').data == b'audio'
    assert preparation.take('syncing/heavy/next/audio') is None


def test_local_slot_token_fences_late_publish_and_release(preparation):
    old = preparation.acquire('a')
    preparation.release('a', old)
    current = preparation.acquire('a')
    preparation.release('a', old)
    assert preparation.acquire('a') is None
    assert not preparation.put('a', old, 'old', StagedBytes(b'old', 'staged', 1))
    assert preparation.put('a', current, 'new', StagedBytes(b'new', 'staged', 1))


def test_byte_bounds_expiry_and_owner_isolation(preparation, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(cache_module.time, 'monotonic', lambda: now[0])
    a, b = preparation.acquire('a'), preparation.acquire('b')
    value = StagedBytes(b'x' * MAX_FILE_BYTES, 'staged', 1)
    assert not preparation.put('a', a, 'oversized', StagedBytes(value.data + b'x', 'staged', 1))
    for index in range(4):
        assert preparation.put('a', a, f'a-{index}', value)
    assert not preparation.put('a', a, 'a-more', value)
    assert preparation.put('b', b, 'b', value)
    now[0] = cache_module.CACHE_SECONDS + 1
    assert preparation.take('a-0') is None
    assert preparation.put('a', a, 'a-new', value)


@pytest.mark.parametrize('fault', ['network', 'nonprod', 'disabled', 'wrong_path'])
def test_speculation_never_becomes_authority(preparation, monkeypatch, fault):
    candidates = MagicMock(return_value=[{'job_id': 'next', 'payload': {'raw_blob_paths': ['elsewhere/audio']}}])
    monkeypatch.setattr(owner_prefetch.registry, 'preparation_candidates', candidates)
    download = MagicMock(side_effect=RuntimeError('network'))
    monkeypatch.setattr(owner_prefetch, 'prefetch_syncing_temporal_file', download)
    if fault == 'network':
        candidates.return_value[0]['payload']['raw_blob_paths'] = ['syncing/a/next/audio']
    elif fault == 'nonprod':
        monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    elif fault == 'disabled':
        monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', 'off')
    owner_prefetch.warm_owner('a', 'head', 1)
    assert preparation.acquire('a') is not None
    if fault != 'network':
        download.assert_not_called()


@pytest.mark.parametrize('state', ['unchanged', 'replaced', 'deleted', 'disabled', 'derived', 'encoded'])
def test_download_validates_generation_lifecycle_bucket_priority_and_switch(preparation, monkeypatch, tmp_path, state):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'derived' if state == 'derived' else '')
    monkeypatch.setattr(storage, 'syncing_local_bucket', 'staged')
    client = MagicMock()
    blob = client.bucket.return_value.blob.return_value
    blob.generation = 2 if state == 'replaced' else 1
    blob.content_encoding = 'gzip' if state == 'encoded' else None
    monkeypatch.setattr(storage, '_get_storage_client', lambda: client)
    path = 'syncing/a/next/audio'
    token = preparation.acquire('a')
    assert preparation.put('a', token, path, StagedBytes(b'prepared', 'staged', 1))
    if state == 'deleted':
        blob.reload.side_effect = NotFound('gone')
    if state == 'disabled':
        monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', 'off')
    assert storage.download_syncing_temporal_file(path) is (state != 'deleted')
    if state == 'unchanged':
        assert (tmp_path / path).read_bytes() == b'prepared'
        blob.download_to_filename.assert_not_called()
    elif state == 'deleted':
        assert not (tmp_path / path).exists()
        blob.download_to_filename.assert_not_called()
    else:
        blob.download_to_filename.assert_called_once_with(path)


def test_prefetch_download_is_generation_fenced_and_size_bounded(monkeypatch):
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', '')
    monkeypatch.setattr(storage, 'syncing_local_bucket', 'staged')
    client = MagicMock()
    blob = client.bucket.return_value.blob.return_value
    blob.size, blob.generation = 5, 42
    blob.content_encoding = None
    blob.download_as_bytes.return_value = b'bytes'
    monkeypatch.setattr(storage, '_get_storage_client', lambda: client)
    assert storage.prefetch_syncing_temporal_file('path') == StagedBytes(b'bytes', 'staged', 42)
    blob.download_as_bytes.assert_called_once_with(
        start=0, end=MAX_FILE_BYTES, if_generation_match=42, timeout=(1, 3), retry=None
    )
    blob.size = MAX_FILE_BYTES + 1
    assert storage.prefetch_syncing_temporal_file('path') is None
    assert blob.download_as_bytes.call_count == 1
    blob.size = 6
    assert storage.prefetch_syncing_temporal_file('path') is None  # Truncated range cannot become authoritative bytes.
    blob.size, blob.content_encoding = 5, 'gzip'
    assert storage.prefetch_syncing_temporal_file('path') is None

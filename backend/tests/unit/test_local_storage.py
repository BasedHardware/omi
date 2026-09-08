from pathlib import Path

import pytest

from utils.other.local_storage import LocalStorageClient, local_storage_root_from_env
from utils.other import storage as storage_helpers


def _configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    state_root = tmp_path / 'harness'
    storage_root = state_root / 'services' / 'storage'
    monkeypatch.setenv('OMI_HARNESS_STATE_ROOT', str(state_root))
    monkeypatch.setenv('OMI_LOCAL_STORAGE_ROOT', str(storage_root))
    monkeypatch.setenv('OMI_LOCAL_STORAGE_BASE_URL', 'http://127.0.0.1:8000/_local/storage')
    monkeypatch.setenv('FIREBASE_PROJECT_ID', 'demo-omi-local')
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8085')
    return storage_root


def test_local_storage_round_trip_and_http_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage_root = _configure(monkeypatch, tmp_path)
    client = LocalStorageClient.from_env()
    assert client is not None

    blob = client.bucket('speech-profiles').blob('user-1/speech profile.wav')
    blob.upload_from_string(b'voice-bytes', content_type='audio/wav')

    assert blob.download_as_bytes() == b'voice-bytes'
    assert blob.size == len(b'voice-bytes')
    assert blob.generate_signed_url() == (
        'http://127.0.0.1:8000/_local/storage/speech-profiles/user-1/speech%20profile.wav'
    )
    assert (storage_root / 'speech-profiles' / 'user-1' / 'speech profile.wav').read_bytes() == b'voice-bytes'


def test_production_storage_helper_returns_reachable_local_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    source = tmp_path / 'profile.wav'
    source.write_bytes(b'profile-audio')
    monkeypatch.setattr(storage_helpers, 'storage_client', None)
    monkeypatch.setattr(storage_helpers, 'speech_profiles_bucket', 'speech-profiles')

    url = storage_helpers.upload_profile_audio(str(source), 'user-1')

    assert url == 'http://127.0.0.1:8000/_local/storage/speech-profiles/user-1/speech_profile.wav'
    assert (tmp_path / 'harness/services/storage/speech-profiles/user-1/speech_profile.wav').read_bytes() == (
        b'profile-audio'
    )


def test_static_production_url_does_not_resolve_cloud_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('OMI_LOCAL_STORAGE_ROOT', raising=False)
    monkeypatch.setattr(storage_helpers, 'app_thumbnails_bucket', 'app-thumbnails')
    monkeypatch.setattr(
        storage_helpers,
        '_get_storage_client',
        lambda: pytest.fail('static URL generation must not construct a credentialed storage client'),
    )

    assert storage_helpers.get_app_thumbnail_url('thumbnail-1') == (
        'https://storage.googleapis.com/app-thumbnails/thumbnail-1.jpg'
    )


def test_local_storage_supports_streaming_copy_and_listing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    client = LocalStorageClient.from_env()
    assert client is not None
    source_bucket = client.bucket('sync-temporal')
    source = source_bucket.blob('user/chunk.bin')
    with source.open('wb') as handle:
        handle.write(b'chunk')

    destination_bucket = client.bucket('omi-private-cloud-sync')
    copied = source_bucket.copy_blob(source, destination_bucket, 'user/archive/chunk.bin')

    assert copied.download_as_bytes() == b'chunk'
    assert [blob.name for blob in destination_bucket.list_blobs(prefix='user/')] == ['user/archive/chunk.bin']


def test_local_storage_rejects_non_harness_and_traversal_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage_root = _configure(monkeypatch, tmp_path)
    monkeypatch.setenv('OMI_LOCAL_STORAGE_ROOT', str(tmp_path / 'outside'))
    with pytest.raises(RuntimeError, match='must be a child'):
        local_storage_root_from_env()

    monkeypatch.setenv('OMI_LOCAL_STORAGE_ROOT', str(storage_root))
    client = LocalStorageClient.from_env()
    assert client is not None
    with pytest.raises(ValueError, match='Unsafe'):
        client.bucket('speech-profiles').blob('../escape')

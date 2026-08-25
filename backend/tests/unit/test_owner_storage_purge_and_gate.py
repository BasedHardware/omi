from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from utils.other import storage as storage_mod
from utils.retrieval import frame_request_storage


class _Blob:
    def __init__(self, bucket, name):
        self.bucket = bucket
        self.name = name

    def delete(self):
        self.bucket.names.remove(self.name)


class _Bucket:
    def __init__(self, names):
        self.names = set(names)

    def blob(self, name):
        return _Blob(self, name)

    def list_blobs(self, *, prefix):
        return [_Blob(self, name) for name in sorted(self.names) if name.startswith(prefix)]


class _Client:
    def __init__(self, buckets):
        self.buckets = buckets

    def bucket(self, name):
        return self.buckets[name]


def test_owner_prefix_purge_removes_private_and_non_private_uid_objects(monkeypatch):
    uid = 'uid1'
    buckets = {
        'speech': _Bucket({f'{uid}/speech.wav', 'other/speech.wav'}),
        'private': _Bucket(
            {
                f'chunks/{uid}/conv/a.opus',
                f'audio/{uid}/conv/a.wav',
                f'merged/{uid}/conv/a.wav',
                f'playback/{uid}/conv/a.mp3',
                'chunks/other/keep.opus',
            }
        ),
        'sync': _Bucket({f'syncing/{uid}/job/input.bin', 'syncing/other/job/input.bin'}),
        'chat': _Bucket({f'{uid}/chat.txt', 'other/chat.txt'}),
    }
    monkeypatch.setattr(storage_mod, 'speech_profiles_bucket', 'speech')
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    monkeypatch.setattr(storage_mod, 'syncing_local_bucket', 'sync')
    monkeypatch.setattr(storage_mod, 'chat_files_bucket', 'chat')
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client(buckets))

    deleted = storage_mod.delete_all_user_storage_objects(uid)

    assert deleted == 7
    assert buckets['speech'].names == {'other/speech.wav'}
    assert buckets['private'].names == {'chunks/other/keep.opus'}
    assert buckets['sync'].names == {'syncing/other/job/input.bin'}
    assert buckets['chat'].names == {'other/chat.txt'}


def test_frame_prefix_purge_covers_both_tiers(monkeypatch):
    uid = 'uid1'
    temporary = _Bucket({f'frame-requests/{uid}/temporary', 'frame-requests/other/keep'})
    permanent = _Bucket({f'frame-requests/{uid}/permanent', 'frame-requests/other/keep'})
    client = _Client({'temporary': temporary, 'permanent': permanent})
    monkeypatch.setenv('BUCKET_FRAME_REQUESTS_TEMPORARY', 'temporary')
    monkeypatch.setenv('BUCKET_FRAME_REQUESTS', 'permanent')
    monkeypatch.setattr(frame_request_storage, '_get_storage_client', lambda: client)

    deleted = frame_request_storage.delete_all_frame_request_pixels_for_user(uid)

    assert deleted == 2
    assert temporary.names == {'frame-requests/other/keep'}
    assert permanent.names == {'frame-requests/other/keep'}


def test_real_gcs_owner_write_is_blocked_before_mutation(monkeypatch):
    bucket = _Bucket(set())
    blob = bucket.blob('uid1/recording.wav')
    client = _Client({'recordings': bucket})
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage_mod, 'memories_recordings_bucket', 'recordings')
    monkeypatch.setattr(storage_mod, '_uses_real_gcs_bucket', lambda value: True)

    @contextmanager
    def blocked_gate(uid, *, kind='external_data_write', firestore_client=None):
        raise RuntimeError('account deletion owns gate')
        yield  # pragma: no cover

    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', blocked_gate)
    upload = MagicMock()
    monkeypatch.setattr(blob, 'upload_from_filename', upload, raising=False)
    monkeypatch.setattr(bucket, 'blob', lambda name: blob)

    with pytest.raises(RuntimeError, match='owns gate'):
        storage_mod.upload_conversation_recording('/tmp/audio.wav', 'uid1', 'conv1')
    upload.assert_not_called()


def test_local_owner_write_keeps_offline_fake_provider_behavior(monkeypatch):
    bucket = _Bucket(set())
    client = _Client({'recordings': bucket})
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage_mod, 'memories_recordings_bucket', 'recordings')
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    blob = bucket.blob('uid1/conv1.wav')
    upload = MagicMock()
    monkeypatch.setattr(blob, 'upload_from_filename', upload, raising=False)
    monkeypatch.setattr(bucket, 'blob', lambda name: blob)

    storage_mod.upload_conversation_recording('/tmp/audio.wav', 'uid1', 'conv1')

    upload.assert_called_once_with('/tmp/audio.wav')


def test_uid_scoped_temporary_sync_upload_is_fenced(monkeypatch):
    bucket = _Bucket(set())
    client = _Client({'sync': bucket})
    blob = bucket.blob('syncing/uid1/job/input.bin')
    upload = MagicMock()
    monkeypatch.setattr(blob, 'upload_from_filename', upload, raising=False)
    monkeypatch.setattr(bucket, 'blob', lambda name: blob)
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage_mod, 'syncing_local_bucket', 'sync')
    monkeypatch.setattr(storage_mod, '_uses_real_gcs_bucket', lambda value: True)

    @contextmanager
    def blocked_gate(uid, *, kind='external_data_write', firestore_client=None):
        raise RuntimeError('account deletion owns gate')
        yield  # pragma: no cover

    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', blocked_gate)

    with pytest.raises(RuntimeError, match='owns gate'):
        storage_mod.upload_syncing_temporal_file('syncing/uid1/job/input.bin')
    upload.assert_not_called()

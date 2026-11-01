from contextlib import contextmanager
from types import SimpleNamespace
import struct
from unittest.mock import MagicMock

import pytest

from utils.other import storage as storage_mod
from database import account_deletion_operational_holds
from utils.retrieval import frame_request_storage


class _Blob:
    def __init__(self, bucket, name):
        self.bucket = bucket
        self.name = name

    def upload_from_string(self, data, **kwargs):
        self.bucket.names.add(self.name)

    @contextmanager
    def open(self, mode, **kwargs):
        stream = MagicMock()
        yield stream
        self.bucket.names.add(self.name)

    def delete(self):
        self.bucket.names.remove(self.name)

    def exists(self):
        return self.name in self.bucket.names


class _Bucket:
    def __init__(self, names):
        self.names = set(names)
        self.location = "us-central1"
        self.versioning_enabled = False
        self.soft_delete_policy = SimpleNamespace(retention_duration_seconds=0)

    def reload(self):
        pass

    def blob(self, name):
        return _Blob(self, name)

    def list_blobs(self, *, prefix, **kwargs):
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
                f'raw-mobile-batch/{uid}/digest/audio.bin',
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

    assert deleted == 8
    assert buckets['speech'].names == {'other/speech.wav'}
    assert buckets['private'].names == {'chunks/other/keep.opus'}
    assert buckets['sync'].names == {'syncing/other/job/input.bin'}
    assert buckets['chat'].names == {'other/chat.txt'}


def test_owner_prefix_purge_removes_diagnostic_ticket_lookup(monkeypatch):
    ticket = 'ABCDEF123456'
    bucket = _Bucket(
        {
            f'diagnostics/uid1/{ticket}.json',
            f'diagnostics/tickets/{ticket}.json',
            'diagnostics/other/keep.json',
        }
    )
    monkeypatch.setattr(storage_mod, 'speech_profiles_bucket', None)
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    monkeypatch.setattr(storage_mod, 'syncing_local_bucket', None)
    monkeypatch.setattr(storage_mod, 'chat_files_bucket', None)
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client({'private': bucket}))

    assert storage_mod.delete_all_user_storage_objects('uid1') == 2
    assert bucket.names == {'diagnostics/other/keep.json'}


def test_account_purge_releases_approved_hold_before_generation_bound_delete(monkeypatch):
    calls = []
    blob = SimpleNamespace(temporary_hold=True, generation=123, metageneration=2)
    bucket = SimpleNamespace(name='syncing-local')
    bucket.list_blobs = MagicMock(side_effect=[[blob], []])
    monkeypatch.setattr(storage_mod, '_uses_real_gcs_bucket', lambda value: True)

    def release(uid, held_blob):
        assert uid == 'uid1' and held_blob is blob
        calls.append('release')
        blob.temporary_hold = False
        blob.metageneration = 3

    def delete(**kwargs):
        assert blob.temporary_hold is False
        assert kwargs == {'if_generation_match': 123, 'if_metageneration_match': 3}
        calls.append('delete')

    blob.delete = delete
    monkeypatch.setattr(account_deletion_operational_holds, 'release_operational_hold_for_account_deletion', release)
    assert storage_mod._delete_owner_bucket_prefix(bucket, 'syncing/uid1/', account_deletion_uid='uid1') == 1
    assert calls == ['release', 'delete']


def test_account_purge_keeps_required_failure_when_hold_is_unapproved(monkeypatch):
    blob = SimpleNamespace(temporary_hold=True, delete=MagicMock())
    bucket = SimpleNamespace(name='syncing-local', list_blobs=MagicMock(return_value=[blob]))
    monkeypatch.setattr(
        account_deletion_operational_holds,
        'release_operational_hold_for_account_deletion',
        MagicMock(side_effect=RuntimeError('unapproved hold')),
    )
    with pytest.raises(RuntimeError, match='unapproved hold'):
        storage_mod._delete_owner_bucket_prefix(bucket, 'syncing/uid1/', account_deletion_uid='uid1')
    blob.delete.assert_not_called()


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
    def blocked_gate(uid, *, firestore_client=None):
        raise RuntimeError('account deletion owns gate')
        yield  # pragma: no cover

    monkeypatch.setattr(storage_mod, 'external_write_fence', blocked_gate)
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
    def blocked_gate(uid, *, firestore_client=None):
        raise RuntimeError('account deletion owns gate')
        yield  # pragma: no cover

    monkeypatch.setattr(storage_mod, 'external_write_fence', blocked_gate)

    with pytest.raises(RuntimeError, match='owns gate'):
        storage_mod.upload_syncing_temporal_file('syncing/uid1/job/input.bin')
    upload.assert_not_called()


def test_account_wipe_removes_packs_intents_and_receipts_with_flag_off(monkeypatch):
    prefixes = (
        storage_mod.audio_packs.SOURCE_PREFIX,
        storage_mod.audio_packs.PACK_PREFIX,
        storage_mod.audio_packs.INDEX_PREFIX,
    )
    names = {f'{p}uid1/day/object' for p in prefixes}
    names.add(f'{storage_mod.audio_packs.INDEX_PREFIX}uid1/captures/receipt.json')
    other = {f'{p}other/day/object' for p in prefixes}
    canonical = _Bucket(names | other)
    monkeypatch.setenv('AUDIO_CANONICAL_PACKING_ENABLED', 'false')
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    monkeypatch.setattr(storage_mod, 'speech_profiles_bucket', None)
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    monkeypatch.setattr(storage_mod, 'syncing_local_bucket', None)
    monkeypatch.setattr(storage_mod, 'chat_files_bucket', None)
    monkeypatch.setattr(
        storage_mod, '_get_storage_client', lambda: _Client({'canonical': canonical, 'private': _Bucket(set())})
    )
    assert storage_mod.delete_all_user_storage_objects('uid1') == 4
    assert canonical.names == other


def test_new_mobile_capture_routes_unchanged_bytes_to_canonical_bucket(monkeypatch, tmp_path):
    monkeypatch.setenv('AUDIO_CANONICAL_PACKING_ENABLED', 'true')
    canonical = _Bucket(set())
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: canonical)
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client({'private': _Bucket(set())}))
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    monkeypatch.setattr(storage_mod.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(storage_mod.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    archive = MagicMock()
    monkeypatch.setattr(storage_mod.audio_packs, 'archive_capture', archive)
    path = tmp_path / 'audio_omimobilebatch001_opus_16000_1_fs160_1726185600.bin'
    raw = b'\x03\x00\x00\x00abc\x03\x00\x00\x00\xf8\xff\xfe'
    path.write_bytes(raw)
    storage_mod.archive_mobile_batch_raw_files('uid1', [str(path)])
    assert archive.call_args.args == (canonical, 'uid1', raw)
    metadata = archive.call_args.kwargs
    assert metadata['format'] == 'omi-wal-uint32le-opus-v1'
    assert metadata['provenance']['capture_day'] == '2024-09-13'
    assert metadata['provenance']['capture_start'] == 1726185600
    assert metadata['identity'].startswith(path.name)


def test_canonical_bucket_rejects_retained_generations(monkeypatch):
    bucket = _Bucket(set())
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client({'canonical': bucket}))
    bucket.versioning_enabled = True
    with pytest.raises(RuntimeError, match='versioning off'):
        storage_mod.get_canonical_audio_bucket()
    bucket.versioning_enabled = False
    bucket.soft_delete_policy.retention_duration_seconds = 604800
    with pytest.raises(RuntimeError, match='soft delete off'):
        storage_mod.get_canonical_audio_bucket()


def test_merge_cleanup_preserves_canonical_and_explicit_privacy_calls_erase(monkeypatch):
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    private = _Bucket(set())
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client({'private': private}))
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    erased = MagicMock()
    linked = MagicMock()
    monkeypatch.setattr(storage_mod.audio_packs, 'delete_conversation', erased)
    monkeypatch.setattr(storage_mod.audio_packs, 'link_conversations', linked)
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: private)

    @contextmanager
    def gate(*args, **kwargs):
        yield

    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', gate)
    storage_mod.delete_conversation_audio_files('u', 'c')
    erased.assert_not_called()
    storage_mod.delete_conversation_audio_files('u', 'c', merged_into='merged')
    linked.assert_called_once_with(private, 'u', ['c'], 'merged')
    erased.assert_not_called()
    storage_mod.delete_privacy_conversation_audio('u', 'merged')
    erased.assert_called_once_with(private, 'u', 'merged')


def test_enhanced_pusher_manifest_matches_envelope_and_full_duration(monkeypatch):
    monkeypatch.setenv('AUDIO_CANONICAL_PACKING_ENABLED', 'true')
    monkeypatch.setattr(storage_mod.conversation_tombstones, 'is_deleted', lambda *args: False)
    canonical = _Bucket(set())
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: canonical)
    archive = MagicMock(side_effect=RuntimeError('stop after canonical intake'))
    monkeypatch.setattr(storage_mod.audio_packs, 'archive_capture', archive)
    _prepare_playback(monkeypatch)
    storage_mod.upload_audio_chunks_batch(
        [{'timestamp': 1726185600, 'data': bytes(32000)}],
        'owner',
        'conv',
        data_protection_level='enhanced',
        sample_rate=16000,
    )
    payload = archive.call_args.args[2]
    assert struct.unpack('>I', payload[:4])[0] == len(payload) - 4
    assert archive.call_args.kwargs['provenance']['encryption_envelope'].startswith('uint32be-')
    assert archive.call_args.kwargs['conversation_ranges'][0]['end'] == 1726185601


def test_preexisting_conversation_deletion_blocks_new_canonical_admission(monkeypatch):
    monkeypatch.setenv('AUDIO_CANONICAL_PACKING_ENABLED', 'true')
    monkeypatch.setattr(storage_mod.conversation_tombstones, 'is_deleted', lambda *args: True)
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: _Bucket(set()))
    monkeypatch.setattr(storage_mod.audio_packs, 'conversation_chain', lambda *args: ['deleted'])
    archive = MagicMock()
    monkeypatch.setattr(storage_mod.audio_packs, 'archive_capture', archive)
    _prepare_playback(monkeypatch)
    storage_mod.upload_audio_chunks_batch(
        [{'timestamp': 1726185600, 'data': bytes(32000)}],
        'owner',
        'deleted',
        data_protection_level='standard',
        sample_rate=16000,
    )
    archive.assert_not_called()


def _prepare_playback(monkeypatch):
    private = _Bucket(set())
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client({'private': private}))
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')

    @contextmanager
    def gate(*args, **kwargs):
        yield

    monkeypatch.setattr(storage_mod, 'owner_storage_write_gate', gate)
    return private


@pytest.mark.parametrize('failure', ['bucket', 'archive', None])
def test_playback_commits_before_optional_archive_and_survives_failure(monkeypatch, failure):
    private = _prepare_playback(monkeypatch)
    monkeypatch.setenv('AUDIO_CANONICAL_PACKING_ENABLED', 'true')
    monkeypatch.setattr(storage_mod.conversation_tombstones, 'is_deleted', lambda *args: False)

    def bucket():
        assert private.names == {'chunks/u/c/100.000.batch.bin'}
        if failure == 'bucket':
            raise RuntimeError('bucket policy unavailable')
        return private

    def archive(*args, **kwargs):
        assert private.names == {'chunks/u/c/100.000.batch.bin'}
        if failure == 'archive':
            raise RuntimeError('archive unavailable')

    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', bucket)
    monkeypatch.setattr(storage_mod.audio_packs, 'archive_capture', archive)
    assert storage_mod.upload_audio_chunks_batch(
        [{'timestamp': 100, 'data': bytes(32000)}], 'u', 'c', data_protection_level='standard', sample_rate=16000
    ) == ['chunks/u/c/100.000.batch.bin']


@pytest.mark.parametrize('failure', [False, True])
def test_mobile_primary_archive_commits_before_canonical_success_or_failure(monkeypatch, tmp_path, failure):
    private = _prepare_playback(monkeypatch)
    monkeypatch.setenv('AUDIO_CANONICAL_PACKING_ENABLED', 'true')
    monkeypatch.setattr(storage_mod.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(storage_mod.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: private)
    path = tmp_path / 'audio_omimobilebatch001_opus_16000_1_fs160_1726185600.bin'
    path.write_bytes(b'original')

    def archive(*args, **kwargs):
        assert len(private.names) == 1
        assert next(iter(private.names)).startswith('raw-mobile-batch/u/')
        if failure:
            raise RuntimeError('canonical unavailable')

    monkeypatch.setattr(storage_mod.audio_packs, 'archive_capture', archive)
    storage_mod.archive_mobile_batch_raw_files('u', [str(path)])
    assert len(private.names) == 1


def test_canonical_bucket_policy_cached_until_expiry(monkeypatch):
    bucket = _Bucket(set())
    bucket.reload = MagicMock()
    client = _Client({'canonical': bucket})
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage_mod, '_canonical_bucket_cache', None)
    now = [100]
    monkeypatch.setattr(storage_mod.time, 'monotonic', lambda: now[0])
    assert storage_mod.get_canonical_audio_bucket() is bucket
    assert storage_mod.get_canonical_audio_bucket() is bucket
    bucket.reload.assert_called_once()
    now[0] += 301
    storage_mod.get_canonical_audio_bucket()
    assert bucket.reload.call_count == 2


def test_privacy_erases_snapshotted_bridge_donors_only_at_explicit_boundary(monkeypatch):
    private = _prepare_playback(monkeypatch)
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: private)
    erased = MagicMock()
    monkeypatch.setattr(storage_mod.audio_packs, 'delete_conversation', erased)

    @contextmanager
    def gate(*args, **kwargs):
        yield

    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', gate)
    storage_mod.delete_privacy_conversation_audio('u', 'survivor', source_ids=['donor', 'donor'])
    assert erased.call_count == 2
    assert {call.args for call in erased.call_args_list} == {(private, 'u', 'survivor'), (private, 'u', 'donor')}

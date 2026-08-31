"""Owner-scoped purges and the owner write fence, over the neutral object-store port (ADR-0032).

Upstream's version injected a fake GCS *client* and asserted on ``blob.upload_from_filename`` /
``bucket.list_blobs``. Those shapes are gone from the port, so each test is re-expressed against the
in-memory ``FakeObjectStore``; the five things being proven are unchanged:

  * an account purge removes every configured owner prefix and nothing else;
  * the frame-request purge covers BOTH tiers;
  * a fenced write raises BEFORE mutating anything;
  * a local/offline stage keeps writing (the fence must not break offline deployments);
  * the sync bucket derives its owner from the path and is fenced the same way.

One difference is ours and deliberate: the fence engages on any real adapter, not only GCS
(``_uses_real_object_store``), because on-prem the external provider is usually S3/RustFS and it is
just as external. See the module docstring in ``utils/other/storage.py``.
"""

from contextlib import contextmanager

import pytest

from tests.object_store_fakes import FakeObjectStore
from utils.other import storage as storage_mod
from utils.retrieval import frame_request_storage


def _store(monkeypatch, seed=()):
    """A fake store injected at the ONE seam both the writes and the fence read."""

    store = FakeObjectStore()
    for bucket, key in seed:
        store.put(bucket, key, b'x')
    monkeypatch.setattr(storage_mod, '_object_store', lambda: store)
    return store


def _keys(store, bucket):
    return {info.key for info in store.list(bucket, '')}


@contextmanager
def _blocked_gate(uid, *, firestore_client=None):
    raise RuntimeError('account deletion owns gate')
    yield  # pragma: no cover


def test_owner_prefix_purge_removes_private_and_non_private_uid_objects(monkeypatch):
    uid = 'uid1'
    store = _store(
        monkeypatch,
        [
            ('speech', f'{uid}/speech.wav'),
            ('speech', 'other/speech.wav'),
            ('private', f'chunks/{uid}/conv/a.opus'),
            ('private', f'audio/{uid}/conv/a.wav'),
            ('private', f'merged/{uid}/conv/a.wav'),
            ('private', f'playback/{uid}/conv/a.mp3'),
            ('private', 'chunks/other/keep.opus'),
            ('sync', f'syncing/{uid}/job/input.bin'),
            ('sync', 'syncing/other/job/input.bin'),
            ('chat', f'{uid}/chat.txt'),
            ('chat', 'other/chat.txt'),
        ],
    )
    monkeypatch.setattr(storage_mod, 'speech_profiles_bucket', 'speech')
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    monkeypatch.setattr(storage_mod, 'syncing_local_bucket', 'sync')
    monkeypatch.setattr(storage_mod, 'chat_files_bucket', 'chat')

    deleted = storage_mod.delete_all_user_storage_objects(uid)

    assert deleted == 7
    assert _keys(store, 'speech') == {'other/speech.wav'}
    assert _keys(store, 'private') == {'chunks/other/keep.opus'}
    assert _keys(store, 'sync') == {'syncing/other/job/input.bin'}
    assert _keys(store, 'chat') == {'other/chat.txt'}


def test_frame_prefix_purge_covers_both_tiers(monkeypatch):
    uid = 'uid1'
    store = _store(
        monkeypatch,
        [
            ('temporary', f'frame-requests/{uid}/temporary'),
            ('temporary', 'frame-requests/other/keep'),
            ('permanent', f'frame-requests/{uid}/permanent'),
            ('permanent', 'frame-requests/other/keep'),
        ],
    )
    monkeypatch.setenv('BUCKET_FRAME_REQUESTS_TEMPORARY', 'temporary')
    monkeypatch.setenv('BUCKET_FRAME_REQUESTS', 'permanent')

    deleted = frame_request_storage.delete_all_frame_request_pixels_for_user(uid)

    assert deleted == 2
    assert _keys(store, 'temporary') == {'frame-requests/other/keep'}
    assert _keys(store, 'permanent') == {'frame-requests/other/keep'}


def test_real_provider_owner_write_is_blocked_before_mutation(monkeypatch, tmp_path):
    store = _store(monkeypatch)
    monkeypatch.setattr(storage_mod, 'memories_recordings_bucket', 'recordings')
    monkeypatch.setattr(storage_mod, '_uses_real_object_store', lambda *_args: True)
    monkeypatch.setattr(storage_mod, 'external_write_fence', _blocked_gate)
    source = tmp_path / 'audio.wav'
    source.write_bytes(b'audio')

    with pytest.raises(RuntimeError, match='owns gate'):
        storage_mod.upload_conversation_recording(str(source), 'uid1', 'conv1')

    # Before the mutation, not after it: nothing reached the store.
    assert not _keys(store, 'recordings')


def test_local_owner_write_keeps_offline_provider_behavior(monkeypatch, tmp_path):
    store = _store(monkeypatch)
    monkeypatch.setattr(storage_mod, 'memories_recordings_bucket', 'recordings')
    monkeypatch.setattr(storage_mod, 'external_write_fence', _blocked_gate)
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    # Not under test here, and it caches through Redis: this test is about the fence NOT blocking an
    # offline write, so the URL the caller gets back afterwards is stubbed.
    monkeypatch.setattr(storage_mod, '_signed_url', lambda bucket, key, minutes: f'signed://{bucket}/{key}')
    source = tmp_path / 'audio.wav'
    source.write_bytes(b'audio')

    storage_mod.upload_conversation_recording(str(source), 'uid1', 'conv1')

    assert _keys(store, 'recordings') == {'uid1/conv1.wav'}


def test_uid_scoped_temporary_sync_upload_is_fenced(monkeypatch, tmp_path):
    store = _store(monkeypatch)
    monkeypatch.setattr(storage_mod, 'syncing_local_bucket', 'sync')
    monkeypatch.setattr(storage_mod, '_uses_real_object_store', lambda *_args: True)
    monkeypatch.setattr(storage_mod, 'external_write_fence', _blocked_gate)
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'syncing' / 'uid1' / 'job').mkdir(parents=True)
    (tmp_path / 'syncing' / 'uid1' / 'job' / 'input.bin').write_bytes(b'sync')

    with pytest.raises(RuntimeError, match='owns gate'):
        storage_mod.upload_syncing_temporal_file('syncing/uid1/job/input.bin')

    assert not _keys(store, 'sync')

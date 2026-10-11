"""Real private serialization/encryption and deletion, with only blob IO faked."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import time

from cryptography.exceptions import InvalidTag
import numpy as np
import pytest

from utils.other import storage
from utils.speaker_tag_prompts import embedding_cache as cache, selection, service


class Blob:
    def __init__(self, bucket, name):
        self.bucket, self.name = bucket, name

    def upload_from_string(self, data, **kwargs):
        self.bucket.objects[self.name] = data

    def download_as_bytes(self):
        if self.name not in self.bucket.objects:
            raise storage.BlobNotFound('synthetic cache miss')
        return self.bucket.objects[self.name]

    def delete(self):
        if self.name not in self.bucket.objects:
            raise storage.BlobNotFound('synthetic cache miss')
        del self.bucket.objects[self.name]


class Bucket:
    def __init__(self):
        self.objects = {}

    def blob(self, name):
        return Blob(self, name)

    def list_blobs(self, *, prefix):
        return [self.blob(name) for name in list(self.objects) if name.startswith(prefix)]


@pytest.fixture
def private_bucket(monkeypatch):
    bucket = Bucket()
    bucket.deleted_conversations = set()
    monkeypatch.setattr(
        cache.conversation_tombstones, 'is_deleted', lambda uid, cid: (uid, cid) in bucket.deleted_conversations
    )
    monkeypatch.setattr(cache.conversations_db, 'get_conversation', lambda uid, cid: {'id': cid})

    class Client:
        def bucket(self, name):
            assert name == 'private-test'
            return bucket

    monkeypatch.setattr(storage, '_get_storage_client', lambda: Client())
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', 'private-test')
    for name in ('speech_profiles_bucket', 'syncing_local_bucket', 'chat_files_bucket'):
        monkeypatch.setattr(storage, name, None)
    return bucket


def entries():
    return {hashlib.sha256(b'clip').hexdigest(): {'vector': [0.5, 0.8660254], 'expires_at': time.time() + 60}}


def test_real_cache_roundtrip_owner_key_expiry_and_conversation_purge(private_bucket, monkeypatch):
    now = time.time()
    original = entries()
    cache.save('u', 'c', original)
    path, ciphertext = next(iter(private_bucket.objects.items()))
    assert path == 'audio/u/c/owner-prompt-embeddings.v1.enc'
    assert b'vector' not in ciphertext and b'0.866' not in ciphertext
    with pytest.raises((UnicodeDecodeError, ValueError)):
        json.loads(ciphertext)
    plaintext = storage.encryption.decrypt_audio_file(ciphertext, 'u')
    decoded = json.loads(plaintext)
    assert decoded['v'] == 1 and len(decoded['entries']) == 1
    loaded = cache.load('u', 'c')
    np.testing.assert_array_equal(next(iter(loaded.values()))['vector'], np.array([0.5, 0.8660254], dtype=np.float32))
    # A copied ciphertext is still unreadable with another owner's key.
    private_bucket.objects['audio/other/c/owner-prompt-embeddings.v1.enc'] = ciphertext
    with pytest.raises(InvalidTag):
        cache.load('other', 'c')
    monkeypatch.setattr(cache.time, 'time', lambda: now + 61)
    assert cache.load('u', 'c') == {}
    storage.delete_conversation_audio_files('u', 'c')
    assert cache.load('u', 'c') == {}
    assert list(private_bucket.objects) == ['audio/other/c/owner-prompt-embeddings.v1.enc']


def test_real_cache_is_bounded_and_account_purge_covers_each_conversation(private_bucket):
    original = {
        hashlib.sha256(str(i).encode()).hexdigest(): {'vector': [1.0, 0.0], 'expires_at': time.time() + 60}
        for i in range(20)
    }
    cache.save('u', 'c', original)
    assert len(cache.load('u', 'c')) == cache.MAX_CONSTITUENTS
    cache.save('u', 'second', entries())
    cache.save('other', 'c', entries())
    assert storage.delete_all_user_storage_objects('u') == 2
    assert cache.load('u', 'c') == cache.load('u', 'second') == {}
    assert cache.load('other', 'c')


def test_cache_upload_uses_real_owner_write_fence(private_bucket, monkeypatch):
    monkeypatch.setattr(storage, '_uses_real_gcs_bucket', lambda bucket: True)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('PROVIDER_MODE', raising=False)
    calls = []

    @contextmanager
    def blocked(uid):
        calls.append(uid)
        raise RuntimeError('deletion owns the owner fence')
        yield

    monkeypatch.setattr(storage, 'external_write_fence', blocked)
    with pytest.raises(RuntimeError, match='owner fence'):
        cache.save('u', 'c', entries())
    assert calls == ['u'] and not private_bucket.objects


def test_service_reuses_real_encrypted_cache_without_plaintext_redis(private_bucket, monkeypatch):
    now = datetime.now(timezone.utc)
    raw = dict(
        id='c',
        started_at=now,
        status='completed',
        audio_files=[dict(chunk_timestamps=[now.timestamp()], duration=30)],
        transcript_segments=[
            dict(
                id=f's{i}', speaker_id=1, start=float(start), end=float(start + 6), text='Synthetic clip', is_user=False
            )
            for i, start in enumerate((0, 10))
        ],
    )
    monkeypatch.setattr(service, 'verified_clip_pcm', lambda uid, raw, start, *a, **k: bytes([int(start)]) * 192000)
    calls = []

    def extract(*args, **kwargs):
        calls.append(True)
        return np.array([[0.5, 0.8660254]], dtype=np.float32)

    monkeypatch.setattr(service, 'extract_embedding_from_bytes', extract)
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda *a, **k: pytest.fail('Plaintext biometric Redis'))
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda *a: pytest.fail('Legacy biometric Redis'))
    runs = selection.complete_owner_runs(raw)
    first = service._owner_group_evidence('u', raw, runs, [1.0, 0.0], time.monotonic() + 8)
    assert len(calls) == 2 and len(cache.load('u', 'c')) == 2
    second = service._owner_group_evidence('u', raw, runs, [1.0, 0.0], time.monotonic() + 8)
    assert len(calls) == 2 and first == second
    storage.delete_conversation_audio_files('u', 'c')
    assert cache.load('u', 'c') == {}


def test_cache_reader_rejects_unbounded_dimensions_and_invalid_serialized_entries(private_bucket):
    malformed = {
        'v': 1,
        'entries': {
            'a' * 64: {'vector': [1.0] * (cache.MAX_DIMENSIONS + 1), 'expires_at': time.time() + 60},
            'b' * 64: {'vector': [float('nan')], 'expires_at': time.time() + 60},
            'c' * 64: {'vector': [1.0], 'expires_at': time.time() + cache.TTL_SECONDS + 60},
        },
    }
    storage.upload_owner_prompt_embedding_cache('u', 'c', json.dumps(malformed).encode())
    assert cache.load('u', 'c') == {}


@pytest.mark.parametrize('during_upload', [False, True])
def test_deletion_intent_blocks_or_purges_late_encrypted_fill(private_bucket, monkeypatch, during_upload):
    if during_upload:
        real_upload = storage.upload_owner_prompt_embedding_cache

        def upload(uid, cid, data):
            real_upload(uid, cid, data)
            private_bucket.deleted_conversations.add((uid, cid))
            storage.delete_owner_prompt_embedding_cache(uid, cid)
            real_upload(uid, cid, data)  # the write that raced after the purge

        monkeypatch.setattr(storage, 'upload_owner_prompt_embedding_cache', upload)
    else:
        private_bucket.deleted_conversations.add(('u', 'c'))
    cache.save('u', 'c', entries())
    assert not private_bucket.objects and cache.load('u', 'c') == {}
    storage.delete_owner_prompt_embedding_cache('u', 'c')  # retry is idempotent


def test_unconfirmed_post_write_deletion_fence_removes_new_object(private_bucket, monkeypatch):
    calls = []

    def is_deleted(*args):
        calls.append(True)
        if len(calls) == 2:
            raise RuntimeError('synthetic fence read failure')
        return False

    monkeypatch.setattr(cache.conversation_tombstones, 'is_deleted', is_deleted)
    with pytest.raises(RuntimeError, match='fence read failure'):
        cache.save('u', 'c', entries())
    assert not private_bucket.objects


def test_parent_removed_during_cache_upload_cannot_leave_orphan(private_bucket, monkeypatch):
    reads = []

    def source(*args):
        reads.append(True)
        return {'id': 'c'} if len(reads) == 1 else None

    monkeypatch.setattr(cache.conversations_db, 'get_conversation', source)
    cache.save('u', 'c', entries())
    assert not private_bucket.objects

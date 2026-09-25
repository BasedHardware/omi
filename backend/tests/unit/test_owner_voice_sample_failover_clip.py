"""Clip-path proof: a post-failover "That's me" pools the owner's real audio.

A v2 conversation that experienced a mid-session STT failover: the replacement
provider's timestamps restarted at zero, and the v2 projection placed the
owner's post-failover segments at their true capture positions (minutes past
the pre-failover audio). "That's me" on those segments must clip and pool
exactly that window's audio — under the legacy first-audio + provider-time
formula the same answer selected audio from the very start of the recording
(the 2026-09-25 incident's missing owner_voice_confirmation). The pooled
sample's provenance is proven by content identity, not by timestamps.

Runs the real ``store_owner_voice_sample`` through the real
``owner_clip_window`` and the real span-carrying clip path (batch upload ->
span-aware listing -> merge -> sample-accurate trim) on an in-memory GCS
double; only the transcription verifier, the embedding model and the
voiceprint write are faked, and the fakes capture exactly what reached them.
"""

import io
import logging
import wave
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

import utils.other.storage as storage_module
from database import conversations as conversations_db
from utils.other.storage import upload_audio_chunks_batch
from utils.speaker_tag_prompts import service as service_module
from utils.speaker_tag_prompts.service import store_owner_voice_sample

RATE = 16000
UID = 'uid-owner-sample'
CONV = 'conv-owner-sample'
T0 = 1_700_000_000.0

PRE_PHRASE_AT = 10.0  # owner speech before the failover
POST_PHRASE_AT = 80.0  # owner speech after the failover, provider time restarted at 0
CLIP_SECONDS = 6.0


def _pattern(marker: int, seconds: float) -> bytes:
    """Identifiable PCM16: every byte encodes (marker + index)."""
    return bytes(((marker + i) & 0xFF) for i in range(int(seconds * RATE) * 2))


class _Writer:
    def __init__(self, blob):
        self.blob = blob
        self.buf = bytearray()

    def write(self, data):
        self.buf.extend(data)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.blob._store(bytes(self.buf))


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket = bucket
        self.name = name
        self._data = None
        self.metadata = None

    @property
    def size(self):
        return len(self._data) if self._data is not None else None

    def _store(self, data):
        self._data = data
        self.bucket.blobs[self.name] = self

    def exists(self):
        return self._data is not None

    def open(self, mode, content_type=None):
        assert mode == 'wb'
        return _Writer(self)

    def download_as_bytes(self):
        if self._data is None:
            raise FileNotFoundError(self.name)
        return self._data

    def delete(self):
        self.bucket.blobs.pop(self.name, None)


class FakeBucket:
    def __init__(self):
        self.blobs = {}

    def blob(self, name):
        return self.blobs.get(name) or FakeBlob(self, name)

    def list_blobs(self, prefix=None):
        return [self.blobs[name] for name in sorted(self.blobs) if name.startswith(prefix)]


class FakeStorageClient:
    def __init__(self):
        self._buckets = {}

    def bucket(self, name):
        return self._buckets.setdefault(name, FakeBucket())


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
def gcs(monkeypatch):
    client = FakeStorageClient()
    monkeypatch.setattr(storage_module, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: 'standard')
    return client


def _row(phrase_pre: bytes, phrase_post: bytes) -> dict:
    return {
        'id': CONV,
        'status': 'completed',
        'language': 'en',
        'started_at': datetime.fromtimestamp(T0, tz=timezone.utc),
        'private_cloud_sync_enabled': True,
        'audio_timeline': {'version': 2},
        'transcript_segments': [
            {
                'id': 'seg-pre',
                'speaker_id': 0,
                'is_user': True,
                'start': PRE_PHRASE_AT,
                'end': PRE_PHRASE_AT + 5.0,
                'text': 'owner line before the failover',
            },
            {
                'id': 'seg-post-1',
                'speaker_id': 0,
                'is_user': True,
                'start': POST_PHRASE_AT,
                'end': POST_PHRASE_AT + 3.0,
                'text': 'owner line after the failover one',
            },
            {
                'id': 'seg-post-2',
                'speaker_id': 0,
                'is_user': True,
                'start': POST_PHRASE_AT + 3.0,
                'end': POST_PHRASE_AT + CLIP_SECONDS,
                'text': 'owner line after the failover two',
            },
        ],
        'audio_files': [
            {
                'id': 'file-1',
                'chunk_timestamps': [T0 + PRE_PHRASE_AT, T0 + POST_PHRASE_AT],
                'chunk_spans': [
                    (T0 + PRE_PHRASE_AT, T0 + PRE_PHRASE_AT + 5.0),
                    (T0 + POST_PHRASE_AT, T0 + POST_PHRASE_AT + CLIP_SECONDS),
                ],
            }
        ],
    }


@pytest.mark.anyio
async def test_thats_me_after_failover_pools_the_owners_actual_window(monkeypatch, gcs, caplog):
    phrase_pre = _pattern(1, 5.0)
    phrase_post = _pattern(2, CLIP_SECONDS)
    assert phrase_pre != phrase_post

    # The real span-carrying uploads, one contiguous batch per run exactly as
    # the pusher flushes them (it never batches across a discontinuity): two
    # chunks whose validated spans place the phrases at their projected wall
    # positions.
    upload_audio_chunks_batch(
        [
            {
                'data': phrase_pre,
                'timestamp': T0 + PRE_PHRASE_AT,
                'span': {'start': T0 + PRE_PHRASE_AT, 'samples': int(5.0 * RATE), 'sample_rate': RATE},
            }
        ],
        UID,
        CONV,
        data_protection_level='standard',
    )
    upload_audio_chunks_batch(
        [
            {
                'data': phrase_post,
                'timestamp': T0 + POST_PHRASE_AT,
                'span': {'start': T0 + POST_PHRASE_AT, 'samples': int(CLIP_SECONDS * RATE), 'sample_rate': RATE},
            }
        ],
        UID,
        CONV,
        data_protection_level='standard',
    )
    row = _row(phrase_pre, phrase_post)
    monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, conversation_id: dict(row))

    captured = {}

    async def fake_verify(wav, sample_rate, text, language=None):
        captured['verified_text'] = text
        return (text, True, '')

    def fake_embedding(wav, name):
        with wave.open(io.BytesIO(wav), 'rb') as handle:
            captured['pooled_pcm'] = handle.readframes(handle.getnframes())
        return np.ones((1, 4), dtype=np.float32)

    def fake_pool_confirmation(uid, embedding, pool, *, conversation_id):
        captured['pooled_embedding'] = embedding
        captured['pooled_conversation'] = conversation_id
        return 1

    monkeypatch.setattr(service_module, 'verify_and_transcribe_sample', fake_verify)
    monkeypatch.setattr(service_module, 'extract_embedding_from_bytes', fake_embedding)
    monkeypatch.setattr(service_module.voice_profiles_db, 'add_owner_voice_confirmation', fake_pool_confirmation)

    with caplog.at_level(logging.INFO, logger='utils.speaker_tag_prompts.service'):
        outcome = await store_owner_voice_sample(UID, CONV, ['seg-post-1', 'seg-post-2'])

    assert outcome == 'stored'
    # The pooled sample is EXACTLY the owner's post-failover audio window -
    # the v2 projection - and not the pre-failover phrase the legacy
    # first-audio + restarted-provider-time formula would have selected.
    assert captured['pooled_pcm'] == phrase_post
    assert captured['pooled_pcm'] != phrase_pre
    assert captured['pooled_embedding'] == [1.0, 1.0, 1.0, 1.0]
    assert captured['pooled_conversation'] == CONV

    # The outcome is attributable: one log line with the conversation id and
    # no uid anywhere on it.
    lines = [record.message for record in caplog.records if 'owner sample outcome=stored' in record.message]
    assert lines == [f'speaker tag prompt owner sample outcome=stored conversation={CONV}']
    assert UID not in lines[0]

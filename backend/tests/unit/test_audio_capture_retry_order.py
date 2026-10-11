"""Capture retry order, single publication, and client frames, through the real coordinators."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from routers.listen import transcripts
from tests.unit import test_speaker_learning_pool as pool
from tests.unit.test_speaker_learning_pool import world  # noqa: F401
from tests.unit.fixtures.audio_chunk_storage import memory_bucket  # noqa: F401
from tests.unit import test_teaching_placement as tp
from utils import speaker_identification as teaching, speaker_sample
from utils.other import storage
from utils.speaker_tag_prompts import service


@pytest.mark.parametrize('gated', [False, True])
def test_live_translation_frames_never_carry_capture_fields(monkeypatch, gated):
    segment = dict(
        id='s', text='hello', start=0.0, end=8.0, speaker_id=0, audio_capture_start=tp.T, audio_capture_end=tp.T + 8.0
    )
    conversation = dict(id='c', transcript_segments=[segment])
    events = []

    class Persistence:
        async def call(self, fn, *a, **k):
            if fn is transcripts.conversations_db.materialize_translation:
                return dict(segment, translations=[dict(lang='es', text='hola')])
            if fn is transcripts.conversations_db.update_conversation_segments:
                return deepcopy(a[2])
            return deepcopy(conversation)

    host = SimpleNamespace(
        limits=SimpleNamespace(max_segment_buffer_size=100, max_photo_buffer_size=100),
        state=SimpleNamespace(active=True, current_conversation_id='c'),
        request=SimpleNamespace(uid='synthetic'),
        persistence=Persistence(),
        translation_language='es',
        send_event=lambda event: events.append(event.to_json()),
    )
    processor = transcripts.TranscriptProcessor(host)
    processor.translation_coordinator = None

    async def get(*a, **k):
        return deepcopy(conversation)

    processor.cache = SimpleNamespace(get=get, protection_level='standard', update_segments=lambda s: None)
    monkeypatch.setattr(
        transcripts, 'resolve_ondemand_config', lambda: SimpleNamespace(gate_enabled=gated, admits=lambda uid: True)
    )
    assert asyncio.run(processor._on_translation_ready('s', 'hola', 'en', 'c'))
    assert len(events) == 1
    assert events[0]['type'] == 'translating'
    sent = events[0]['segments'][0]
    assert 'audio_capture_start' not in sent and 'audio_capture_end' not in sent
    assert sent['id'] == 's'


def _mock_word_search(monkeypatch):
    calls = []

    def stt(wav, rate, diarize, **kwargs):
        calls.append(wav)
        return tp._prefix_words(first=5.0 if len(calls) % 2 == 1 else 0.0)

    monkeypatch.setattr(speaker_sample, 'deepgram_prerecorded_from_bytes', stt)
    return calls


def test_owner_text_recovery_runs_before_the_capture_retry(monkeypatch, memory_bucket):
    monkeypatch.setenv('SPEAKER_TEACHING_TEXT_PLACEMENT', '1')
    segment = tp._owner_seg('a', 0.0, 8.0, text=tp.EXPECTED)
    conv = tp._owner_conversation([segment])
    conv.update(started_at=tp.T, audio_files=[dict(chunk_timestamps=[tp.T], duration=20.0)])
    memory_bucket.add(tp.T, 20.0, uid=tp.UID, conversation_id=tp.CONV)
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda *a: deepcopy(conv))

    async def mismatch(*a, **k):
        return None, False, 'text_mismatch: containment=0.20'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', mismatch)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a: np.array([[1.0, 0.0]], dtype=np.float32))
    published = []
    monkeypatch.setattr(
        service.voice_profiles_db, 'add_owner_voice_confirmation', lambda *a, **k: published.append(k) or 1
    )
    searches = _mock_word_search(monkeypatch)
    assert asyncio.run(service.store_owner_voice_sample(tp.UID, tp.CONV, ['a'])) == 'stored'
    assert len(searches) == 2 and len(published) == 1
    segment.update(audio_capture_start=tp.T + 100.0, audio_capture_end=tp.T + 108.0)
    assert asyncio.run(service.store_owner_voice_sample(tp.UID, tp.CONV, ['a'])) == 'stored'
    assert len(searches) == 4 and len(published) == 2


def test_person_text_recovery_runs_before_the_capture_retry(world, memory_bucket, monkeypatch):
    monkeypatch.setenv('SPEAKER_TEACHING_TEXT_PLACEMENT', '1')
    memory_bucket.add(pool.STARTED_AT, 20.0, uid=pool.UID, conversation_id=pool.CONV)
    monkeypatch.setattr(storage, 'list_audio_chunks', world.real_listing)
    monkeypatch.setattr(storage, 'download_audio_chunks_and_merge', world.real_merge)
    segment = pool.seg('a', 0.0, 10.0, scope='live:a', text=tp.EXPECTED)
    conv = pool.conversation(
        [segment], id=pool.CONV, audio_files=[dict(chunk_timestamps=[pool.STARTED_AT], duration=20.0)]
    )
    pool.set_conversation(world, conv)

    async def mismatch(*a, **k):
        return None, False, 'text_mismatch: containment=0.20'

    monkeypatch.setattr(teaching, 'verify_and_transcribe_sample', mismatch)
    searches = _mock_word_search(monkeypatch)
    assert pool.teach(('a',)) == 'stored'
    assert len(searches) == 2 and len(world.uploads) == 1
    segment.update(audio_capture_start=pool.STARTED_AT + 100.0, audio_capture_end=pool.STARTED_AT + 110.0)
    pool.set_conversation(world, conv)
    assert pool.teach(('a',)) == 'stored'
    assert len(searches) == 4 and len(world.uploads) == 2


def test_person_retry_resets_all_attempt_state_and_publishes_once(world, monkeypatch):
    origin = pool.STARTED_AT
    a = pool.seg('a', 0.0, 10.0, scope='live:a', text='alpha bravo charlie delta echo foxtrot golf')
    b = pool.seg('b', 20.0, 30.0, scope='live:a', text='hotel india juliet kilo lima mike november')
    for segment in (a, b):
        segment.update(
            audio_capture_start=origin + 100.0 + segment['start'], audio_capture_end=origin + 100.0 + segment['end']
        )
    pool.set_conversation(world, pool.conversation([a, b]))
    from utils.speaker_learning_policy import PooledClipPlan

    monkeypatch.setattr(
        teaching,
        'plan_pooled_intervals',
        lambda *a_, **k: PooledClipPlan([(0.0, 10.0), (20.0, 30.0)], [[a], [b]], 20.0, False),
    )
    reads = []

    def reader(uid, cid, start, end, rate, **kwargs):
        reads.append(start - origin)
        if start - origin == 20.0:
            return pool.pcm_for(3.0)
        if start - origin == 100.0:
            return None
        return pool.pcm_for(10.0)

    monkeypatch.setattr(teaching, 'legacy_speaker_clip_pcm', reader)
    verified = []

    async def verify(wav, rate, text, **kwargs):
        verified.append((len(wav) - 44, text))
        if len(verified) == 1:
            return None, False, 'text_mismatch: containment=0.20'
        return text, True, ''

    monkeypatch.setattr(teaching, 'verify_and_transcribe_sample', verify)
    assert pool.teach(('a', 'b')) == 'stored'
    assert reads == [0.0, 20.0, 100.0, 120.0], 'covered_end resets and retry occurs once'
    assert len(verified) == 2 and verified[1] == (pool.RATE * 10 * 2, b['text'])
    assert len(world.uploads) == 1
    saved = world.store.rows[pool.PERSON_PATH]
    assert saved['voice_speech_seconds'] == 10.0
    assert saved['speech_sample_source']['segment_ids'] == ['b']


@pytest.mark.parametrize('capture_valid', [False, True])
def test_owner_retries_once_and_only_publishes_verified_retry(monkeypatch, capture_valid):
    monkeypatch.delenv('SPEAKER_TEACHING_TEXT_PLACEMENT', raising=False)
    segment = tp._owner_seg('a', 0.0, 8.0, text=tp.EXPECTED)
    segment.update(audio_capture_start=tp.T + 100.0, audio_capture_end=tp.T + 108.0)
    conv = tp._owner_conversation([segment])
    conv['started_at'] = tp.T
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda *a: deepcopy(conv))
    reads = []

    def reader(*a, prefer_capture=False, **k):
        reads.append(prefer_capture)
        return (b'\x02\x00' if prefer_capture else b'\x01\x00') * int(8 * service.CLIP_SAMPLE_RATE)

    monkeypatch.setattr(service, 'conversation_clip_pcm', reader)
    verified = []

    async def verify(wav, *a, **k):
        verified.append(wav)
        return (
            (tp.EXPECTED, capture_valid, '')
            if len(verified) == 2 and capture_valid
            else (None, False, 'insufficient_words: 3/5')
        )

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    embedded = []
    published = []
    monkeypatch.setattr(
        service,
        'extract_embedding_from_bytes',
        lambda wav, *a: embedded.append(wav) or np.array([[1.0, 0.0]], dtype=np.float32),
    )
    monkeypatch.setattr(
        service.voice_profiles_db, 'add_owner_voice_confirmation', lambda *a, **k: published.append(k) or 1
    )
    assert asyncio.run(service.store_owner_voice_sample(tp.UID, tp.CONV, ['a'])) == (
        'stored' if capture_valid else 'rejected_quality'
    )
    assert reads == [False, True] and len(verified) == 2
    assert len(published) == int(capture_valid)
    if capture_valid:
        assert embedded == [verified[1]]

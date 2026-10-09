"""Bounded teaching text-anchored recovery: seams faked, policy real.

Storage reads (``legacy_speaker_clip_pcm``), the STT provider seam
(``speaker_sample.deepgram_prerecorded_from_bytes``) and the final verifier
are fakes; window math, word-granularity validation, anchoring, outcome
labels, fallback accounting and the person/owner wiring are production code.
"""

import asyncio
import io
import time
import wave as wave_mod
from copy import deepcopy
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

import utils.speaker_sample as speaker_sample
from tests.unit import test_speaker_learning_pool as pool
from utils import speaker_identification as teaching
from utils.conversations import teaching_placement
from utils.other.audio_chunks import AudioChunkReadSession
from utils.speaker_learning_policy import PooledClipPlan
from utils.speaker_tag_prompts import service
from utils.stt import pre_recorded

UID = 'account-a'
CONV = 'conv-1'
T = 1_700_000_000.0
RATE = 16000
EXPECTED = 'alpha bravo charlie delta echo foxtrot golf'

AUDIO = bytes(((i * 7 + 3) & 0xFF) for i in range(40 * RATE * 2))


def _audio_slice(start, end):
    return AUDIO[round(start * RATE) * 2 : round(end * RATE) * 2]


def _conversation(segments=None, **extra):
    conv = {
        'id': CONV,
        'started_at': T,
        'language': 'en',
        'transcript_segments': segments if segments is not None else [],
        'audio_files': [{'chunk_timestamps': [T]}],
    }
    conv.update(extra)
    return conv


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv('SPEAKER_TEACHING_TEXT_PLACEMENT', '1')
    return monkeypatch


def _fake_reader(buffer_origin=T):
    calls = []

    def read(uid, conversation_id, start, end, sample_rate, *, session=None, timestamps=None, caller='unknown'):
        calls.append({'window': (start, end), 'session': session, 'caller': caller})
        first = round((start - buffer_origin) * sample_rate) * 2
        last = round((end - buffer_origin) * sample_rate) * 2
        if first < 0 or last > len(AUDIO):
            return None
        return AUDIO[first:last]

    return read, calls


def _word(text, start, end=0.45):
    return {'timestamp': [start, start + end], 'text': text, 'speaker': 'SPEAKER_00'}


def _prefix_words(first=5.0, texts=None):
    return [_word(text, first + i * 0.5) for i, text in enumerate(texts or EXPECTED.split())]


def test_disabled_flag_does_no_io(monkeypatch):
    monkeypatch.delenv('SPEAKER_TEACHING_TEXT_PLACEMENT', raising=False)

    def banned(*args, **kwargs):
        raise AssertionError('disabled placement must not touch storage or STT')

    monkeypatch.setattr(teaching_placement, 'legacy_speaker_clip_pcm', banned)
    monkeypatch.setattr(teaching_placement, 'AudioChunkReadSession', banned)
    monkeypatch.setattr(speaker_sample, 'deepgram_prerecorded_from_bytes', banned)
    fallbacks = []
    monkeypatch.setattr(teaching_placement, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    conv = _conversation([pool.seg('a', 0.0, 10.0, scope='sync:1', text=EXPECTED)])
    result = asyncio.run(teaching_placement.recover_teaching_clip(UID, conv, 0.0, 10.0, EXPECTED, 'en'))
    assert result is None
    assert fallbacks == []


def _wav_pcm(audio_bytes, rate):
    with wave_mod.open(io.BytesIO(audio_bytes), 'rb') as wav_in:
        assert wav_in.getnchannels() == 1
        assert wav_in.getsampwidth() == 2
        assert wav_in.getframerate() == rate
        return wav_in.readframes(wav_in.getnframes())


def test_recovers_exact_words_window_with_one_search_and_one_verify(enabled):
    read, calls = _fake_reader()
    enabled.setattr(teaching_placement, 'legacy_speaker_clip_pcm', read)
    stt_calls = []
    deadlines = []
    words = _prefix_words(first=5.0)

    def fake_stt(audio_bytes, rate, diarize, *, language=None, **kwargs):
        deadlines.append(pre_recorded._verification_deadline.get())
        stt_calls.append(_wav_pcm(audio_bytes, rate))
        return list(words)

    enabled.setattr(speaker_sample, 'deepgram_prerecorded_from_bytes', fake_stt)
    seconds_before = teaching_placement.OMI_SPEAKER_PLACEMENT_SEARCH_AUDIO_SECONDS._value.get()

    conv = _conversation([pool.seg('a', 0.0, 10.0, scope='sync:1', text=EXPECTED)])
    session = AudioChunkReadSession(UID, CONV, RATE)
    result = asyncio.run(
        teaching_placement.recover_teaching_clip(UID, conv, 0.0, 10.0, EXPECTED, 'en', session=session)
    )
    assert result is not None
    pcm, transcript = result
    assert pcm == _audio_slice(5.0, 15.0)
    assert transcript == EXPECTED
    assert len(stt_calls) == 2, 'one search transcription plus one verification transcription'
    assert stt_calls[0] == AUDIO[: 20 * RATE * 2], 'the bounded search window arrives as 16 kHz mono WAV'
    assert stt_calls[1] == _audio_slice(5.0, 15.0), 'final verification sees exactly the anchored cut'
    assert deadlines[0] is not None and deadlines[0] == deadlines[1]
    assert deadlines[0] > time.monotonic(), 'provider sees the shared remaining budget'
    audio_seconds = teaching_placement.OMI_SPEAKER_PLACEMENT_SEARCH_AUDIO_SECONDS._value.get() - seconds_before
    assert audio_seconds == pytest.approx(30.0)
    assert audio_seconds <= 44.0
    assert all(call['session'] is session for call in calls), 'one shared read session for every piece'
    assert calls[0]['caller'] == 'teaching'
    total_audio_seconds = sum(call['window'][1] - call['window'][0] for call in calls)
    assert total_audio_seconds == pytest.approx(20.0), 'padded 10 s window searches at most 20 s here'


def test_modulate_retry_suppressed_under_shared_deadline(monkeypatch):
    monkeypatch.setenv('MODULATE_API_KEY', 'fake-key')
    calls = []

    def boom(self, *args, **kwargs):
        calls.append(1)
        raise RuntimeError('transport down')

    monkeypatch.setattr(httpx.Client, 'post', boom)
    deadline = time.monotonic() + 30.0
    with pytest.raises(RuntimeError):
        with pre_recorded.verification_stt_deadline(deadline):
            pre_recorded.modulate_prerecorded_from_bytes(b'\x00' * 64)
    assert len(calls) == 1, 'one provider invocation; the deadline suppresses internal retries'


def test_sequential_pieces_under_piece_cap(enabled):
    read, calls = _fake_reader()
    enabled.setattr(teaching_placement, 'legacy_speaker_clip_pcm', read)
    words = _prefix_words(first=5.0)
    enabled.setattr(speaker_sample, 'deepgram_prerecorded_from_bytes', lambda *a, **k: list(words))

    async def verify(*args, **kwargs):
        return ('t', True, 'ok')

    enabled.setattr(speaker_sample, 'verify_and_transcribe_sample', verify)
    conv = _conversation([pool.seg('a', 0.0, 12.0, scope='sync:1', text=EXPECTED)])
    asyncio.run(teaching_placement.recover_teaching_clip(UID, conv, 0.0, 12.0, EXPECTED, 'en'))
    assert calls
    for call in calls:
        assert call['window'][1] - call['window'][0] <= 12.0


def test_ambiguous_or_unsupported_words_skip_final_verification(enabled):
    for outcome_words, expected in (
        (_prefix_words(first=1.0) + _prefix_words(first=8.0), 'ambiguous_text_anchor'),
        ([{'text': 'whole segment text here', 'timestamp': [5.0, 7.0]}] * 7, 'unsupported_word_times'),
    ):
        read, _calls = _fake_reader()
        enabled.setattr(teaching_placement, 'legacy_speaker_clip_pcm', read)
        enabled.setattr(speaker_sample, 'deepgram_prerecorded_from_bytes', lambda *a, **k: list(outcome_words))
        verify_calls = []

        async def verify(*args, **kwargs):
            verify_calls.append(args)
            return ('t', True, 'ok')

        enabled.setattr(speaker_sample, 'verify_and_transcribe_sample', verify)
        conv = _conversation([pool.seg('a', 0.0, 10.0, scope='sync:1', text=EXPECTED)])
        result = asyncio.run(teaching_placement.recover_teaching_clip(UID, conv, 0.0, 10.0, EXPECTED, 'en'))
        assert result is None
        assert verify_calls == [], f'{expected} must not spend the final STT call'


def test_unreadable_or_short_piece_aborts_without_stt(enabled):
    stt_calls = []
    enabled.setattr(speaker_sample, 'deepgram_prerecorded_from_bytes', lambda *a, **k: stt_calls.append(1) or [])

    def missing(*args, **kwargs):
        return None

    enabled.setattr(teaching_placement, 'legacy_speaker_clip_pcm', missing)
    conv = _conversation([pool.seg('a', 0.0, 10.0, scope='sync:1', text=EXPECTED)])
    assert asyncio.run(teaching_placement.recover_teaching_clip(UID, conv, 0.0, 10.0, EXPECTED, 'en')) is None
    assert stt_calls == []

    def short(uid, conversation_id, start, end, sample_rate, **kwargs):
        return b'\x00' * 10

    enabled.setattr(teaching_placement, 'legacy_speaker_clip_pcm', short)
    assert asyncio.run(teaching_placement.recover_teaching_clip(UID, conv, 0.0, 10.0, EXPECTED, 'en')) is None
    assert stt_calls == []


def test_anchor_outside_audio_does_not_fabricate(enabled):
    read, _calls = _fake_reader()
    enabled.setattr(teaching_placement, 'legacy_speaker_clip_pcm', read)
    enabled.setattr(speaker_sample, 'deepgram_prerecorded_from_bytes', lambda *a, **k: _prefix_words(first=25.0))
    conv = _conversation([pool.seg('a', 0.0, 10.0, scope='sync:1', text=EXPECTED)])
    assert asyncio.run(teaching_placement.recover_teaching_clip(UID, conv, 0.0, 10.0, EXPECTED, 'en')) is None


def test_unplaced_overlap_is_not_eligible(enabled):
    segments = [
        pool.seg('a', 0.0, 10.0, scope='sync:1', text=EXPECTED),
        {**pool.seg('u', 2.0, 4.0), 'audio_alignment': 'unplaced'},
    ]
    conv = _conversation(segments)
    read, calls = _fake_reader()
    enabled.setattr(teaching_placement, 'legacy_speaker_clip_pcm', read)
    assert asyncio.run(teaching_placement.recover_teaching_clip(UID, conv, 0.0, 10.0, EXPECTED, 'en')) is None
    assert calls == []


@pytest.fixture
def world(monkeypatch):
    return pool.world.__wrapped__(monkeypatch)


def test_person_text_mismatch_invokes_recovery_once(world, monkeypatch):
    monkeypatch.setenv('SPEAKER_TEACHING_TEXT_PLACEMENT', '1')
    pool.set_conversation(world, pool.conversation([pool.seg('a', 0.0, 12.0)]))
    world.transcripts['text'] = 'entirely different unrelated audio content right here'
    recovered_pcm = pool.pcm_for(10)
    calls = []

    async def fake_recover(uid, conversation, start, end, expected_text, language, sample_rate=16000, **kwargs):
        calls.append(
            {
                'window': (start, end),
                'expected_text': expected_text,
                'anchor_offset': kwargs.get('anchor_offset'),
                'session': kwargs.get('session'),
            }
        )
        return recovered_pcm, 'alpha bravo charlie delta echo foxtrot golf'

    monkeypatch.setattr(teaching, 'recover_teaching_clip', fake_recover)
    outcome = pool.teach(('a',))
    assert outcome == 'stored'
    assert len(calls) == 1
    assert calls[0]['window'] == (1.0, 11.0), 'the cropped 10 s interval actually cut'
    assert calls[0]['expected_text'] == 'words from a that keep going'
    assert calls[0]['anchor_offset'] == pytest.approx(1.0)
    assert isinstance(calls[0]['session'], AudioChunkReadSession)
    saved = world.store.rows[pool.PERSON_PATH]
    assert saved['speech_sample_transcripts'] == ['alpha bravo charlie delta echo foxtrot golf']


def test_person_non_mismatch_failures_never_recover(world, monkeypatch):
    monkeypatch.setenv('SPEAKER_TEACHING_TEXT_PLACEMENT', '1')
    pool.set_conversation(world, pool.conversation([pool.seg('a', 0.0, 12.0)]))
    calls = []

    async def fake_recover(*args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr(teaching, 'recover_teaching_clip', fake_recover)

    world.transcripts['words'] = [{'text': 'hi', 'speaker': 'SPEAKER_00'}]
    assert pool.teach(('a',)) == 'insufficient_words'
    world.transcripts['words'] = [
        {'text': 'hello world this', 'speaker': 'SPEAKER_00'},
        {'text': 'is mixed audio', 'speaker': 'SPEAKER_01'},
    ]
    assert pool.teach(('a',)) == 'multi_speaker'
    assert calls == []


def test_person_mismatch_without_flag_does_no_search_io(world, monkeypatch):
    monkeypatch.delenv('SPEAKER_TEACHING_TEXT_PLACEMENT', raising=False)
    pool.set_conversation(world, pool.conversation([pool.seg('a', 0.0, 12.0)]))
    world.transcripts['text'] = 'entirely different unrelated audio content right here'

    def banned(*args, **kwargs):
        raise AssertionError('flag-off recovery must not read more audio')

    monkeypatch.setattr(teaching_placement, 'legacy_speaker_clip_pcm', banned)
    assert pool.teach(('a',)) == 'text_mismatch'


def test_multi_interval_pool_never_recovers(world, monkeypatch):
    monkeypatch.setenv('SPEAKER_TEACHING_TEXT_PLACEMENT', '1')
    pool.set_conversation(world, pool.conversation([pool.seg('a', 0.0, 6.0), pool.seg('b', 10.0, 16.0)]))
    world.transcripts['text'] = 'entirely different unrelated audio content right here'
    calls = []

    async def fake_recover(*args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr(teaching, 'recover_teaching_clip', fake_recover)
    assert pool.teach(('a', 'b')) == 'text_mismatch'
    assert calls == [], 'pooled multi-interval clips cannot bind pooled word times safely'


def test_person_v2_iso_started_at_matches_numeric(world, monkeypatch):
    spans = [{'start': pool.STARTED_AT, 'end': pool.STARTED_AT + 60}]
    files = [{'chunk_timestamps': [pool.STARTED_AT], 'chunk_spans': spans}]
    conv = pool.conversation(
        [pool.seg('a', 0.0, 12.0)],
        started_at='2023-11-14T22:13:20Z',
        audio_files=files,
        audio_timeline={'version': 2},
    )
    pool.set_conversation(world, conv)
    assert pool.teach(('a',)) == 'stored'
    iso_pcm = world.captured['pcm']
    pool.set_conversation(world, {**conv, 'started_at': pool.STARTED_AT})
    assert pool.teach(('a',)) == 'stored'
    assert world.captured['pcm'] == iso_pcm == pool.pcm_for(10)


def test_partial_extra_interval_never_recovers(world, monkeypatch):
    monkeypatch.setenv('SPEAKER_TEACHING_TEXT_PLACEMENT', '1')
    seg_a = pool.seg('a', 0.0, 10.0)
    seg_b = pool.seg('b', 20.0, 28.0)
    pool.set_conversation(world, pool.conversation([seg_a, seg_b]))
    plan = PooledClipPlan(
        intervals=[(0.0, 10.0), (20.0, 28.0)],
        contributors=[[seg_a], [seg_b]],
        total_seconds=18.0,
        contaminated=False,
    )
    monkeypatch.setattr(teaching, 'plan_pooled_intervals', lambda *a, **k: plan)

    def partial_clip(uid, conversation_id, start, end, sample_rate, **kwargs):
        return pool.pcm_for(end - start) if start - pool.STARTED_AT < 15.0 else pool.pcm_for(2.0)

    monkeypatch.setattr(teaching, 'legacy_speaker_clip_pcm', partial_clip)
    world.transcripts['text'] = 'entirely different unrelated audio content right here'
    calls = []

    async def fake_recover(*args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr(teaching, 'recover_teaching_clip', fake_recover)
    assert pool.teach(('a', 'b')) == 'text_mismatch'
    assert calls == [], 'a partially decoded second interval must not keep stale source ids'


def _owner_conversation(segments):
    conv = {
        'id': CONV,
        'language': 'en',
        'transcript_segments': segments,
        'manual_speaker_assignments': {
            'generation': 1,
            'segments': {s['id']: {'generation': 1, 'is_user': True} for s in segments},
        },
    }
    return conv


def _owner_seg(seg_id, start, end, text='owner words here and more'):
    return {
        'id': seg_id,
        'start': start,
        'end': end,
        'speaker_id': 0,
        'is_user': True,
        'text': text,
    }


def test_owner_text_mismatch_invokes_recovery_once(monkeypatch):
    monkeypatch.setenv('SPEAKER_TEACHING_TEXT_PLACEMENT', '1')
    segments = [_owner_seg('a', 0.0, 6.0), _owner_seg('b', 6.0, 12.0)]
    conv = _owner_conversation(segments)
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: deepcopy(conv))
    monkeypatch.setattr(
        service, 'conversation_clip_pcm', lambda *a, **k: b'\x01\x00' * int(service.CLIP_SAMPLE_RATE * 10)
    )

    async def verify(wav, rate, text, language=None):
        return None, False, 'text_mismatch: containment=0.20'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    calls = []
    recovered_pcm = b'\x02\x00' * int(service.CLIP_SAMPLE_RATE * 10)

    async def fake_recover(uid, conversation, start, end, expected_text, language, sample_rate=16000, **kwargs):
        calls.append({'window': (start, end), 'anchor_offset': kwargs.get('anchor_offset')})
        return recovered_pcm, 'recovered owner transcript'

    monkeypatch.setattr(service, 'recover_teaching_clip', fake_recover)
    captured = {}

    def fake_embed(wav, name):
        captured['wav'] = wav
        return np.array([[1.0, 0.0]], dtype=np.float32)

    def fake_confirm(uid, embedding, pool_fn, **kwargs):
        captured['segments'] = kwargs['segment_ids']
        return 1

    monkeypatch.setattr(service, 'extract_embedding_from_bytes', fake_embed)
    monkeypatch.setattr(service.voice_profiles_db, 'add_owner_voice_confirmation', fake_confirm)
    assert asyncio.run(service.store_owner_voice_sample(UID, CONV, ['a', 'b'])) == 'stored'
    assert len(calls) == 1
    assert calls[0]['window'] == (1.0, 11.0), 'the center-cropped run window actually cut'
    assert calls[0]['anchor_offset'] == pytest.approx(1.0)
    with wave_mod.open(io.BytesIO(captured['wav']), 'rb') as wav_in:
        assert wav_in.readframes(wav_in.getnframes()) == recovered_pcm
    assert set(captured['segments']) == {'a', 'b'}, 'authority fence and source ids unchanged'


def test_owner_non_mismatch_never_recovers(monkeypatch):
    monkeypatch.setenv('SPEAKER_TEACHING_TEXT_PLACEMENT', '1')
    segments = [_owner_seg('a', 0.0, 8.0)]
    conv = _owner_conversation(segments)
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: deepcopy(conv))
    monkeypatch.setattr(
        service, 'conversation_clip_pcm', lambda *a, **k: b'\x01\x00' * int(service.CLIP_SAMPLE_RATE * 8)
    )

    async def verify(wav, rate, text, language=None):
        return None, False, 'insufficient_words: 3/5'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    calls = []

    async def fake_recover(*args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr(service, 'recover_teaching_clip', fake_recover)
    assert asyncio.run(service.store_owner_voice_sample(UID, CONV, ['a'])) == 'rejected_quality'
    assert calls == []

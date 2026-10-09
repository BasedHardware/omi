"""Live model cost refills with wall time, independent of conversation churn."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from tests.unit.test_speaker_match import _live_matcher, _segment
from routers.listen import speakers
from models.transcript_segment import TranscriptSegment
from tests.unit.test_owner_speaker_profiles import _Persistence
from utils.speaker_assignment import process_speaker_assigned_segments


def _clock(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(speakers, 'time', SimpleNamespace(monotonic=lambda: clock.now))
    return clock


def test_ambiguous_voice_has_twelve_embedding_attempts_per_conversation(monkeypatch):
    _clock(monkeypatch)
    matcher, _, _ = _live_matcher(monkeypatch, [])
    calls = []
    monkeypatch.setattr(
        speakers, 'extract_embedding_from_bytes', lambda *a: calls.append(1) or np.array([[1.0, 1.0]], dtype=np.float32)
    )

    async def speech():
        for i in range(120):
            await matcher.match(1, _segment(f's{i}', i * 0.5, 0.5))

    asyncio.run(speech())
    assert len(calls) == 12
    assert not matcher.speaker_to_person


def test_socket_refill_waits_for_one_token_and_caps_idle_credit(monkeypatch):
    clock = _clock(monkeypatch)
    matcher, _, _ = _live_matcher(monkeypatch, [])
    for voice in range(16):
        matcher._admit_voice(voice)
        assert matcher._reserve_embedding(voice)
    matcher._admit_voice(16)
    clock.now = 14.0
    assert not matcher._reserve_embedding(16)
    clock.now = 15.0
    assert matcher._reserve_embedding(16)
    assert matcher._socket_embedding_tokens == pytest.approx(0)
    clock.now = 3600.0
    assert matcher._reserve_embedding(16)
    assert matcher._socket_embedding_tokens == 15
    # Even a backwards clock cannot manufacture elapsed time twice.
    clock.now = 3500.0
    assert matcher._reserve_embedding(16)
    clock.now = 3600.0
    assert matcher._reserve_embedding(16)
    assert matcher._socket_embedding_tokens == 13


@pytest.mark.anyio
async def test_rollover_resets_reused_voice_but_same_conversation_refresh_does_not(monkeypatch):
    _clock(monkeypatch)
    matcher, host, _ = _live_matcher(monkeypatch, [])
    profiles = dict(matcher.person_embeddings)
    host.state.speaker_id_enabled = True

    async def load():
        matcher.person_embeddings.update(profiles)

    matcher._load_profiles = AsyncMock(side_effect=load)
    await matcher.refresh_for_conversation('first')
    matcher._admit_voice(1)
    for _ in range(12):
        assert matcher._reserve_embedding(1)
    await matcher.refresh_for_conversation('first')
    assert not matcher._reserve_embedding(1)
    await matcher.refresh_for_conversation('second')
    matcher._admit_voice(1)
    assert matcher._reserve_embedding(1)
    assert matcher._embedding_attempts[1] == 1
    assert matcher._socket_embedding_tokens == 3


@pytest.mark.anyio
async def test_manual_carried_voice_keeps_attempts(monkeypatch):
    _clock(monkeypatch)
    matcher, host, _ = _live_matcher(monkeypatch, [])
    host.state.speaker_id_enabled = False
    matcher._profile_conversation_id = 'first'
    matcher._embedding_attempts = {1: 12, 2: 12}
    matcher._mapping_origin[1] = 'manual'
    matcher.speaker_to_person[1] = ('user', 'User')
    matcher.note_rollover_carry({1})
    await matcher.refresh_for_conversation('second')
    assert matcher._embedding_attempts == {1: 12}
    matcher._admit_voice(1)
    assert not matcher._reserve_embedding(1)


@pytest.mark.anyio
async def test_churn_cannot_exceed_first_hour_or_steady_state_cost_bound(monkeypatch):
    clock = _clock(monkeypatch)
    matcher, host, _ = _live_matcher(monkeypatch, [])
    host.state.speaker_id_enabled = True
    owner = matcher.person_embeddings['user']
    calls = []

    async def load():
        matcher.person_embeddings['user'] = owner

    matcher._load_profiles = AsyncMock(side_effect=load)
    monkeypatch.setattr(
        speakers, 'extract_embedding_from_bytes', lambda *a: calls.append(1) or np.array([[0.0, 1.0]], dtype=np.float32)
    )

    # Every attempt churns conversation and speaker IDs. Forged audio clocks
    # also cannot refill the socket's monotonic wall-time budget.
    async def churn(n):
        for i in range(n):
            await matcher.refresh_for_conversation(f'c{len(calls)}-{i}-{clock.now}')
            await matcher.match(i % 8, dict(_segment(f's{i}', 0, 5), abs_end=10**9))
            await matcher.refresh_for_conversation(matcher._profile_conversation_id)

    await churn(24)
    assert len(calls) == 16
    for step in range(1, 241):
        clock.now = step * 15.0
        await churn(2)
    assert len(calls) == 256
    for step in range(241, 481):
        clock.now = step * 15.0
        await churn(2)
    assert len(calls) == 496  # 16 + 2 * 240


@pytest.mark.anyio
async def test_exhausted_socket_can_match_owner_in_later_conversation(monkeypatch):
    clock = _clock(monkeypatch)
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, _ = _live_matcher(monkeypatch, [owner])
    host.state.speaker_id_enabled = True
    host.request.uid = 'u'
    host.persistence = SimpleNamespace(call=AsyncMock(return_value={}))
    profiles = dict(matcher.person_embeddings)
    matcher._load_profiles = AsyncMock(side_effect=lambda: matcher.person_embeddings.update(profiles))
    for voice in range(16):
        matcher._admit_voice(voice)
        assert matcher._reserve_embedding(voice)
    await matcher.refresh_for_conversation('later')
    await matcher.match(1, _segment('owner', 0, 5))
    assert not matcher.speaker_to_person
    clock.now = 15.0
    await matcher.match(1, _segment('owner', 0, 5))
    assert matcher.speaker_to_person[1][0] == 'user'


@pytest.mark.anyio
@pytest.mark.parametrize('kind', ['accepted', 'confident_reject', 'near_reject', 'margin_reject', 'contended'])
async def test_decided_voice_stops_but_uncertain_voice_keeps_spending(monkeypatch, kind):
    _clock(monkeypatch)
    vectors = {
        'accepted': [1.0, 0.0],
        'confident_reject': [-1.0, 0.0],
        'near_reject': [0.30, np.sqrt(1 - 0.30**2)],  # distance 0.70: less than margin beyond threshold
        'margin_reject': [1.0, 1.0],
        'contended': [1.0, 0.0],
    }
    query = np.array([vectors[kind]], dtype=np.float32)
    matcher, _, _ = _live_matcher(monkeypatch, [query] * 3)
    if kind == 'near_reject':
        matcher.person_embeddings.pop('p1')
    if kind == 'contended':
        await matcher.match(2, _segment('competitor', 0, 5))
    await matcher.match(1, _segment('first', 6, 5))
    attempts, tokens = matcher._embedding_attempts[1], matcher._socket_embedding_tokens
    exits = []
    monkeypatch.setattr(matcher, '_record_exit', lambda reason, voice: exits.append(reason))
    await matcher.match(1, _segment('next', 12, 5))
    stopped = kind in ('accepted', 'confident_reject')
    assert matcher._embedding_attempts[1] == attempts + (not stopped)
    assert matcher._socket_embedding_tokens == tokens - (not stopped)
    if stopped:
        assert exits == ['already_mapped' if kind == 'accepted' else 'decided_voice']


@pytest.mark.anyio
async def test_failed_embeddings_and_concurrent_voices_share_the_bucket(monkeypatch):
    _clock(monkeypatch)
    matcher, _, _ = _live_matcher(monkeypatch, [])
    calls = []

    def fail(*args):
        calls.append(1)
        raise RuntimeError('offline injected failure')

    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', fail)
    await asyncio.gather(*(matcher.match(voice, _segment(f's{voice}', 0, 5)) for voice in range(32)))
    assert len(calls) == 16
    assert sum(matcher._embedding_attempts.values()) == 16
    assert matcher._socket_embedding_tokens == 0


@pytest.mark.parametrize('other_print', [False, True])
def test_taught_owner_reuses_evidence_after_voice_stop(monkeypatch, other_print):
    _clock(monkeypatch)
    matcher, host, _ = _live_matcher(monkeypatch, [])
    matcher.person_embeddings.pop('user')
    if not other_print:
        matcher.person_embeddings.clear()
    host.request.uid = 'u'
    host.has_speech_profile = False
    host.persistence = _Persistence()
    calls = []
    monkeypatch.setattr(
        speakers, 'extract_embedding_from_bytes', lambda *a: calls.append(1) or np.array([[1.0, 0.0]], dtype=np.float32)
    )
    monkeypatch.setattr(speakers.user_db, 'get_user_speaker_embedding', lambda uid: [1.0, 0.0])
    monkeypatch.setattr(speakers, 'get_user_name', lambda *a: 'Owner')

    async def speech():
        for i in range(120):
            await matcher.match(1, _segment(f's{i}', i * 0.5, 0.5))
        assert len(calls) == (3 if other_print else 12)
        assert not matcher.speaker_to_person
        await matcher._load_profiles(owner_only=True)

    asyncio.run(speech())
    segments = [
        TranscriptSegment(id='render', speaker_id=1, speaker='SPEAKER_1', text='hello', start=0, end=1, is_user=False)
    ]
    process_speaker_assigned_segments(segments, {}, matcher.speaker_to_person)
    assert segments[0].model_dump()['is_user'] is True
    assert len(calls) == (3 if other_print else 12)

"""Live recovery and capacity regressions from the independent review."""

import asyncio
from collections import deque
from types import SimpleNamespace

import numpy as np
import pytest

from models.transcript_segment import SpeakerIdentityStatus
from routers.listen import speakers
from tests.unit.test_speaker_match import _live_matcher, _segment
from utils.audio import AudioRingBuffer
from utils.stt.speaker_match import select_speaker_match


def _assert_short_voice_recovers(monkeypatch, noisy):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, _, _ = _live_matcher(monkeypatch, [noisy] * 3 + [owner] * 117)
    matcher.person_embeddings.pop('p1')

    async def speech():
        for i in range(120):
            await matcher.match(1, _segment(f's{i}', i * 0.5, 0.5))

    asyncio.run(speech())
    assert matcher.speaker_to_person.get(1) == ('user', 'User')
    assert 3 < matcher._embedding_attempts[1] <= speakers.MAX_VOICE_EMBEDDING_ATTEMPTS


def test_rejected_short_voice_can_recover_after_deque_eviction(monkeypatch):
    _assert_short_voice_recovers(monkeypatch, np.array([[0.0, 1.0]], dtype=np.float32))


def test_near_threshold_short_voice_can_recover_after_deque_eviction(monkeypatch):
    _assert_short_voice_recovers(monkeypatch, np.array([[0.30, np.sqrt(1 - 0.30**2)]], dtype=np.float32))


@pytest.mark.anyio
async def test_recovered_owner_withdraws_competing_automatic_owner_mapping(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    noisy = np.array([[0.0, 1.0]], dtype=np.float32)
    peer = np.array([[0.47, np.sqrt(1 - 0.47**2)]], dtype=np.float32)
    matcher, host, emitted = _live_matcher(monkeypatch, [noisy, peer, owner, owner, owner])
    matcher.person_embeddings.pop('p1')
    host.emit_speaker_suggestion = lambda *args, **kwargs: emitted.append((args, kwargs))

    await matcher.match(1, _segment('owner-noisy', 0, 5))
    assert 1 not in matcher.speaker_to_person
    await matcher.match(2, _segment('peer', 6, 5))
    assert matcher.speaker_to_person[2][0] == 'user'
    assert matcher._mapping_origin[2] == 'automatic'
    for i in range(3):
        await matcher.match(1, _segment(f'owner-clean-{i}', 12 + i * 6, 5))

    assert matcher.speaker_to_person == {1: ('user', 'User')}
    assert 2 not in matcher._mapping_origin
    assert matcher.voice_identity_status[2] == SpeakerIdentityStatus.ambiguous
    assert matcher.segment_identity_status['peer'] == SpeakerIdentityStatus.ambiguous
    assert ((2, '', '', 'peer'), {'retracted': True}) in emitted
    assert matcher._embedding_attempts[1] <= speakers.MAX_VOICE_EMBEDDING_ATTEMPTS


@pytest.mark.anyio
async def test_failed_short_reconnect_probe_can_recover_with_full_owner_evidence(monkeypatch):
    # Replay the failed 1s reconnect state documented by #21051. It is not
    # a completed ordinary rejection and must permit fresh full-length audio.
    monkeypatch.setattr(speakers, 'time', SimpleNamespace(monotonic=lambda: 0.0))
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    noisy = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher, _, _ = _live_matcher(monkeypatch, [owner])
    matcher.person_embeddings.pop('p1')
    matcher._admit_voice(1)
    matcher._embedding_attempts[1] = 1
    matcher._socket_embedding_tokens -= 1
    matcher.speaker_evidence[1] = deque([(noisy, 1.0)], maxlen=3)
    matcher._voice_distances[1] = {'user': 1.0}
    matcher._voice_decisions[1] = select_speaker_match({'user': 1.0})
    matcher._voice_centroids[1] = noisy
    matcher._voice_segments[1] = 'short-reconnect'
    matcher._covered_audio[1] = [(0.0, 1.0)]

    await matcher.match(1, _segment('fresh-owner', 2, 5))

    assert matcher.speaker_to_person[1] == ('user', 'User')
    assert matcher._embedding_attempts[1] == 2
    assert matcher._socket_embedding_tokens == speakers.SOCKET_EMBEDDING_BURST - 2


@pytest.mark.anyio
@pytest.mark.parametrize('usable_seconds', [0.5, 5.0])
async def test_pool_skips_unavailable_interval_and_rechecks_actual_pcm(monkeypatch, usable_seconds):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, _ = _live_matcher(monkeypatch, [owner])
    ring = AudioRingBuffer(3.0 + usable_seconds, 16000)
    ring.write_positioned(b'\x00\x00' * (3 * 16000), 0.0)
    ring.write_positioned(b'\x01\x00' * round(usable_seconds * 16000), 10.0)
    time_range = ring.get_time_range()

    def snapshot_then_evict():
        # Advance the real ring after the range snapshot. The old fragment
        # loses all its PCM while the newer fragment remains fully usable.
        ring.write_positioned(b'\x02\x00' * (3 * 16000), 20.0)
        return time_range

    monkeypatch.setattr(ring, 'get_time_range', snapshot_then_evict)
    host.state.audio_ring_buffer = ring
    matcher._pending_audio[1] = [(0.0, 3.0)]
    exits = []
    monkeypatch.setattr(matcher, '_record_exit', lambda reason, voice: exits.append(reason))
    tokens = matcher._socket_embedding_tokens
    await matcher.match(1, _segment('fresh', 10.0, usable_seconds))
    if usable_seconds == 5.0:
        assert matcher.speaker_to_person[1][0] == 'user'
        assert matcher._covered_audio[1] == [(10.0, 15.0)]
        assert sum(seconds for _, seconds in matcher.speaker_evidence[1]) == 5.0
        assert exits == []
    else:
        assert exits == ['window_shorter_than_minimum']
        assert not matcher.speaker_evidence
        assert matcher._socket_embedding_tokens == tokens


@pytest.mark.anyio
async def test_no_pcm_is_one_exit_only_when_entire_pool_is_unusable(monkeypatch):
    matcher, host, _ = _live_matcher(monkeypatch, [])
    monkeypatch.setattr(host.state.audio_ring_buffer, 'extract', lambda *args: None)
    matcher._pending_audio[1] = [(0.0, 3.0), (5.0, 8.0)]
    exits = []
    monkeypatch.setattr(matcher, '_record_exit', lambda reason, voice: exits.append(reason))
    tokens = matcher._socket_embedding_tokens
    await matcher.match(1, _segment('missing', 10.0, 5.0))
    assert exits == ['no_pcm']
    assert not matcher.speaker_evidence
    assert matcher._socket_embedding_tokens == tokens

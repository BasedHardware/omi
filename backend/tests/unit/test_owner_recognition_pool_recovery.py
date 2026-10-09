"""Live recovery and capacity regressions from the independent review."""

import asyncio
import numpy as np
import pytest

from tests.unit.test_speaker_match import _live_matcher, _segment
from utils.audio import AudioRingBuffer


def test_near_threshold_short_voice_can_recover_after_deque_eviction(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    noisy = np.array([[0.30, np.sqrt(1 - 0.30**2)]], dtype=np.float32)
    matcher, _, _ = _live_matcher(monkeypatch, [noisy] * 3 + [owner] * 117)
    matcher.person_embeddings.pop('p1')

    async def speech():
        for i in range(120):
            await matcher.match(1, _segment(f's{i}', i * 0.5, 0.5))

    asyncio.run(speech())
    assert matcher.speaker_to_person.get(1) == ('user', 'User')


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

"""Live recovery and capacity regressions from the independent review."""

import asyncio
import numpy as np

from tests.unit.test_speaker_match import _live_matcher, _segment


def test_rejected_short_voice_can_recover_after_deque_eviction(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    noisy = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher, _, _ = _live_matcher(monkeypatch, [noisy] * 3 + [owner] * 117)
    matcher.person_embeddings.pop('p1')

    async def speech():
        for i in range(120):
            await matcher.match(1, _segment(f's{i}', i * 0.5, 0.5))

    asyncio.run(speech())
    assert matcher.speaker_to_person.get(1) == ('user', 'User')

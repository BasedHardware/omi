"""Live recovery and capacity regressions from the independent review."""

import asyncio
import numpy as np

from tests.unit.test_speaker_match import _live_matcher, _segment


def test_short_only_voice_state_and_rollover_locks_are_bounded(monkeypatch):
    matcher, _, _ = _live_matcher(monkeypatch, [])
    owner = dict(matcher.person_embeddings)

    async def speech():
        for rollover in range(3):
            matcher.person_embeddings.update(owner)
            for i in range(1000):
                await matcher.match(i, _segment(f'{rollover}:{i}', 0, 0.5))
            for state in (
                matcher._speaker_locks,
                matcher._covered_audio,
                matcher._pending_audio,
                matcher.speaker_evidence,
                matcher._voice_decisions,
            ):
                assert len(state) <= 128
            matcher.clear()
            assert not matcher._speaker_locks

    asyncio.run(speech())


def test_rollover_retires_locks_without_old_work_touching_new_voice(monkeypatch):
    from routers.listen import speakers

    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    noisy = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher, _, _ = _live_matcher(monkeypatch, [])
    matcher.person_embeddings.pop('p1')

    async def interleave():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = [0]

        async def embed(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                entered.set()
                await release.wait()
                return noisy
            return owner

        monkeypatch.setattr(speakers, 'run_blocking', embed)
        old = asyncio.create_task(matcher.match(1, _segment('old', 0, 5)))
        await entered.wait()
        matcher.clear()
        matcher.person_embeddings['user'] = {'embedding': owner, 'name': 'User'}
        await matcher.match(1, _segment('new', 6, 5))
        release.set()
        await old
        assert matcher.speaker_to_person[1] == ('user', 'User')
        assert matcher._voice_segments[1] == 'new'
        assert len(matcher._speaker_locks) == 1

    asyncio.run(interleave())

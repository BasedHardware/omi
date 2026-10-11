"""Queue fairness and coalescing execute the real capped live matcher."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from routers.listen import speakers
from routers.listen.speaker_queue import SpeakerMatchQueue, MAX_QUEUED_INTERVALS, SPEAKER_QUEUE_MAX_WAIT_SECONDS
from tests.unit.test_speaker_match import _live_matcher, _segment
from tests.unit.test_owner_recognition_embedding_budget import _clock
from utils.stt.speaker_match import select_speaker_match


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _work(voice=1, start=0, seconds=5, *, scope='provider', conversation='conversation', segment=None):
    return {
        **_segment(segment or f's-{voice}-{start}', start, seconds),
        'speaker_id': voice,
        'speaker_id_scope': scope,
        'conversation_id': conversation,
    }


def _queue():
    state = SimpleNamespace(now=0.0, generation=0, attempts={}, near=set())
    queue = SpeakerMatchQueue(
        generation=lambda: state.generation,
        attempts=lambda voice: state.attempts.get(voice, 0),
        near_owner=lambda voice: voice in state.near,
        clock=lambda: state.now,
    )
    return queue, state


def test_untried_voice_precedes_repeated_rejector_then_near_owner_and_longer_clips():
    queue, state = _queue()
    state.attempts = {1: 8, 3: 2, 4: 2}
    state.near = {3}
    for voice, seconds in [(1, 10), (4, 10), (3, 2), (2, 1)]:
        queue.put_nowait(_work(voice, seconds=seconds))
    selected = []
    while not queue.empty():
        work = queue.get_nowait()
        selected.append(work['speaker_id'])
        queue.complete(work)
    assert selected == [2, 3, 1, 4]


def test_age_beats_continuing_new_voices_and_coalescing_does_not_renew_age():
    queue, state = _queue()
    state.attempts[1] = 8
    queue.put_nowait(_work(1, seconds=2))
    state.now = SPEAKER_QUEUE_MAX_WAIT_SECONDS
    queue.put_nowait(_work(1, start=3, seconds=2))
    for voice in range(2, 100):
        queue.put_nowait(_work(voice, seconds=10))
    assert queue.get_nowait()['speaker_id'] == 1


def test_coalescing_preserves_distinct_audio_and_latest_identity_without_gaps_or_pii():
    queue, _ = _queue()
    for start, end, sid in [(0, 2, 'old'), (1, 3, 'updated'), (10, 12, 'latest')]:
        queue.put_nowait(
            {
                **_work(start=start, seconds=end - start, segment=sid),
                'text': 'must never enter queue',
                'pcm': b'private',
            }
        )
    assert queue.qsize() == 1
    work = queue.get_nowait()
    assert work['_speaker_audio_ranges'] == [(0, 3), (10, 12)]
    assert work['id'] == 'latest' and 'text' not in work and 'pcm' not in work


def test_coalescing_is_bounded_and_full_queue_still_accepts_an_existing_voice_update():
    queue, _ = _queue()
    for voice in range(100):
        queue.put_nowait(_work(voice))
    with pytest.raises(asyncio.QueueFull):
        queue.put_nowait(_work(100))
    for i in range(MAX_QUEUED_INTERVALS + 10):
        queue.put_nowait(_work(0, start=i * 2, seconds=1))
    assert queue.qsize() == queue.maxsize == 100
    items = []
    while not queue.empty():
        work = queue.get_nowait()
        if work['speaker_id'] == 0:
            items = work['_speaker_audio_ranges']
        queue.complete(work)
    assert len(items) == MAX_QUEUED_INTERVALS


def test_scope_conversation_and_generation_are_separate_coalescing_keys():
    queue, state = _queue()
    queue.put_nowait(_work(scope='first'))
    queue.put_nowait(_work(scope='second'))
    queue.put_nowait(_work(conversation='next'))
    state.generation += 1
    queue.put_nowait(_work(scope='first'))
    assert queue.qsize() == 4


@pytest.mark.anyio
async def test_active_voice_cannot_fill_task_slots_and_completion_wakes_waiter():
    queue, _ = _queue()
    queue.put_nowait(_work())
    active = await queue.get()
    queue.put_nowait(_work(start=6))
    with pytest.raises(asyncio.QueueEmpty):
        queue.get_nowait()
    waiter = asyncio.create_task(queue.get())
    await asyncio.sleep(0)
    assert not waiter.done() and queue.qsize() == 1
    queue.complete(active)
    work = await asyncio.wait_for(waiter, timeout=1)
    assert work['abs_start'] == 6
    queue.complete(work)


@pytest.mark.anyio
async def test_get_cancellation_does_not_lose_work_or_future_wakeups():
    queue, _ = _queue()
    waiter = asyncio.create_task(queue.get())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    queue.put_nowait(_work())
    assert (await asyncio.wait_for(queue.get(), timeout=1))['speaker_id'] == 1


def test_numeric_active_voice_blocks_scope_and_generation_duplicates_without_blocking_other_voices():
    queue, state = _queue()
    queue.put_nowait(_work(1))
    active = queue.get_nowait()
    queue.put_nowait(_work(1, scope='next-provider'))
    state.generation += 1
    queue.put_nowait(_work(1, conversation='next-conversation'))
    queue.put_nowait(_work(2))
    other = queue.get_nowait()
    assert other['speaker_id'] == 2
    queue.complete(other)
    with pytest.raises(asyncio.QueueEmpty):
        queue.get_nowait()
    queue.complete(active)
    for _ in range(2):
        work = queue.get_nowait()
        assert work['speaker_id'] == 1
        queue.complete(work)
    assert queue.empty()


@pytest.mark.anyio
async def test_coalesced_audio_beyond_one_query_recovers_without_another_provider_update(monkeypatch):
    _clock(monkeypatch)
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    noisy = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher, host, _ = _live_matcher(monkeypatch, [noisy, owner])
    matcher.person_embeddings.pop('p1')
    windows = []
    extract = host.state.audio_ring_buffer.extract

    def record(start, end):
        windows.append((start, end))
        return extract(start, end)

    monkeypatch.setattr(host.state.audio_ring_buffer, 'extract', record)
    for start, seconds in [(0, 10), (12, 5)]:
        matcher.queue.put_nowait(_work(start=start, seconds=seconds, conversation=None))
    work = await matcher.queue.get()
    await matcher.match(1, work)
    matcher.queue.complete(work)
    assert matcher._pending_audio[1] == [(12, 17)]
    assert 1 not in matcher.speaker_to_person
    assert matcher.queue.qsize() == 1 and matcher._embedding_attempts[1] == 1
    # The remaining already-queued clean interval waits for normal scheduling
    # and still reserves through the unchanged caps, without another update.
    work = await matcher.queue.get()
    await matcher.match(1, work)
    matcher.queue.complete(work)
    assert windows == [(0, 10), (12, 17)]
    assert 1 not in matcher._pending_audio
    assert matcher.speaker_to_person[1] == ('user', 'User')
    assert matcher._embedding_attempts[1] == 2 and matcher._socket_embedding_tokens == 14


def test_retained_work_preserves_latest_update_and_age_and_cannot_cross_generation_or_queue_cap():
    queue, state = _queue()
    queue.put_nowait(_work(segment='old'))
    active = queue.get_nowait()
    state.now = 1
    queue.put_nowait(_work(start=12, segment='latest'))
    state.now = 5
    queue.retain_unselected(active, [(6, 10)])
    queue.complete(active)
    state.attempts[1] = 1
    state.now = 6
    queue.put_nowait(_work(2))
    retained = queue.get_nowait()
    assert retained['id'] == 'latest' and retained['_speaker_audio_ranges'] == [(6, 10), (12, 17)]
    queue.complete(retained)
    other = queue.get_nowait()
    assert other['speaker_id'] == 2
    queue.complete(other)
    state.generation += 1
    queue.retain_unselected(active, [(6, 10)])
    assert queue.empty()
    for voice in range(2, 102):
        queue.put_nowait(_work(voice))
    active['_matcher_generation'] = state.generation
    queue.retain_unselected(active, [(6, 10)])
    assert queue.full() and queue.qsize() == 100


@pytest.mark.anyio
async def test_remaining_queued_work_cannot_raise_voice_ceiling_or_retry_a_budget_denial(monkeypatch):
    _clock(monkeypatch)
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    noisy = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher, host, _ = _live_matcher(monkeypatch, [noisy] * 12 + [owner])
    matcher.person_embeddings.pop('p1')
    monkeypatch.setattr(host.state.audio_ring_buffer, 'get_time_range', lambda: (0, 200))
    for i in range(26):
        matcher.queue.put_nowait(_work(start=i * 6, seconds=5, conversation=None))
    selected = 0
    while not matcher.queue.empty():
        work = await matcher.queue.get()
        await matcher.match(1, work)
        matcher.queue.complete(work)
        selected += 1
        assert selected <= 13
    assert selected == 13  # twelve successful queries, one denial, no denial retry
    assert matcher._embedding_attempts[1] == 12 and matcher._socket_embedding_tokens == 4
    assert matcher._pending_audio[1] and 1 not in matcher.speaker_to_person
    matcher.queue.put_nowait(_work(2, start=160, seconds=5, conversation=None))
    work = await matcher.queue.get()
    await matcher.match(2, work)
    matcher.queue.complete(work)
    assert matcher.speaker_to_person[2] == ('user', 'User')
    assert matcher._embedding_attempts[2] == 1 and matcher._socket_embedding_tokens == 3


@pytest.mark.anyio
async def test_coalesced_pcm_uses_distinct_intervals_and_recovers_owner(monkeypatch):
    _clock(monkeypatch)
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, _ = _live_matcher(monkeypatch, [owner])
    windows = []
    extract = host.state.audio_ring_buffer.extract

    def record(start, end):
        windows.append((start, end))
        return extract(start, end)

    monkeypatch.setattr(host.state.audio_ring_buffer, 'extract', record)
    for start, seconds in [(0, 2), (1, 2), (10, 2)]:
        matcher.queue.put_nowait(_work(start=start, seconds=seconds, conversation=None))
    work = await matcher.queue.get()
    await matcher.match(1, work)
    matcher.queue.complete(work)
    assert windows == [(0, 3), (10, 12)]
    assert matcher._embedding_attempts[1] == 1
    assert sum(seconds for _, seconds in matcher.speaker_evidence[1]) == 5
    assert matcher.speaker_to_person[1] == ('user', 'User')


@pytest.mark.anyio
async def test_coalesced_older_in_buffer_audio_is_kept_when_latest_update_is_outside(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, _, _ = _live_matcher(monkeypatch, [owner])
    matcher.queue.put_nowait(_work(start=0, seconds=5, conversation=None))
    matcher.queue.put_nowait(_work(start=100, seconds=5, conversation=None))
    work = await matcher.queue.get()
    await matcher.match(1, work)
    matcher.queue.complete(work)
    assert matcher.speaker_to_person[1] == ('user', 'User')
    assert sum(seconds for _, seconds in matcher.speaker_evidence[1]) == 5


@pytest.mark.anyio
async def test_coalesced_work_cannot_cross_generation_or_conversation_fences(monkeypatch):
    matcher, _, _ = _live_matcher(monkeypatch, [])
    matcher.queue.put_nowait(_work(conversation=None))
    work = await matcher.queue.get()
    matcher.clear()
    await matcher.match(1, work)
    assert not matcher._embedding_attempts and matcher._socket_embedding_tokens == 16
    work['_matcher_generation'] = matcher._generation
    work['conversation_id'] = 'previous-conversation'
    await matcher.match(1, work)
    assert not matcher._embedding_attempts and matcher._socket_embedding_tokens == 16


@pytest.mark.anyio
async def test_real_runner_late_untried_owner_gets_last_token_before_rejector(monkeypatch):
    _clock(monkeypatch)
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, _ = _live_matcher(monkeypatch, [owner])
    host.state.active = True
    host.state.speaker_id_enabled = True
    host.state.speaker_id_done = asyncio.Event()
    host.request.uid = 'test-owner'
    host.persistence = SimpleNamespace(call=AsyncMock(return_value={}))
    matcher._profile_conversation_id = 'conversation'
    matcher._embedding_attempts[1] = 8
    matcher._socket_embedding_tokens = 1
    for i in range(80):
        matcher.queue.put_nowait(_work(1, start=0, seconds=5, segment=f'rejector-{i}'))
    matcher.queue.put_nowait(_work(2, start=6, seconds=5))
    order = []
    original = matcher.match
    finished = asyncio.Event()

    async def match(voice, work):
        order.append(voice)
        await original(voice, work)
        if len(order) == 2:
            finished.set()

    monkeypatch.setattr(matcher, 'match', match)
    host.spawn = lambda coro, **kwargs: asyncio.create_task(coro)
    runner = asyncio.create_task(matcher.load_and_run())
    try:
        await asyncio.wait_for(finished.wait(), timeout=1)
        assert order == [2, 1]
        assert matcher.speaker_to_person[2] == ('user', 'User')
        assert matcher._embedding_attempts[2] == 1 and matcher._embedding_attempts[1] == 8
        assert matcher._socket_embedding_tokens == 0
    finally:
        runner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await runner
        await asyncio.gather(*matcher.tasks)


@pytest.mark.anyio
async def test_rejected_voice_recovers_after_coalesced_fresh_evidence_replaces_old_clips(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    noisy = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher, _, _ = _live_matcher(monkeypatch, [noisy] * 3 + [owner] * 3)
    matcher.person_embeddings.pop('p1')
    for i in range(6):
        for start in (i * 6, i * 6 + 2):
            matcher.queue.put_nowait(_work(start=start, seconds=3, conversation=None))
        work = await matcher.queue.get()
        await matcher.match(1, work)
        matcher.queue.complete(work)
        if i < 3:
            assert 1 not in matcher.speaker_to_person
            assert matcher._embedding_attempts[1] == i + 1
    assert matcher.speaker_to_person[1] == ('user', 'User')
    # Keep the existing acceptance threshold: recovery may precede eviction of
    # every noisy clip, and mapped updates must not spend further reservations.
    assert 3 < matcher._embedding_attempts[1] <= 6


def test_priority_never_promotes_contended_owner_to_near_owner(monkeypatch):
    matcher, _, _ = _live_matcher(monkeypatch, [])
    decision = select_speaker_match({'user': 0.67})
    matcher._voice_decisions = {1: replace(decision, owner_contended=True), 2: decision}
    matcher._embedding_attempts = {1: 2, 2: 2}
    for voice in (1, 2):
        matcher.queue.put_nowait(_work(voice, conversation=None))
    assert matcher.queue.get_nowait()['speaker_id'] == 2

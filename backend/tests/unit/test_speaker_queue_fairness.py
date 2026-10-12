"""Restored FIFO scheduling and provider-driven query cadence use the real matcher."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from routers.listen.speaker_queue import SpeakerMatchQueue
from tests.unit.test_speaker_match import _live_matcher, _segment
from tests.unit.test_owner_recognition_embedding_budget import _clock


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
    state = SimpleNamespace(generation=0)
    return SpeakerMatchQueue(generation=lambda: state.generation), state


def test_fifo_preserves_every_update_and_its_identity_without_coalescing_or_payloads():
    queue, _ = _queue()
    for voice, start, seconds, sid in [(1, 0, 2, 'first'), (2, 6, 10, 'other'), (1, 1, 3, 'updated')]:
        queue.put_nowait({**_work(voice, start, seconds, segment=sid), 'text': 'private', 'pcm': b'private'})
    assert queue.qsize() == 3
    work = [queue.get_nowait() for _ in range(3)]
    assert [item['id'] for item in work] == ['first', 'other', 'updated']
    assert [(item['abs_start'], item['duration']) for item in work] == [(0, 2), (6, 10), (1, 3)]
    assert all('text' not in item and 'pcm' not in item and '_speaker_audio_ranges' not in item for item in work)


def test_fifo_capacity_is_per_update_even_for_one_voice():
    queue, _ = _queue()
    for i in range(100):
        queue.put_nowait(_work(segment=f'update-{i}'))
    assert queue.qsize() == queue.maxsize == 100
    with pytest.raises(asyncio.QueueFull):
        queue.put_nowait(_work(segment='overflow'))
    assert [queue.get_nowait()['id'] for _ in range(100)] == [f'update-{i}' for i in range(100)]


@pytest.mark.anyio
async def test_same_voice_updates_remain_ready_for_existing_matcher_lock_serialization():
    queue, _ = _queue()
    queue.put_nowait(_work(segment='active'))
    assert (await queue.get())['id'] == 'active'
    queue.put_nowait(_work(start=6, segment='next'))
    assert (await asyncio.wait_for(queue.get(), timeout=1))['id'] == 'next'


@pytest.mark.anyio
async def test_fifo_get_cancellation_does_not_lose_future_updates():
    queue, _ = _queue()
    waiter = asyncio.create_task(queue.get())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    queue.put_nowait(_work())
    assert (await asyncio.wait_for(queue.get(), timeout=1))['speaker_id'] == 1


@pytest.mark.anyio
async def test_queued_work_keeps_enqueue_generation_and_conversation_fences(monkeypatch):
    matcher, _, _ = _live_matcher(monkeypatch, [])
    matcher.queue.put_nowait(_work(conversation=None))
    work = await matcher.queue.get()
    assert work['_matcher_generation'] == matcher._generation
    matcher.clear()
    await matcher.match(1, work)
    assert not matcher._embedding_attempts and matcher._socket_embedding_tokens == 16
    work['_matcher_generation'] = matcher._generation
    work['conversation_id'] = 'previous-conversation'
    await matcher.match(1, work)
    assert not matcher._embedding_attempts and matcher._socket_embedding_tokens == 16


@pytest.mark.anyio
async def test_queued_short_updates_extract_separately_and_accumulate_initial_owner_evidence(monkeypatch):
    _clock(monkeypatch)
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, _ = _live_matcher(monkeypatch, [owner, owner])
    windows = []
    extract = host.state.audio_ring_buffer.extract

    def record(start, end):
        windows.append((start, end))
        return extract(start, end)

    monkeypatch.setattr(host.state.audio_ring_buffer, 'extract', record)
    for start, seconds in [(0, 2), (3, 3)]:
        matcher.queue.put_nowait(_work(start=start, seconds=seconds, conversation=None))
    await matcher.match(1, await matcher.queue.get())
    assert matcher._embedding_attempts[1] == 1 and 1 not in matcher.speaker_to_person
    assert sum(seconds for _, seconds in matcher.speaker_evidence[1]) == 2
    assert matcher.queue.qsize() == 1
    await matcher.match(1, await matcher.queue.get())
    assert windows == [(0, 2), (3, 6)]
    assert matcher._embedding_attempts[1] == 2 and matcher._socket_embedding_tokens == 14
    assert sum(seconds for _, seconds in matcher.speaker_evidence[1]) == 5
    assert matcher.speaker_to_person[1] == ('user', 'User')


@pytest.mark.anyio
async def test_provider_repeats_do_not_double_count_successful_audio(monkeypatch):
    _clock(monkeypatch)
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, _, _ = _live_matcher(monkeypatch, [owner, owner])
    for start, seconds in [(0, 2), (0, 2), (1, 2), (4, 2)]:
        matcher.queue.put_nowait(_work(start=start, seconds=seconds, conversation=None))
    while not matcher.queue.empty():
        await matcher.match(1, await matcher.queue.get())
    assert matcher._embedding_attempts[1] == 2 and matcher._socket_embedding_tokens == 14
    assert sum(seconds for _, seconds in matcher.speaker_evidence[1]) == 5
    assert matcher._covered_audio[1] == [(0, 2), (2, 3), (4, 6)]
    assert matcher.speaker_to_person[1] == ('user', 'User')


def _runner_host(matcher, host):
    host.state.active = True
    host.state.speaker_id_enabled = True
    host.state.speaker_id_done = asyncio.Event()
    host.request.uid = 'test-owner'
    host.persistence = SimpleNamespace(call=AsyncMock(return_value={}))
    host.spawn = lambda coro, **kwargs: asyncio.create_task(coro)
    matcher._profile_conversation_id = 'conversation'


@pytest.mark.anyio
@pytest.mark.parametrize('owner_first', [True, False])
@pytest.mark.parametrize('owner_is_tried', [True, False])
async def test_real_runner_last_token_follows_fifo_for_tried_or_untried_owner(monkeypatch, owner_first, owner_is_tried):
    _clock(monkeypatch)
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    non_owner = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher, host, _ = _live_matcher(monkeypatch, [owner])
    if owner_is_tried:
        # One real query has spent an attempt but has only two seconds:
        # no acoustic decision exists yet. Three more seconds complete its floor.
        await matcher.match(1, _work(seconds=2, conversation=None))
        assert matcher._embedding_attempts[1] == 1 and 1 not in matcher._voice_decisions
    else:
        # Pin the converse too: an untried owner cannot jump an earlier rejector.
        matcher.person_embeddings.pop('p1')
        matcher._embedding_attempts[2] = 8
    _runner_host(matcher, host)
    matcher._socket_embedding_tokens = 1
    extraction_order = []

    async def query(pcm):
        seconds = len(pcm) / (2 * host.request.sample_rate)
        extraction_order.append(seconds)
        return non_owner if seconds == 6 else owner

    monkeypatch.setattr(matcher, '_extract_query', query)
    owner_seconds = 3 if owner_is_tried else 5
    queued = [_work(1, start=3, seconds=owner_seconds), _work(2, start=10, seconds=6)]
    if not owner_first:
        queued.reverse()
    for work in queued:
        matcher.queue.put_nowait(work)
    original = matcher.match
    order = []
    completed = []
    finished = asyncio.Event()

    async def match(voice, work):
        order.append(voice)
        await original(voice, work)
        completed.append(voice)
        if len(completed) == 2:
            finished.set()

    monkeypatch.setattr(matcher, 'match', match)
    runner = asyncio.create_task(matcher.load_and_run())
    try:
        await asyncio.wait_for(finished.wait(), timeout=1)
        assert order == ([1, 2] if owner_first else [2, 1])
        assert extraction_order == ([owner_seconds] if owner_first else [6])
        assert matcher._embedding_attempts[1] == int(owner_is_tried) + int(owner_first)
        assert matcher._embedding_attempts[2] == (0 if owner_is_tried else 8) + int(not owner_first)
        assert matcher._socket_embedding_tokens == 0
        assert (matcher.speaker_to_person.get(1) == ('user', 'User')) is owner_first
        assert matcher.queue.empty()
    finally:
        runner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(runner, timeout=1)
        for task in matcher.tasks:
            task.cancel()
        await asyncio.wait_for(asyncio.gather(*matcher.tasks, return_exceptions=True), timeout=1)


@pytest.mark.anyio
async def test_long_unresolved_buffer_does_not_self_requeue_without_provider_update(monkeypatch):
    _clock(monkeypatch)
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    rejector = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher, host, _ = _live_matcher(monkeypatch, [rejector, owner])
    matcher.person_embeddings.pop('p1')
    _runner_host(matcher, host)
    windows = []
    extract = host.state.audio_ring_buffer.extract

    def record(start, end):
        windows.append((start, end))
        return extract(start, end)

    monkeypatch.setattr(host.state.audio_ring_buffer, 'extract', record)
    matcher.queue.put_nowait(_work(seconds=30))
    original = matcher.match
    completions = asyncio.Queue()

    async def match(voice, work):
        await original(voice, work)
        completions.put_nowait(work['id'])

    monkeypatch.setattr(matcher, 'match', match)
    runner = asyncio.create_task(matcher.load_and_run())
    try:
        await asyncio.wait_for(completions.get(), timeout=1)
        assert windows == [(10, 20)]
        assert matcher._embedding_attempts[1] == 1 and matcher._socket_embedding_tokens == 15
        assert 1 not in matcher.speaker_to_person and 1 not in matcher._pending_audio
        assert matcher.queue.empty()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(completions.get(), timeout=0.02)
        assert matcher._embedding_attempts[1] == 1 and windows == [(10, 20)]
        # An ordinary update can still drive another query of uncovered speech.
        matcher.queue.put_nowait(_work(seconds=30, segment='provider-update'))
        assert await asyncio.wait_for(completions.get(), timeout=1) == 'provider-update'
        assert windows == [(10, 20), (0, 10)]
        assert matcher._embedding_attempts[1] == 2 and matcher._socket_embedding_tokens == 14
        assert matcher.queue.empty()
    finally:
        runner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(runner, timeout=1)
        for task in matcher.tasks:
            task.cancel()
        await asyncio.wait_for(asyncio.gather(*matcher.tasks, return_exceptions=True), timeout=1)

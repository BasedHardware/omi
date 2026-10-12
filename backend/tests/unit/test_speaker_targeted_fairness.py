"""Targeted demotion exercises the real FIFO runner, evidence and reservation gates."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from tests.unit.test_owner_recognition_diagnostics import live, snapshot
from tests.unit.test_owner_recognition_embedding_budget import _clock
from tests.unit.test_speaker_queue_fairness import _work
from utils.metrics import OMI_SPEAKER_ID_MATCH_EXITS_TOTAL
from utils.observability.speaker_embedding_budget import BUDGET_EXITS, REJECTOR_DEMOTIONS, REJECTOR_TAIL_DENIALS

OWNER = np.array([[1.0, 0.0]], dtype=np.float32)
FAR = np.array([[-1.0, -1.0]], dtype=np.float32)


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def work(voice=2, start=0, seconds=5, *, segment=None, conversation='c', scope='socket:0'):
    return _work(voice, start, seconds, segment=segment, conversation=conversation, scope=scope)


async def serve(matcher, host, monkeypatch, count):
    host.state.active = True
    host.state.speaker_id_done = asyncio.Event()
    host.spawn = lambda coro, **kwargs: asyncio.create_task(coro)
    original = matcher.match
    completed = asyncio.Queue()
    started = []

    async def match(voice, item):
        started.append((voice, item['id']))
        await original(voice, item)
        completed.put_nowait(item['id'])

    monkeypatch.setattr(matcher, 'match', match)
    runner = asyncio.create_task(matcher.load_and_run())
    try:
        if count is None:

            async def settle():
                while True:
                    try:
                        await asyncio.wait_for(completed.get(), timeout=0.02)
                    except asyncio.TimeoutError:
                        if matcher.queue.empty() and all(task.done() for task in matcher.tasks):
                            return

            await asyncio.wait_for(settle(), timeout=2)
        else:
            for _ in range(count):
                await asyncio.wait_for(completed.get(), timeout=2)
        assert matcher.queue.empty()
        # Unselected audio does not turn into autonomous work.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(completed.get(), timeout=0.02)
        return started
    finally:
        runner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(runner, timeout=1)
        tasks = list(matcher.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1)
        monkeypatch.setattr(matcher, 'match', original)


async def prove(matcher, host, monkeypatch):
    for start in (0, 5, 10):
        matcher.queue.put_nowait(work(start=start))
    await serve(matcher, host, monkeypatch, 3)
    assert matcher._rejectors.comparisons[2] == 3
    assert matcher._rejectors.proven(2)
    assert matcher._embedding_attempts[2] == 3


@pytest.mark.anyio
@pytest.mark.parametrize('tokens', [1, 2])
async def test_eighty_rejector_updates_yield_to_late_owner_without_spending_the_tail(monkeypatch, tokens):
    _clock(monkeypatch)
    matcher, host, _ = live(monkeypatch, [FAR] * 3 + [OWNER])
    await prove(matcher, host, monkeypatch)
    before = {action: REJECTOR_DEMOTIONS.labels(action=action)._value.get() for action in ('deferred', 'coalesced')}
    denied = REJECTOR_TAIL_DENIALS.labels(reason='reserved_tail')._value.get()
    cap_exits = sum(BUDGET_EXITS.labels(cap=cap)._value.get() for cap in ('voice', 'socket', 'both'))
    legacy = OMI_SPEAKER_ID_MATCH_EXITS_TOTAL.labels(reason='embedding_budget')._value.get()
    matcher._socket_embedding_tokens = tokens
    for index in range(80):
        matcher.queue.put_nowait(work(start=15 + index * 0.5, seconds=2, segment=f'reject-{index}'))
    assert matcher.queue.qsize() == 1
    matcher.queue.put_nowait(work(1, 40, segment='late-owner'))
    assert matcher.queue.qsize() == 2
    order = await serve(matcher, host, monkeypatch, 2)
    assert order == [(1, 'late-owner'), (2, 'reject-79')]
    assert matcher.speaker_to_person[1] == ('user', 'User')
    assert matcher._embedding_attempts == {2: 3, 1: 1}
    assert matcher._socket_embedding_tokens == tokens - 1
    assert snapshot(matcher)['owner_comparisons'] == 4
    assert snapshot(matcher)['reasons']['rejector_tail_reserved' if tokens == 2 else 'embedding_budget'] == 1
    assert REJECTOR_DEMOTIONS.labels(action='deferred')._value.get() == before['deferred'] + 1
    assert REJECTOR_DEMOTIONS.labels(action='coalesced')._value.get() == before['coalesced'] + 79
    assert REJECTOR_TAIL_DENIALS.labels(reason='reserved_tail')._value.get() == denied + (tokens == 2)
    assert sum(BUDGET_EXITS.labels(cap=cap)._value.get() for cap in ('voice', 'socket', 'both')) - cap_exits == (
        tokens == 1
    )
    assert OMI_SPEAKER_ID_MATCH_EXITS_TOTAL.labels(reason='embedding_budget')._value.get() - legacy == (tokens == 1)


@pytest.mark.anyio
async def test_runner_demotes_already_queued_updates_when_third_rejection_completes(monkeypatch):
    _clock(monkeypatch)
    matcher, host, _ = live(monkeypatch, [])
    calls = []

    async def query(pcm):
        # The owner turn is seven seconds; rejector updates are two or five.
        seconds = len(pcm) / (2 * host.request.sample_rate)
        calls.append(seconds)
        await asyncio.sleep(0)
        return OWNER if seconds == 7 else FAR

    monkeypatch.setattr(matcher, '_extract_query', query)
    coalesced = REJECTOR_DEMOTIONS.labels(action='coalesced')._value.get()
    for start in (0, 5, 10):
        matcher.queue.put_nowait(work(start=start))
    for index in range(80):
        matcher.queue.put_nowait(work(start=15 + index * 0.5, seconds=2, segment=f'queued-{index}'))
    matcher.queue.put_nowait(work(1, 50, 7, segment='late-owner'))
    assert matcher.queue.qsize() == 84 and not matcher._rejectors.comparisons
    order = await serve(matcher, host, monkeypatch, None)
    assert matcher.speaker_to_person[1] == ('user', 'User')
    assert matcher._rejectors.proven(2)
    assert matcher._embedding_attempts[2] <= 12 and len(calls) <= 15
    assert matcher._embedding_attempts[1] == 1
    assert (2, 'queued-79') in order and order.index((1, 'late-owner')) < order.index((2, 'queued-79'))
    assert REJECTOR_DEMOTIONS.labels(action='coalesced')._value.get() > coalesced


@pytest.mark.anyio
@pytest.mark.parametrize('owner_first', [True, False])
async def test_tried_owner_needing_final_evidence_keeps_fifo_against_untried_non_owner(monkeypatch, owner_first):
    _clock(monkeypatch)
    matcher, host, _ = live(monkeypatch, [OWNER, OWNER if owner_first else FAR])
    matcher.queue.put_nowait(work(1, seconds=2))
    await serve(matcher, host, monkeypatch, 1)
    assert not matcher._rejectors.proven(1) and 1 not in matcher._voice_decisions
    matcher._socket_embedding_tokens = 1
    updates = [work(1, 3, 3, segment='final-evidence'), work(3, 10, segment='untried')]
    if not owner_first:
        updates.reverse()
    for item in updates:
        matcher.queue.put_nowait(item)
    order = await serve(matcher, host, monkeypatch, 2)
    assert [voice for voice, _ in order] == ([1, 3] if owner_first else [3, 1])
    assert (matcher.speaker_to_person.get(1) == ('user', 'User')) is owner_first
    assert matcher._embedding_attempts[1] == 1 + owner_first
    assert matcher._socket_embedding_tokens == 0


@pytest.mark.anyio
@pytest.mark.parametrize('kind', ['near', 'ambiguous', 'contended', 'manual', 'pending'])
async def test_protected_voices_keep_separate_fifo_updates(monkeypatch, kind):
    _clock(monkeypatch)
    vector = {
        'near': np.array([[0.32, np.sqrt(1 - 0.32**2)]], dtype=np.float32),
        'ambiguous': np.array([[1.0, 1.0]], dtype=np.float32),
        'contended': OWNER,
        'manual': FAR,
        'pending': OWNER,
    }[kind]
    matcher, host, _ = live(monkeypatch, ([OWNER] if kind == 'contended' else []) + [vector] * 3)
    if kind in ('near', 'contended'):
        matcher.person_embeddings.pop('p1')
    if kind == 'contended':
        matcher.queue.put_nowait(work(1))
        await serve(matcher, host, monkeypatch, 1)
    if kind == 'manual':
        host.persistence.call = AsyncMock(
            return_value={'segments': {'manual-segment': {'speaker_id': 2, 'is_user': True, 'generation': 1}}}
        )
    for start in (0, 5, 10):
        matcher.queue.put_nowait(work(start=start, seconds=2 if kind == 'pending' else 5))
    await serve(matcher, host, monkeypatch, 3)
    assert not matcher._rejectors.proven(2)
    for start in (20, 25):
        matcher.queue.put_nowait(work(start=start))
    matcher.queue.put_nowait(work(3, 30))
    assert matcher.queue.qsize() == 3
    assert [matcher.queue.get_nowait()['speaker_id'] for _ in range(3)] == [2, 2, 3]


@pytest.mark.anyio
async def test_only_completed_fresh_comparisons_count_and_nonreject_history_is_sticky(monkeypatch):
    _clock(monkeypatch)
    near = np.array([[0.32, np.sqrt(1 - 0.32**2)]], dtype=np.float32)
    matcher, host, _ = live(monkeypatch, [near] + [FAR] * 5)
    matcher.person_embeddings.pop('p1')
    for start in range(0, 30, 5):
        matcher.queue.put_nowait(work(start=start))
        await serve(matcher, host, monkeypatch, 1)
    assert snapshot(matcher)['owner_comparisons'] == 6
    assert matcher._rejectors.comparisons[2] == -1 and not matcher._rejectors.proven(2)
    attempts = matcher._embedding_attempts[2]
    for index in range(5):
        matcher.queue.put_nowait(work(start=25, segment=f'duplicate-{index}'))
    await serve(matcher, host, monkeypatch, 5)
    assert matcher._embedding_attempts[2] == attempts
    assert snapshot(matcher)['owner_comparisons'] == 6


@pytest.mark.anyio
async def test_uncarried_rollover_resets_proof_but_preserves_socket_spend_and_stale_fences(monkeypatch):
    _clock(monkeypatch)
    matcher, host, _ = live(monkeypatch, [FAR] * 3)
    await prove(matcher, host, monkeypatch)
    matcher.queue.put_nowait(work(start=20, segment='old'))
    profiles = dict(matcher.person_embeddings)

    async def load():
        matcher.person_embeddings.update(profiles)

    monkeypatch.setattr(matcher, '_load_profiles', AsyncMock(side_effect=load))
    await matcher.refresh_for_conversation('next')
    assert matcher._generation == 1 and not matcher._rejectors.comparisons
    assert not matcher._rejectors.proven(2) and matcher._socket_embedding_tokens == 13
    for start in (30, 35):
        matcher.queue.put_nowait(work(start=start, conversation='next'))
    assert matcher.queue.qsize() == 3
    old = matcher.queue.get_nowait()
    await matcher.match(2, old)
    assert not matcher._embedding_attempts and matcher._socket_embedding_tokens == 13
    assert [matcher.queue.get_nowait()['abs_start'] for _ in range(2)] == [30, 35]


@pytest.mark.anyio
async def test_rejector_pool_preserves_gaps_latest_id_and_ten_second_query_without_requeue(monkeypatch):
    _clock(monkeypatch)
    matcher, host, _ = live(monkeypatch, [FAR] * 4)
    await prove(matcher, host, monkeypatch)
    windows = []
    extract = host.state.audio_ring_buffer.extract

    def record(start, end):
        windows.append((start, end))
        return extract(start, end)

    monkeypatch.setattr(host.state.audio_ring_buffer, 'extract', record)
    for start, seconds in ((20, 2), (20, 2), (24, 2), (28, 2), (32, 6)):
        matcher.queue.put_nowait(work(start=start, seconds=seconds, segment=f'latest-{start}'))
    assert matcher.queue.qsize() == 1
    assert await serve(matcher, host, monkeypatch, 1) == [(2, 'latest-32')]
    assert windows == [(20, 22), (24, 26), (28, 30), (33, 37)]
    assert matcher._embedding_attempts[2] == 4 and matcher._socket_embedding_tokens == 12
    assert not matcher._pending_audio and matcher.queue.empty()


@pytest.mark.anyio
@pytest.mark.parametrize('distinct', [False, True])
async def test_failed_queries_still_spend_and_never_exceed_voice_socket_or_task_ceilings(monkeypatch, distinct):
    _clock(monkeypatch)
    matcher, host, _ = live(monkeypatch, [])
    state = SimpleNamespace(active=0, peak=0, calls=0, largest=0)

    async def fail(pcm):
        state.calls += 1
        state.largest = max(state.largest, len(pcm) / (2 * host.request.sample_rate))
        state.active += 1
        state.peak = max(state.peak, state.active)
        await asyncio.sleep(0)
        state.active -= 1
        raise RuntimeError('injected failure')

    monkeypatch.setattr(matcher, '_extract_query', fail)
    for index in range(32):
        matcher.queue.put_nowait(work(index if distinct else 2, seconds=30, segment=f'failure-{index}'))
    await serve(matcher, host, monkeypatch, 32)
    assert state.calls == (16 if distinct else 12)
    assert state.peak <= 16 and state.largest == 10
    assert sum(matcher._embedding_attempts.values()) == state.calls
    assert max(matcher._embedding_attempts.values()) <= 12
    assert matcher._socket_embedding_tokens == 16 - state.calls
    assert not matcher._rejectors.comparisons and not matcher._covered_audio.get(2)


def test_targeted_metric_labels_have_closed_cardinality():
    for counter, labels in (
        (REJECTOR_DEMOTIONS, [{'action': 'deferred'}, {'action': 'coalesced'}]),
        (REJECTOR_TAIL_DENIALS, [{'reason': 'reserved_tail'}]),
    ):
        samples = [
            sample for metric in counter.collect() for sample in metric.samples if sample.name.endswith('_total')
        ]
        assert [sample.labels for sample in samples] == labels


@pytest.mark.anyio
@pytest.mark.parametrize('tokens', [2.0, 2.1, 2.9, 3.0])
async def test_approved_tail_cutoff_uses_literal_fractional_balance(monkeypatch, tokens):
    _clock(monkeypatch)
    matcher, host, _ = live(monkeypatch, [FAR] * 4)
    await prove(matcher, host, monkeypatch)
    matcher._socket_embedding_tokens = tokens
    matcher.queue.put_nowait(work(start=20))
    await serve(matcher, host, monkeypatch, 1)
    allowed = tokens > 2
    assert matcher._embedding_attempts[2] == 3 + allowed
    assert matcher._socket_embedding_tokens == pytest.approx(tokens - allowed)


@pytest.mark.anyio
@pytest.mark.parametrize('revocation', ['manual', 'profile'])
async def test_revoked_rejector_returns_to_earliest_fifo_position_with_latest_id(monkeypatch, revocation):
    _clock(monkeypatch)
    matcher, host, _ = live(monkeypatch, [FAR] * 6)
    await prove(matcher, host, monkeypatch)
    matcher.queue.put_nowait(work(start=20, segment='earliest'))
    matcher.queue.put_nowait(work(3, 30, segment='later-ordinary'))
    matcher.queue.put_nowait(work(start=21, segment='latest-rejector'))
    assert matcher.queue.qsize() == 2
    if revocation == 'manual':
        host.persistence.call = AsyncMock(
            return_value={'segments': {'manual-2': {'speaker_id': 2, 'is_user': True, 'generation': 1}}}
        )
        # Another real in-flight comparison observes the manual authority.
        await matcher.match(4, work(4, 40))
    else:
        direction = FAR / np.linalg.norm(FAR)
        orthogonal = np.array([[1.0, -1.0]], dtype=np.float32) / np.sqrt(2)
        matcher.person_embeddings['user']['embedding'] = 0.32 * direction + np.sqrt(1 - 0.32**2) * orthogonal
        await matcher._reevaluate_loaded_owner()
        assert matcher._voice_distances[2]['user'] == pytest.approx(0.68)
    assert not matcher._rejectors.proven(2)
    order = await serve(matcher, host, monkeypatch, 2)
    assert order == [(2, 'latest-rejector'), (3, 'later-ordinary')]


@pytest.mark.anyio
async def test_queue_coalescing_releases_all_open_slots_and_preserves_join_accounting(monkeypatch):
    _clock(monkeypatch)
    matcher, host, _ = live(monkeypatch, [FAR] * 3)
    for start in (0, 5):
        matcher.queue.put_nowait(work(start=start))
    await serve(matcher, host, monkeypatch, 2)
    for _ in range(2):
        matcher.queue.task_done()
    for index in range(100):
        matcher.queue.put_nowait(work(start=15 + index * 0.1, seconds=2))
    putters = [asyncio.create_task(matcher.queue.put(work(voice, 40))) for voice in (3, 4, 5)]
    try:
        await asyncio.sleep(0)
        assert matcher.queue.full() and not any(task.done() for task in putters)
        # A real third comparison qualifies the queued voice; get collapses
        # its pending updates and must wake every producer whose slot is freed.
        await matcher.match(2, work(start=10))
        assert matcher._rejectors.proven(2)
        assert matcher.queue.get_nowait()['speaker_id'] == 2
        matcher.queue.task_done()
        await asyncio.wait_for(asyncio.gather(*putters), timeout=1)
        assert matcher.queue.qsize() == 3
        assert [matcher.queue.get_nowait()['speaker_id'] for _ in range(3)] == [3, 4, 5]
        for _ in range(3):
            matcher.queue.task_done()
        await asyncio.wait_for(matcher.queue.join(), timeout=1)
    finally:
        for task in putters:
            task.cancel()
        await asyncio.gather(*putters, return_exceptions=True)

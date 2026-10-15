"""Merged diagnostics observe FIFO queries and boundaries without changing cadence."""

import asyncio
import copy

import numpy as np

from tests.unit.test_owner_recognition_diagnostics import live, snapshot
from tests.unit.test_owner_recognition_embedding_budget import _clock
from tests.unit.test_speaker_match import _segment


def work(segment, start, seconds):
    return dict(
        _segment(segment, start, seconds),
        speaker_id=1,
        speaker_id_scope='socket:0',
        conversation_id='c',
    )


def test_fifo_runner_records_separate_queries_owner_comparison_and_rollover_stop(monkeypatch, caplog):
    _clock(monkeypatch)
    monkeypatch.setenv('SPEAKER_MATCH_SCORES_ENABLED', 'true')
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, _ = live(monkeypatch, [owner, owner])
    caplog.set_level('INFO')

    async def run():
        host.state.active = True
        host.state.speaker_id_done = asyncio.Event()
        host.spawn = lambda coro, **kwargs: asyncio.create_task(coro)
        for item in (work('first', 0, 2), work('final-evidence', 3, 3)):
            matcher.queue.put_nowait(item)
        assert matcher.queue.qsize() == 2
        original = matcher.match
        completed = asyncio.Queue()

        async def match(voice, item):
            await original(voice, item)
            completed.put_nowait(item['id'])

        monkeypatch.setattr(matcher, 'match', match)
        runner = asyncio.create_task(matcher.load_and_run())
        try:
            assert await asyncio.wait_for(completed.get(), timeout=2) == 'first'
            assert await asyncio.wait_for(completed.get(), timeout=2) == 'final-evidence'
            assert matcher.speaker_to_person[1][0] == 'user'
        finally:
            runner.cancel()
            try:
                await asyncio.wait_for(runner, timeout=1)
            except asyncio.CancelledError:
                pass
            for task in matcher.tasks:
                task.cancel()
            await asyncio.wait_for(asyncio.gather(*matcher.tasks, return_exceptions=True), timeout=1)
        await asyncio.sleep(0)  # Let the runner's task-discard callbacks complete.
        summary = snapshot(matcher)
        assert summary['attempted'] == summary['successful'] == matcher._embedding_attempts[1] == 2
        assert summary['pcm_seconds'] == summary['evidence_seconds'] == 5
        assert summary['comparisons'] == summary['owner_comparisons'] == 1
        assert summary['reasons']['evidence_pending'] == 1
        assert summary['published'] == summary['scores_generated'] == 1
        assert summary['scopes'] == ['socket:0']
        assert matcher.queue.empty() and not matcher.tasks
        # Stop counts queued updates, including two entries for the same voice.
        for item in (work('pending-1', 10, 5), work('pending-2', 20, 5)):
            matcher.queue.put_nowait(item)
        matcher.clear()
        frozen = copy.deepcopy(snapshot(matcher))
        assert frozen['stop'] == 'rollover' and frozen['pending_queue'] == 2
        assert frozen['pending_tasks'] == 0
        matcher._profile_conversation_id = 'next'
        matcher.diagnostics.begin('next', matcher._generation)
        await matcher.match(1, await matcher.queue.get())
        assert snapshot(matcher) == frozen  # Stale FIFO work cannot repaint either generation.
        assert matcher.diagnostics.snapshot('next')['live'][0].get('comparisons', 0) == 0
        assert matcher._socket_embedding_tokens == 14

    asyncio.run(run())
    assert caplog.text.count('kind=live_stop') == 1
    assert 'kind=live_progress' in caplog.text and 'kind=live_refusal' in caplog.text


def test_fifo_refusal_and_budget_path_are_recorded_before_drain_stop(monkeypatch, caplog):
    _clock(monkeypatch)
    matcher, _, _ = live(monkeypatch, [])
    matcher._socket_embedding_tokens = 0
    caplog.set_level('INFO')
    for item in (work('short', 0, 0.5), work('blocked', 2, 3), work('pending-1', 6, 3), work('pending-2', 10, 3)):
        matcher.queue.put_nowait(item)
    assert matcher.queue.qsize() == 4

    async def run():
        await matcher.match(1, await matcher.queue.get())
        await matcher.match(1, await matcher.queue.get())

    asyncio.run(run())
    summary = snapshot(matcher)
    assert summary['reasons']['window_shorter_than_minimum'] == 1
    assert summary['reasons']['embedding_budget'] == summary['budget_socket'] == 1
    assert summary.get('attempted', 0) == summary.get('comparisons', 0) == 0
    assert matcher._embedding_attempts[1] == matcher._socket_embedding_tokens == 0
    matcher.diagnostics.stop('drain', matcher.queue, matcher.tasks)
    frozen = copy.deepcopy(snapshot(matcher))
    matcher.diagnostics.stop('drain', matcher.queue, matcher.tasks)
    assert snapshot(matcher) == frozen
    assert frozen['stop'] == 'drain' and frozen['pending_queue'] == 2 and frozen['pending_tasks'] == 0
    assert caplog.text.count('speaker_id_budget_first_block') == 1
    assert caplog.text.count('kind=live_stop') == 1
    assert caplog.text.count('kind=live_refusal') == 1

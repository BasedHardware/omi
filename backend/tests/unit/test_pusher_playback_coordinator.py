"""Bound the whole process and keep optional discovery off custody workers."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from routers import pusher
from tests.unit.test_audio_durable_outbox import Socket, _audio_frames, inline_session, remote
from utils import pusher_playback_coordinator as module
from utils.pusher_audio_projection import PusherAudioProjection


@pytest.mark.asyncio
async def test_process_limit_and_isolated_pool_across_many_socket_instances(monkeypatch):
    monkeypatch.setattr(module, 'MAX_CONVERSATIONS', 3)
    monkeypatch.setattr(module, 'MAX_PATHS', 3)
    monkeypatch.setattr(module, '_owner', None)
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    threads = []

    def refresh(self, *args, **kwargs):
        threads.append(threading.current_thread().name)
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10)
        return None

    monkeypatch.setattr(PusherAudioProjection, 'refresh', refresh)
    monkeypatch.setattr(module, 'record_fallback', MagicMock())
    owner = module.coordinator()
    try:
        assert owner.submit('u1', 'a', ['p1'], False, None)
        assert owner.submit('u2', 'b', ['p2'], False, None)
        assert owner.submit('u3', 'c', ['p3'], False, None)
        assert not owner.submit('u4', 'd', ['p4'], False, None)
        assert not owner.submit('u3', 'c', ['p3', 'overflow'], True, None)
        await asyncio.wait_for(entered.wait(), 5)
        assert len(owner.active) == 2 and len(owner.pending) == 1
        assert len(owner.tasks) == 2
    finally:
        release.set()
        while owner.tasks:
            await asyncio.wait_for(asyncio.gather(*list(owner.tasks)), 5)
    assert threads and all(name.startswith('playback-metadata') for name in threads)


@pytest.mark.asyncio
async def test_overflow_writes_debt_and_never_discovers_in_audio_drain(inline_session, monkeypatch):
    client, path, _, _ = inline_session
    queue = SimpleNamespace(submit=MagicMock(return_value=False), wait_owner=AsyncMock())
    monkeypatch.setattr(module, 'coordinator', lambda: queue)
    fallback = MagicMock()
    monkeypatch.setattr('utils.pusher_audio_projection.record_fallback', fallback)
    discovery = MagicMock(side_effect=AssertionError('discovery must not run on overflow'))
    monkeypatch.setattr(PusherAudioProjection, 'refresh', discovery)
    await pusher._websocket_util_trigger(
        Socket(_audio_frames('conversation', [b'\x01\x00'])), 'owner', 16000, audio_custody=1
    )
    assert client.rows[path]['record_audio_closed']
    assert client.rows[path]['record_upload_sessions'] == {}
    discovery.assert_not_called()
    queue.submit.assert_called()
    assert any(
        call.kwargs.get('reason') == 'capacity_full' and call.kwargs.get('outcome') == 'degraded'
        for call in fallback.call_args_list
    )


@pytest.mark.asyncio
async def test_failed_durable_debt_keeps_token_until_commit_ack(inline_session, monkeypatch):
    from database import record_projection_rebuild

    client, path, _, _ = inline_session
    failed, sealed = asyncio.Event(), asyncio.Event()
    can_commit = threading.Event()
    loop = asyncio.get_running_loop()

    def mark(*args):
        if not can_commit.is_set():
            loop.call_soon_threadsafe(failed.set)
            raise OSError('synthetic unavailable commit')

    monkeypatch.setattr(record_projection_rebuild, 'mark_many', mark)
    monkeypatch.setattr(module, 'coordinator', lambda: SimpleNamespace(submit=MagicMock(), wait_owner=AsyncMock()))
    # The fixture substitutes a barrier factory, so inspect the actual shared barrier.
    barrier = inline_session[2]
    finish = barrier.finish_recording

    async def observe(cid):
        result = await finish(cid)
        if result:
            sealed.set()
        return result

    monkeypatch.setattr(barrier, 'finish_recording', observe)
    handler = asyncio.create_task(
        pusher._websocket_util_trigger(
            Socket(_audio_frames('conversation', [b'\x01\x00'])), 'owner', 16000, audio_custody=1
        )
    )
    try:
        await asyncio.wait_for(failed.wait(), 5)
        assert not sealed.is_set()
        assert client.rows[path]['record_upload_sessions']
        assert not client.rows[path]['record_audio_closed']
        can_commit.set()
        await asyncio.wait_for(sealed.wait(), 5)
        assert client.rows[path]['record_audio_closed']
    finally:
        can_commit.set()
        await asyncio.wait_for(handler, 5)


@pytest.mark.asyncio
@pytest.mark.parametrize('closing,applied', [(True, True), (False, True), (True, False), (True, None)])
async def test_only_successful_closing_refresh_retires_acknowledged_debt(monkeypatch, closing, applied):
    monkeypatch.setattr(module, '_owner', None)
    monkeypatch.setattr(PusherAudioProjection, 'refresh', lambda *args, **kwargs: applied)
    retire = MagicMock(return_value=True)
    fallback = MagicMock()
    monkeypatch.setattr(module, 'record_fallback', fallback)
    monkeypatch.setattr(module.record_projection_rebuild, 'retire_observed', retire)
    from utils import speaker_learning_jobs

    monkeypatch.setattr(speaker_learning_jobs, 'schedule_person_voice_learning_retry', MagicMock())
    owner = module.coordinator()
    assert owner.submit('u', 'c', [], closing, None, observed_update_time='committed')
    await owner.wait_owner('u')
    if closing and applied is True:
        retire.assert_called_once_with('u', 'c', observed_update_time='committed')
    else:
        retire.assert_not_called()
    if applied is None:
        assert fallback.call_args.kwargs['reason'] == 'input_missing'
        assert fallback.call_args.kwargs['outcome'] == 'degraded'
    else:
        fallback.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_optional_worker_reports_durable_repair_handoff(monkeypatch):
    monkeypatch.setattr(module, '_owner', None)
    monkeypatch.setattr(module, 'run_blocking', AsyncMock(side_effect=asyncio.CancelledError()))
    fallback = MagicMock()
    monkeypatch.setattr(module, 'record_fallback', fallback)
    owner = module.coordinator()
    assert owner.submit('u', 'c', [], True, None)
    await asyncio.gather(*list(owner.tasks), return_exceptions=True)
    assert not owner.active
    assert fallback.call_args.kwargs['reason'] == 'cancelled'
    assert fallback.call_args.kwargs['outcome'] == 'degraded'

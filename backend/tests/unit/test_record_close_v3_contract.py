"""Version/switch boundaries, exact watermarks, and bounded local exits."""

import asyncio
import json
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import pusher
from routers.listen import conversations as conversation_module
from routers.listen.conversations import LiveConversationController
from tests.unit.test_audio_durable_outbox import inline_session, remote, Socket, _audio_frames
from tests.unit.utils.test_listen_pusher_session import FakePusherWebSocket, make_session
from utils.listen_record_boundary import ListenRecordBoundary
from utils.pusher_record_close import PusherCloseState


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('version', [None, 2, 3])
async def test_listener_requires_matching_v3_and_its_own_switch(monkeypatch, enabled, version):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', str(enabled).lower())
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    ack = (
        []
        if version is None
        else [struct.pack('<I', 204) + json.dumps(dict(type='record_close_ack', version=version)).encode()]
    )
    active = {'active': True}
    socket = FakePusherWebSocket(incoming=[*ack, b''])
    socket.on_recv = lambda: active.update(active=len(socket.incoming) > 1)
    session = make_session(
        ws=socket,
        active_ref=active,
        deps_overrides={'finish_recording_audio': AsyncMock(return_value=True)},
    )
    await session.connect()
    await session.request_recording_close('conv-1')
    # A switch-off listener has no pending work; wake its ordinary receive pump.
    session.pending_request_event.set()
    if not enabled:
        session.pending_conversation_requests['unrelated'] = {'sent_at': 1000, 'retries': 0}
    await session.pusher_receive()
    expected = enabled and version == 3
    assert session.record_close_supported is expected
    controls = [frame for frame in socket.sent if struct.unpack('<I', frame[:4])[0] == 104]
    assert bool(controls) is expected
    assert not socket.closed_codes


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('version', [None, 2, 3])
async def test_pusher_requires_matching_v3_and_its_own_switch(inline_session, monkeypatch, enabled, version):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', str(enabled).lower())
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    client, path, _, projected = inline_session
    controls = [
        struct.pack('<I', 104)
        + json.dumps(
            dict(
                conversation_id='conversation',
                record_close_only=True,
                request_id='request',
                phase=phase,
                watermark=4,
            )
        ).encode()
        for phase in ['prepare', 'commit']
    ]
    socket = Socket(_audio_frames('conversation', [b'\x01\x00' * 2]) + controls)
    await pusher._websocket_util_trigger(socket, 'owner', 16000, audio_custody=1, record_close_protocol=version)
    replies = [json.loads(frame[4:]) for frame in socket.sent if struct.unpack('<I', frame[:4])[0] == 206]
    expected = enabled and version == 3
    assert [reply['status'] for reply in replies] == (['prepared', 'accepted'] if expected else ['unsupported'] * 2)
    assert any(struct.unpack('<I', frame[:4])[0] == 204 for frame in socket.sent) is expected
    assert client.rows[path]['record_audio_closed'] and client.rows[path]['record_upload_sessions'] == {}
    assert b''.join(chunk['data'] for batch in projected for chunk in batch[0]) == b'\x01\x00' * 2


@pytest.mark.asyncio
async def test_handshake_deadline_exits_with_source_and_producer_fences_intact(monkeypatch):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', 'true')
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    clock = [100.0]
    socket = FakePusherWebSocket()
    session = make_session(
        ws=socket,
        deps_overrides={
            'monotonic': lambda: clock[0],
            'finish_recording_audio': AsyncMock(return_value=False),
        },
    )
    await session.connect()
    session.record_close_supported = True
    with session.audio_frame('conv-1'):
        await session.request_recording_close('conv-1')
        close = session.pending_record_closes['conv-1']
        close.prepared = True
        clock[0] += 31
        assert not await session.request_recording_close('conv-1')
        assert not session.pending_record_closes
        assert 'conv-1' in session.deferred_record_closes
        assert not session.record_boundary.ready('conv-1')
        assert [json.loads(frame[4:])['phase'] for frame in socket.sent] == ['prepare']
    # Expiry never resumes ingress into the prepared recording or closes a stream.
    with session.audio_frame('conv-1') as frame:
        assert frame.conversation_id is None
    assert not socket.closed_codes


def test_retired_current_binding_survives_history_eviction_and_failed_frame():
    boundary = ListenRecordBoundary(2)
    boundary.retire('current', current='current')
    for name in ['previous-a', 'previous-b', 'previous-c']:
        boundary.retire(name, current='current')
    assert len(boundary.retired) == 2
    with boundary.frame('current') as frame:
        assert frame.conversation_id is None
    with pytest.raises(RuntimeError):
        with boundary.frame('successor'):
            raise RuntimeError('unknown acceptance')
    assert boundary.failed and not boundary.inflight and not boundary.ready('current')


def test_commit_requires_exact_received_watermark():
    state = PusherCloseState(True)
    state.audio('record', 4)
    assert state.prepare('record', 'request', set()) == ('prepared', 4)
    state.audio('record', 4)
    assert state.commit('record', 'request', 4) == 'invalid_watermark'
    assert state.blocks('record', True)


@pytest.mark.asyncio
async def test_switch_off_ignores_previously_retired_boundaries(monkeypatch):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', 'true')
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    session = make_session(deps_overrides={'finish_recording_audio': AsyncMock(return_value=True)})
    session.record_boundary.retire('conv-1', current='conv-1')
    session.record_close_boundaries['conv-1'] = True
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', 'false')
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    with session.audio_frame('conv-1') as frame:
        assert frame is None
        session.audio_bytes_send(b'\x01\x00', 100)
    assert session.audio_runs[-1].conversation_id is None  # Main resolves implicit binding at flush.
    await session.connect()
    await session._audio_bytes_flush()
    assert session.pusher_ws.sent[0] == struct.pack('<I', 103) + b'conv-1'
    assert not await session.request_recording_close('conv-1')


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('status', ['completed', 'processing'])
async def test_cloud_tasks_poll_notifies_before_waiting_for_successor(monkeypatch, enabled, status):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', str(enabled).lower())
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    entered, release = asyncio.Event(), asyncio.Event()
    state = SimpleNamespace(active=True, current_conversation_id='current', last_audio_received_time=None)
    row = {'id': 'current', 'status': status}
    notify = AsyncMock(return_value=False)
    host = SimpleNamespace(
        state=state,
        request=SimpleNamespace(uid='test-owner'),
        wait=AsyncMock(return_value=False),
        persistence=SimpleNamespace(call=AsyncMock(return_value=row)),
        conversation_creation_timeout=120,
        request_recording_close=notify,
    )
    controller = LiveConversationController(host)
    monkeypatch.setattr(conversation_module, 'poll_calendar', AsyncMock())

    async def successor(**kwargs):
        entered.set()
        await release.wait()
        state.active = False

    controller.create_new_in_progress_conversation = successor
    polling = asyncio.create_task(controller.lifecycle_loop())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert notify.await_count == int(enabled)
        assert state.current_conversation_id == 'current'
    finally:
        release.set()
        await asyncio.wait_for(polling, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_cloud_tasks_close_signal_is_sent_for_completed_row(monkeypatch, enabled):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', str(enabled).lower())
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    notify = AsyncMock(return_value=False)
    host = SimpleNamespace(
        state=SimpleNamespace(active=True, current_conversation_id='current', last_audio_received_time=None),
        request=SimpleNamespace(uid='test-owner'),
        wait=AsyncMock(side_effect=[False, True]),
        persistence=SimpleNamespace(call=AsyncMock(return_value={'id': 'current', 'status': 'completed'})),
        conversation_creation_timeout=120,
        request_recording_close=notify,
    )
    controller = LiveConversationController(host)
    monkeypatch.setattr(conversation_module, 'poll_calendar', AsyncMock())
    controller.create_new_in_progress_conversation = AsyncMock()
    await controller.lifecycle_loop()
    assert notify.await_count == int(enabled)
    controller.create_new_in_progress_conversation.assert_awaited_once_with(rollover=True)

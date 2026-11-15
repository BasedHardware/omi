"""Shipping defaults leave the experimental close boundary entirely unallocated."""

import asyncio
import struct
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config.record_audio import record_identity
from config.pusher_record import close_notify_enabled, close_fast_path_enabled, seal_wake_enabled
from routers import pusher
from routers.listen import conversations as conversation_module
from routers.listen.conversations import LiveConversationController
from tests.unit.test_audio_durable_outbox import inline_session, remote, Socket
from tests.unit.utils.test_listen_pusher_session import make_session, FakePusherWebSocket
from utils import listen_pusher_session, pusher_playback_coordinator


@pytest.mark.parametrize('value', [None, 'false', 'invalid'])
def test_shipping_switch_defaults_are_independent(monkeypatch, value):
    monkeypatch.delenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', raising=False)
    if value is not None:
        monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', value)
    monkeypatch.delenv('PUSHER_RECORD_CLOSE_FAST_PATH_ENABLED', raising=False)
    monkeypatch.delenv('PUSHER_RECORD_SEAL_WAKE_ENABLED', raising=False)
    assert not close_notify_enabled()
    assert close_fast_path_enabled() and seal_wake_enabled()


@pytest.fixture(scope='module')
def protocol_harness():
    # AsyncMock's first signature/spec inspection is shared setup, not work
    # performed by an audio drain. Each case still drives the real protocol.
    return SimpleNamespace(
        process=AsyncMock(),
        optional=SimpleNamespace(submit=Mock(return_value=True), wait_owner=AsyncMock()),
    )


@pytest.fixture
def legacy_session(inline_session, monkeypatch, ending, protocol_harness):
    client, path, _, projected = inline_session
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client.rows[path]['status'] = 'completed'
    _, job_id = record_identity('owner', 'conversation')
    job_path = ('batch_pipeline_prod_jobs', job_id)
    retry_at = time.time() + 900
    client.rows[job_path] = dict(
        owner_id='owner',
        conversation_id='conversation',
        state='record_pending',
        enqueued_at=time.time(),
        available_at=retry_at,
        record_intake_retry_at=retry_at,
    )
    monkeypatch.delenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', raising=False)
    monkeypatch.setattr(pusher, 'PusherCloseState', Mock(side_effect=AssertionError('disabled protocol allocated')))
    monkeypatch.setattr(
        listen_pusher_session, 'PendingClose', Mock(side_effect=AssertionError('disabled close allocated'))
    )
    monkeypatch.setattr(pusher, 'process_conversation_task', protocol_harness.process)
    # Optional worker behavior has its own blocked-discovery proof. Keep this
    # matrix focused on real receipt/token/seal/wake and durable marker writes.
    monkeypatch.setattr(pusher_playback_coordinator, 'coordinator', lambda: protocol_harness.optional)
    offered = []
    socket = FakePusherWebSocket()

    async def connect(*args, **kwargs):
        offered.append(kwargs)
        return socket

    binding = {'cid': 'conversation'}
    active = {'active': True}
    session = make_session(
        ws=socket,
        active_ref=active,
        config_overrides={'uid': 'owner', 'sample_rate': 16000},
        deps_overrides={'connect_to_pusher': connect, 'get_current_conversation_id': lambda: binding['cid']},
    )
    route = 'pusher' if ending == 'normal' else 'cloud_tasks'
    persist = AsyncMock(return_value={'route': route, 'job_id': 'job', 'dispatch_generation': 1})
    host = SimpleNamespace(
        request=SimpleNamespace(uid='owner'),
        speakers=None,
        persistence=SimpleNamespace(call=persist),
        client_kind='ios',
        request_recording_close=AsyncMock(side_effect=AssertionError('disabled notification called')),
        request_conversation_processing=session.request_conversation_processing,
    )
    monkeypatch.setattr(conversation_module, 'get_byok_keys', lambda: None)
    controller = LiveConversationController(host)
    controller.on_conversation_processing_started = Mock()
    return SimpleNamespace(
        client=client,
        path=path,
        projected=projected,
        job_path=job_path,
        offered=offered,
        socket=socket,
        binding=binding,
        active=active,
        session=session,
        host=host,
        controller=controller,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('ending', ['normal', 'rollover', 'disconnect', 'cloud_tasks'])
async def test_absent_notify_uses_existing_listener_and_pusher_close_paths(legacy_session, ending):
    harness = legacy_session
    session, host, controller = harness.session, harness.host, harness.controller
    client, path, projected = harness.client, harness.path, harness.projected
    socket, binding, active = harness.socket, harness.binding, harness.active
    await session.connect()
    assert 'record_close_protocol' not in harness.offered[0]
    assert session.pending_record_closes is None and session.record_close_boundaries is None
    assert session.record_boundary is None and session.deferred_record_closes is None
    session.audio_bytes_send(b'\x01\x00', 100)
    # Model an established stream: the pusher has its conversation header
    # before receiving the legacy finalizer. Keep the accepted tail below.
    await session._audio_bytes_flush()
    assert await controller.schedule_finalization('conversation')
    host.request_recording_close.assert_not_awaited()
    assert not await session.request_recording_close('conversation')
    if ending == 'rollover':
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed_successor():
            entered.set()
            await release.wait()
            binding['cid'] = 'successor'

        successor = asyncio.create_task(delayed_successor())
        await entered.wait()
        # A relay tick during persistence must neither freeze nor defer custody.
        assert not await session.request_recording_close('conversation')
        session.audio_bytes_send(b'\x02\x00', 101)
        await session._audio_bytes_flush()
        release.set()
        await successor
    else:
        session.audio_bytes_send(b'\x02\x00', 101)
    if ending == 'disconnect':
        active['active'] = False
        await session.close()
    else:
        await session._audio_bytes_flush()
    assert not session.pending_record_closes and not session.record_close_boundaries
    assert all(struct.unpack('<I', frame[:4])[0] != 104 for frame in socket.sent) if ending != 'normal' else True
    sock = Socket(socket.sent)
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1, record_close_protocol=2)
    assert all(struct.unpack('<I', frame[:4])[0] not in {204, 206} for frame in sock.sent)
    assert client.rows[path]['record_audio_closed'] and client.rows[path]['record_upload_sessions'] == {}
    assert b''.join(chunk['data'] for batch in projected for chunk in batch[0]) == b'\x01\x00\x02\x00'
    assert client.rows[harness.job_path]['available_at'] == 0
    pusher.PusherCloseState.assert_not_called()
    listen_pusher_session.PendingClose.assert_not_called()


@pytest.mark.asyncio
async def test_absent_notify_keeps_implicit_binding_lazy_until_flush(monkeypatch):
    monkeypatch.delenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', raising=False)
    binding = {'cid': 'X'}
    read_binding = Mock(side_effect=lambda: binding['cid'])
    socket = FakePusherWebSocket()
    session = make_session(
        ws=socket,
        config_overrides={'sample_rate': 16000},
        deps_overrides={'get_current_conversation_id': read_binding},
    )
    await session.connect()
    read_binding.reset_mock()
    pcm = b'\x01\x00\x02\x00'
    session.audio_bytes_send(pcm, 100)
    read_binding.assert_not_called()
    assert session.audio_runs[0].conversation_id is None
    binding['cid'] = 'Y'
    await session._audio_bytes_flush()
    read_binding.assert_called_once_with()
    assert socket.sent == [
        struct.pack('<I', 103) + b'Y',
        struct.pack('<Id', 101, 100 - len(pcm) / 32000) + pcm,
    ]
    await session.close()

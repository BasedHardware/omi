"""Real relay/parser/receipt/seal/wake with a yielding close-control transport."""

import asyncio
import json
import struct
import threading
import time

import pytest
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

from config.record_audio import record_identity
from database import record_audio
from routers import pusher
from tests.unit.test_audio_durable_outbox import inline_session, remote
from tests.unit.utils.test_listen_pusher_session import make_session, FakePusherWebSocket
from utils.pusher_protocol import AudioBackpressure
from utils.pusher_record_close import PusherCloseState, PendingClose
from utils.pusher_record_close import result_frame


@pytest.mark.asyncio
@pytest.mark.parametrize('rollover', [False, True])
@pytest.mark.parametrize('explicit_binding', [False, True])
async def test_yielding_close_cannot_overtake_accepted_tail_or_wake_intake(
    inline_session, monkeypatch, rollover, explicit_binding
):
    client, path, _, _ = inline_session
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client.rows[path]['status'] = 'completed'
    _, key = record_identity('owner', 'conversation')
    job = ('batch_pipeline_prod_jobs', key)
    available = time.time() + 900
    client.rows[job] = dict(
        owner_id='owner',
        conversation_id='conversation',
        state='record_pending',
        enqueued_at=time.time(),
        available_at=available,
        record_intake_retry_at=available,
    )
    server_input, listen_input = asyncio.Queue(), asyncio.Queue()
    preparing, release_prepare, read_entered, sealed = (asyncio.Event() for _ in range(4))
    release_read = threading.Event()
    loop = asyncio.get_running_loop()
    read = pusher.read_pcm
    payloads = []

    def held_read(*args):
        loop.call_soon_threadsafe(read_entered.set)
        assert release_read.wait(10)
        pcm = read(*args)
        payloads.append(pcm)
        return pcm

    monkeypatch.setattr(pusher, 'read_pcm', held_read)
    original_seal = record_audio.seal_record_audio

    def observe_seal(*args, **kwargs):
        result = original_seal(*args, **kwargs)
        if result is None:
            loop.call_soon_threadsafe(sealed.set)
        return result

    monkeypatch.setattr(record_audio, 'seal_record_audio', observe_seal)

    class Server:
        client_state = WebSocketState.CONNECTED

        async def accept(self):
            pass

        async def send_bytes(self, data):
            listen_input.put_nowait(data)

        async def receive_bytes(self):
            data = await server_input.get()
            if data is None:
                raise WebSocketDisconnect(1000)
            return data

        async def close(self, **kwargs):
            self.client_state = WebSocketState.DISCONNECTED

    class ListenSocket:
        async def send(self, data):
            if struct.unpack('<I', data[:4])[0] == 104 and json.loads(data[4:])['phase'] == 'prepare':
                preparing.set()
                await release_prepare.wait()
            server_input.put_nowait(data)

        async def recv(self):
            return await listen_input.get()

    active = {'active': True}
    binding = {'cid': 'conversation'}
    session = make_session(
        ws=ListenSocket(),
        current_conversation_id='conversation',
        active_ref=active,
        config_overrides={'uid': 'owner', 'sample_rate': 16000, 'max_audio_buffer_size': 128},
        deps_overrides={'get_current_conversation_id': lambda: binding['cid']},
    )
    handler = asyncio.create_task(
        pusher._websocket_util_trigger(Server(), 'owner', 16000, audio_custody=1, record_close_protocol=2)
    )
    await session.connect()
    receiver = asyncio.create_task(session.pusher_receive())
    binding_kw = {'conversation_id': 'conversation'} if explicit_binding else {}
    session.audio_bytes_send(b'\x01\x00' * 2, 100, **binding_kw)
    await session.request_recording_close('conversation')  # Starts waiting for capability.
    try:
        await asyncio.wait_for(preparing.wait(), 5)
        # The close-control send is suspended; this run IS accepted by listen.
        session.audio_bytes_send(b'\x02\x00' * 2, 101, **binding_kw)
        assert session.audio_total_size == 8
        assert not client.rows[path].get('record_audio_closed')
        assert client.rows[job]['available_at'] == available
        release_prepare.set()
        for _ in range(1000):
            if session.pending_record_closes['conversation'].prepared:
                break
            await asyncio.sleep(0.001)
        if rollover:
            binding['cid'] = 'next'
        await session.request_recording_close('conversation')
        await asyncio.wait_for(read_entered.wait(), 5)
        assert not sealed.is_set()
        assert client.rows[path]['record_upload_sessions']
        assert client.rows[job]['available_at'] == available
        with pytest.raises(AudioBackpressure):
            session.audio_bytes_send(b'\x03\x00', 102, conversation_id='conversation')
        release_read.set()
        await asyncio.wait_for(sealed.wait(), 5)
        assert b''.join(payloads) == b'\x01\x00' * 2 + b'\x02\x00' * 2
        assert client.rows[path]['record_audio_closed']
        assert client.rows[job]['available_at'] == 0
    finally:
        release_prepare.set()
        release_read.set()
        active['active'] = False
        receiver.cancel()
        await asyncio.gather(receiver, return_exceptions=True)
        server_input.put_nowait(None)
        await asyncio.wait_for(handler, 5)


def test_close_capacity_idempotence_watermark_and_uncommitted_fence():
    state = PusherCloseState(True)
    state.audio('c', 4)
    assert state.prepare('c', 'request', set()) == ('prepared', 4)
    state.audio('c', 4)
    assert state.prepare('c', 'request', set()) == ('prepared', 4)
    assert state.blocks('c', True) and state.blocks('c', False)
    assert state.commit('c', 'request', 10) == 'watermark_pending'
    assert state.commit('c', 'request', 8) == 'accepted'
    assert state.commit('c', 'request', 8) == 'accepted'
    assert not state.blocks('c', True)
    assert state.prepare('new', 'other', {str(i) for i in range(128)}) == ('capacity', 0)


@pytest.mark.asyncio
async def test_local_capacity_never_sends_an_unretained_close():
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, config_overrides={'max_pending_requests': 1})
    await session.connect()
    session.record_close_supported = True
    session.pending_record_closes['other'] = PendingClose()
    assert not await session.request_recording_close('new')
    assert set(session.pending_record_closes) == {'other'}
    assert not ws.sent


@pytest.mark.asyncio
async def test_disconnect_before_commit_preserves_the_prepared_producer(inline_session):
    client, path, _, _ = inline_session
    from tests.unit.test_audio_durable_outbox import Socket, _audio_frames

    prepare = (
        struct.pack('<I', 104)
        + json.dumps(
            dict(
                conversation_id='conversation',
                request_id='request',
                record_close_only=True,
                phase='prepare',
                watermark=0,
            )
        ).encode()
    )
    await pusher._websocket_util_trigger(
        Socket(_audio_frames('conversation', [b'\x01\x00']) + [prepare]),
        'owner',
        16000,
        audio_custody=1,
        record_close_protocol=2,
    )
    assert client.rows[path]['record_upload_sessions']
    assert not client.rows[path]['record_audio_closed']


@pytest.mark.asyncio
async def test_capacity_lost_ack_and_reconnect_retain_exact_close_until_acceptance():
    active = {'active': True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active)
    await session.connect()
    session.record_close_supported = True
    await session.request_recording_close('conv-1')
    close = session.pending_record_closes['conv-1']
    request_id = close.request_id

    async def deliver(socket, phase, status, watermark=0, ticket=request_id):
        active['active'] = True
        socket.incoming.append(result_frame('conv-1', ticket, phase, status, watermark))
        socket.on_recv = lambda: active.update(active=False)
        await session.pusher_receive()

    await deliver(ws, 'prepare', 'capacity')
    assert not close.prepared and 'conv-1' in session.pending_record_closes
    await session.request_recording_close('conv-1')
    await deliver(ws, 'prepare', 'prepared')
    await session.request_recording_close('conv-1')
    assert close.frozen and 'conv-1' in session.pending_record_closes
    await session.request_recording_close('conv-1')  # Lost ACK: idempotent retransmit.
    assert json.loads(ws.sent[-1][4:]) == json.loads(ws.sent[-2][4:])
    replacement = FakePusherWebSocket()
    session.pusher_ws = replacement
    session.pusher_connected = True
    await session.request_recording_close('conv-1')
    assert close.request_id == request_id and not close.prepared and close.frozen
    await deliver(replacement, 'commit', 'accepted', ticket='stale')
    assert 'conv-1' in session.pending_record_closes
    await deliver(replacement, 'prepare', 'prepared')
    await session.request_recording_close('conv-1')
    await deliver(replacement, 'commit', 'accepted')
    assert not session.pending_record_closes
    assert 'conv-1' in session.record_close_boundaries


@pytest.mark.asyncio
async def test_yielding_final_commit_refuses_new_input_before_acceptance():
    entered, release = asyncio.Event(), asyncio.Event()

    class Socket(FakePusherWebSocket):
        async def send(self, data):
            if struct.unpack('<I', data[:4])[0] == 104 and json.loads(data[4:])['phase'] == 'commit':
                entered.set()
                await release.wait()
            await super().send(data)

    socket = Socket()
    session = make_session(ws=socket)
    await session.connect()
    session.record_close_supported = True
    await session.request_recording_close('conv-1')
    session.pending_record_closes['conv-1'].prepared = True
    sending = asyncio.create_task(session.request_recording_close('conv-1'))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        with pytest.raises(AudioBackpressure):
            session.audio_bytes_send(b'new', 100, conversation_id='conv-1')
        assert not session.audio_runs and not session.audio_total_size
        assert 'conv-1' in session.pending_record_closes
    finally:
        release.set()
        await sending


@pytest.mark.asyncio
async def test_nondurable_relay_never_negotiates_fast_close(monkeypatch):
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'false')
    offered = []

    async def connect(uid, rate, **kwargs):
        offered.append(kwargs)
        return FakePusherWebSocket()

    session = make_session(deps_overrides={'connect_to_pusher': connect})
    await session.connect()
    assert 'record_close_protocol' not in offered[0]
    session.record_close_supported = True  # Even a spurious/stale capability is insufficient.
    assert not await session.request_recording_close('conv-1')
    assert not session.pending_record_closes

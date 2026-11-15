"""Real relay/parser/receipt/seal/wake with a yielding close-control transport."""

import asyncio
import json
import struct
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from routers.listen.receiver import ListenReceiver

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


@pytest.fixture(autouse=True)
def staged_protocol_opt_in(monkeypatch):
    # Experimental handshake proofs opt in explicitly; shipping defaults are off.
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', 'true')
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')


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
    unlinked = asyncio.Event()
    unlinked_receipts = []
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
            if struct.unpack('<I', data[:4])[0] == 203:
                receipt = json.loads(data[4:])['receipt']
                if not receipt.get('conversation_id'):
                    unlinked_receipts.append(receipt)
                    unlinked.set()
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
        deps_overrides={
            'get_current_conversation_id': lambda: binding['cid'],
            'finish_recording_audio': AsyncMock(side_effect=lambda cid: binding['cid'] != cid),
        },
    )
    handler = asyncio.create_task(
        pusher._websocket_util_trigger(Server(), 'owner', 16000, audio_custody=1, record_close_protocol=3)
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
        assert session.pending_record_closes['conversation'].prepared
        expected_pcm = b'\x01\x00' * 2 + b'\x02\x00' * 2
        if rollover:
            # Finalization has prepared X, but successor persistence has not
            # switched the live binding. Exercise the actual receiver's generic
            # exception boundary, rather than calling audio_bytes_send alone.
            frames, accepted = asyncio.Queue(), asyncio.Event()
            state = SimpleNamespace(
                active=True,
                close_code=1001,
                current_conversation_id='conversation',
                last_audio_received_time=None,
                last_activity_time=None,
                first_audio_byte_timestamp=None,
                last_usage_record_timestamp=None,
                audio_ring_buffer=None,
            )
            count = 0

            def accept_frame(*args, **kwargs):
                nonlocal count
                session.audio_bytes_send(*args, **kwargs)
                count += 1
                if count == 2:
                    accepted.set()

            host = SimpleNamespace(
                state=state,
                request=SimpleNamespace(
                    websocket=SimpleNamespace(receive=frames.get),
                    uid='owner',
                    codec='pcm16',
                    sample_rate=16000,
                ),
                limits=SimpleNamespace(ws_receive_timeout=5),
                is_multi_channel=False,
                use_custom_stt=True,
                frame_size=320,
                audio_bytes_send=accept_frame,
                transcripts=SimpleNamespace(enqueue=lambda _: None),
                start_live_transcription=lambda: None,
            )
            live_receiver = ListenReceiver(host, [], {})
            live_receiver.raw_archive = SimpleNamespace(append=AsyncMock(), close=AsyncMock())
            receiving = asyncio.create_task(live_receiver.receive_data())
            successor_persisted = asyncio.Event()

            async def create_successor():
                await successor_persisted.wait()  # Inject persistence latency.
                binding['cid'] = state.current_conversation_id = 'next'

            successor = asyncio.create_task(create_successor())
            try:
                for _ in range(3):  # Several relay ticks during slow successor creation.
                    await session.request_recording_close('conversation')
                    assert not session.pending_record_closes['conversation'].frozen
                for sample in (4, 5):
                    frames.put_nowait({'bytes': bytes((sample, 0)) * 2})
                await asyncio.wait_for(accepted.wait(), 5)
                assert state.active and state.close_code == 1001 and not receiving.done()
                assert not sealed.is_set() and client.rows[path]['record_upload_sessions']
                successor_persisted.set()
                await successor
            finally:
                successor_persisted.set()
                await successor
                frames.put_nowait({'type': 'websocket.disconnect', 'code': 1000})
                await asyncio.wait_for(receiving, 5)
            assert count == 2 and state.close_code == 1000
            expected_pcm += b'\x04\x00' * 2 + b'\x05\x00' * 2
        binding['cid'] = 'next' if rollover else None
        await session.request_recording_close('conversation')
        await asyncio.wait_for(read_entered.wait(), 5)
        assert not sealed.is_set()
        assert client.rows[path]['record_upload_sessions']
        assert client.rows[job]['available_at'] == available
        with pytest.raises(AudioBackpressure):
            session.audio_bytes_send(b'\x03\x00', 102, conversation_id='conversation')
        release_read.set()
        await asyncio.wait_for(sealed.wait(), 5)
        assert b''.join(payloads) == expected_pcm
        assert client.rows[path]['record_audio_closed']
        assert client.rows[job]['available_at'] == 0
        # The same socket must remain usable for audio between conversations.
        binding['cid'] = None
        session.audio_bytes_send(b'\x03\x00', 102)
        await session._audio_bytes_flush()
        binding['cid'] = 'next'
        await session._audio_bytes_flush()  # Flush the unlinked custody window.
        await asyncio.wait_for(unlinked.wait(), 5)
        from utils.other.audio_outbox import AudioReceipt

        assert read('owner', AudioReceipt(**unlinked_receipts[-1])) == b'\x03\x00'
        assert not handler.done() and client.rows[path]['record_audio_closed']
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
    assert state.commit('c', 'request', 3) == 'invalid_watermark'
    assert state.commit('c', 'request', 10) == 'watermark_pending'
    assert state.commit('c', 'request', 8) == 'accepted'
    assert state.commit('c', 'request', 8) == 'accepted'
    assert not state.blocks('c', True)
    assert state.prepare('new', 'other', {str(i) for i in range(128)}) == ('capacity', 0)


@pytest.mark.asyncio
async def test_local_capacity_never_sends_an_unretained_close(monkeypatch):
    fallback = Mock()
    monkeypatch.setattr('utils.listen_pusher_session.record_fallback', fallback)
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, config_overrides={'max_pending_requests': 1})
    await session.connect()
    session.record_close_supported = True
    session.pending_record_closes['other'] = PendingClose()
    assert not await session.request_recording_close('new')
    assert set(session.pending_record_closes) == {'other'}
    assert not ws.sent
    assert fallback.call_args.kwargs['reason'] == 'capacity_full'


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
        record_close_protocol=3,
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
        active['active'] = True  # The fixture stopped the pump, not the live session.

    await deliver(ws, 'prepare', 'capacity')
    assert not close.prepared and 'conv-1' in session.pending_record_closes
    await session.request_recording_close('conv-1')
    await deliver(ws, 'prepare', 'prepared')
    session.deps.get_current_conversation_id = lambda: 'next'
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
    session.deps.get_current_conversation_id = lambda: 'next'
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


def test_terminal_wire_state_reclaims_slots_and_preserves_recent_idempotence():
    state = PusherCloseState(True)
    for i in range(150):
        cid = f'c-{i}'
        state.audio(cid, 2)
        assert state.prepare(cid, cid, set()) == ('prepared', 2)
        assert state.commit(cid, cid, 2) == 'accepted'
        state.retire(cid)
        assert not state.requests and not state.received and not state.watermarks
        assert len(state.completed) <= 128 and len(state.committed) <= 128
        assert state.commit(cid, cid, 2) == 'accepted'
    assert state.prepare('uncommitted', 'r', set()) == ('prepared', 0)
    state.retire('uncommitted')
    assert state.blocks('uncommitted', False)
    assert state.prepare('c-0', 'new', set()) == ('prepared', 0)
    assert state.blocks('c-0', True)  # Evicted history must acquire/prove a new close.


# A full day on one live relay: keep the fast lane's state-machine proof above,
# and run this real receipt/token/seal stress proof in the explicit slow suite.
@pytest.mark.slow
@pytest.mark.asyncio
async def test_150_sequential_closes_share_one_socket_and_bound_terminal_state(inline_session, monkeypatch):
    await _sequential_closes(inline_session, monkeypatch, total=150, limit=100)


@pytest.mark.asyncio
async def test_production_retirement_survives_more_closes_than_wire_capacity(inline_session, monkeypatch):
    from utils import pusher_record_close

    monkeypatch.setattr(pusher_record_close, 'MAX_CLOSES', 2)
    await _sequential_closes(inline_session, monkeypatch, total=5, limit=2)


async def _sequential_closes(inline_session, monkeypatch, *, total, limit):
    client, path, _, _ = inline_session
    incoming, replies = asyncio.Queue(), asyncio.Queue()
    active = {'active': True}
    binding = {'cid': None}
    states = []
    original_state = pusher.PusherCloseState

    def state_factory(*args):
        state = original_state(*args)
        states.append(state)
        return state

    monkeypatch.setattr(pusher, 'PusherCloseState', state_factory)

    class Server:
        client_state = WebSocketState.CONNECTED

        async def accept(self):
            pass

        async def send_bytes(self, data):
            replies.put_nowait(data)

        async def receive_bytes(self):
            data = await incoming.get()
            if data is None:
                raise WebSocketDisconnect(1000)
            return data

        async def close(self, **kwargs):
            self.client_state = WebSocketState.DISCONNECTED

    class Relay:
        async def send(self, data):
            incoming.put_nowait(data)

        async def recv(self):
            return await replies.get()

    session = make_session(
        ws=Relay(),
        active_ref=active,
        config_overrides={'uid': 'owner', 'sample_rate': 16000, 'max_pending_requests': limit},
        deps_overrides={
            'get_current_conversation_id': lambda: binding['cid'],
            'finish_recording_audio': AsyncMock(side_effect=lambda cid: binding['cid'] != cid),
        },
    )
    handler = asyncio.create_task(
        pusher._websocket_util_trigger(Server(), 'owner', 16000, audio_custody=1, record_close_protocol=3)
    )
    await session.connect()
    receiver = asyncio.create_task(session.pusher_receive())
    try:
        for i in range(total):
            cid = f'close-{i}'
            row_path = (*path[:-1], cid)
            client.rows[row_path] = {'record_lane_owner': 'batch_live_v1', 'status': 'completed'}
            binding['cid'] = cid
            # Real accepted PCM, receipt readback and producer proof for every close.
            session.audio_bytes_send(b'\x01\x00', 100 + i)
            await session.request_recording_close(cid)
            binding['cid'] = None  # Successor/detach before the final close boundary.
            async with asyncio.timeout(10):
                while not session.record_close_supported:
                    await asyncio.sleep(0.001)
                while cid not in session.record_close_boundaries or not client.rows[row_path].get(
                    'record_audio_closed'
                ):
                    await session.request_recording_close(cid)
                    await asyncio.sleep(0.001)
            assert not session.pending_record_closes
            assert len(session.record_close_boundaries) <= limit
            assert len(states[0].requests) <= 1 and len(states[0].received) <= 1
            assert len(states[0].completed) <= 128 and len(states[0].committed) <= 129
        with pytest.raises(AudioBackpressure):
            session.audio_bytes_send(b'late', 1000, conversation_id='close-0')
        assert not session.audio_runs
        assert not handler.done()
    finally:
        active['active'] = False
        receiver.cancel()
        await asyncio.gather(receiver, return_exceptions=True)
        incoming.put_nowait(None)
        await asyncio.wait_for(handler, 10)


@pytest.mark.asyncio
@pytest.mark.parametrize('frozen', [False, True])
async def test_unsupported_close_is_terminal_until_reconnect(monkeypatch, frozen):
    fallback = Mock()
    monkeypatch.setattr('utils.listen_pusher_session.record_fallback', fallback)
    active = {'active': True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active)
    await session.connect()
    session.record_close_supported = True
    await session.request_recording_close('conv-1')
    close = session.pending_record_closes['conv-1']
    close.frozen = frozen
    ws.incoming.append(result_frame('conv-1', close.request_id, 'commit' if frozen else 'prepare', 'unsupported'))
    ws.on_recv = lambda: active.update(active=False)
    await session.pusher_receive()
    active['active'] = True
    assert not session.pending_record_closes
    assert not session.record_close_supported
    assert fallback.call_args.kwargs['reason'] == 'capability_mismatch'
    before = len(ws.sent)
    for cid in ['conv-1', 'next', 'later']:
        assert not await session.request_recording_close(cid)
    assert len(ws.sent) == before and not session.pending_record_closes
    if frozen:
        with pytest.raises(AudioBackpressure):
            session.audio_bytes_send(b'late', 100)
    replacement = FakePusherWebSocket()
    session.pusher_ws, session.pusher_connected, session.record_close_supported = replacement, True, True
    await session.request_recording_close('next')
    assert 'next' in session.pending_record_closes and replacement.sent


@pytest.mark.asyncio
async def test_evicted_lost_ack_reprepares_fresh_baseline_without_unfreezing():
    active = {'active': True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active)
    await session.connect()
    session.record_close_supported = True
    await session.request_recording_close('conv-1')
    close = session.pending_record_closes['conv-1']
    close.prepared, close.frozen, close.base, close.sent = True, True, 10, 4
    ws.incoming.append(result_frame('conv-1', close.request_id, 'commit', 'unknown'))
    ws.on_recv = lambda: active.update(active=False)
    await session.pusher_receive()
    active['active'] = True
    assert close.frozen and not close.prepared
    await session.request_recording_close('conv-1')
    assert close.frozen and close.base == 0 and close.sent == 0
    control = json.loads(ws.sent[-1][4:])
    assert control['phase'] == 'prepare' and control['watermark'] == 0
    with pytest.raises(AudioBackpressure):
        session.audio_bytes_send(b'late', 100)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'status,reason',
    [
        ('capacity', 'capacity_full'),
        ('invalid_watermark', 'usage_fence_blocked'),
        ('producer_unavailable', 'usage_fence_blocked'),
        ('conflict', 'usage_fence_blocked'),
        ('unknown', 'local_heal'),
    ],
)
async def test_close_refusal_fallback_is_bounded_per_pending_request(monkeypatch, status, reason):
    fallback = Mock()
    monkeypatch.setattr('utils.listen_pusher_session.record_fallback', fallback)
    active = {'active': True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active)
    await session.connect()
    session.record_close_supported = True
    await session.request_recording_close('conv-1')
    close = session.pending_record_closes['conv-1']
    for _ in range(3):
        close.socket = ws
        active['active'] = True
        ws.incoming.append(result_frame('conv-1', close.request_id, 'prepare', status))
        ws.on_recv = lambda: active.update(active=False)
        await session.pusher_receive()
    assert fallback.call_count == 1
    assert fallback.call_args.kwargs['reason'] == reason
    assert fallback.call_args.kwargs['outcome'] == 'degraded'
    assert 'conv-1' in session.pending_record_closes

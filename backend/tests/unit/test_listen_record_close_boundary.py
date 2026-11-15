"""Real receiver interleavings at the archive/relay recording boundary."""

import asyncio
import json
import struct
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

from routers import pusher
from routers.listen.receiver import ListenReceiver
from tests.unit.test_audio_durable_outbox import inline_session, remote
from utils.audio_timeline import CaptureTimeline
from tests.unit.utils.test_listen_pusher_session import FakePusherWebSocket, make_session


@pytest.fixture(params=[False, True], ids=["clockless", "capture-clock"])
def boundary_receiver(monkeypatch, request):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', 'true')
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    frames = asyncio.Queue()
    state = SimpleNamespace(
        active=True,
        close_code=1001,
        current_conversation_id='first',
        last_audio_received_time=None,
        last_activity_time=None,
        first_audio_byte_timestamp=None,
        last_usage_record_timestamp=None,
        audio_ring_buffer=None,
    )
    socket = FakePusherWebSocket()
    session = make_session(
        ws=socket,
        config_overrides={'max_audio_buffer_size': 128},
        deps_overrides={
            'get_current_conversation_id': lambda: state.current_conversation_id,
            'is_active': lambda: state.active,
        },
    )
    host = SimpleNamespace(
        state=state,
        request=SimpleNamespace(
            websocket=SimpleNamespace(receive=frames.get), uid='test-owner', codec='pcm16', sample_rate=8000
        ),
        limits=SimpleNamespace(ws_receive_timeout=5),
        is_multi_channel=False,
        use_custom_stt=True,
        frame_size=320,
        audio_bytes_send=session.audio_bytes_send,
        pusher_audio_session=session,
        transcripts=SimpleNamespace(enqueue=lambda _: None),
        start_live_transcription=lambda: None,
    )
    receiver = ListenReceiver(host, [], {})
    if request.param:
        receiver.capture_timeline = CaptureTimeline(sample_rate=8000)
        receiver.capture_timeline_spans = True
        state.conversation_sample_ranges = deque()
        state.conversation_capture_origins = {}
        state.conversations_awaiting_capture_origin = set()
        state.source_position_map = None
    receiver.raw_archive = SimpleNamespace(append=AsyncMock(), close=AsyncMock(), finish_recording=AsyncMock())
    # The fallback lets the regression run against the unfixed source as well.
    session.deps.finish_recording_audio = getattr(receiver, 'finish_recording_audio', AsyncMock(return_value=True))
    return SimpleNamespace(frames=frames, state=state, socket=socket, session=session, receiver=receiver)


def controls(socket):
    return [json.loads(data[4:]) for data in socket.sent if struct.unpack('<I', data[:4])[0] == 104]


@pytest.mark.asyncio
async def test_paused_archive_frame_keeps_original_owner_and_blocks_close(boundary_receiver):
    h = boundary_receiver
    entered, release, accepted = (asyncio.Event() for _ in range(3))
    archived = []

    async def append(raw, owner, *args, **kwargs):
        archived.append((owner, raw))
        entered.set()
        await release.wait()

    h.receiver.raw_archive.append.side_effect = append

    def accept(*args, **kwargs):
        h.session.audio_bytes_send(*args, **kwargs)
        accepted.set()

    h.receiver.host.audio_bytes_send = accept
    await h.session.connect()
    h.session.record_close_supported = True
    h.frames.put_nowait({'bytes': b'\x01\x00' * 2})
    receiving = asyncio.create_task(h.receiver.receive_data())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await h.session.request_recording_close('first')
        h.session.pending_record_closes['first'].prepared = True
        h.state.current_conversation_id = 'second'
        await h.session.request_recording_close('first')
        assert all(control['phase'] != 'commit' for control in controls(h.socket))
        release.set()
        await asyncio.wait_for(accepted.wait(), 1)
        await h.session.request_recording_close('first')
        assert controls(h.socket)[-1]['phase'] == 'commit'
        assert controls(h.socket)[-1]['watermark'] == 4
        assert archived == [('first', b'\x01\x00' * 2)]
        assert b'first' in [data[4:] for data in h.socket.sent if struct.unpack('<I', data[:4])[0] == 103]
        assert h.state.active and h.state.close_code == 1001
    finally:
        release.set()
        h.frames.put_nowait({'type': 'websocket.disconnect', 'code': 1000})
        await asyncio.wait_for(receiving, 1)


@pytest.mark.asyncio
async def test_real_pusher_seals_only_after_source_frame_and_archive_drain(boundary_receiver, inline_session):
    h = boundary_receiver
    client, path, _, projected = inline_session
    first = (*path[:-1], 'first')
    client.rows[first] = {'record_lane_owner': 'batch_live_v1', 'status': 'completed'}
    h.session.config.uid = 'owner'
    incoming, replies = asyncio.Queue(), asyncio.Queue()
    entered, release, accepted, draining, drained = (asyncio.Event() for _ in range(5))

    async def append(*args, **kwargs):
        entered.set()
        await release.wait()

    async def archive_drain(_conversation_id):
        draining.set()
        await drained.wait()

    h.receiver.raw_archive.append.side_effect = append
    h.receiver.raw_archive.finish_recording.side_effect = archive_drain

    def accept(*args, **kwargs):
        h.session.audio_bytes_send(*args, **kwargs)
        accepted.set()

    h.receiver.host.audio_bytes_send = accept

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

    async def connect(*args, **kwargs):
        assert kwargs['record_close_protocol'] == 3
        return Relay()

    h.session.deps.connect_to_pusher = connect
    handler = asyncio.create_task(
        pusher._websocket_util_trigger(Server(), 'owner', 8000, audio_custody=1, record_close_protocol=3)
    )
    await h.session.connect()
    pump = asyncio.create_task(h.session.pusher_receive())
    receiving = asyncio.create_task(h.receiver.receive_data())
    closing = None
    try:
        h.frames.put_nowait({'bytes': b'\x01\x00' * 2})
        await asyncio.wait_for(entered.wait(), 1)
        await h.session.request_recording_close('first')
        async with asyncio.timeout(2):
            while not h.session.pending_record_closes['first'].prepared:
                await asyncio.sleep(0)
        # There is deliberately no successor: the source frame owns the tail.
        await h.session.request_recording_close('first')
        assert not client.rows[first].get('record_audio_closed')
        assert client.rows[first]['record_upload_sessions']
        release.set()
        await asyncio.wait_for(accepted.wait(), 1)
        closing = asyncio.create_task(h.session.request_recording_close('first'))
        await asyncio.wait_for(draining.wait(), 1)
        assert not client.rows[first].get('record_audio_closed')
        assert client.rows[first]['record_upload_sessions']
        drained.set()
        await closing
        async with asyncio.timeout(2):
            while not client.rows[first].get('record_audio_closed'):
                await asyncio.sleep(0)
        assert client.rows[first]['record_upload_sessions'] == {}
        assert b''.join(chunk['data'] for batch in projected for chunk in batch[0]) == b'\x01\x00' * 2
        assert h.state.active and not receiving.done() and not handler.done()
    finally:
        release.set()
        drained.set()
        if closing is not None:
            await closing
        h.frames.put_nowait({'type': 'websocket.disconnect', 'code': 1000})
        await asyncio.wait_for(receiving, 2)
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)
        incoming.put_nowait(None)
        await asyncio.wait_for(handler, 2)


@pytest.mark.asyncio
async def test_close_finishes_without_successor_and_keeps_receiver_open(boundary_receiver):
    h = boundary_receiver
    entered, release, accepted = (asyncio.Event() for _ in range(3))

    async def append(*args, **kwargs):
        entered.set()
        await release.wait()

    h.receiver.raw_archive.append.side_effect = append

    def accept(*args, **kwargs):
        h.session.audio_bytes_send(*args, **kwargs)
        accepted.set()

    h.receiver.host.audio_bytes_send = accept
    await h.session.connect()
    h.session.record_close_supported = True
    h.frames.put_nowait({'bytes': b'\x02\x00' * 2})
    receiving = asyncio.create_task(h.receiver.receive_data())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await h.session.request_recording_close('first')
        h.session.pending_record_closes['first'].prepared = True
        await h.session.request_recording_close('first')
        assert controls(h.socket)[-1]['phase'] == 'prepare'
        release.set()
        await asyncio.wait_for(accepted.wait(), 1)
        await h.session.request_recording_close('first')
        assert controls(h.socket)[-1]['phase'] == 'commit'
        assert h.state.current_conversation_id == 'first'  # No successor was created.
        accepted.clear()
        h.frames.put_nowait({'bytes': b'\x03\x00' * 2})
        await asyncio.wait_for(accepted.wait(), 1)
        assert h.session.audio_runs[-1].conversation_id is None
        assert h.state.active and h.state.close_code == 1001 and not receiving.done()
    finally:
        release.set()
        h.frames.put_nowait({'type': 'websocket.disconnect', 'code': 1000})
        await asyncio.wait_for(receiving, 1)

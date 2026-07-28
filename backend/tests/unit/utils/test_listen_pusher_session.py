import asyncio
import json
import struct

import pytest

import utils.listen_pusher_session as listen_pusher_module
from utils.listen_pusher_session import (
    TARGET_SAMPLE_RATE,
    ListenPusherSession,
    ListenPusherSessionConfig,
    ListenPusherSessionDeps,
)


class FakePusherWebSocket:
    def __init__(self, incoming=None, *, ack_supported=False):
        self.sent = []
        self.incoming = list(incoming or [])
        self.closed_codes = []
        self.on_recv = None
        self.response_headers = {'X-Omi-Delivery-Ack': '1'} if ack_supported else {}

    async def send(self, data):
        self.sent.append(bytes(data))

    async def recv(self):
        if self.on_recv:
            self.on_recv()
        if self.incoming:
            return self.incoming.pop(0)
        await asyncio.sleep(10)

    async def close(self, code=1000):
        self.closed_codes.append(code)


class FailFirstFrameWebSocket(FakePusherWebSocket):
    def __init__(self, failing_frame_type: int, *, block_failure: bool = False):
        super().__init__()
        self.failing_frame_type = failing_frame_type
        self.block_failure = block_failure
        self.failure_started = asyncio.Event()
        self.release_failure = asyncio.Event()
        self.failed = False

    async def send(self, data):
        frame = bytes(data)
        if frame_type(frame) == self.failing_frame_type and not self.failed:
            self.failed = True
            self.failure_started.set()
            if self.block_failure:
                await self.release_failure.wait()
            raise RuntimeError(f"failed frame {self.failing_frame_type}")
        self.sent.append(frame)


class DeliverThenFailFirstFrameWebSocket(FakePusherWebSocket):
    def __init__(self, failing_frame_type: int):
        super().__init__()
        self.failing_frame_type = failing_frame_type
        self.failed = False

    async def send(self, data):
        frame = bytes(data)
        self.sent.append(frame)
        if frame_type(frame) == self.failing_frame_type and not self.failed:
            self.failed = True
            raise RuntimeError(f"ambiguous frame {self.failing_frame_type}")


class BlockingConnectionClosedWebSocket(FakePusherWebSocket):
    def __init__(self, operation: str):
        super().__init__()
        self.operation = operation
        self.failure_started = asyncio.Event()
        self.release_failure = asyncio.Event()

    async def recv(self):
        if self.operation == "recv":
            self.failure_started.set()
            await self.release_failure.wait()
            raise ControlledConnectionClosed()
        return await super().recv()

    async def send(self, data):
        if self.operation == "send":
            self.failure_started.set()
            await self.release_failure.wait()
            raise ControlledConnectionClosed()
        await super().send(data)


class ControlledConnectionClosed(Exception):
    pass


def frame_type(frame: bytes) -> int:
    return struct.unpack("I", frame[:4])[0]


def frame_json(frame: bytes):
    return json.loads(frame[4:].decode("utf-8"))


def response_201(conversation_id: str, success=True):
    payload = json.dumps({"conversation_id": conversation_id, "success": success}).encode("utf-8")
    return struct.pack("<I", 201) + payload


def error_response_201(conversation_id: str, terminal: bool = False):
    payload = json.dumps(
        {"conversation_id": conversation_id, "error": "processing_failed", "terminal": terminal}
    ).encode("utf-8")
    return struct.pack("<I", 201) + payload


def fenced_response_201(conversation_id: str):
    payload = json.dumps({"conversation_id": conversation_id, "fenced": True}).encode("utf-8")
    return struct.pack("<I", 201) + payload


def response_202(kind: str, delivery_id: str):
    payload = json.dumps({"kind": kind, "delivery_id": delivery_id}).encode("utf-8")
    return struct.pack("<I", 202) + payload


@pytest.fixture
def anyio_backend():
    return "asyncio"


def make_session(
    *,
    ws=None,
    current_conversation_id="conv-1",
    active_ref=None,
    config_overrides=None,
    deps_overrides=None,
    connect_calls=None,
):
    active_ref = active_ref if active_ref is not None else {"active": True}
    config_values = {
        "uid": "uid-1",
        "session_id": "session-1",
        "sample_rate": 8000,
        "is_multi_channel": False,
        "language": "en",
        "audio_bytes_enabled": True,
        "max_segment_buffer_size": 3,
        "max_audio_buffer_size": 8,
        "max_pending_requests": 3,
        "max_pending_speaker_sample_requests": 2,
    }
    if config_overrides:
        config_values.update(config_overrides)

    async def connect_to_pusher(uid, sample_rate, retries=5, is_active=None):
        if connect_calls is not None:
            connect_calls.append((uid, sample_rate, retries, is_active))
        return ws or FakePusherWebSocket()

    async def wait_for_event(event, timeout):
        return False

    callbacks = []
    deps_values = {
        "get_current_conversation_id": lambda: current_conversation_id,
        "is_active": lambda: active_ref["active"],
        "shutdown_event": asyncio.Event(),
        "get_byok_keys": lambda: {"openai": "key"},
        "on_conversation_processed": callbacks.append,
        "wait_for_event": wait_for_event,
        "connect_to_pusher": connect_to_pusher,
        "sleep": asyncio.sleep,
        "random": lambda: 0.5,
        "now": lambda: 1000.0,
        "monotonic": lambda: 2000.0,
    }
    if deps_overrides:
        deps_values.update(deps_overrides)

    session = ListenPusherSession(ListenPusherSessionConfig(**config_values), ListenPusherSessionDeps(**deps_values))
    session.callbacks = callbacks
    return session


@pytest.mark.anyio
async def test_frame_payloads_and_order():
    ws = FakePusherWebSocket()
    session = make_session(ws=ws)
    await session.connect()

    session.audio_bytes_send(b"abcd", received_at=100.0)
    await session._audio_bytes_flush()
    session.transcript_send([{"id": "seg-1", "text": "hello"}])
    await session._transcript_flush()
    await session.request_conversation_processing("conv-1")
    await session.send_speaker_sample_request("person-1", "conv-1", ["seg-1"])

    active_ref = {"active": True}

    async def wait_for_event(event, timeout):
        if active_ref["active"]:
            active_ref["active"] = False
            return False
        return True

    session.deps.wait_for_event = wait_for_event
    session.deps.is_active = lambda: active_ref["active"]
    await session.pusher_heartbeat()

    assert [frame_type(frame) for frame in ws.sent] == [103, 101, 102, 104, 105, 100]
    assert ws.sent[0][4:].decode("utf-8") == "conv-1"
    timestamp = struct.unpack("d", ws.sent[1][4:12])[0]
    assert timestamp == 100.0 - (4 / (8000 * 2))
    assert ws.sent[1][12:] == b"abcd"
    transcript_payload = frame_json(ws.sent[2])
    assert transcript_payload["segments"] == [{"id": "seg-1", "text": "hello"}]
    assert transcript_payload["memory_id"] == "conv-1"
    assert transcript_payload["delivery_id"]
    assert frame_json(ws.sent[3]) == {
        "conversation_id": "conv-1",
        "language": "en",
        "byok_keys": {"openai": "key"},
    }
    speaker_payload = frame_json(ws.sent[4])
    assert {key: speaker_payload[key] for key in ("person_id", "conversation_id", "segment_ids")} == {
        "person_id": "person-1",
        "conversation_id": "conv-1",
        "segment_ids": ["seg-1"],
    }
    assert speaker_payload["delivery_id"]


@pytest.mark.anyio
@pytest.mark.parametrize(("operation", "session_method"), [("recv", "pusher_receive"), ("send", "pusher_heartbeat")])
async def test_stale_socket_failure_does_not_disconnect_replacement(monkeypatch, operation, session_method):
    monkeypatch.setattr(listen_pusher_module, "ConnectionClosed", ControlledConnectionClosed)
    active_ref = {"active": True}
    old_ws = BlockingConnectionClosedWebSocket(operation)
    replacement_ws = FakePusherWebSocket()
    sockets = iter([old_ws, replacement_ws])

    async def connect_to_pusher(*_args, **_kwargs):
        return next(sockets)

    async def wait_for_event(_event, _timeout):
        return False

    session = make_session(
        active_ref=active_ref,
        deps_overrides={"connect_to_pusher": connect_to_pusher, "wait_for_event": wait_for_event},
    )
    await session.connect()
    if operation == "recv":
        session.pending_conversation_requests["blocked-old-socket"] = {
            "sent_at": session.deps.now(),
            "retries": 0,
        }
    operation_task = asyncio.create_task(getattr(session, session_method)())
    await old_ws.failure_started.wait()

    session.pusher_connected = False
    await session.connect()
    old_ws.release_failure.set()
    active_ref["active"] = False
    await operation_task

    try:
        assert session.pusher_ws is replacement_ws, 'stale socket failure replaced the healthy current socket'
        assert session.pusher_connected is True, 'stale socket failure disconnected the healthy replacement'
        assert replacement_ws.closed_codes == [], 'stale socket failure closed the healthy replacement'
        assert session.reconnect_task is None, 'stale socket failure started a redundant reconnect'
    finally:
        reconnect_task = session.reconnect_task
        if reconnect_task is not None:
            reconnect_task.cancel()
            await asyncio.gather(reconnect_task, return_exceptions=True)


@pytest.mark.anyio
async def test_finalization_job_identity_survives_pusher_reconnect():
    ws = FakePusherWebSocket()
    session = make_session(ws=ws)
    await session.connect()

    await session.request_conversation_processing('conv-1', 'job-1', 3)
    session.pusher_connected = False
    await session.connect()

    finalization_frames = [frame_json(frame) for frame in ws.sent if frame_type(frame) == 104]
    assert finalization_frames == [
        {
            'conversation_id': 'conv-1',
            'language': 'en',
            'byok_keys': {'openai': 'key'},
            'finalization_job_id': 'job-1',
            'dispatch_generation': 3,
        },
        {
            'conversation_id': 'conv-1',
            'language': 'en',
            'byok_keys': {'openai': 'key'},
            'finalization_job_id': 'job-1',
            'dispatch_generation': 3,
        },
    ]


@pytest.mark.anyio
async def test_finalization_send_failure_disconnects_dead_socket_and_preserves_request():
    ws = FailFirstFrameWebSocket(104)
    session = make_session(ws=ws, active_ref={"active": False})
    await session.connect()

    sent = await session.request_conversation_processing(
        "conv-1",
        finalization_job_id="job-1",
        dispatch_generation=7,
    )

    assert sent is False
    assert session.pusher_connected is False, "failed finalization send must disconnect the dead pusher socket"
    assert session.pending_conversation_requests["conv-1"]["finalization_job_id"] == "job-1"
    assert session.pending_conversation_requests["conv-1"]["dispatch_generation"] == 7


@pytest.mark.anyio
async def test_pending_conversation_and_speaker_sample_replay_uses_target_rate_for_multi_channel():
    ws = FakePusherWebSocket()
    connect_calls = []
    session = make_session(
        ws=ws,
        config_overrides={"is_multi_channel": True, "sample_rate": 44100},
        connect_calls=connect_calls,
    )

    assert await session.request_conversation_processing("conv-pending") is False
    await session.send_speaker_sample_request("person-1", "conv-pending", ["seg-1", "seg-2"])
    await session.connect()

    assert connect_calls[0][1] == TARGET_SAMPLE_RATE
    assert [frame_type(frame) for frame in ws.sent] == [104, 105]
    assert frame_json(ws.sent[0])["conversation_id"] == "conv-pending"
    assert frame_json(ws.sent[1])["segment_ids"] == ["seg-1", "seg-2"]
    assert list(session.pending_speaker_sample_requests) == []


@pytest.mark.anyio
async def test_transcript_flush_failure_replays_original_route_before_new_conversation():
    ws = FailFirstFrameWebSocket(102, block_failure=True)
    conversation = {"id": "conv-a"}
    session = make_session(
        ws=ws,
        active_ref={"active": False},
        config_overrides={"max_segment_buffer_size": 3},
        deps_overrides={"get_current_conversation_id": lambda: conversation["id"]},
    )
    await session.connect()
    session.transcript_send([{"id": "old-1"}, {"id": "old-2"}])

    flush_task = asyncio.create_task(session._transcript_flush())
    await ws.failure_started.wait()
    conversation["id"] = "conv-b"
    session.transcript_send([{"id": "new-1"}, {"id": "new-2"}])
    ws.release_failure.set()
    await flush_task

    assert session.pending_transcript_delivery is not None
    failed_delivery_id = session.pending_transcript_delivery.delivery_id
    assert session.pending_transcript_delivery.conversation_id == "conv-a"
    assert session.pending_transcript_delivery.segments == [{"id": "old-1"}, {"id": "old-2"}]
    assert (list(session.segment_buffers), session.pusher_connected) == ([{"id": "new-1"}], False)

    await session.connect()
    await session._transcript_flush()
    await session._transcript_flush()

    retried, newer = [frame_json(frame) for frame in ws.sent if frame_type(frame) == 102]
    assert retried == {
        "segments": [{"id": "old-1"}, {"id": "old-2"}],
        "memory_id": "conv-a",
        "delivery_id": failed_delivery_id,
    }
    assert newer["segments"] == [{"id": "new-1"}]
    assert newer["memory_id"] == "conv-b"
    assert newer["delivery_id"] != failed_delivery_id
    assert list(session.segment_buffers) == []


@pytest.mark.anyio
async def test_audio_flush_failure_replays_original_route_before_new_conversation():
    ws = FailFirstFrameWebSocket(101, block_failure=True)
    conversation = {"id": "conv-a"}
    session = make_session(
        ws=ws,
        active_ref={"active": False},
        config_overrides={"max_audio_buffer_size": 8},
        deps_overrides={"get_current_conversation_id": lambda: conversation["id"]},
    )
    await session.connect()
    session.last_synced_conversation_id = "conv-a"
    session.audio_bytes_send(b"abcd", received_at=100.0)

    flush_task = asyncio.create_task(session._audio_bytes_flush())
    await ws.failure_started.wait()
    conversation["id"] = "conv-b"
    session.audio_bytes_send(b"efghij", received_at=101.0)
    ws.release_failure.set()
    await flush_task

    assert session.pending_audio_delivery is not None
    assert session.pending_audio_delivery.conversation_id == "conv-a"
    assert b"".join(session.pending_audio_delivery.chunks) == b"abcd"
    assert (b"".join(session.audio_chunks), session.audio_total_size, session.pusher_connected) == (b"ghij", 4, False)

    await session.connect()
    await session._audio_bytes_flush()
    await session._audio_bytes_flush()

    routes = [frame[4:].decode("utf-8") for frame in ws.sent if frame_type(frame) == 103]
    audio_frames = [frame for frame in ws.sent if frame_type(frame) == 101]
    assert routes == ["conv-a", "conv-b"]
    assert [frame[12:] for frame in audio_frames] == [b"abcd", b"ghij"]
    assert struct.unpack("d", audio_frames[0][4:12])[0] == 100.0 - (4 / (8000 * 2))
    assert struct.unpack("d", audio_frames[1][4:12])[0] == 101.0 - (4 / (8000 * 2))
    assert session.audio_total_size == 0


@pytest.mark.anyio
async def test_connected_speaker_sample_send_failure_buffers_once_and_replays_on_reconnect():
    ws = FailFirstFrameWebSocket(105)
    session = make_session(ws=ws, active_ref={"active": False})
    await session.connect()

    await session.send_speaker_sample_request("person-1", "conv-1", ["seg-1", "seg-2"])

    expected = [("person-1", "conv-1", ["seg-1", "seg-2"])]
    assert (list(session.pending_speaker_sample_requests), session.pusher_connected) == (expected, False)
    request_key = ("person-1", "conv-1", ("seg-1", "seg-2"))
    failed_delivery_id = session.pending_speaker_sample_delivery_ids[request_key]

    await session.connect()

    assert [frame_type(frame) for frame in ws.sent] == [105]
    payload = frame_json(ws.sent[0])
    assert {key: payload[key] for key in ("person_id", "conversation_id", "segment_ids")} == {
        "person_id": "person-1",
        "conversation_id": "conv-1",
        "segment_ids": ["seg-1", "seg-2"],
    }
    assert payload["delivery_id"] == failed_delivery_id
    assert list(session.pending_speaker_sample_requests) == []


@pytest.mark.anyio
async def test_ambiguous_transcript_failure_reuses_stable_delivery_id():
    ws = DeliverThenFailFirstFrameWebSocket(102)
    session = make_session(ws=ws, active_ref={"active": False})
    await session.connect()
    session.transcript_send([{"id": "seg-1"}])

    await session._transcript_flush()
    assert session.pending_transcript_delivery is not None
    delivery_id = session.pending_transcript_delivery.delivery_id

    await session.connect()
    await session._transcript_flush()

    deliveries = [frame_json(frame) for frame in ws.sent if frame_type(frame) == 102]
    assert [delivery["delivery_id"] for delivery in deliveries] == [delivery_id, delivery_id]
    assert [delivery["segments"] for delivery in deliveries] == [[{"id": "seg-1"}], [{"id": "seg-1"}]]


@pytest.mark.anyio
async def test_ack_capability_retains_and_replays_transcript_until_peer_completion():
    first_ws = FakePusherWebSocket(ack_supported=True)
    second_ws = FakePusherWebSocket(ack_supported=True)
    sockets = iter([first_ws, second_ws])
    active_ref = {"active": True}

    async def connect_to_pusher(*_args, **_kwargs):
        return next(sockets)

    session = make_session(
        active_ref=active_ref,
        deps_overrides={"connect_to_pusher": connect_to_pusher},
    )
    await session.connect()
    session.transcript_send([{"id": "seg-1"}])
    await session._transcript_flush()

    assert session.pending_transcript_delivery is not None
    delivery_id = session.pending_transcript_delivery.delivery_id
    assert frame_json(first_ws.sent[0])["delivery_id"] == delivery_id

    session.pusher_connected = False
    await session.connect()
    await session._transcript_flush()

    assert frame_json(second_ws.sent[0])["delivery_id"] == delivery_id
    second_ws.incoming.append(response_202("transcript", delivery_id))
    second_ws.on_recv = lambda: active_ref.update(active=False)
    await session.pusher_receive()

    assert session.pending_transcript_delivery is None


@pytest.mark.anyio
async def test_ack_capability_retains_speaker_request_until_peer_completion():
    active_ref = {"active": True}
    ws = FakePusherWebSocket(ack_supported=True)
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.send_speaker_sample_request("person-1", "conv-1", ["seg-1"])

    request_key = ("person-1", "conv-1", ("seg-1",))
    delivery_id = session.pending_speaker_sample_delivery_ids[request_key]
    assert list(session.pending_speaker_sample_requests) == [("person-1", "conv-1", ["seg-1"])]

    ws.incoming.append(response_202("speaker_sample", delivery_id))
    ws.on_recv = lambda: active_ref.update(active=False)
    await session.pusher_receive()

    assert list(session.pending_speaker_sample_requests) == []
    assert request_key not in session.pending_speaker_sample_delivery_ids


@pytest.mark.anyio
async def test_graceful_close_drains_delivery_ack_after_runtime_becomes_inactive():
    ws = FakePusherWebSocket(ack_supported=True)
    session = make_session(ws=ws, active_ref={"active": False})
    await session.connect()
    session.transcript_send([{"id": "seg-1"}])
    delivery = session._take_transcript_delivery()
    assert delivery is not None
    ws.incoming.append(response_202("transcript", delivery.delivery_id))

    await session.close(code=1001)

    assert session.pending_transcript_delivery is None
    assert [frame_type(frame) for frame in ws.sent] == [107, 102]
    assert ws.closed_codes == [1001]


@pytest.mark.anyio
async def test_graceful_close_flushes_transcript_groups_behind_pending_ack():
    class AutoAckWebSocket(FakePusherWebSocket):
        def __init__(self):
            super().__init__(ack_supported=True)

        async def send(self, data):
            await super().send(data)
            frame = bytes(data)
            if frame_type(frame) == 102:
                self.incoming.append(response_202("transcript", frame_json(frame)["delivery_id"]))

    conversation = {"id": "conv-a"}
    ws = AutoAckWebSocket()
    session = make_session(
        ws=ws,
        active_ref={"active": False},
        deps_overrides={"get_current_conversation_id": lambda: conversation["id"]},
    )
    await session.connect()
    session.transcript_send([{"id": "segment-a"}])
    conversation["id"] = "conv-b"
    session.transcript_send([{"id": "segment-b"}])

    await session.close(code=1001)

    transcript_frames = [frame_json(frame) for frame in ws.sent if frame_type(frame) == 102]
    assert [frame["memory_id"] for frame in transcript_frames] == ["conv-a", "conv-b"]
    assert [frame["segments"] for frame in transcript_frames] == [
        [{"id": "segment-a"}],
        [{"id": "segment-b"}],
    ]
    assert session.pending_transcript_delivery is None
    assert list(session.segment_buffers) == []


@pytest.mark.anyio
async def test_close_deadline_bounds_a_blocked_delivery_send(monkeypatch):
    class BlockingSendWebSocket(FakePusherWebSocket):
        def __init__(self):
            super().__init__(ack_supported=True)
            self.send_started = asyncio.Event()

        async def send(self, _data):
            self.send_started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(listen_pusher_module, 'PUSHER_CLOSE_ACK_TIMEOUT', 0.05)
    monkeypatch.setattr(listen_pusher_module, 'PUSHER_SOCKET_CLOSE_TIMEOUT', 0.05)
    ws = BlockingSendWebSocket()
    session = make_session(ws=ws, active_ref={"active": False})
    await session.connect()
    session.transcript_send([{"id": "seg-1"}])

    await asyncio.wait_for(session.close(code=1001), timeout=1)

    assert ws.send_started.is_set()
    assert ws.closed_codes == [1001]
    assert session.segment_buffers or session.pending_transcript_delivery is not None


@pytest.mark.anyio
async def test_transcript_cancellation_keeps_route_stamped_delivery():
    ws = FailFirstFrameWebSocket(102, block_failure=True)
    session = make_session(ws=ws, active_ref={"active": False}, current_conversation_id="conv-a")
    await session.connect()
    session.transcript_send([{"id": "seg-1"}])

    task = asyncio.create_task(session._transcript_flush())
    await ws.failure_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert session.pending_transcript_delivery is not None
    assert session.pending_transcript_delivery.conversation_id == "conv-a"
    assert session.pending_transcript_delivery.segments == [{"id": "seg-1"}]
    assert session.pusher_connected is False


@pytest.mark.anyio
async def test_audio_cancellation_keeps_route_stamped_delivery():
    ws = FailFirstFrameWebSocket(101, block_failure=True)
    session = make_session(ws=ws, active_ref={"active": False}, current_conversation_id="conv-a")
    await session.connect()
    session.audio_bytes_send(b"abcd", received_at=100.0)

    task = asyncio.create_task(session._audio_bytes_flush())
    await ws.failure_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert session.pending_audio_delivery is not None
    assert session.pending_audio_delivery.conversation_id == "conv-a"
    assert b"".join(session.pending_audio_delivery.chunks) == b"abcd"
    assert session.pusher_connected is False


@pytest.mark.anyio
async def test_speaker_request_cancellation_keeps_stable_pending_delivery():
    ws = FailFirstFrameWebSocket(105, block_failure=True)
    session = make_session(ws=ws, active_ref={"active": False})
    await session.connect()

    task = asyncio.create_task(session.send_speaker_sample_request("person-1", "conv-1", ["seg-1"]))
    await ws.failure_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    request_key = ("person-1", "conv-1", ("seg-1",))
    assert list(session.pending_speaker_sample_requests) == [("person-1", "conv-1", ["seg-1"])]
    assert session.pending_speaker_sample_delivery_ids[request_key]
    assert session.pusher_connected is False


@pytest.mark.anyio
async def test_full_speaker_buffer_preserves_accepted_unacknowledged_delivery():
    ws = FakePusherWebSocket(ack_supported=True)
    session = make_session(
        ws=ws,
        active_ref={"active": False},
        config_overrides={"max_pending_speaker_sample_requests": 1},
    )
    await session.connect()

    await session.send_speaker_sample_request("person-1", "conv-1", ["seg-1"])
    first_key = ("person-1", "conv-1", ("seg-1",))
    first_delivery_id = session.pending_speaker_sample_delivery_ids[first_key]
    await session.send_speaker_sample_request("person-2", "conv-2", ["seg-2"])

    assert list(session.pending_speaker_sample_requests) == [("person-1", "conv-1", ["seg-1"])]
    assert session.pending_speaker_sample_delivery_ids == {first_key: first_delivery_id}
    assert [frame_type(frame) for frame in ws.sent] == [105]
    assert frame_json(ws.sent[0])["delivery_id"] == first_delivery_id


@pytest.mark.anyio
async def test_disconnected_conversation_buffer_respects_max_pending_requests():
    now = {"value": 1000.0}
    session = make_session(
        config_overrides={"max_pending_requests": 2},
        deps_overrides={"now": lambda: now["value"]},
    )

    assert await session.request_conversation_processing("conv-1") is False
    now["value"] += 1
    assert await session.request_conversation_processing("conv-2") is False
    now["value"] += 1
    assert await session.request_conversation_processing("conv-3") is False

    assert list(session.pending_conversation_requests.keys()) == ["conv-2", "conv-3"]


def test_bounded_audio_and_transcript_buffers():
    session = make_session(config_overrides={"max_segment_buffer_size": 2, "max_audio_buffer_size": 5})

    session.transcript_send([{"id": "seg-1"}, {"id": "seg-2"}, {"id": "seg-3"}])
    assert list(session.segment_buffers) == [{"id": "seg-1"}, {"id": "seg-2"}]

    session.audio_bytes_send(b"abc", received_at=1.0)
    session.audio_bytes_send(b"def", received_at=2.0)
    assert b"".join(session.audio_chunks) == b"def"
    assert session.audio_total_size == 3

    session.audio_bytes_send(b"123456789", received_at=3.0)
    assert b"".join(session.audio_chunks) == b"56789"
    assert session.audio_total_size == 5


@pytest.mark.anyio
async def test_incoming_201_invokes_callback_and_removes_pending_request():
    active_ref = {"active": True}
    ws = FakePusherWebSocket(incoming=[response_201("conv-1")])
    ws.on_recv = lambda: active_ref.update(active=False)
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1")

    await session.pusher_receive()

    assert session.pending_conversation_requests == {}
    assert session.callbacks == ["conv-1"]


@pytest.mark.anyio
async def test_incoming_finalization_error_keeps_request_for_bounded_retry():
    active_ref = {"active": True}
    ws = FakePusherWebSocket(incoming=[error_response_201("conv-1")])
    ws.on_recv = lambda: active_ref.update(active=False)
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)

    await session.pusher_receive()

    finalization_frames = [frame for frame in ws.sent if frame_type(frame) == 104]
    assert len(finalization_frames) == 2
    assert session.pending_conversation_requests['conv-1']['retries'] == 1


@pytest.mark.anyio
async def test_incoming_terminal_finalization_error_stops_retrying():
    active_ref = {"active": True}
    ws = FakePusherWebSocket(incoming=[error_response_201("conv-1", terminal=True)])
    ws.on_recv = lambda: active_ref.update(active=False)
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)

    await session.pusher_receive()

    # A dead-lettered job can never succeed: re-requesting it would retry the
    # same failing finalization for the whole life of the session.
    assert session.pending_conversation_requests == {}
    finalization_frames = [frame for frame in ws.sent if frame_type(frame) == 104]
    assert len(finalization_frames) == 1


@pytest.mark.anyio
async def test_incoming_fenced_finalization_consumes_request_without_completed_callback():
    active_ref = {"active": True}
    ws = FakePusherWebSocket(incoming=[fenced_response_201("conv-1")])
    ws.on_recv = lambda: active_ref.update(active=False)
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)

    await session.pusher_receive()

    assert session.pending_conversation_requests == {}
    assert session.callbacks == []


@pytest.mark.anyio
async def test_mark_disconnected_starts_single_reconnect_loop():
    session = make_session()
    session.pusher_ws = FakePusherWebSocket()
    session.pusher_connected = True

    session._mark_disconnected()
    first_task = session.reconnect_task
    session._mark_disconnected()

    assert session.reconnect_task is first_task
    first_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_task


@pytest.mark.anyio
async def test_close_cancels_reconnect_flushes_buffers_and_closes_socket():
    ws = FakePusherWebSocket()
    session = make_session(ws=ws)
    await session.connect()
    session.transcript_send([{"id": "seg-1"}])
    session.audio_bytes_send(b"abc", received_at=100.0)

    async def sleepy_reconnect():
        await asyncio.sleep(10)

    session.reconnect_task = asyncio.create_task(sleepy_reconnect())
    await session.close(code=1001)

    assert session.reconnect_task is None
    assert [frame_type(frame) for frame in ws.sent] == [103, 101, 102]
    assert ws.closed_codes == [1001]

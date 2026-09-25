import asyncio
import json
import logging
import struct

import pytest

from utils.listen_pusher_session import (
    FINALIZATION_IN_FLIGHT_ERROR,
    FINALIZATION_RESULT_PROTOCOL,
    FINALIZATION_STALE_GENERATION_ERROR,
    TARGET_SAMPLE_RATE,
    ListenPusherSession,
    ListenPusherSessionConfig,
    ListenPusherSessionDeps,
)


class FakePusherWebSocket:
    def __init__(self, incoming=None, send_errors=None):
        self.sent = []
        self.incoming = list(incoming or [])
        self.send_errors = list(send_errors or [])
        self.closed_codes = []
        self.on_recv = None

    async def send(self, data):
        if self.send_errors:
            error = self.send_errors.pop(0)
            if error:
                raise error
        self.sent.append(bytes(data))

    async def recv(self):
        if self.on_recv:
            self.on_recv()
        if self.incoming:
            return self.incoming.pop(0)
        await asyncio.sleep(10)

    async def close(self, code=1000):
        self.closed_codes.append(code)


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


def in_flight_response_201(conversation_id: str):
    payload = json.dumps(
        {"conversation_id": conversation_id, "error": FINALIZATION_IN_FLIGHT_ERROR, "terminal": False}
    ).encode("utf-8")
    return struct.pack("<I", 201) + payload


def stale_generation_response_201(conversation_id: str, dispatch_generation=None, terminal: bool = False):
    payload = {
        "conversation_id": conversation_id,
        "error": FINALIZATION_STALE_GENERATION_ERROR,
        "terminal": terminal,
    }
    if dispatch_generation is not None:
        payload["dispatch_generation"] = dispatch_generation
    payload = json.dumps(payload).encode("utf-8")
    return struct.pack("<I", 201) + payload


def fenced_response_201(conversation_id: str):
    payload = json.dumps({"conversation_id": conversation_id, "fenced": True}).encode("utf-8")
    return struct.pack("<I", 201) + payload


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
    client_kind_calls=None,
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

    async def connect_to_pusher(uid, sample_rate, retries=5, is_active=None, client_kind='unknown'):
        if connect_calls is not None:
            connect_calls.append((uid, sample_rate, retries, is_active))
        if client_kind_calls is not None:
            client_kind_calls.append(client_kind)
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
    assert frame_json(ws.sent[2]) == {"segments": [{"id": "seg-1", "text": "hello"}], "memory_id": "conv-1"}
    assert frame_json(ws.sent[3]) == {
        "conversation_id": "conv-1",
        "language": "en",
        "byok_keys": {"openai": "key"},
    }
    assert frame_json(ws.sent[4]) == {
        "person_id": "person-1",
        "conversation_id": "conv-1",
        "segment_ids": ["seg-1"],
    }


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
            'finalization_result_protocol': FINALIZATION_RESULT_PROTOCOL,
        },
        {
            'conversation_id': 'conv-1',
            'language': 'en',
            'byok_keys': {'openai': 'key'},
            'finalization_job_id': 'job-1',
            'dispatch_generation': 3,
            'finalization_result_protocol': FINALIZATION_RESULT_PROTOCOL,
        },
    ]


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
    assert list(session.segment_buffers) == [{"id": "seg-2"}, {"id": "seg-3"}]

    session.audio_bytes_send(b"abc", received_at=1.0)
    session.audio_bytes_send(b"def", received_at=2.0)
    assert b"".join(session.audio_chunks) == b"def"
    assert session.audio_total_size == 3

    session.audio_bytes_send(b"123456789", received_at=3.0)
    assert b"".join(session.audio_chunks) == b"56789"
    assert session.audio_total_size == 5


@pytest.mark.anyio
async def test_failed_transcript_send_retains_buffer_for_retry():
    ws = FakePusherWebSocket(send_errors=[RuntimeError("send failed"), None])
    session = make_session(ws=ws)
    await session.connect()
    session.transcript_send([{"id": "seg-1"}])

    await session._transcript_flush()
    assert list(session.segment_buffers) == [{"id": "seg-1"}]

    await session._transcript_flush()
    assert list(session.segment_buffers) == []
    transcript_frames = [frame for frame in ws.sent if frame_type(frame) == 102]
    assert frame_json(transcript_frames[0])["segments"] == [{"id": "seg-1"}]


@pytest.mark.anyio
async def test_failed_audio_send_retains_buffer_for_retry():
    ws = FakePusherWebSocket(send_errors=[None, RuntimeError("send failed"), None])
    session = make_session(ws=ws)
    await session.connect()
    session.audio_bytes_send(b"abcd", received_at=100.0)

    await session._audio_bytes_flush()
    assert b"".join(session.audio_chunks) == b"abcd"
    assert session.audio_total_size == 4

    await session._audio_bytes_flush()
    assert list(session.audio_chunks) == []
    assert session.audio_total_size == 0
    assert ws.sent[-1][12:] == b"abcd"


@pytest.mark.anyio
@pytest.mark.parametrize("flush", ["transcript", "audio"])
async def test_cancelled_send_retains_buffer(flush):
    ws = FakePusherWebSocket(send_errors=[asyncio.CancelledError()])
    session = make_session(ws=ws, current_conversation_id=None)
    await session.connect()
    if flush == "transcript":
        session.transcript_send([{"id": "seg-1"}])
        with pytest.raises(asyncio.CancelledError):
            await session._transcript_flush()
        assert list(session.segment_buffers) == [{"id": "seg-1"}]
    else:
        session.audio_bytes_send(b"abcd", received_at=100.0)
        with pytest.raises(asyncio.CancelledError):
            await session._audio_bytes_flush()
        assert b"".join(session.audio_chunks) == b"abcd"
        assert session.audio_total_size == 4


@pytest.mark.anyio
async def test_close_waits_for_failed_transcript_flush_and_retries_before_closing():
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingPusherWebSocket(FakePusherWebSocket):
        async def send(self, data):
            if not started.is_set():
                started.set()
                await release.wait()
                raise RuntimeError("send failed")
            await super().send(data)

    ws = BlockingPusherWebSocket()
    session = make_session(ws=ws)
    await session.connect()
    session.transcript_send([{"id": "seg-1"}])

    flush = asyncio.create_task(session._transcript_flush())
    await started.wait()
    close = asyncio.create_task(session.close())
    await asyncio.sleep(0)
    assert not close.done()
    release.set()
    await flush
    await close

    transcript_frames = [frame for frame in ws.sent if frame_type(frame) == 102]
    assert frame_json(transcript_frames[0])["segments"] == [{"id": "seg-1"}]
    assert ws.closed_codes == [1000]


@pytest.mark.anyio
async def test_failed_speaker_sample_replay_stays_buffered():
    ws = FakePusherWebSocket(send_errors=[RuntimeError("send failed")])
    session = make_session(ws=ws)
    await session.send_speaker_sample_request("person-1", "conv-1", ["seg-1"])

    await session.connect()

    assert list(session.pending_speaker_sample_requests) == [("person-1", "conv-1", ["seg-1"])]


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
async def test_will_retry_finalization_error_logs_warning_not_error(caplog):
    # The will-retry branch is healthy in-flight work by the session's own
    # accounting (the pending entry is re-armed for bounded retry); logging
    # it at ERROR paged on-call for traffic that self-heals (2026-09-05:
    # 40-50 ERROR/30min for 2h against ~250-270 healthy processing/30min,
    # 0-17 terminal). Severity is the fault-origin signal — same boundary
    # as the WS-auth reclassification (FC-request-input-rejection-escapes-
    # as-server-fault). The terminal branch keeps ERROR (companion test).
    with caplog.at_level(logging.DEBUG, logger="utils.listen_pusher_session"):
        active_ref = {"active": True}
        ws = FakePusherWebSocket(incoming=[error_response_201("conv-1")])
        ws.on_recv = lambda: active_ref.update(active=False)
        session = make_session(ws=ws, active_ref=active_ref)
        await session.connect()
        await session.request_conversation_processing("conv-1", "job-1", 2)

        await session.pusher_receive()

    records = [r for r in caplog.records if r.getMessage().startswith("Conversation processing failed")]
    assert records, "expected a will-retry failure record"
    assert all(
        r.levelno == logging.WARNING for r in records
    ), "the will-retry finalization branch must log at WARNING, not ERROR"
    # WARNING must not mean dropped: the request stays armed for bounded retry.
    assert session.pending_conversation_requests['conv-1']['retries'] == 1


@pytest.mark.anyio
async def test_in_flight_finalization_lease_does_not_consume_the_retry_burst():
    # `job_leased` means a concurrent dispatch of the same job is finalizing
    # normally. Treating it as a failure re-requested it immediately, and each
    # rejection re-armed the next one, so the whole burst burned in under a
    # second and left a genuine later failure with no attempts.
    active_ref = {"active": True}
    ws = FakePusherWebSocket(incoming=[in_flight_response_201("conv-1")])
    ws.on_recv = lambda: active_ref.update(active=False)
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)

    await session.pusher_receive()

    finalization_frames = [frame for frame in ws.sent if frame_type(frame) == 104]
    assert len(finalization_frames) == 1
    pending = session.pending_conversation_requests['conv-1']
    assert pending['retries'] == 0
    assert pending['sent_at'] == session.deps.now()


@pytest.mark.anyio
async def test_stale_finalization_generation_drops_live_request_for_durable_replay():
    active_ref = {"active": True}
    ws = FakePusherWebSocket(incoming=[stale_generation_response_201("conv-1", 2)])
    ws.on_recv = lambda: active_ref.update(active=False)
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)

    await session.pusher_receive()

    # The reconciler owns the newer dispatch generation; a live retry of 2
    # can never claim it and must not consume the session's retry burst.
    assert session.pending_conversation_requests == {}
    finalization_frames = [frame for frame in ws.sent if frame_type(frame) == 104]
    assert len(finalization_frames) == 1


@pytest.mark.anyio
async def test_delayed_stale_finalization_response_does_not_drop_newer_pending_generation():
    active_ref = {"active": True}
    ws = FakePusherWebSocket(incoming=[stale_generation_response_201("conv-1", 1)])
    ws.on_recv = lambda: active_ref.update(active=False)
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)

    await session.pusher_receive()

    assert session.pending_conversation_requests["conv-1"]["dispatch_generation"] == 2
    finalization_frames = [frame for frame in ws.sent if frame_type(frame) == 104]
    assert len(finalization_frames) == 1


@pytest.mark.anyio
async def test_legacy_pusher_stale_response_without_generation_preserves_newer_pending_generation():
    active_ref = {"active": True}
    ws = FakePusherWebSocket(incoming=[stale_generation_response_201("conv-1")])
    ws.on_recv = lambda: active_ref.update(active=False)
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)

    await session.pusher_receive()

    # A pre-v2 pusher cannot identify which pending generation it rejected.
    assert session.pending_conversation_requests["conv-1"]["dispatch_generation"] == 2
    finalization_frames = [frame for frame in ws.sent if frame_type(frame) == 104]
    assert len(finalization_frames) == 1


@pytest.mark.anyio
async def test_stale_generation_one_drops_pending_job_with_omitted_generation():
    active_ref = {"active": True}
    ws = FakePusherWebSocket(incoming=[stale_generation_response_201("conv-1", 1)])
    ws.on_recv = lambda: active_ref.update(active=False)
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1")

    await session.pusher_receive()

    # The wire serializer defaults an omitted generation to 1, so the stale
    # response must match that effective generation and drop the request.
    assert session.pending_conversation_requests == {}
    finalization_frames = [frame for frame in ws.sent if frame_type(frame) == 104]
    assert len(finalization_frames) == 1
    assert frame_json(finalization_frames[0])["dispatch_generation"] == 1


@pytest.mark.anyio
async def test_incoming_terminal_finalization_error_stops_retrying(caplog):
    active_ref = {"active": True}
    ws = FakePusherWebSocket(incoming=[error_response_201("conv-1", terminal=True)])
    ws.on_recv = lambda: active_ref.update(active=False)
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)

    with caplog.at_level(logging.DEBUG, logger="utils.listen_pusher_session"):
        await session.pusher_receive()

    # A dead-lettered job can never succeed: re-requesting it would retry the
    # same failing finalization for the whole life of the session.
    assert session.pending_conversation_requests == {}
    finalization_frames = [frame for frame in ws.sent if frame_type(frame) == 104]
    assert len(finalization_frames) == 1
    # The terminal branch is the genuine fault signal: it stays at ERROR.
    terminal_records = [
        r for r in caplog.records if r.getMessage().startswith("Conversation processing failed terminally")
    ]
    assert terminal_records, "expected a terminal failure record"
    assert all(r.levelno == logging.ERROR for r in terminal_records)


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


@pytest.mark.anyio
async def test_pusher_connection_carries_the_bounded_client_kind():
    """The pusher session is the only place that knows which client opened it.

    Without this the pusher-side journey counters cannot tell an iOS outage from
    a healthy Android population, which is the aggregation that let a 19-hour
    desktop chat outage hide behind a larger healthy client.
    """
    client_kind_calls = []
    session = make_session(
        config_overrides={"client_kind": "mobile_ios"},
        client_kind_calls=client_kind_calls,
    )

    await session.connect()

    assert client_kind_calls == ["mobile_ios"]


@pytest.mark.anyio
async def test_pusher_connection_defaults_to_unknown_rather_than_guessing():
    client_kind_calls = []
    session = make_session(client_kind_calls=client_kind_calls)

    await session.connect()

    assert client_kind_calls == ["unknown"]

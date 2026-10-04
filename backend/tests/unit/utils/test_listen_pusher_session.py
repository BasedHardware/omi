import asyncio
import json
import logging
import struct
import time

import pytest
from websockets.exceptions import ConnectionClosedError

import utils.listen_pusher_session as pusher_session
from utils.listen_pusher_session import (
    AUDIO_TIMELINE_PROTOCOL,
    FINALIZATION_IN_FLIGHT_ERROR,
    FINALIZATION_RESULT_PROTOCOL,
    FINALIZATION_STALE_GENERATION_ERROR,
    TARGET_SAMPLE_RATE,
    ListenPusherSession,
    ListenPusherSessionConfig,
    ListenPusherSessionDeps,
)
from utils.pusher_protocol import audio_timeline_ack_frame


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

    async def connect_to_pusher(
        uid, sample_rate, retries=5, is_active=None, client_kind='unknown', audio_timeline=None
    ):
        if connect_calls is not None:
            connect_calls.append((uid, sample_rate, retries, is_active, audio_timeline))
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
    # Audio runs (not bare chunks) since audio-timeline v2: each run carries
    # its conversation binding and projected start alongside the bytes.
    assert b"".join(run.data for run in session.audio_runs) == b"def"
    assert session.audio_total_size == 3

    session.audio_bytes_send(b"123456789", received_at=3.0)
    assert b"".join(run.data for run in session.audio_runs) == b"56789"
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


def _discarded_legacy_bytes():
    return pusher_session.OMI_LISTEN_PUSHER_AUDIO_DISCARDED_BYTES_TOTAL.labels(
        reason='legacy_uncertain_send'
    )._value.get()


def _install_replacement_socket(session):
    replacement = FakePusherWebSocket()
    session.pusher_ws = replacement
    session.pusher_connected = True
    session.last_synced_conversation_id = None
    return replacement


@pytest.mark.anyio
async def test_failed_legacy_audio_send_retries_on_the_same_socket(monkeypatch):
    """Main's semantics while the socket stays installed: a failed legacy 101
    returns to the buffer and the next ordinary flush resends it, followed by
    newer audio; nothing is discarded."""
    discarded = _discarded_legacy_bytes()
    ws = FakePusherWebSocket(send_errors=[None, RuntimeError("send failed"), None])
    session = make_session(ws=ws, config_overrides={'max_audio_buffer_size': 64})
    await session.connect()
    session.audio_bytes_send(b"abcd", received_at=100.0)

    await session._audio_bytes_flush()
    assert b"".join(run.data for run in session.audio_runs) == b"abcd"
    assert session.pusher_connected and session.pusher_ws is ws

    await session._audio_bytes_flush()
    session.audio_bytes_send(b"efgh", received_at=101.0)
    await session._audio_bytes_flush()
    audio = [frame[12:] for frame in ws.sent if frame_type(frame) == 101]
    assert audio[-2:] == [b"abcd", b"efgh"]
    assert _discarded_legacy_bytes() - discarded == 0


@pytest.mark.anyio
async def test_failed_legacy_audio_send_regroups_with_newer_audio_on_the_same_socket(monkeypatch):
    """Newer audio arriving before the retry is regrouped with the failed runs
    into one contiguous frame, as main does."""
    ws = FakePusherWebSocket(send_errors=[None, RuntimeError("send failed"), None])
    session = make_session(ws=ws, config_overrides={'max_audio_buffer_size': 64})
    await session.connect()
    session.audio_bytes_send(b"abcd", received_at=100.0)
    await session._audio_bytes_flush()
    session.audio_bytes_send(b"efgh", received_at=101.0)

    await session._audio_bytes_flush()
    assert [frame[12:] for frame in ws.sent if frame_type(frame) == 101][-1] == b"abcdefgh"


@pytest.mark.anyio
@pytest.mark.parametrize('error', [RuntimeError("send failed"), ConnectionClosedError(None, None)])
@pytest.mark.parametrize('delivered', [False, True])
async def test_legacy_failed_send_is_discarded_once_after_socket_replacement(monkeypatch, error, delivered):
    """Once a replacement socket is installed, runs that failed on the previous
    socket are discarded and counted exactly once (main never replays them);
    newer audio on the replacement still flushes."""
    ws = FakePusherWebSocket()
    if delivered:
        inner_send = ws.send
        raise_once = []

        async def delivered_then_raise(data):
            await inner_send(data)
            if frame_type(data) == 101 and not raise_once:
                raise_once.append(True)
                raise error

        ws.send = delivered_then_raise
    else:
        ws.send_errors = [None, error]
    session = make_session(ws=ws, config_overrides={'max_audio_buffer_size': 64})
    discarded_before = _discarded_legacy_bytes()
    await session.connect()
    session.audio_bytes_send(b"abcd", received_at=100.0)

    await session._audio_bytes_flush()
    assert b"".join(run.data for run in session.audio_runs) == b"abcd"

    replacement = _install_replacement_socket(session)
    session.audio_bytes_send(b"efgh", received_at=101.0)
    await session._audio_bytes_flush()
    audio = [frame[12:] for frame in replacement.sent if frame_type(frame) == 101]
    assert audio == [b"efgh"]
    assert [frame_type(frame) for frame in replacement.sent][0] == 103
    assert list(session.audio_runs) == []
    assert _discarded_legacy_bytes() - discarded_before == 4

    await session._audio_bytes_flush()
    assert _discarded_legacy_bytes() - discarded_before == 4


@pytest.mark.anyio
async def test_legacy_cancelled_audio_send_is_retained_for_the_same_socket(monkeypatch):
    """Cancellation keeps the attempted runs buffered (main's behavior); they
    are only discarded if a replacement socket is installed later."""
    ws = FakePusherWebSocket(send_errors=[asyncio.CancelledError()])
    session = make_session(ws=ws, current_conversation_id=None)
    discarded_before = _discarded_legacy_bytes()
    await session.connect()
    session.audio_bytes_send(b"abcd", received_at=100.0)

    with pytest.raises(asyncio.CancelledError):
        await session._audio_bytes_flush()
    assert b"".join(run.data for run in session.audio_runs) == b"abcd"
    assert _discarded_legacy_bytes() - discarded_before == 0

    await session._audio_bytes_flush()
    assert [frame[12:] for frame in ws.sent if frame_type(frame) == 101][-1] == b"abcd"


@pytest.mark.anyio
async def test_legacy_unattempted_later_envelope_stays_retained(monkeypatch):
    """A failed send on envelope one keeps both the attempted and the
    never-attempted envelope buffered; the next same-socket flush resends them
    in order, each after its own conversation announcement."""
    discarded = _discarded_legacy_bytes()
    ws = FakePusherWebSocket(send_errors=[None, RuntimeError("send failed")])
    session = make_session(ws=ws, config_overrides={'max_audio_buffer_size': 64})
    await session.connect()
    session.audio_bytes_send(b"aaaa", received_at=100.0, conversation_id='conv-1')
    session.audio_bytes_send(b"bbbb", received_at=101.0, conversation_id='conv-2')

    await session._audio_bytes_flush()
    assert [run.data for run in session.audio_runs] == [b"aaaa", b"bbbb"]
    assert _discarded_legacy_bytes() - discarded == 0

    await session._audio_bytes_flush()
    audio_frames = [frame[12:] for frame in ws.sent if frame_type(frame) == 101]
    assert audio_frames[-2:] == [b"aaaa", b"bbbb"]


@pytest.mark.anyio
async def test_legacy_failed_announcement_retains_every_unattempted_envelope(monkeypatch):
    """If the conversation announcement fails, no 101 was attempted: every
    buffered envelope stays retained and nothing is counted as discarded."""
    discarded = pusher_session.OMI_LISTEN_PUSHER_AUDIO_DISCARDED_BYTES_TOTAL.labels(
        reason='legacy_uncertain_send'
    )._value.get()
    ws = FakePusherWebSocket(send_errors=[RuntimeError("send failed")])
    session = make_session(ws=ws, config_overrides={'max_audio_buffer_size': 64})
    await session.connect()
    session.audio_bytes_send(b"aaaa", received_at=100.0, conversation_id='conv-1')

    await session._audio_bytes_flush()
    assert b"".join(run.data for run in session.audio_runs) == b"aaaa"
    assert (
        pusher_session.OMI_LISTEN_PUSHER_AUDIO_DISCARDED_BYTES_TOTAL.labels(reason='legacy_uncertain_send')._value.get()
        == discarded
    )

    await session._audio_bytes_flush()
    audio_frames = [frame for frame in ws.sent if frame_type(frame) == 101]
    assert audio_frames[-1][12:] == b"aaaa"


@pytest.mark.anyio
async def test_legacy_already_uncertain_envelope_is_counted_and_skipped_without_reconcile(monkeypatch):
    """Defensive: an already-uncertain envelope on a legacy socket is counted
    once and skipped with no reconcile call."""
    monkeypatch.setattr(
        pusher_session,
        'reconcile_audio_chunk_prefix',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('legacy must not reconcile')),
    )
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, config_overrides={'max_audio_buffer_size': 64})
    discarded_before = pusher_session.OMI_LISTEN_PUSHER_AUDIO_DISCARDED_BYTES_TOTAL.labels(
        reason='legacy_uncertain_send'
    )._value.get()
    await session.connect()
    session.audio_bytes_send(b"abcd", received_at=100.0, conversation_id='conv-1')
    session.audio_runs[0].uncertain = True
    session.audio_runs[0].header_timestamp = 99.9

    await session._audio_bytes_flush()
    assert list(session.audio_runs) == []
    assert session.audio_total_size == 0
    assert [frame for frame in ws.sent if frame_type(frame) == 101] == []
    assert (
        pusher_session.OMI_LISTEN_PUSHER_AUDIO_DISCARDED_BYTES_TOTAL.labels(reason='legacy_uncertain_send')._value.get()
        - discarded_before
        == 4
    )


@pytest.mark.anyio
async def test_legacy_send_failure_uses_socket_mode_pinned_at_flush_start(monkeypatch):
    """A send that flips session.audio_timeline_active mid-flush — e.g. a
    simultaneous capable replacement racing the old socket — must not promote
    the originally-legacy frame to span retention: the pinned legacy mode
    keeps main's semantics (raw runs retained for the same socket, never
    marked uncertain, nothing discarded)."""
    monkeypatch.setattr(pusher_session, 'reconcile_audio_chunk_prefix', lambda *args, **kwargs: (0, []))
    ws = FakePusherWebSocket()
    session = make_session(ws=ws)
    inner_send = ws.send

    async def flip_then_raise(data):
        await inner_send(data)
        if frame_type(data) == 101:
            session.audio_timeline_active = True
            raise RuntimeError("send failed")

    ws.send = flip_then_raise
    discarded = pusher_session.OMI_LISTEN_PUSHER_AUDIO_DISCARDED_BYTES_TOTAL.labels(
        reason='legacy_uncertain_send'
    )._value.get()
    await session.connect()
    session.audio_bytes_send(b"abcd", received_at=100.0)

    await session._audio_bytes_flush()
    assert [run.data for run in session.audio_runs] == [b"abcd"]
    assert not any(run.uncertain for run in session.audio_runs)
    assert all(run.failed_socket is ws for run in session.audio_runs)
    assert (
        pusher_session.OMI_LISTEN_PUSHER_AUDIO_DISCARDED_BYTES_TOTAL.labels(reason='legacy_uncertain_send')._value.get()
        - discarded
        == 0
    )


@pytest.mark.anyio
async def test_span_socket_send_failure_retains_uncertain_while_mode_stays_active(monkeypatch):
    """A negotiated socket whose mode stays active through the failing send
    retains the frozen envelope as uncertain and reconciles it on resend."""
    calls = []

    def recording_reconcile(*args, **kwargs):
        calls.append(kwargs.get('require_spans'))
        return 0, []

    monkeypatch.setattr(pusher_session, 'reconcile_audio_chunk_prefix', recording_reconcile)
    ws = FakePusherWebSocket(incoming=[audio_timeline_ack_frame()], send_errors=[None, RuntimeError("send failed")])
    session = make_session(ws=ws, config_overrides={'audio_timeline_spans': True})
    await session.connect()
    assert session.audio_timeline_active
    session.audio_bytes_send(b"abcd", received_at=100.0, conversation_id='conv-1', start_wall=100.0)

    await session._audio_bytes_flush()
    assert session.audio_runs and session.audio_runs[0].uncertain

    await session._audio_bytes_flush()
    assert calls == [True]
    assert ws.sent[-1][12:] == b"abcd"


def _retained_pcm_bytes(session):
    seen = {}
    stack = list(session.audio_runs)
    while stack:
        run = stack.pop()
        seen[id(run.data)] = len(run.data)
        stack.extend(run.source_runs or [])
    return sum(seen.values())


@pytest.mark.anyio
async def test_span_envelope_retains_no_pcm_outside_the_byte_cap(monkeypatch):
    """A grouped span envelope that fails, is trimmed by prefix
    reconciliation, and fails again must not keep its original raw runs
    reachable: retained PCM equals the accounted buffer size."""

    def verified_prefix(*args, **kwargs):
        return len(args[3]) - 2, []

    monkeypatch.setattr(pusher_session, 'reconcile_audio_chunk_prefix', verified_prefix)
    ws = FakePusherWebSocket(
        incoming=[audio_timeline_ack_frame()],
        send_errors=[None, RuntimeError("send failed"), RuntimeError("send failed")],
    )
    session = make_session(ws=ws, config_overrides={'audio_timeline_spans': True, 'max_audio_buffer_size': 64})
    await session.connect()
    assert session.audio_timeline_active
    session.audio_bytes_send(b"a" * 16, received_at=101.0, conversation_id='conv-1', start_wall=100.0)
    session.audio_bytes_send(b"b" * 16, received_at=103.0, conversation_id='conv-1', start_wall=100.001)

    await session._audio_bytes_flush()
    assert len(session.audio_runs) == 1 and session.audio_runs[0].uncertain
    assert session.audio_runs[0].source_runs is None
    assert _retained_pcm_bytes(session) == session.audio_total_size == 32

    await session._audio_bytes_flush()
    assert session.audio_total_size == 2
    assert _retained_pcm_bytes(session) == 2

    session.audio_bytes_send(b"c" * 62, received_at=110.0, conversation_id='conv-1', start_wall=110.0)
    assert session.audio_total_size == 64
    assert _retained_pcm_bytes(session) == 64


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
        assert [run.data for run in session.audio_runs] == [b"abcd"]
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


@pytest.mark.anyio
async def test_v2_runs_split_into_separate_101_frames_across_a_wall_gap():
    """A wall gap between buffered runs must not be concatenated into one frame.

    Two v2 runs of the same conversation with a 0.5 s projected gap flush as
    two opcode-101 frames, each header carrying its own run's projected start;
    concatenating them would delete the gap from the stored audio while the
    header still claimed the first run's position.
    """
    ws = FakePusherWebSocket(incoming=[audio_timeline_ack_frame()])
    session = make_session(ws=ws, config_overrides={'max_audio_buffer_size': 1_000_000, 'audio_timeline_v2': True})
    await session.connect()

    rate = 8000
    run_a = b'\x01\x00' * rate  # 1 s at 100.0
    run_b = b'\x02\x00' * rate  # 1 s at 101.5 (0.5 s past run A's end)
    session.audio_bytes_send(run_a, received_at=100.5, conversation_id='conv-1', start_wall=100.0)
    session.audio_bytes_send(run_b, received_at=101.5, conversation_id='conv-1', start_wall=101.5)
    await session._audio_bytes_flush()

    audio_frames = [frame for frame in ws.sent if frame_type(frame) == 101]
    assert len(audio_frames) == 2, 'a projected discontinuity must flush separate frames'
    first_ts = struct.unpack('d', audio_frames[0][4:12])[0]
    second_ts = struct.unpack('d', audio_frames[1][4:12])[0]
    assert first_ts == 100.0
    assert second_ts == 101.5
    assert audio_frames[0][12:] == run_a
    assert audio_frames[1][12:] == run_b


@pytest.mark.anyio
async def test_v2_contiguous_runs_still_share_one_101_frame():
    ws = FakePusherWebSocket(incoming=[audio_timeline_ack_frame()])
    session = make_session(ws=ws, config_overrides={'max_audio_buffer_size': 1_000_000, 'audio_timeline_v2': True})
    await session.connect()

    rate = 8000
    run_a = b'\x03\x00' * rate
    run_b = b'\x04\x00' * rate
    session.audio_bytes_send(run_a, received_at=100.9, conversation_id='conv-1', start_wall=100.0)
    # Contiguous within 1 ms: exactly run A's end.
    session.audio_bytes_send(run_b, received_at=102.0, conversation_id='conv-1', start_wall=101.0)
    await session._audio_bytes_flush()

    audio_frames = [frame for frame in ws.sent if frame_type(frame) == 101]
    assert len(audio_frames) == 1
    assert struct.unpack('d', audio_frames[0][4:12])[0] == 100.0
    assert audio_frames[0][12:] == run_a + run_b


@pytest.mark.anyio
async def test_v2_runs_split_into_separate_101_frames_on_overlap_or_backward_jump():
    """Overlapping runs or backward jumps must not be concatenated into one frame."""
    ws = FakePusherWebSocket(incoming=[audio_timeline_ack_frame()])
    session = make_session(ws=ws, config_overrides={'max_audio_buffer_size': 1_000_000, 'audio_timeline_v2': True})
    await session.connect()

    rate = 8000
    run_a = b'\x05\x00' * rate  # 1 s at 100.0 (ends at 101.0)
    run_b = b'\x06\x00' * rate  # 1 s at 100.5 (0.5 s overlap)
    session.audio_bytes_send(run_a, received_at=100.5, conversation_id='conv-1', start_wall=100.0)
    session.audio_bytes_send(run_b, received_at=101.5, conversation_id='conv-1', start_wall=100.5)
    await session._audio_bytes_flush()

    audio_frames = [frame for frame in ws.sent if frame_type(frame) == 101]
    assert len(audio_frames) == 2, 'overlapping runs must flush separate frames'
    first_ts = struct.unpack('d', audio_frames[0][4:12])[0]
    second_ts = struct.unpack('d', audio_frames[1][4:12])[0]
    assert first_ts == 100.0
    assert second_ts == 100.5
    assert audio_frames[0][12:] == run_a
    assert audio_frames[1][12:] == run_b


@pytest.mark.anyio
async def test_legacy_runs_without_projection_keep_legacy_grouping():
    """Runs without a projected start (flag-off sessions) never split on gaps."""
    ws = FakePusherWebSocket()
    session = make_session(ws=ws)
    await session.connect()

    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.audio_bytes_send(b'efgh', received_at=200.0)
    await session._audio_bytes_flush()

    audio_frames = [frame for frame in ws.sent if frame_type(frame) == 101]
    assert len(audio_frames) == 1
    assert audio_frames[0][12:] == b'abcdefgh'


@pytest.mark.anyio
@pytest.mark.parametrize('span_state', ['config_v2', 'negotiated_spans'])
async def test_spans_active_run_without_projection_falls_back_to_legacy_header(monkeypatch, span_state):
    """A run accepted without a projected start still needs a legacy header.

    When either the config flag or a negotiated handshake makes the session
    projection-honoring, close_group used to leave ``header_timestamp`` as
    ``None`` for a ``start_wall=None`` run, so ``struct.pack`` failed and the
    envelope stalled instead of keeping the legacy arrival-minus-duration
    estimate. The negotiated leg must resend that same header verbatim; the
    declared-flag-only leg is not span proof and discards the attempted
    envelope like any legacy socket.
    """
    monkeypatch.setattr(pusher_session, 'reconcile_audio_chunk_prefix', lambda *args, **kwargs: (0, []))
    config = {'max_audio_buffer_size': 1_000_000}
    incoming = None
    if span_state == 'config_v2':
        config['audio_timeline_v2'] = True
    else:
        config['audio_timeline_spans'] = True
        incoming = [audio_timeline_ack_frame()]
    ws = FakePusherWebSocket(incoming=incoming, send_errors=[None, RuntimeError("send failed")])
    session = make_session(ws=ws, config_overrides=config)
    await session.connect()
    if span_state == 'negotiated_spans':
        assert session.audio_timeline_active

    rate = 8000
    run = b'\x07\x00' * rate
    session.audio_bytes_send(run, received_at=100.5, conversation_id='conv-1', start_wall=None)
    await session._audio_bytes_flush()

    expected_header = 100.5 - len(run) / (rate * 2)
    assert [frame for frame in ws.sent if frame_type(frame) == 101] == []
    if span_state == 'config_v2':
        # Declared-flag-only is not span proof: legacy same-socket retry.
        assert not session.audio_timeline_active
        assert [r.data for r in session.audio_runs] == [run]
        assert not session.audio_runs[0].uncertain
        await session._audio_bytes_flush()
        audio_frames = [frame for frame in ws.sent if frame_type(frame) == 101]
        assert audio_frames[-1][12:] == run
        return
    assert session.audio_runs and session.audio_runs[0].uncertain

    await session._audio_bytes_flush()

    audio_frames = [frame for frame in ws.sent if frame_type(frame) == 101]
    assert len(audio_frames) == 1
    assert struct.unpack('d', audio_frames[0][4:12])[0] == expected_header
    assert audio_frames[0][12:] == run


@pytest.mark.anyio
async def test_spans_session_negotiates_the_timeline_handshake():
    connect_calls = []
    ws = FakePusherWebSocket(incoming=[audio_timeline_ack_frame()])
    session = make_session(
        ws=ws,
        config_overrides={'audio_timeline_spans': True},
        connect_calls=connect_calls,
    )

    await session.connect()

    assert connect_calls[0][4] == AUDIO_TIMELINE_PROTOCOL
    assert session.audio_timeline_active
    assert not session.audio_timeline_suspended


@pytest.mark.anyio
async def test_spans_session_without_ack_keeps_legacy_byte_semantics(monkeypatch):
    """An unacknowledged spans session must not let projected starts reach the wire."""
    monkeypatch.setattr(pusher_session, 'AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS', 0.05)
    connect_calls = []
    uncertain = FakePusherWebSocket()
    replacement = FakePusherWebSocket()
    sockets = [uncertain, replacement]

    async def connector(uid, sample_rate, retries=5, is_active=None, client_kind='unknown', audio_timeline=None):
        connect_calls.append((uid, sample_rate, retries, is_active, audio_timeline))
        return sockets.pop(0)

    session = make_session(
        config_overrides={'audio_timeline_spans': True, 'max_audio_buffer_size': 1_000_000},
        deps_overrides={'connect_to_pusher': connector, 'monotonic': time.monotonic},
    )
    await session.connect()

    assert connect_calls[0][4] == AUDIO_TIMELINE_PROTOCOL
    assert connect_calls[1][4] is None
    assert session.pusher_ws is replacement
    assert not session.audio_timeline_active
    assert not session.audio_timeline_suspended

    rate = 8000
    run_a = b'\x01\x00' * rate
    run_b = b'\x02\x00' * rate
    session.audio_bytes_send(run_a, received_at=100.5, conversation_id='conv-1', start_wall=100.0)
    session.audio_bytes_send(run_b, received_at=101.5, conversation_id='conv-1', start_wall=101.5)
    await session._audio_bytes_flush()

    assert [frame for frame in uncertain.sent if frame_type(frame) == 101] == []
    audio_frames = [frame for frame in replacement.sent if frame_type(frame) == 101]
    assert len(audio_frames) == 1
    timestamp = struct.unpack('d', audio_frames[0][4:12])[0]
    assert timestamp == 101.5 - (2 * rate * 2) / (rate * 2)
    assert audio_frames[0][12:] == run_a + run_b


@pytest.mark.anyio
async def test_spans_session_ack_enables_projected_runs_and_gap_splits():
    ws = FakePusherWebSocket(incoming=[audio_timeline_ack_frame()])
    session = make_session(
        ws=ws,
        config_overrides={'audio_timeline_spans': True, 'max_audio_buffer_size': 1_000_000},
    )
    await session.connect()

    rate = 8000
    run_a = b'\x01\x00' * rate
    run_b = b'\x02\x00' * rate
    session.audio_bytes_send(run_a, received_at=100.5, conversation_id='conv-1', start_wall=100.0)
    session.audio_bytes_send(run_b, received_at=101.5, conversation_id='conv-1', start_wall=101.5)
    await session._audio_bytes_flush()

    audio_frames = [frame for frame in ws.sent if frame_type(frame) == 101]
    assert len(audio_frames) == 2
    assert struct.unpack('d', audio_frames[0][4:12])[0] == 100.0
    assert struct.unpack('d', audio_frames[1][4:12])[0] == 101.5


@pytest.mark.anyio
async def test_spans_capability_loss_mid_recording_withholds_audio_then_resumes(monkeypatch):
    monkeypatch.setattr(pusher_session, 'AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS', 0.05)
    capable = FakePusherWebSocket(incoming=[audio_timeline_ack_frame()])
    capable_again = FakePusherWebSocket(incoming=[audio_timeline_ack_frame()])
    incapable = FakePusherWebSocket()
    sockets = [capable, incapable, capable_again]
    session = make_session(
        ws=capable,
        config_overrides={'audio_timeline_spans': True, 'max_audio_buffer_size': 1_000_000},
    )

    async def rotating_connector(
        uid, sample_rate, retries=5, is_active=None, client_kind='unknown', audio_timeline=None
    ):
        return sockets.pop(0)

    session.deps.connect_to_pusher = rotating_connector

    await session.connect()
    assert session.audio_timeline_active

    session.audio_bytes_send(b'abcd', received_at=100.0, conversation_id='conv-1', start_wall=99.9)
    session._mark_disconnected()
    session.reconnect_task.cancel()
    try:
        await session.reconnect_task
    except asyncio.CancelledError:
        pass
    session.reconnect_task = None

    session.pusher_connected = False
    await session.connect()
    assert session.audio_timeline_suspended

    await session._audio_bytes_flush()
    assert session.audio_total_size == 4
    assert [frame for frame in incapable.sent if frame_type(frame) == 101] == []

    session.pusher_connected = False
    await session.connect()
    assert not session.audio_timeline_suspended
    await session._audio_bytes_flush()
    audio_frames = [frame for frame in capable_again.sent if frame_type(frame) == 101]
    assert len(audio_frames) == 1
    assert struct.unpack('d', audio_frames[0][4:12])[0] == 99.9


@pytest.mark.anyio
async def test_replacement_socket_reannounces_conversation_before_audio():
    """The conversation announcement is socket-local, not session-local.

    A fresh pusher socket starts with no conversation bound, so the first
    audio flush on every installed socket must re-emit opcode 103 before 101;
    otherwise the pusher drops that audio unbound. Same-socket suppression and
    buffered run bindings are preserved.
    """
    first = FakePusherWebSocket()
    session = make_session(ws=first, config_overrides={'max_audio_buffer_size': 1_000_000})
    await session.connect()

    session.audio_bytes_send(b'abcd', received_at=100.0, conversation_id='conv-1')
    await session._audio_bytes_flush()
    session.audio_bytes_send(b'efgh', received_at=101.0, conversation_id='conv-1')
    await session._audio_bytes_flush()
    assert [frame_type(frame) for frame in first.sent] == [103, 101, 101]

    second = FakePusherWebSocket()

    async def next_connector(*args, **kwargs):
        return second

    session.deps.connect_to_pusher = next_connector
    session.pusher_connected = False
    await session.connect()

    session.audio_bytes_send(b'ijkl', received_at=102.0, conversation_id='conv-1')
    await session._audio_bytes_flush()
    assert [frame_type(frame) for frame in second.sent] == [103, 101]
    assert second.sent[0][4:].decode('utf-8') == 'conv-1'
    assert second.sent[1][12:] == b'ijkl'


@pytest.mark.anyio
async def test_late_ack_replaces_uncertain_socket_with_legacy_replacement(monkeypatch, caplog):
    """A timeline-negotiated socket that never ACKs is unverifiable: it must be
    closed and replaced by a socket connected without the timeline query.
    Legacy grouping/stamping may only ever reach the replacement."""
    monkeypatch.setattr(pusher_session, 'AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS', 0.05)
    uncertain = FakePusherWebSocket()
    replacement = FakePusherWebSocket()
    connect_queries = []
    sockets = [uncertain, replacement]

    async def connector(uid, sample_rate, retries=5, is_active=None, client_kind='unknown', audio_timeline=None):
        connect_queries.append(audio_timeline)
        return sockets.pop(0)

    session = make_session(
        config_overrides={'audio_timeline_spans': True, 'max_audio_buffer_size': 1_000_000},
        deps_overrides={'monotonic': time.monotonic},
    )
    session.deps.connect_to_pusher = connector
    await session.connect()

    assert connect_queries == [AUDIO_TIMELINE_PROTOCOL, None]
    assert uncertain.closed_codes, 'the uncertain socket must be closed before fallback'
    assert session.pusher_connected
    assert session.pusher_ws is replacement
    assert not session.audio_timeline_active
    assert not session.audio_timeline_suspended
    assert 'component=pusher from=audio_timeline to=legacy_audio' in caplog.text

    session.audio_bytes_send(b'abcd', received_at=100.0, conversation_id='conv-1', start_wall=99.9)
    session.audio_bytes_send(b'efgh', received_at=101.0, conversation_id='conv-1', start_wall=101.0)
    await session._audio_bytes_flush()

    assert [frame_type(frame) for frame in uncertain.sent] == [], 'no 101 or 103 may reach the uncertain socket'
    assert [frame_type(frame) for frame in replacement.sent] == [103, 101]
    assert replacement.sent[0][4:].decode('utf-8') == 'conv-1'
    assert replacement.sent[1][12:] == b'abcdefgh'
    assert struct.unpack('d', replacement.sent[1][4:12])[0] == 101.0 - (8 / (8000 * 2))


@pytest.mark.anyio
async def test_late_ack_failed_replacement_leaves_buffered_runs_disconnected(monkeypatch):
    """A failed replacement connect must leave the session disconnected and the
    buffered audio intact for a later attempt — never flushed on the old socket."""
    monkeypatch.setattr(pusher_session, 'AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS', 0.05)
    uncertain = FakePusherWebSocket()
    sockets = [uncertain, None]

    async def connector(uid, sample_rate, retries=5, is_active=None, client_kind='unknown', audio_timeline=None):
        return sockets.pop(0)

    session = make_session(
        config_overrides={'audio_timeline_spans': True},
        deps_overrides={'monotonic': time.monotonic},
    )
    session.deps.connect_to_pusher = connector
    session.audio_bytes_send(b'abcd', received_at=100.0, conversation_id='conv-1', start_wall=99.9)
    await session.connect()

    assert not session.pusher_connected
    assert session.pusher_ws is None
    assert uncertain.closed_codes
    assert [frame_type(frame) for frame in uncertain.sent] == []
    assert b''.join(run.data for run in session.audio_runs) == b'abcd'
    assert session.audio_total_size == 4


@pytest.mark.anyio
async def test_late_ack_close_failure_does_not_fall_back_on_uncertain_socket(monkeypatch):
    """If closing the uncertain socket fails, the session must not mark it
    connected nor silently fall back to legacy on it."""
    monkeypatch.setattr(pusher_session, 'AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS', 0.05)

    class FailingCloseWebSocket(FakePusherWebSocket):
        async def close(self, code=1000):
            raise RuntimeError('close failed')

    uncertain = FailingCloseWebSocket()
    replacement = FakePusherWebSocket()
    sockets = [uncertain, replacement]

    async def connector(uid, sample_rate, retries=5, is_active=None, client_kind='unknown', audio_timeline=None):
        return sockets.pop(0)

    session = make_session(
        config_overrides={'audio_timeline_spans': True},
        deps_overrides={'monotonic': time.monotonic},
    )
    session.deps.connect_to_pusher = connector
    await session.connect()

    assert not session.pusher_connected
    assert session.pusher_ws is uncertain, 'a failed close keeps the socket for a later drain attempt'
    assert sockets == [replacement], 'a failed close must not spend the replacement connection'
    assert [frame_type(frame) for frame in uncertain.sent] == []


@pytest.mark.anyio
async def test_ack_wait_cancellation_does_not_fall_back():
    """Cancelling the session while the ACK is pending must re-raise, not
    swallow the cancellation into a legacy downgrade."""
    uncertain = FakePusherWebSocket()
    replacement = FakePusherWebSocket()
    connect_queries = []
    sockets = [uncertain, replacement]

    async def connector(uid, sample_rate, retries=5, is_active=None, client_kind='unknown', audio_timeline=None):
        connect_queries.append(audio_timeline)
        return sockets.pop(0)

    session = make_session(
        config_overrides={'audio_timeline_spans': True},
        deps_overrides={'monotonic': time.monotonic},
    )
    session.deps.connect_to_pusher = connector
    task = asyncio.create_task(session.connect())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert connect_queries == [AUDIO_TIMELINE_PROTOCOL]
    assert uncertain.closed_codes == []
    assert not session.pusher_connected


def _timeline_ack_frame(**overrides):
    payload = {"type": "audio_timeline_ack", "version": AUDIO_TIMELINE_PROTOCOL}
    payload.update(overrides)
    return struct.pack("<I", 202) + json.dumps(payload).encode("utf-8")


async def _capable_timeline_session(monkeypatch, active_ref, sockets):
    """Connect once on a capable socket; the caller drives the reconnect."""
    monkeypatch.setattr(pusher_session, 'AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS', 0.01)

    async def connector(uid, sample_rate, retries=5, is_active=None, client_kind='unknown', audio_timeline=None):
        return sockets.pop(0)

    session = make_session(
        active_ref=active_ref,
        config_overrides={'audio_timeline_spans': True, 'audio_timeline_v2': False, 'max_audio_buffer_size': 16},
        deps_overrides={'connect_to_pusher': connector, 'monotonic': time.monotonic},
    )
    await session.connect()
    assert session.audio_timeline_active
    return session


async def _drive_suspension(session, active_ref):
    """Reconnect onto the silent socket; the ACK wait times out and the
    session keeps the socket but suspends timeline audio."""
    session.pusher_connected = False
    await session.connect()
    assert session.audio_timeline_suspended


@pytest.mark.anyio
@pytest.mark.parametrize('pending', [False, True])
async def test_late_ack_on_suspended_socket_resumes_and_flushes(monkeypatch, pending):
    """A late but valid ACK on the still-installed socket lifts the suspension
    and flushes the retained audio through the ordinary path — with and
    without a pending conversation request. The receive loop is already
    parked on the pending-request event when suspension begins."""
    active_ref = {"active": True}
    first = FakePusherWebSocket(incoming=[audio_timeline_ack_frame()])
    second = FakePusherWebSocket()
    session = await _capable_timeline_session(monkeypatch, active_ref, [first, second])
    assert session.config.max_audio_buffer_size == 16

    async def second_recv():
        while not second.incoming and active_ref['active']:
            await asyncio.sleep(0.005)
        return second.incoming.pop(0) if second.incoming else b''

    second.recv = second_recv
    receiver = asyncio.create_task(session.pusher_receive())
    await asyncio.sleep(0)
    await _drive_suspension(session, active_ref)
    assert session.pusher_ws is second

    session.audio_bytes_send(b'abcdefgh', received_at=100.0, conversation_id='conv-1', start_wall=99.9)
    await session._audio_bytes_flush()
    assert session.audio_total_size == 8
    assert [frame for frame in second.sent if frame_type(frame) == 101] == []
    session.transcript_send([{'id': 'seg-1', 'text': 'hi', 'speaker': 'SPEAKER_00', 'start': 0.0, 'end': 1.0}])
    await session._transcript_flush()
    assert [frame for frame in second.sent if frame_type(frame) == 102]

    if pending:
        await session.request_conversation_processing('conv-1')
    second.incoming.append(audio_timeline_ack_frame())
    deadline = time.monotonic() + 5
    while (session.audio_timeline_suspended or session.audio_total_size) and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    active_ref['active'] = False
    for _ in range(400):
        session.pending_request_event.set()
        if receiver.done():
            break
        await asyncio.sleep(0.005)
    await asyncio.wait_for(asyncio.shield(receiver), timeout=2)

    assert not session.audio_timeline_suspended
    assert session.pusher_connected
    assert session.pusher_ws is second
    assert session.audio_total_size == 0
    audio_frames = [frame for frame in second.sent if frame_type(frame) == 101]
    assert len(audio_frames) == 1
    assert struct.unpack('d', audio_frames[0][4:12])[0] == 99.9
    assert audio_frames[0][12:] == b'abcdefgh'

    session.audio_bytes_send(b'ijklmnop', received_at=100.5, conversation_id='conv-1', start_wall=100.4)
    session.audio_bytes_send(b'qrstuvwx', received_at=101.0, conversation_id='conv-1', start_wall=100.9)
    await session._audio_bytes_flush()
    audio_frames = [frame for frame in second.sent if frame_type(frame) == 101]
    payloads = b''.join(frame[12:] for frame in audio_frames)
    assert payloads == b'abcdefgh' + b'ijklmnop' + b'qrstuvwx'


@pytest.mark.anyio
@pytest.mark.parametrize(
    'frame',
    [
        _timeline_ack_frame(version=True),
        _timeline_ack_frame(version=AUDIO_TIMELINE_PROTOCOL - 1),
        _timeline_ack_frame(type='not_an_ack'),
        struct.pack('<I', 202) + b'not-json',
        struct.pack('<I', 202) + json.dumps([1, 2]).encode('utf-8'),
    ],
    ids=['bool_version', 'unsupported_version', 'wrong_type', 'malformed_json', 'non_dict'],
)
async def test_invalid_late_ack_never_resumes_suspension(monkeypatch, frame):
    """The ordinary receive loop holds a late ACK to the exact handshake
    validation; anything failing it leaves the suspension in place."""
    active_ref = {"active": True}
    first = FakePusherWebSocket(incoming=[audio_timeline_ack_frame()])
    second = FakePusherWebSocket()
    session = await _capable_timeline_session(monkeypatch, active_ref, [first, second])
    await _drive_suspension(session, active_ref)

    second.incoming.append(frame)
    second.on_recv = lambda: active_ref.update(active=False)
    await asyncio.wait_for(session.pusher_receive(), timeout=15)

    assert session.audio_timeline_suspended
    assert session.pusher_connected
    assert [f for f in second.sent if frame_type(f) == 101] == []


@pytest.mark.anyio
async def test_late_ack_on_replaced_socket_does_not_resume(monkeypatch):
    """If the socket the ACK was read from is no longer the installed one, the
    ACK belongs to a dead connection and must not lift the suspension."""
    active_ref = {"active": True}
    first = FakePusherWebSocket(incoming=[audio_timeline_ack_frame()])
    second = FakePusherWebSocket()
    third = FakePusherWebSocket()
    session = await _capable_timeline_session(monkeypatch, active_ref, [first, second])
    await _drive_suspension(session, active_ref)

    async def stale_ack():
        session.pusher_ws = third
        active_ref.update(active=False)
        return audio_timeline_ack_frame()

    second.recv = stale_ack
    await asyncio.wait_for(session.pusher_receive(), timeout=15)

    assert session.audio_timeline_suspended
    assert [f for f in second.sent if frame_type(f) == 101] == []
    assert [f for f in third.sent if frame_type(f) == 101] == []


@pytest.mark.anyio
async def test_late_ack_on_legacy_fallback_socket_is_ignored(monkeypatch):
    """The v1 replacement socket never requested the capability, so an
    unsolicited ACK on it can never promote it to timeline audio."""
    monkeypatch.setattr(pusher_session, 'AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS', 0.01)
    active_ref = {"active": True}
    uncertain = FakePusherWebSocket()
    fallback = FakePusherWebSocket()
    sockets = [uncertain, fallback]

    async def connector(uid, sample_rate, retries=5, is_active=None, client_kind='unknown', audio_timeline=None):
        return sockets.pop(0)

    session = make_session(
        active_ref=active_ref,
        config_overrides={'audio_timeline_spans': True, 'max_audio_buffer_size': 64},
        deps_overrides={'connect_to_pusher': connector, 'monotonic': time.monotonic},
    )
    await session.connect()
    assert session.pusher_ws is fallback
    assert not session.audio_timeline_active
    assert not session.audio_timeline_suspended

    session.audio_bytes_send(b'abcd', received_at=100.0, conversation_id='conv-1', start_wall=99.9)
    await session.request_conversation_processing('conv-1')
    fallback.incoming.append(audio_timeline_ack_frame())
    fallback.on_recv = lambda: active_ref.update(active=False)
    await session.pusher_receive()

    assert not session.audio_timeline_active
    assert not session.audio_timeline_suspended
    await session._audio_bytes_flush()
    audio_frames = [frame for frame in fallback.sent if frame_type(frame) == 101]
    assert len(audio_frames) == 1
    assert struct.unpack('d', audio_frames[0][4:12])[0] == 100.0 - (4 / (8000 * 2))


@pytest.mark.anyio
async def test_replaced_socket_close_does_not_disconnect_new_socket():
    """A ConnectionClosed raised by a replaced socket must not mark the newly
    installed socket disconnected."""
    active_ref = {"active": True}
    stale = FakePusherWebSocket()
    fresh = FakePusherWebSocket()
    session = make_session(ws=fresh, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing('conv-1')

    async def stale_close():
        session.pusher_ws = fresh
        session.pusher_connected = True
        active_ref.update(active=False)
        raise ConnectionClosedError(None, None)

    session.pusher_ws = stale
    stale.recv = stale_close
    await session.pusher_receive()

    assert session.pusher_connected
    assert session.pusher_ws is fresh
    assert session.reconnect_task is None

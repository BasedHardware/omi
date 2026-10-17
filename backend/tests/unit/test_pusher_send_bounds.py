"""Every protocol send on the session pusher socket honors the cancel bound.

Failure-Class: FC-teardown-socket-send-parks-past-drain-window — instance in
backend/utils/listen_pusher_session.py, the six send sites still using a raw
``pusher_ws.send`` while only ``request_conversation_processing`` honored
``PUSHER_SEND_CANCEL_BOUND_SECONDS`` (2026-10-16, backend-listen): teardown
drains the session's background tasks gracefully first (``cancel=False``)
and only force-cancels stragglers at the end of the window, so any task that
parks inside a non-cooperative websockets send — a send into a closing or
stalled socket whose open-check shields the close-completion wait from
cancellation — absorbs the force-cancel wait and surfaces as
``drain_tasks: N tasks ignored cancellation after 5s [listen_bg]``. The
finalization request send was bounded in the first pass; the same class of
park remained reachable through the transcript flush, the audio-run and
conversation-boundary frames, the speaker-sample request, the heartbeat,
and the late-ACK resume flush that runs inside the receive loop.

Contract under test: every protocol send on the session socket goes through
``_bounded_protocol_send``, which raises ``TimeoutError`` at the bound so
each caller's existing failure classification is preserved — the transcript
batch returns to its buffer, an audio envelope turns ``uncertain`` (v2) or
keeps its runs for a same-socket retry (legacy), a stalled conversation
header is not treated as synced, the speaker-sample request stays buffered,
a pending finalization request stays armed for the reconnect replay, a
connection close still marks the session disconnected, and a bound hit
never marks a healthy-connected session disconnected. Cancellation still
ends the caller: the bound never swallows the drain's force-cancel.
"""

import asyncio
import inspect
import json
import logging
import struct
import time

import pytest
from websockets.exceptions import ConnectionClosedError

import utils.listen_pusher_session as pusher_session
from utils.async_tasks import wait_for_event
from utils.listen_pusher_session import (
    ListenPusherSession,
    ListenPusherSessionConfig,
    ListenPusherSessionDeps,
)

# Read dynamically (module attribute) so the suite still collects — and the
# behavioral assertions still run and fail — on a tree without the fix.
SEND_BOUND = lambda: pusher_session.PUSHER_SEND_CANCEL_BOUND_SECONDS  # noqa: E731

logger = logging.getLogger(__name__)


class StalledSendSocket:
    """A connected socket whose send never completes (transport stalled)."""

    def __init__(self):
        self.sent = []
        self.send_gate = asyncio.Event()
        self.send_gate.clear()

    async def send(self, data):
        await self.send_gate.wait()
        self.sent.append(bytes(data))

    async def recv(self):
        await asyncio.sleep(30)

    async def close(self, code=1000):
        pass


class NonCooperativeSendSocket(StalledSendSocket):
    """The production websockets shape: send absorbs task cancellation.

    websockets' open-check shields the close-completion wait, so a cancel
    landing inside a send into a closing socket does not end the await —
    the calling task keeps parking exactly as the drain's force-cancel
    stragglers did.
    """

    def __init__(self):
        super().__init__()
        self._park = asyncio.Event()

    async def send(self, data):
        try:
            await self.send_gate.wait()
            self.sent.append(bytes(data))
        except asyncio.CancelledError:
            await asyncio.shield(self._park.wait())


class HealthySocket:
    def __init__(self, incoming=None):
        self.sent = []
        self.incoming = list(incoming or [])

    async def send(self, data):
        self.sent.append(bytes(data))

    async def recv(self):
        if self.incoming:
            return self.incoming.pop(0)
        await asyncio.sleep(30)

    async def close(self, code=1000):
        pass


def finalization_frame(conversation_id="conv-1"):
    payload = json.dumps({"conversation_id": conversation_id, "language": "en", "byok_keys": {}}).encode("utf-8")
    return struct.pack("<I", 104) + payload


def ack_frame():
    return struct.pack("<I", 202) + json.dumps({"type": "audio_timeline_ack", "version": 2}).encode("utf-8")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def make_session(*, ws=None, active_ref=None, deps_overrides=None, audio_timeline_v2=False, sockets=None):
    """A session wired like production: real wait_for_event (shutdown wake).

    ``sockets`` is consumed in order by each ``connect_to_pusher`` call
    (the last entry serves every further connect), so a test can install a
    replacement socket for a reconnect.
    """
    active_ref = active_ref if active_ref is not None else {"active": True}
    sockets = list(sockets if sockets is not None else [ws if ws is not None else HealthySocket()])

    async def connect_to_pusher(
        uid, sample_rate, retries=5, is_active=None, client_kind="unknown", audio_timeline=None
    ):
        return sockets.pop(0) if len(sockets) > 1 else sockets[0]

    deps_values = {
        "get_current_conversation_id": lambda: "conv-1",
        "is_active": lambda: active_ref["active"],
        "shutdown_event": asyncio.Event(),
        "get_byok_keys": lambda: {},
        "on_conversation_processed": lambda conversation_id: None,
        "wait_for_event": wait_for_event,
        "connect_to_pusher": connect_to_pusher,
    }
    if deps_overrides:
        deps_values.update(deps_overrides)
    config = ListenPusherSessionConfig(
        uid="uid-1",
        session_id="session-1",
        sample_rate=8000,
        is_multi_channel=False,
        language="en",
        audio_bytes_enabled=False,
        audio_timeline_v2=audio_timeline_v2,
        max_segment_buffer_size=3,
        max_audio_buffer_size=1024,
        max_pending_requests=3,
        max_pending_speaker_sample_requests=2,
    )
    return ListenPusherSession(config, ListenPusherSessionDeps(**deps_values))


def install_socket(session, ws):
    """Attach an already-open socket without going through connect()."""
    session.pusher_ws = ws
    session.pusher_connected = True


def presync_conversation(session, conversation_id="conv-1"):
    """Skip the opcode-103 header on the next flush so the stall lands on the
    audio/data frame under test instead of the conversation boundary."""
    session.last_synced_conversation_id = conversation_id


# ---------------------------------------------------------------------------
# The shared helper
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_bounded_send_delivers_a_healthy_frame_unchanged():
    session = make_session()
    ws = HealthySocket()
    await asyncio.wait_for(session._bounded_protocol_send(ws, b"frame"), timeout=1.0)
    assert ws.sent == [b"frame"], "a healthy send must be delivered untouched"


@pytest.mark.anyio
async def test_bounded_send_raises_timeout_at_the_bound_when_socket_stalls(monkeypatch):
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    session = make_session()
    ws = StalledSendSocket()
    started = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await session._bounded_protocol_send(ws, b"frame")
    assert time.monotonic() - started < 1.0, "the bound, not the socket, must end the wait"


@pytest.mark.anyio
async def test_bounded_send_frees_the_caller_even_when_the_send_absorbs_expiry_cancel(monkeypatch):
    """The production trap this helper exists for: a send that swallows its
    own cancellation (websockets' shielded open-check) also swallows an
    asyncio.timeout's expiry-cancel — only an unshielded wait on a separate
    task frees the caller."""
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    session = make_session()
    ws = NonCooperativeSendSocket()
    started = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await session._bounded_protocol_send(ws, b"frame")
    assert time.monotonic() - started < 1.0, "an absorbing send must not eat the bound"
    # The abandoned task parks until the socket itself answers; release it so
    # the test loop can close cleanly (websockets bounds this with close_timeout).
    ws.send_gate.set()
    await asyncio.sleep(0)


@pytest.mark.anyio
async def test_bounded_send_still_ends_when_cancelled_mid_stall(monkeypatch):
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 5.0)
    session = make_session()
    ws = StalledSendSocket()
    task = asyncio.create_task(session._bounded_protocol_send(ws, b"frame"))
    await asyncio.sleep(0.05)
    task.cancel()
    _, still_pending = await asyncio.wait({task}, timeout=1.0)
    assert not still_pending, "cancellation must end the bounded send, never be absorbed by it"
    ws.send_gate.set()
    await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Transcript flush
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_transcript_flush_returns_to_buffer_within_bound_when_send_stalls(monkeypatch):
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    session = make_session()
    install_socket(session, StalledSendSocket())
    session.transcript_send([{"text": "hello"}])

    started = time.monotonic()
    await asyncio.wait_for(session._transcript_flush(), timeout=2.0)
    assert time.monotonic() - started < 1.0, "a stalled transcript send must not park past the bound"
    assert len(session.segment_buffers) == 1, "unsent segments must return to the buffer"


@pytest.mark.anyio
async def test_transcript_flush_stall_does_not_mark_a_connected_session_disconnected(monkeypatch):
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    session = make_session()
    install_socket(session, StalledSendSocket())
    session.transcript_send([{"text": "hello"}])

    await asyncio.wait_for(session._transcript_flush(), timeout=2.0)
    assert session.pusher_connected, "a bound hit is a stalled send, not a closed connection"


@pytest.mark.anyio
async def test_transcript_flush_still_delivers_when_socket_is_healthy():
    session = make_session()
    ws = HealthySocket()
    install_socket(session, ws)
    session.transcript_send([{"text": "hello"}])

    await asyncio.wait_for(session._transcript_flush(), timeout=2.0)
    assert len(ws.sent) == 1, "the bound must not disturb the healthy flush"
    assert len(session.segment_buffers) == 0


# ---------------------------------------------------------------------------
# Audio flush
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_audio_flush_v2_stalled_send_marks_envelope_uncertain_and_ends(monkeypatch):
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    session = make_session()
    install_socket(session, StalledSendSocket())
    session.audio_timeline_active = True
    presync_conversation(session)
    session.audio_bytes_send(b"\x01" * 100, received_at=1000.0)

    await asyncio.wait_for(session._audio_bytes_flush(), timeout=2.0)
    assert len(session.audio_runs) == 1, "the stalled envelope must be re-queued for the next flush"
    assert session.audio_runs[0].uncertain, "a v2 send that may have parked is uncertain, not lost"
    assert session.pusher_connected, "a bound hit is not a disconnect"


@pytest.mark.anyio
async def test_audio_flush_legacy_stalled_send_keeps_runs_for_same_socket_retry(monkeypatch):
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    session = make_session()
    ws = StalledSendSocket()
    install_socket(session, ws)
    presync_conversation(session)
    session.audio_bytes_send(b"\x01" * 100, received_at=1000.0)

    await asyncio.wait_for(session._audio_bytes_flush(), timeout=2.0)
    assert len(session.audio_runs) == 1, "legacy runs must survive for the same-socket retry"
    assert session.audio_runs[0].failed_socket is ws, "the failed send pins the socket it may have used"


@pytest.mark.anyio
async def test_audio_flush_stalled_conversation_header_does_not_sync_conversation(monkeypatch):
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    session = make_session()
    install_socket(session, StalledSendSocket())
    session.audio_timeline_active = True
    session.audio_bytes_send(b"\x01" * 100, received_at=1000.0, conversation_id="conv-9")

    await asyncio.wait_for(session._audio_bytes_flush(), timeout=2.0)
    assert session.last_synced_conversation_id is None, "a header that never made it out must not be treated as sent"


@pytest.mark.anyio
async def test_audio_flush_still_sends_all_frames_when_socket_is_healthy():
    session = make_session()
    ws = HealthySocket()
    install_socket(session, ws)
    session.audio_bytes_send(b"\x01" * 100, received_at=1000.0, conversation_id="conv-1")

    await asyncio.wait_for(session._audio_bytes_flush(), timeout=2.0)
    assert len(ws.sent) == 2, "conversation header (103) plus audio frame (101)"
    assert struct.unpack("<I", ws.sent[0][:4])[0] == 103
    assert struct.unpack("<I", ws.sent[1][:4])[0] == 101
    assert len(session.audio_runs) == 0


@pytest.mark.anyio
async def test_audio_flush_v2_absorbing_send_still_frees_the_flush(monkeypatch):
    """The regression the asyncio.timeout first-pass would reintroduce: a
    send that absorbs its own cancellation also absorbs a timeout's
    expiry-cancel. The flush must still return within the bound and mark
    the envelope uncertain."""
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    session = make_session()
    ws = NonCooperativeSendSocket()
    install_socket(session, ws)
    session.audio_timeline_active = True
    presync_conversation(session)
    session.audio_bytes_send(b"\x01" * 100, received_at=1000.0)

    flush = asyncio.create_task(session._audio_bytes_flush())
    started = time.monotonic()
    try:
        _, still_pending = await asyncio.wait({flush}, timeout=2.0)
        assert not still_pending, "an absorbing send must not park the flush past the bound"
        assert time.monotonic() - started < 1.0
        assert len(session.audio_runs) == 1 and session.audio_runs[0].uncertain
        assert session.pusher_connected
    finally:
        # Release the abandoned send task and JOIN the flush so no task is
        # still parked in an absorbed cancellation when the test's event
        # loop closes (on a tree without the fix this assert-failed path is
        # exactly the production drain shape — release before teardown).
        ws.send_gate.set()
        await asyncio.wait({flush}, timeout=2.0)


@pytest.mark.anyio
async def test_conversation_header_is_resent_after_a_bound_hit_not_skipped(monkeypatch):
    """Ordering invariant across a bound hit: the 103 header that never made
    it out stays unsynced, so the post-reconnect flush re-sends the header
    before the audio instead of streaming audio into a conversation the
    pusher never saw announced."""
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    stalled = StalledSendSocket()
    healthy = HealthySocket()
    session = make_session(sockets=[stalled, healthy])
    await session.connect()
    session.audio_bytes_send(b"\x01" * 100, received_at=1000.0, conversation_id="conv-1")
    session.audio_timeline_active = True

    await asyncio.wait_for(session._audio_bytes_flush(), timeout=2.0)
    assert session.last_synced_conversation_id is None, "the stalled header must stay unsynced"

    # Reconnect installs the healthy socket; the next flush must resend the
    # conversation announcement ahead of the audio.
    session.reconnect_state = pusher_session.PusherReconnectState.RECONNECT_BACKOFF
    await session._connect()
    await asyncio.wait_for(session._audio_bytes_flush(), timeout=2.0)
    assert len(session.pusher_ws.sent) == 2, "header (103) then audio (101)"
    assert struct.unpack("<I", session.pusher_ws.sent[0][:4])[0] == 103
    assert struct.unpack("<I", session.pusher_ws.sent[1][:4])[0] == 101


# ---------------------------------------------------------------------------
# Speaker sample request
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_speaker_sample_request_returns_within_bound_when_send_stalls(monkeypatch):
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    session = make_session()
    install_socket(session, StalledSendSocket())

    started = time.monotonic()
    sent = await asyncio.wait_for(session.send_speaker_sample_request("person-1", "conv-1", ["seg-1"]), timeout=2.0)
    assert time.monotonic() - started < 1.0, "a stalled speaker-sample send must not park past the bound"
    assert sent is False
    assert len(session.pending_speaker_sample_requests) == 1, "the request must stay buffered for reconnect replay"


@pytest.mark.anyio
async def test_speaker_sample_request_still_delivers_when_socket_is_healthy():
    session = make_session()
    ws = HealthySocket()
    install_socket(session, ws)

    sent = await asyncio.wait_for(session.send_speaker_sample_request("person-1", "conv-1", ["seg-1"]), timeout=2.0)
    assert sent is True
    assert len(ws.sent) == 1 and ws.sent[0][:4] == struct.pack("<I", 105)


@pytest.mark.anyio
async def test_speaker_sample_request_replays_after_a_bound_hit(monkeypatch):
    """The buffered speaker-sample request must replay on the reconnected
    socket, mirroring the pending-conversation replay."""
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    stalled = StalledSendSocket()
    healthy = HealthySocket()
    session = make_session(sockets=[stalled, healthy])
    await session.connect()
    sent = await asyncio.wait_for(session.send_speaker_sample_request("person-1", "conv-1", ["seg-1"]), timeout=2.0)
    assert sent is False
    assert len(session.pending_speaker_sample_requests) == 1

    # Reconnect installs the healthy socket; the buffered request must replay.
    session.reconnect_state = pusher_session.PusherReconnectState.RECONNECT_BACKOFF
    await session._connect()
    assert len(session.pending_speaker_sample_requests) == 0, "the buffer drained on reconnect"
    assert any(f[:4] == struct.pack("<I", 105) for f in healthy.sent), "the 105 frame was replayed"


@pytest.mark.anyio
async def test_speaker_sample_request_closed_socket_still_marks_disconnected():
    session = make_session()

    class ClosedSocket(HealthySocket):
        async def send(self, data):
            raise ConnectionClosedError(None, None)

    install_socket(session, ClosedSocket())
    sent = await asyncio.wait_for(session.send_speaker_sample_request("person-1", "conv-1", ["seg-1"]), timeout=2.0)
    assert sent is False
    assert not session.pusher_connected, "a real connection close must keep its disconnect marking"


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_heartbeat_still_sends_when_socket_is_healthy(monkeypatch):
    """No-regression control for the heartbeat site: the bound must not
    disturb the healthy 100-frame heartbeat."""
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 5.0)
    active_ref = {"active": True}
    ws = HealthySocket()
    session = make_session(ws=ws, active_ref=active_ref)
    install_socket(session, ws)

    async def short_interval(event, seconds):
        await asyncio.sleep(0.05)
        return False

    session.deps.wait_for_event = short_interval
    heartbeat = asyncio.create_task(session.pusher_heartbeat(), name="ws:uid-1:pusher_heartbeat")
    try:
        _, still_pending = await asyncio.wait({heartbeat}, timeout=5.0)
        assert still_pending, "a healthy heartbeat loop keeps running"
        assert ws.sent and ws.sent[0][:4] == struct.pack("<I", 100), "the heartbeat frame went out"
    finally:
        heartbeat.cancel()
        await asyncio.wait({heartbeat}, timeout=1.0)


@pytest.mark.anyio
async def test_heartbeat_ends_within_drain_window_when_send_absorbs_cancellation(monkeypatch):
    """The production end-game on the sibling task: the drain's graceful
    window ends while the heartbeat sits in a cancellation-absorbing send.
    The bound must end the send; the loop then observes shutdown and exits.
    """
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    active_ref = {"active": True}
    ws = NonCooperativeSendSocket()
    session = make_session(ws=ws, active_ref=active_ref)
    install_socket(session, ws)

    async def shutdown_mid_send(event, seconds):
        session.deps.shutdown_event.set()
        active_ref["active"] = False
        return False

    session.deps.wait_for_event = shutdown_mid_send
    heartbeat = asyncio.create_task(session.pusher_heartbeat(), name="ws:uid-1:pusher_heartbeat")
    try:
        _, still_pending = await asyncio.wait({heartbeat}, timeout=2.0)
        assert not still_pending, "a stalled heartbeat send must not absorb the drain's force-cancel window"
    finally:
        # On a tree without the fix this releases the parked send so the
        # event loop can close instead of hanging on an absorbed cancel.
        ws.send_gate.set()
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Finalization request (refactored onto the shared helper)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_finalization_request_fails_open_within_bound_when_send_stalls(monkeypatch):
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    session = make_session()
    install_socket(session, StalledSendSocket())

    started = time.monotonic()
    sent = await asyncio.wait_for(session.request_conversation_processing("conv-1", "job-1", 2), timeout=2.0)
    assert time.monotonic() - started < 1.0, "the burst's send must stay bounded"
    assert sent is False
    assert "conv-1" in session.pending_conversation_requests, "a bounded send keeps the request armed for replay"


@pytest.mark.anyio
async def test_finalization_request_still_sends_when_socket_is_healthy():
    session = make_session()
    ws = HealthySocket()
    install_socket(session, ws)

    sent = await asyncio.wait_for(session.request_conversation_processing("conv-1", "job-1", 2), timeout=2.0)
    assert sent is True
    assert any(f[:4] == finalization_frame()[:4] for f in ws.sent)


@pytest.mark.anyio
async def test_finalization_request_replays_after_a_bound_hit(monkeypatch):
    """The fail-open contract end to end: a bounded send during a stall is
    replayed by the reconnect path."""
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    stalled = StalledSendSocket()
    healthy = HealthySocket()
    sockets = [stalled, healthy]
    session = make_session(sockets=sockets)
    await session.connect()
    await asyncio.wait_for(session.request_conversation_processing("conv-1", "job-1", 2), timeout=2.0)
    assert "conv-1" in session.pending_conversation_requests

    # Reconnect installs the healthy socket; the pending request must replay.
    session.reconnect_state = pusher_session.PusherReconnectState.RECONNECT_BACKOFF
    await session._connect()
    assert session.pusher_ws is healthy
    assert session.pusher_ws.sent, "the reconnect replay must re-send the pending request"


@pytest.mark.anyio
async def test_finalization_request_transport_error_still_returns_false():
    session = make_session()

    class ClosedSocket(HealthySocket):
        async def send(self, data):
            raise ConnectionClosedError(None, None)

    install_socket(session, ClosedSocket())
    sent = await asyncio.wait_for(session.request_conversation_processing("conv-1", "job-1", 2), timeout=2.0)
    assert sent is False


# ---------------------------------------------------------------------------
# Receive loop: late-ACK resume flush runs bounded inside pusher_receive
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_retry_burst_still_sends_when_session_goes_inactive_mid_burst():
    """Behavior preservation on the burst path: the deferral gates on the
    shutdown event only — a session that merely went inactive (the historic
    liveness contract) still sends its burst."""
    active_ref = {"active": True}
    ws = HealthySocket()
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)
    session.deps.now = lambda: 1000.0 + 200.0  # sent_at long expired

    async def recv_times_out_then_inactive():
        active_ref["active"] = False
        raise TimeoutError()

    ws.recv = recv_times_out_then_inactive
    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    try:
        _, still_pending = await asyncio.wait({receiver}, timeout=5.0)
        assert not still_pending, "loop ends when the session goes inactive"
    finally:
        if not receiver.done():
            receiver.cancel()
            await asyncio.wait({receiver}, timeout=1.0)

    assert any(f[:4] == finalization_frame()[:4] for f in ws.sent), "an inactive-but-live burst still sends"


@pytest.mark.anyio
async def test_late_ack_resume_flush_is_bounded_inside_the_receive_loop(monkeypatch):
    """The receive loop's own send path: a late ACK on a suspended v2 socket
    triggers the resume flush inside ``pusher_receive``. With a stalled
    socket the old code parked the whole loop in that flush; the bound must
    return the loop to service (envelope re-queued), and the loop must still
    end itself within one drain window once shutdown fires."""
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    active_ref = {"active": True}
    ws = StalledSendSocket()
    session = make_session(ws=ws, active_ref=active_ref, audio_timeline_v2=True)
    install_socket(session, ws)
    session.audio_timeline_active = True
    session.audio_timeline_suspended = True
    presync_conversation(session)
    session.audio_bytes_send(b"\x01" * 100, received_at=1000.0)
    session.pending_request_event.set()

    async def recv_serves_ack_then_parks():
        if ws is session.pusher_ws and not getattr(ws, "_ack_served", False):
            ws._ack_served = True
            return ack_frame()
        await asyncio.sleep(30)

    ws.recv = recv_serves_ack_then_parks
    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    try:
        # Wait past the 0.2s send bound: the resume flush must hit the bound,
        # re-queue the envelope, and hand the loop back to its recv park.
        await asyncio.sleep(0.45)
        assert not receiver.done(), "the loop must survive a stalled resume flush"
        assert session.audio_timeline_suspended is False, "the ACK resumed the timeline before the bounded flush ran"
        assert len(session.audio_runs) == 1, "the stalled envelope must be back in the buffer, not parked in a send"
        assert session.audio_runs[0].uncertain, "a v2 send that may have parked is uncertain, not lost"

        session.deps.shutdown_event.set()
        active_ref["active"] = False
        _, still_pending = await asyncio.wait({receiver}, timeout=2.0)
        assert not still_pending, "the loop must end inside one drain window despite the stalled resume flush"
    finally:
        if not receiver.done():
            receiver.cancel()
            await asyncio.wait({receiver}, timeout=1.0)


@pytest.mark.anyio
async def test_late_ack_resume_delivers_audio_on_a_healthy_socket():
    """No-regression guard: the resume path still delivers the buffered audio
    when the socket is healthy."""
    active_ref = {"active": True}
    ws = HealthySocket(incoming=[ack_frame()])
    session = make_session(ws=ws, active_ref=active_ref, audio_timeline_v2=True)
    install_socket(session, ws)
    session.audio_timeline_active = True
    session.audio_timeline_suspended = True
    presync_conversation(session)
    session.audio_bytes_send(b"\x01" * 100, received_at=1000.0)
    session.pending_request_event.set()

    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    try:
        await asyncio.sleep(0.3)
        assert session.audio_timeline_suspended is False
        assert len(ws.sent) == 1 and ws.sent[0][:4] == struct.pack("<I", 101), "the resumed flush delivered the audio"
        assert len(session.audio_runs) == 0
    finally:
        receiver.cancel()
        await asyncio.wait({receiver}, timeout=1.0)


# ---------------------------------------------------------------------------
# Structural guard
# ---------------------------------------------------------------------------


def test_every_protocol_send_on_the_session_socket_goes_through_the_bound():
    """The class invariant holds by construction: the bound helper is the
    only place allowed to call ``ws.send`` directly, and every teardown-
    reachable protocol send goes through it."""
    src = inspect.getsource(pusher_session)
    lines = src.splitlines()
    raw_send_lines = [
        (i, line.strip()) for i, line in enumerate(lines, start=1) if ".send(" in line and "_protocol_send(" not in line
    ]
    helper_def = next((i for i, line in enumerate(lines, start=1) if "async def _bounded_protocol_send" in line), None)
    assert helper_def is not None, "the bounded-send helper must exist"
    # The helper body itself is the one place allowed to call ws.send.
    helper_body = [i for i, _ in raw_send_lines if helper_def < i <= helper_def + 60]
    outside_helper = [(i, line) for i, line in raw_send_lines if not (helper_def < i <= helper_def + 60)]
    assert (
        not outside_helper
    ), f"raw sends outside _bounded_protocol_send at {outside_helper}; route every protocol send through the helper"
    assert helper_body, "the helper must perform the send itself"
    call_sites = [line.strip() for line in lines if "_bounded_protocol_send(" in line and "async def" not in line]
    assert len(call_sites) >= 7, (
        f"expected the seven protocol send sites to use the helper (transcript, 103 header, 101 audio, "
        f"standalone 103, speaker sample, heartbeat, finalization), got {len(call_sites)}: {call_sites}"
    )

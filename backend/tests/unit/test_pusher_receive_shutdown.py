"""pusher_receive must end itself inside one drain window once the session shuts down.

Failure-Class: FC-cancel-path-unbounded-terminal-send — instance in
backend/utils/listen_pusher_session.py ``pusher_receive`` /
``request_conversation_processing`` (2026-10-15, backend-listen): teardown
drains the session's supervised background tasks gracefully first —
``drain_monitored(cancel=False)`` with ``state.shutdown_event`` already set
(``end_session``) and ``state.active`` still True — so a lifetime task must
observe the shutdown event and end itself inside that window. The receive
loop observed nothing but ``deps.is_active``: its idle park
(``pending_request_event.wait()`` with a 5s timeout), its recv window, its
disconnected backoff, and its pending-request retry burst all ran straight
through the graceful drain, so the task reached the END of the window still
running, was force-cancelled, and drain_tasks logged
``drain_tasks: 1 tasks ignored cancellation after 5s [listen_bg]:
['ws:<uid>:pusher_receive']`` at ERROR. Production census (2026-10-15,
backend-listen, 40-minute window): 293 of 300 sampled occurrences name
``pusher_receive`` across 170 distinct uids; the sibling lifetime tasks that
park on the shutdown event (``pusher_heartbeat``, the flush loops) never
appear. The same loop's finalization retry burst can fire during teardown
(the recv window's timeout expiry is what triggers the burst), and its
protocol send rode an unbounded ``websockets`` send — a send that ignores
task cancellation while the connection is closing (the open-check shields
the close-completion wait), so a cancel landing inside it was absorbed until
the force-cancel wait expired.

Contract under test: every parked wait in the loop races the shutdown event
(``_race_shutdown``) and ends the loop when shutdown wins; the disconnected
backoff parks on the shutdown event; a retry burst that starts after
shutdown defers its sends to the reconnect replay; and the protocol send is
bounded (``PUSHER_SEND_CANCEL_BOUND_SECONDS``) so the non-cooperative send
cannot absorb the force-cancel window — a stalled send fails open and the
request stays pending for replay.
"""

import asyncio
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


class FakePusherWebSocket:
    def __init__(self, incoming=None):
        self.sent = []
        self.incoming = list(incoming or [])
        self.on_recv = None
        self.send_gate = asyncio.Event()
        self.send_gate.set()

    async def send(self, data):
        await self.send_gate.wait()
        self.sent.append(bytes(data))

    async def recv(self):
        if self.on_recv:
            self.on_recv()
        if self.incoming:
            return self.incoming.pop(0)
        await asyncio.sleep(30)

    async def close(self, code=1000):
        pass


def finalization_frame(conversation_id="conv-1"):
    payload = json.dumps({"conversation_id": conversation_id, "language": "en", "byok_keys": {}}).encode("utf-8")
    return struct.pack("<I", 104) + payload


@pytest.fixture
def anyio_backend():
    return "asyncio"


def make_session(*, ws=None, active_ref=None, deps_overrides=None):
    """A session wired like production: real wait_for_event (shutdown wake)."""
    active_ref = active_ref if active_ref is not None else {"active": True}

    async def connect_to_pusher(
        uid, sample_rate, retries=5, is_active=None, client_kind="unknown", audio_timeline=None
    ):
        return ws or FakePusherWebSocket()

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
        max_segment_buffer_size=3,
        max_audio_buffer_size=8,
        max_pending_requests=3,
        max_pending_speaker_sample_requests=2,
    )
    return ListenPusherSession(config, ListenPusherSessionDeps(**deps_values))


async def _join_within_drain_window(task, timeout=3.0):
    """Join the loop inside one bounded window; fail with the drain's signal.

    Mirrors drain_tasks' bounded force-cancel wait: the loop must reach its
    own exit inside the window. On failure the task is cancelled and joined
    so nothing leaks between tests.
    """
    _, still_pending = await asyncio.wait({task}, timeout=timeout)
    if still_pending:
        task.cancel()
        await asyncio.wait({task}, timeout=1.0)
        raise AssertionError("pusher_receive did not end itself inside one drain window")


async def _shutdown(session, active_ref):
    """The teardown order that precedes the graceful drain."""
    session.deps.shutdown_event.set()
    active_ref["active"] = False


@pytest.mark.anyio
async def test_idle_loop_ends_within_one_drain_window_after_shutdown():
    """The idle park (pending-request poll) must race shutdown, not ignore it.

    The production shape: a connected-but-idle session hangs up; teardown
    sets the shutdown event and drains without cancelling; the old loop sat
    in its 5s poll timeout re-arming through the whole graceful window.
    """
    active_ref = {"active": True}
    session = make_session(active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1")

    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    await asyncio.sleep(0.05)
    assert not receiver.done()
    await _shutdown(session, active_ref)
    started = time.monotonic()
    await _join_within_drain_window(receiver)
    assert time.monotonic() - started < 1.0, "shutdown wake must be immediate, not the poll interval"
    assert not receiver.cancelled(), "the loop must end on its own, before any force-cancel"


@pytest.mark.anyio
async def test_idle_loop_wakes_immediately_when_shutdown_fires_mid_wait():
    """Shutdown firing mid-park must wake the parked wait at once."""
    active_ref = {"active": True}
    session = make_session(active_ref=active_ref)

    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    await asyncio.sleep(0.05)
    assert not receiver.done()
    started = time.monotonic()
    session.deps.shutdown_event.set()
    await _join_within_drain_window(receiver)
    assert time.monotonic() - started < 1.0


@pytest.mark.anyio
async def test_idle_loop_stays_alive_without_shutdown():
    """The shutdown race must not end a healthy loop: no event, loop parks on."""
    active_ref = {"active": True}
    session = make_session(active_ref=active_ref)
    await session.connect()

    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    try:
        await asyncio.sleep(0.4)
        assert not receiver.done(), "a live session's receive loop must keep running"
    finally:
        receiver.cancel()
        await asyncio.wait({receiver}, timeout=1.0)


@pytest.mark.anyio
async def test_recv_park_ends_within_one_drain_window_after_shutdown():
    """The recv window is the park the failing sessions actually sat in."""
    active_ref = {"active": True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)

    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    await asyncio.sleep(0.05)
    assert not receiver.done()
    await _shutdown(session, active_ref)
    await _join_within_drain_window(receiver)
    assert not receiver.cancelled()


@pytest.mark.anyio
async def test_disconnected_backoff_ends_promptly_on_shutdown():
    """The not-connected backoff parks on the shutdown event itself."""
    active_ref = {"active": True}
    session = make_session(active_ref=active_ref)
    sent = await session.request_conversation_processing("conv-1")
    assert sent is False
    assert not session.pusher_connected

    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    await asyncio.sleep(0.05)
    assert not receiver.done()
    started = time.monotonic()
    await _shutdown(session, active_ref)
    await _join_within_drain_window(receiver)
    assert time.monotonic() - started < 1.0, "backoff must wake on shutdown, not sleep through it"


@pytest.mark.anyio
async def test_disconnected_backoff_keeps_looping_without_shutdown():
    """Without shutdown the backoff must keep the loop alive (retry on reconnect)."""
    active_ref = {"active": True}
    session = make_session(active_ref=active_ref)
    await session.request_conversation_processing("conv-1")

    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    try:
        await asyncio.sleep(0.6)
        assert not receiver.done(), "backoff must not end a live session's loop"
    finally:
        receiver.cancel()
        await asyncio.wait({receiver}, timeout=1.0)


@pytest.mark.anyio
async def test_suspended_timeline_park_ends_within_one_drain_window_after_shutdown():
    """A v2-suspended session parks through the same idle gate; it must exit too."""
    active_ref = {"active": True}
    session = make_session(active_ref=active_ref)
    await session.connect()
    session.audio_timeline_active = True
    session.audio_timeline_suspended = True

    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    await asyncio.sleep(0.05)
    assert not receiver.done()
    await _shutdown(session, active_ref)
    await _join_within_drain_window(receiver)


@pytest.mark.anyio
async def test_retry_burst_after_shutdown_defers_sends_to_replay():
    """A burst that would fire during teardown must not send; replay keeps it.

    The recv window's timeout expiry is what triggers the pending-request
    sweep — exactly when teardown is draining — so the burst is a teardown-
    time send path. With shutdown already observed, the entries stay armed
    for the durable replay instead of spending sends into a closing socket.
    """
    active_ref = {"active": True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)
    session.deps.now = lambda: 1000.0 + 200.0  # sent_at long expired
    sent_before_loop = len(ws.sent)

    async def recv_times_out_then_shutdown():
        session.deps.shutdown_event.set()
        raise ConnectionClosedError(None, None)

    ws.recv = recv_times_out_then_shutdown
    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    await _join_within_drain_window(receiver)

    assert len(ws.sent) == sent_before_loop, "no send into a shutting-down session"
    assert "conv-1" in session.pending_conversation_requests, "request must stay armed for the reconnect replay"


@pytest.mark.anyio
async def test_retry_burst_still_sends_when_session_is_live():
    """The deferral must not eat the live path: a live burst still sends."""
    active_ref = {"active": True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1", "job-1", 2)
    session.deps.now = lambda: 1000.0 + 200.0

    async def recv_fails_transiently_then_inactive():
        active_ref["active"] = False
        raise RuntimeError("transient recv failure")

    ws.recv = recv_fails_transiently_then_inactive
    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    try:
        _, still_pending = await asyncio.wait({receiver}, timeout=5.0)
        assert not still_pending, "loop should end when the session goes inactive"
    finally:
        if not receiver.done():
            receiver.cancel()
            await asyncio.wait({receiver}, timeout=1.0)

    assert any(f[:4] == finalization_frame()[:4] for f in ws.sent), "a live burst must still send the 104 frame"


@pytest.mark.anyio
async def test_frame_in_flight_is_processed_when_shutdown_fires_same_step():
    """A response that completed with the shutdown event in the same step is
    real data: it is processed before the loop exits (no dropped success)."""
    active_ref = {"active": True}
    processed = []
    ws = FakePusherWebSocket(
        incoming=[struct.pack("<I", 201) + json.dumps({"conversation_id": "conv-1", "success": True}).encode()]
    )
    session = make_session(ws=ws, active_ref=active_ref, deps_overrides={"on_conversation_processed": processed.append})
    await session.connect()
    await session.request_conversation_processing("conv-1")

    def complete_and_shutdown():
        session.deps.shutdown_event.set()
        active_ref["active"] = False

    ws.on_recv = complete_and_shutdown
    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    await _join_within_drain_window(receiver)
    assert processed == ["conv-1"], "the in-flight success must be processed, not dropped"


@pytest.mark.anyio
async def test_race_shutdown_returns_coro_result_when_coro_wins():
    active_ref = {"active": True}
    session = make_session(active_ref=active_ref)

    async def quick():
        return "payload"

    completed, result = await session._race_shutdown(quick(), session.deps.shutdown_event)
    assert completed is True
    assert result == "payload"


@pytest.mark.anyio
async def test_race_shutdown_reports_shutdown_when_event_wins():
    active_ref = {"active": True}
    session = make_session(active_ref=active_ref)

    async def parked():
        await asyncio.sleep(30)
        return "never"

    session.deps.shutdown_event.set()
    started = time.monotonic()
    completed, result = await session._race_shutdown(parked(), session.deps.shutdown_event)
    assert completed is False
    assert result is None
    assert time.monotonic() - started < 1.0


@pytest.mark.anyio
async def test_race_shutdown_propagates_the_parked_coros_exception():
    """The recv window's TimeoutError must still reach the loop's handler."""
    active_ref = {"active": True}
    session = make_session(active_ref=active_ref)

    async def times_out():
        await asyncio.sleep(0.05)
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        await session._race_shutdown(times_out(), session.deps.shutdown_event)


@pytest.mark.anyio
async def test_bounded_send_returns_within_bound_when_socket_stalls(monkeypatch):
    """The send hole: a websockets send can ignore cancellation while the
    connection is closing, so the burst's terminal send must be bounded."""
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    active_ref = {"active": True}
    ws = FakePusherWebSocket()
    ws.send_gate.clear()  # the send never completes
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()

    started = time.monotonic()
    sent = await asyncio.wait_for(session.request_conversation_processing("conv-1", "job-1", 2), timeout=2.0)
    elapsed = time.monotonic() - started
    assert sent is False
    assert elapsed < 1.0, f"bounded send must fail open fast, took {elapsed:.2f}s"
    assert "conv-1" in session.pending_conversation_requests, "stalled send keeps the request pending for replay"


@pytest.mark.anyio
async def test_bounded_send_success_returns_true_and_delivers_frame(monkeypatch):
    """The bound must not disturb the healthy path."""
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    active_ref = {"active": True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()

    sent = await session.request_conversation_processing("conv-1", "job-1", 2)
    assert sent is True
    assert any(f[:4] == finalization_frame()[:4] for f in ws.sent)


@pytest.mark.anyio
async def test_force_cancel_during_stalled_send_ends_the_task_within_the_bound(monkeypatch):
    """The exact production end-game: force-cancel lands while the burst's
    send is parked in the non-cooperative await. The task must end within
    the send bound + slack instead of absorbing the whole wait."""
    monkeypatch.setattr(pusher_session, "PUSHER_SEND_CANCEL_BOUND_SECONDS", 0.2)
    active_ref = {"active": True}
    ws = FakePusherWebSocket()
    ws.send_gate.clear()
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()

    task = asyncio.create_task(session.request_conversation_processing("conv-1", "job-1", 2))
    await asyncio.sleep(0.05)
    task.cancel()
    _, still_pending = await asyncio.wait({task}, timeout=1.5)
    assert not still_pending, "a cancelled stalled send must not absorb the drain window"


@pytest.mark.anyio
async def test_force_cancel_inside_recv_park_ends_the_task_promptly():
    """drain's force-cancel inside the recv park must still end the task.

    On the old loop this cancel surfaced as drain_tasks' ERROR line whenever
    it lost the race with the recv timeout; the contract is simply that the
    task ends promptly either way."""
    active_ref = {"active": True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    await session.request_conversation_processing("conv-1")

    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    await asyncio.sleep(0.05)
    receiver.cancel()
    _, still_pending = await asyncio.wait({receiver}, timeout=2.0)
    assert not still_pending, "force-cancel inside the recv park must end the task"


@pytest.mark.anyio
async def test_poll_wake_on_new_request_keeps_loop_alive():
    """A request buffered while the loop is parked must resume processing,
    not end the loop (the park completing is the keep-looping signal)."""
    active_ref = {"active": True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()

    receiver = asyncio.create_task(session.pusher_receive(), name="ws:uid-1:pusher_receive")
    try:
        await asyncio.sleep(0.05)
        assert not receiver.done()
        await session.request_conversation_processing("conv-1", "job-1", 2)
        await asyncio.sleep(0.3)
        assert not receiver.done(), "a parked loop woken by a new request must keep serving the socket"
    finally:
        receiver.cancel()
        await asyncio.wait({receiver}, timeout=1.0)

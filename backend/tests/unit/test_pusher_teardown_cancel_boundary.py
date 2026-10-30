"""Pod-teardown cancels end pusher sessions without an application traceback.

Failure-Class: FC-lifecycle-close-classified-by-transport-phase — a teardown
the system already recognizes as an expected lifecycle event must classify as
expected on every path it can arrive on. The pusher pod drain is such an
event: the chart's preStop hook flips ReadinessGate to DRAINING, the LB stops
admitting sessions, and clients replay buffered audio on the replacement
socket. But when uvicorn's ``--timeout-graceful-shutdown`` budget expired
while sessions were still draining, its hard cancel surfaced inside
``_websocket_util_trigger`` at whatever await the handler was parked on; the
handler re-raised every cancel unconditionally, so the expected teardown
escaped the ASGI application and uvicorn logged a full ERROR traceback per
drained connection (``Exception in ASGI application`` ending in
``CancelledError: Task cancelled, timeout graceful shutdown exceeded``) and
then attempted a terminal close on the transport its own shutdown had already
failed (``Error closing WebSocket``). Production 2026-10-29: 176 such lines,
all pusher, burst-shaped on rolling deploys (88 in the 19:00Z hour alone),
while backend-listen recorded zero — its teardown fits the grace window; the
pusher handler was the boundary re-raising platform churn as an application
fault.

The fix is two halves of one root cause. First, the mechanism: every accepted
session registers a drain waiter with ``ReadinessGate``; the preStop flip
gives the session ``PUSHER_DRAIN_WIND_DOWN_SECONDS`` to finish its queue
timers and in-flight uploads, then the session ends with a real 1001 Going
Away close frame and journey outcome ``success`` — an orderly close roughly a
minute before the platform cut, needing no uvicorn budget at all. Second, the
backstop: a ``CancelledError`` observed while the process is draining — or
within ``PUSHER_TEARDOWN_CANCEL_GRACE_SECONDS`` of the flip, so a restart
that bypassed the drain hook still classifies — is absorbed at the handler
(one INFO line, journey outcome ``cancelled``, close code 1006 so the
terminal SLI keeps its interrupted-session meaning). A cancel observed while
serving has no platform owner and keeps propagating as a fault. The terminal
close send shares the classifier: non-cancel faults stay absorbed (prior
behavior), teardown-window cancels are absorbed because uvicorn's shutdown
already failed that transport, and a serving-phase close cancel propagates.
A wind-down watcher that dies before the drain flip reports as the crash it
is — never as a benign session end.

The tests replay the production sequence: the session is accepted while the
gate serves, the gate flips to DRAINING (preStop), and the session either
winds down on the flip or — when the platform cancel wins the race — is
absorbed at the boundary, at both supervision and session admission.
"""

import asyncio
import json
import struct
from unittest.mock import MagicMock

import pytest
from starlette.websockets import WebSocketState

import routers.pusher as pusher
import utils.pusher_protocol as pusher_protocol
from utils.readiness import ReadinessGate


class FakeWebSocket:
    def __init__(self, frames=(), close_error=None, hang_receive=False):
        self.frames = list(frames)
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None
        self.close_calls = []
        self.close_error = close_error
        self.hang_receive = hang_receive

    async def accept(self):
        return None

    async def close(self, code=1000, reason=None):
        self.close_calls.append(code)
        if self.close_error is not None:
            raise self.close_error
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED

    async def receive_bytes(self):
        if self.frames:
            return self.frames.pop(0)
        if self.hang_receive:
            # A live session parked on receive: the wind-down flip must end it.
            await asyncio.sleep(3600)
        raise asyncio.CancelledError


class _GateStub:
    """Mutable stub over the gate seam the handler and classifier read.

    Mirrors the real waiter contract: events issued by ``drain_wait_event``
    are registered and get set by ``flip_to_draining``.
    """

    def __init__(self):
        self.serving = True
        self.drain_age = None
        self._waiters = []

    def flip_to_draining(self, drain_age=2.0):
        self.serving = False
        self.drain_age = drain_age
        for event in self._waiters:
            event.set()

    def is_serving(self):
        return self.serving

    def drain_age_seconds(self):
        return self.drain_age

    def drain_wait_event(self):
        event = asyncio.Event()
        if not self.serving:
            event.set()
        else:
            self._waiters.append(event)
        return event

    def remove_drain_wait_event(self, event):
        try:
            self._waiters.remove(event)
        except ValueError:
            pass


def _set_gate(monkeypatch) -> _GateStub:
    stub = _GateStub()
    monkeypatch.setattr(pusher, 'ReadinessGate', stub)
    return stub


def _poke_real_gate(monotonic_drain_start):
    """Set the real singleton's state and return a restore finalizer."""

    saved_state = ReadinessGate._state
    saved_age = ReadinessGate._drain_started_monotonic
    ReadinessGate._state = 'DRAINING' if monotonic_drain_start is not None else 'SERVING'
    ReadinessGate._drain_started_monotonic = monotonic_drain_start

    def _restore():
        ReadinessGate._state = saved_state
        ReadinessGate._drain_started_monotonic = saved_age

    return _restore


class TestTeardownCancelClassifier:
    """Truth table of _teardown_cancel_observed against the real gate."""

    def test_serving_cancel_is_not_teardown(self):
        restore = _poke_real_gate(None)
        try:
            assert pusher._teardown_cancel_observed() is False
        finally:
            restore()

    def test_fresh_drain_flip_is_teardown(self):
        import time

        restore = _poke_real_gate(time.monotonic())  # flipped this instant
        try:
            assert pusher._teardown_cancel_observed() is True
        finally:
            restore()

    def test_drain_flip_inside_window_is_teardown(self):
        import time

        restore = _poke_real_gate(time.monotonic() - pusher.PUSHER_TEARDOWN_CANCEL_GRACE_SECONDS / 2.0)
        try:
            assert pusher._teardown_cancel_observed() is True
        finally:
            restore()

    def test_old_drain_beyond_window_is_not_teardown(self):
        restore = _poke_real_gate(-1e12)  # drained "ages ago"
        try:
            assert pusher._teardown_cancel_observed() is False
        finally:
            restore()

    def test_window_is_positive_and_inside_uvicorn_budget(self):
        # The window is a classification window, not a shutdown budget: it must
        # stay positive and bounded well inside uvicorn's own 60s graceful
        # budget (prod CMD) so a long drain still ends in a loud cancel.
        assert 0.0 < pusher.PUSHER_TEARDOWN_CANCEL_GRACE_SECONDS < 60.0


class TestCloseBestEffort:
    @pytest.mark.asyncio
    async def test_close_not_connected_is_skipped(self):
        ws = FakeWebSocket()
        ws.client_state = WebSocketState.DISCONNECTED
        await pusher._close_websocket_best_effort(ws, 1006, 'uid')
        assert ws.close_calls == []

    @pytest.mark.asyncio
    async def test_close_connected_sends_code(self):
        ws = FakeWebSocket()
        await pusher._close_websocket_best_effort(ws, 1006, 'uid')
        assert ws.close_calls == [1006]
        assert ws.close_code == 1006

    @pytest.mark.asyncio
    async def test_close_fault_is_absorbed_without_cancel(self):
        ws = FakeWebSocket(close_error=RuntimeError('transport closed'))
        await pusher._close_websocket_best_effort(ws, 1006, 'uid')
        assert ws.close_calls == [1006]  # attempted, fault absorbed

    @pytest.mark.asyncio
    async def test_close_cancel_inside_teardown_window_is_absorbed(self, monkeypatch):
        _set_gate(monkeypatch).flip_to_draining(drain_age=1.0)
        ws = FakeWebSocket(close_error=asyncio.CancelledError())
        await pusher._close_websocket_best_effort(ws, 1006, 'uid')
        assert ws.close_calls == [1006]

    @pytest.mark.asyncio
    async def test_close_cancel_while_serving_propagates(self, monkeypatch):
        _set_gate(monkeypatch)  # stays serving
        ws = FakeWebSocket(close_error=asyncio.CancelledError())
        with pytest.raises(asyncio.CancelledError):
            await pusher._close_websocket_best_effort(ws, 1006, 'uid')


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: False)
    monkeypatch.setattr(pusher, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', MagicMock())
    monkeypatch.setattr(pusher, 'PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS', MagicMock())
    journeys = []

    def _journey_factory(name):
        attempt = MagicMock()
        attempt.name = name
        journeys.append(attempt)
        return attempt

    monkeypatch.setattr(pusher, 'JourneyAttempt', _journey_factory)
    return journeys


def _supervise_that_flips_then_cancels(gate, drain_age=2.0):
    """Production cancel sequence: preStop flips the gate, then uvicorn's
    hard cancel lands on the supervised session."""

    async def _supervise(**kwargs):
        gate.flip_to_draining(drain_age=drain_age)
        asyncio.current_task().cancel()
        await asyncio.sleep(0)
        return MagicMock(reason='never')

    return _supervise


def _supervise_that_raises(gate):
    async def _supervise(**kwargs):
        gate.flip_to_draining(drain_age=1.0)
        raise RuntimeError('receive loop exploded')

    return _supervise


def _admission_read_that_flips_then_cancels(gate, drain_age=0.5):
    async def _read(pool, fn, *args):
        gate.flip_to_draining(drain_age=drain_age)
        asyncio.current_task().cancel()
        await asyncio.sleep(0)

    return _read


class TestSupervisionTeardownCancel:
    """The production surface: uvicorn's hard cancel during supervised drain."""

    async def _run_handler(self):
        ws = FakeWebSocket()
        task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid', 8000))
        return ws, task

    @pytest.mark.asyncio
    async def test_teardown_cancel_is_absorbed_with_cancelled_outcome(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'supervise_tasks', _supervise_that_flips_then_cancels(gate))
        ws, task = await self._run_handler()

        await task  # absorbed: no CancelledError escapes the handler

        assert ws.close_calls == [1006]
        assert ws.close_code == 1006
        assert len(runtime) == 1
        runtime[0].finish.assert_called_once_with('cancelled')

    @pytest.mark.asyncio
    async def test_serving_cancel_still_propagates(self, runtime, monkeypatch):
        _set_gate(monkeypatch)  # never flips: no platform owner

        async def _supervise_serving_cancel(**kwargs):
            asyncio.current_task().cancel()
            await asyncio.sleep(0)
            return MagicMock(reason='never')

        monkeypatch.setattr(pusher, 'supervise_tasks', _supervise_serving_cancel)
        task = asyncio.create_task(pusher._websocket_util_trigger(FakeWebSocket(), 'uid', 8000))

        with pytest.raises(asyncio.CancelledError):
            await task

        runtime[0].finish.assert_called_once_with('cancelled')
        # Gauge released on both paths — the finally boundary is unconditional.
        pusher.PUSHER_ACTIVE_WS_CONNECTIONS.dec.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_ordinary_exception_still_fails_session_loudly(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'supervise_tasks', _supervise_that_raises(gate))
        ws, task = await self._run_handler()

        await task  # the Exception is handled (1011), never escapes

        runtime[0].finish.assert_called_once_with('failure')
        assert ws.close_calls == [1011]

    @pytest.mark.asyncio
    async def test_teardown_cancel_after_window_expiry_propagates(self, runtime, monkeypatch):
        # A cancel observed long after the drain flip (window elapsed, gate
        # still DRAINING) is no longer attributable to the teardown window.
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'supervise_tasks', _supervise_that_flips_then_cancels(gate, drain_age=1e9))
        ws, task = await self._run_handler()

        with pytest.raises(asyncio.CancelledError):
            await task

        runtime[0].finish.assert_called_once_with('cancelled')


class TestAdmissionTeardownCancel:
    """Same boundary before supervision: the session-admission profile reads.

    Production shape: the drain lands while an admission read is in flight —
    the fake read flips the gate, then the cancel arrives.
    """

    @pytest.mark.asyncio
    async def test_admission_teardown_cancel_is_absorbed(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'run_blocking', _admission_read_that_flips_then_cancels(gate))
        ws = FakeWebSocket()

        await pusher._websocket_util_trigger(ws, 'uid', 8000)

        runtime[0].finish.assert_called_once_with('cancelled')
        # No gauge has been acquired yet at admission time.
        pusher.PUSHER_ACTIVE_WS_CONNECTIONS.dec.assert_not_called()
        assert ws.close_calls == [1006]

    @pytest.mark.asyncio
    async def test_admission_serving_cancel_propagates(self, runtime, monkeypatch):
        _set_gate(monkeypatch)  # stays serving

        async def _read(pool, fn, *args):
            asyncio.current_task().cancel()
            await asyncio.sleep(0)

        monkeypatch.setattr(pusher, 'run_blocking', _read)
        ws = FakeWebSocket()

        with pytest.raises(asyncio.CancelledError):
            await pusher._websocket_util_trigger(ws, 'uid', 8000)

        runtime[0].finish.assert_called_once_with('cancelled')


class TestDrainWindDown:
    """The orderly wind-down: the drain flip itself ends sessions with 1001.

    Production shape: session accepted while serving, preStop flips the gate,
    the watcher gives the session its wind-down window and closes with
    1001 Going Away — no uvicorn budget, no hard cancel, no traceback.
    """

    async def _run_handler(self, hang_receive=False):
        ws = FakeWebSocket(hang_receive=hang_receive)
        task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid', 8000))
        return ws, task

    @pytest.mark.asyncio
    async def test_drain_flip_ends_session_with_1001(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.0)
        ws, task = await self._run_handler(hang_receive=True)
        await asyncio.sleep(0.05)  # session parked in supervision, serving

        gate.flip_to_draining(drain_age=0.0)  # preStop fires
        await task

        assert ws.close_calls == [1001]
        assert ws.close_code == 1001

    @pytest.mark.asyncio
    async def test_winddown_outcome_is_success_not_failure(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.0)
        ws, task = await self._run_handler(hang_receive=True)
        await asyncio.sleep(0.05)
        gate.flip_to_draining(drain_age=0.0)
        await task

        runtime[0].finish.assert_called_once_with('success')
        pusher.PUSHER_ACTIVE_WS_CONNECTIONS.dec.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_winddown_completes_without_uvicorn_budget(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.0)
        ws, task = await self._run_handler(hang_receive=True)
        await asyncio.sleep(0.05)
        gate.flip_to_draining(drain_age=0.0)

        # The whole point: session end needs no 60s platform budget.
        await asyncio.wait_for(task, timeout=3.0)

    @pytest.mark.asyncio
    async def test_winddown_never_marks_application_failure(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.0)
        ws, task = await self._run_handler(hang_receive=True)
        await asyncio.sleep(0.05)
        gate.flip_to_draining(drain_age=0.0)
        await task

        # outcome derives from close code 1001 + application_failed=False.
        assert pusher.pusher_session_outcome(1001, application_failed=False) == 'success'
        assert ws.close_code == 1001

    @pytest.mark.asyncio
    async def test_broken_watcher_before_flip_is_not_benign(self, runtime, monkeypatch):
        # A wind-down watcher that dies before the drain flip must not let the
        # session end silently as a success-shaped teardown: it reports as the
        # crash it is, exactly like any other monitored task.
        _set_gate(monkeypatch)

        async def supervise_watcher_crash(**kwargs):
            return MagicMock(reason='crash', task_name='ws:uid:drain_winddown')

        monkeypatch.setattr(pusher, 'supervise_tasks', supervise_watcher_crash)
        ws = FakeWebSocket()

        await pusher._websocket_util_trigger(ws, 'uid', 8000)

        runtime[0].finish.assert_called_once_with('failure')
        assert ws.close_calls == [1011]

    @pytest.mark.asyncio
    async def test_client_disconnect_without_drain_keeps_existing_contract(self, runtime, monkeypatch):
        _set_gate(monkeypatch)
        ws, task = await self._run_handler()
        # FakeWebSocket raises CancelledError out of receive_bytes once its
        # (empty) frame list is exhausted: receive ends cancelled, supervisor
        # reports disconnect, session closes 1000 like it always did.
        await task
        assert ws.close_calls == [1000]

    @pytest.mark.asyncio
    async def test_winddown_window_constant_sized_inside_uvicorn_budget(self):
        # Wind-down + bg drain must fit inside uvicorn's 60s graceful budget
        # (prod CMD) so the orderly close wins the race it exists to win.
        assert 0.0 < pusher.PUSHER_DRAIN_WIND_DOWN_SECONDS < 60.0 - pusher.BG_DRAIN_TIMEOUT


class TestReadinessDrainWaiters:
    """The gate side: waiter registration, flip wake-up, weak registry."""

    def test_drain_flip_wakes_registered_waiter(self):
        ReadinessGate.reset_for_test()
        event = None
        try:
            event = ReadinessGate.drain_wait_event()
            assert event.is_set() is False
            ReadinessGate.begin_drain()
            assert event.is_set() is True
        finally:
            if event is not None:
                ReadinessGate.remove_drain_wait_event(event)
            ReadinessGate.reset_for_test()

    def test_late_subscriber_gets_preset_event(self):
        import time

        restore = _poke_real_gate(time.monotonic())
        try:
            event = ReadinessGate.drain_wait_event()
            assert event.is_set() is True  # never registered: preset, no leak
            assert len(ReadinessGate._drain_listeners) == 0
        finally:
            restore()

    def test_waiter_registry_is_weak(self):
        import gc

        ReadinessGate.reset_for_test()
        event = ReadinessGate.drain_wait_event()
        assert len(ReadinessGate._drain_listeners) == 1
        del event
        gc.collect()
        assert len(ReadinessGate._drain_listeners) == 0

    def test_reset_for_test_clears_waiters(self):
        ReadinessGate.reset_for_test()
        event = ReadinessGate.drain_wait_event()
        # Hold the reference: the WeakSet must not have collected it.
        assert len(ReadinessGate._drain_listeners) == 1
        ReadinessGate.reset_for_test()
        assert len(ReadinessGate._drain_listeners) == 0
        ReadinessGate.remove_drain_wait_event(event)  # idempotent after clear


class TestWindDownDataPreservation:
    """The wind-down window exists to preserve queued session data.

    Production shape: a session mid-recording has queued private-cloud audio
    and transcripts when preStop fires. The 25s window plus the bg drain must
    land that data (uploads, dispatches) before the session closes — the whole
    reason the orderly close beats the platform cut.
    """

    def _passthrough_blocking(self):
        """run_blocking stub that calls through for everything. Admission
        reads are monkeypatched on ``pusher.users_db`` by the test, so the
        call-through reaches the fixtures (never real Firestore); the
        name-matching in an earlier draft of this stub silently shadowed
        those monkeypatches with ``None`` and the private-cloud branch
        never ran."""

        async def _run_blocking(pool, fn, *args, **kwargs):
            return fn(*args, **kwargs)

        return _run_blocking

    @pytest.mark.asyncio
    async def test_winddown_uploads_queued_private_cloud_audio(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        # A real (short) window: the workers must land the data while the
        # session is still winding down — the production contract (25s window,
        # workers flush on their timers inside it).
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.5)
        # Same stub set as the deleted-conversation sync harness: admission
        # reads and storage seams all fixture-backed, nothing real touched.
        monkeypatch.setattr(pusher, 'is_audio_merge_dispatch_enabled', lambda: False)
        monkeypatch.setattr(pusher, 'schedule_person_voice_learning_retry', lambda *args, **kwargs: None)
        monkeypatch.setattr(pusher.conversations_db, 'create_audio_files_from_chunks', lambda uid, conversation_id: [])
        # Flush every queued chunk on the next worker tick instead of after 60s
        # of audio (same technique as the deleted-conversation sync harness).
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0.0)
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_BATCH_MAX_AGE', 0.0)
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.01)
        monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
        monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
        upload = MagicMock(return_value=None)
        monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
        ws = FakeWebSocket(
            frames=[
                struct.pack('<I', 103) + b'conv-1',
                struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\x01\x02',
            ],
            hang_receive=True,
        )
        task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid', 8000))
        await asyncio.sleep(0.05)

        gate.flip_to_draining(drain_age=0.0)
        await task

        # The 2-byte tail buffer was flushed by receive teardown, queued, and
        # uploaded during the drain — not dropped with the socket.
        assert upload.call_count >= 1
        uploaded_chunks = upload.call_args[0][0]
        assert uploaded_chunks[0]['data'] == b'\x01\x02'
        assert ws.close_calls == [1001]

    @pytest.mark.asyncio
    async def test_winddown_dispatches_queued_transcripts(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.5)
        monkeypatch.setattr(pusher, 'TRANSCRIPT_QUEUE_FLUSH_INTERVAL', 0.01)
        monkeypatch.setattr(pusher, 'run_blocking', self._passthrough_blocking())
        integrations = MagicMock()
        webhook = MagicMock()

        async def _record(*args, **kwargs):
            return None

        integrations.side_effect = _record
        webhook.side_effect = _record
        monkeypatch.setattr(pusher, 'trigger_realtime_integrations', integrations)
        monkeypatch.setattr(pusher, 'realtime_transcript_webhook', webhook)
        ws = FakeWebSocket(
            frames=[
                struct.pack('<I', 103) + b'conv-1',
                struct.pack('<I', 102) + json.dumps({'segments': [{'text': 'hello'}], 'memory_id': 'conv-1'}).encode(),
            ],
            hang_receive=True,
        )
        task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid', 8000))
        await asyncio.sleep(0.05)

        gate.flip_to_draining(drain_age=0.0)
        await task

        assert integrations.call_count == 1
        assert webhook.call_count == 1
        assert ws.close_calls == [1001]

    @pytest.mark.asyncio
    async def test_drain_lane_retries_failed_upload_without_waiting(self, runtime, monkeypatch):
        # During drain (websocket_active False) the ready lane skips the
        # retry_at wait: a failed upload retries immediately so the bounded
        # drain is spent landing data, not sleeping.
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.5)
        monkeypatch.setattr(pusher, 'run_blocking', self._passthrough_blocking())
        monkeypatch.setattr(pusher, 'is_audio_merge_dispatch_enabled', lambda: False)
        monkeypatch.setattr(pusher, 'schedule_person_voice_learning_retry', lambda *args, **kwargs: None)
        monkeypatch.setattr(pusher.conversations_db, 'create_audio_files_from_chunks', lambda uid, conversation_id: [])
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0.0)
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_BATCH_MAX_AGE', 0.0)
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.01)
        monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
        monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
        upload = MagicMock(side_effect=[RuntimeError('transient'), None, None])
        monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
        monkeypatch.setattr(pusher.conversations_db, 'create_audio_files_from_chunks', MagicMock(return_value=[]))
        ws = FakeWebSocket(
            frames=[
                struct.pack('<I', 103) + b'conv-1',
                struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\x03\x04',
            ],
            hang_receive=True,
        )
        task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid', 8000))
        await asyncio.sleep(0.05)

        gate.flip_to_draining(drain_age=0.0)
        await task

        # First attempt fails, the drain-lane retry lands it without waiting
        # for the retry_at delay (no second failure injected).
        assert upload.call_count == 2
        assert ws.close_calls == [1001]

    @pytest.mark.asyncio
    async def test_winddown_processes_queued_audio_bytes_and_stays_bounded(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.5)
        monkeypatch.setattr(pusher, 'run_blocking', self._passthrough_blocking())
        monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: 4)
        webhook = MagicMock()

        async def _record(*args, **kwargs):
            return None

        webhook.side_effect = _record
        monkeypatch.setattr(pusher, 'send_audio_bytes_developer_webhook', webhook)
        payload = b'\x00' * (8000 * 4 * 2 + 2)  # just over the 4s webhook threshold at 8 kHz
        ws = FakeWebSocket(frames=[struct.pack('<I', 101) + struct.pack('d', 1.0) + payload], hang_receive=True)
        task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid', 8000))
        await asyncio.sleep(0.05)

        gate.flip_to_draining(drain_age=0.0)
        await asyncio.wait_for(task, timeout=5.0)  # bounded: the consumer must exit

        assert webhook.call_count == 1
        assert ws.close_calls == [1001]

    @pytest.mark.asyncio
    async def test_heartbeat_frames_do_not_block_winddown(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.0)
        heartbeat = struct.pack('<I', 100)
        ws = FakeWebSocket(frames=[heartbeat, heartbeat], hang_receive=True)
        task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid', 8000))
        await asyncio.sleep(0.05)

        gate.flip_to_draining(drain_age=0.0)
        await task

        assert ws.close_calls == [1001]

    @pytest.mark.asyncio
    async def test_malformed_frame_still_closes_1003_with_watcher_alive(self, runtime, monkeypatch):
        # The wind-down watcher must not alter the protocol-error path: a
        # malformed frame during a fully-served session still closes 1003,
        # exactly as before the boundary existed.
        _set_gate(monkeypatch)
        bad_frame = struct.pack('<I', 102) + b'{'
        ws = FakeWebSocket(frames=[bad_frame], hang_receive=True)

        await pusher._websocket_util_trigger(ws, 'uid', 8000)

        assert ws.close_calls == [1003]

    @pytest.mark.asyncio
    async def test_waiter_unsubscribed_after_normal_session_end(self, runtime, monkeypatch):
        # Registry hygiene: a session that ends normally (client disconnect,
        # no drain) must leave its drain waiter unsubscribed — the WeakSet
        # would eventually collect it anyway, but the explicit removal keeps
        # the registry exactly as large as the live session count.
        gate = _set_gate(monkeypatch)
        ws = FakeWebSocket()
        task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid', 8000))

        await task  # client disconnect, gate never flipped

        assert gate.serving is True
        assert gate._waiters == []  # removed in the finally boundary

    @pytest.mark.asyncio
    async def test_conversation_switch_flush_lands_during_winddown(self, runtime, monkeypatch):
        # A conversation switch (opcode 103) flushes the old conversation's
        # chunk through the switch boundary; that queued chunk must land in
        # GCS during the wind-down window like any other queued data.
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.5)
        monkeypatch.setattr(pusher, 'run_blocking', self._passthrough_blocking())
        monkeypatch.setattr(pusher, 'is_audio_merge_dispatch_enabled', lambda: False)
        monkeypatch.setattr(pusher, 'schedule_person_voice_learning_retry', lambda *args, **kwargs: None)
        monkeypatch.setattr(pusher.conversations_db, 'create_audio_files_from_chunks', lambda uid, conversation_id: [])
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 60.0)  # real threshold: chunk holds
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_BATCH_MAX_AGE', 60.0)
        monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.01)
        monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
        monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
        upload = MagicMock(return_value=None)
        monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
        ws = FakeWebSocket(
            frames=[
                struct.pack('<I', 103) + b'conv-A',
                struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\x01\x02',
                struct.pack('<I', 103) + b'conv-B',  # switch: flushes conv-A's held chunk
            ],
            hang_receive=True,
        )
        task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid', 8000))
        await asyncio.sleep(0.05)
        assert upload.call_count == 0  # held in the 60s chunk buffer

        gate.flip_to_draining(drain_age=0.0)
        await task

        # The switch-flushed chunk landed during the wind-down, not lost.
        assert upload.call_count == 1
        assert upload.call_args[0][0][0]['data'] == b'\x01\x02'
        assert ws.close_calls == [1001]


class TestWindDownLifecycleEdges:
    """Admission-time flips, close-fault paths, and supervisor precedence."""

    @pytest.mark.asyncio
    async def test_drain_flip_during_admission_still_winds_down(self, runtime, monkeypatch):
        # Production shape: preStop lands while the session-admission reads
        # are in flight. The session is already accepted (admission began
        # while serving), so it completes admission and then winds down.
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.0)
        calls = {'n': 0}

        async def _read(pool, fn, *args):
            calls['n'] += 1
            if calls['n'] == 1:
                gate.flip_to_draining(drain_age=0.0)
            if getattr(fn, '__name__', '') == 'get_audio_bytes_webhook_seconds':
                return None
            return False

        monkeypatch.setattr(pusher, 'run_blocking', _read)
        ws = FakeWebSocket(hang_receive=True)

        await pusher._websocket_util_trigger(ws, 'uid', 8000)

        assert calls['n'] == 3  # protection read skipped: sync is force-disabled
        assert ws.close_calls == [1001]
        runtime[0].finish.assert_called_once_with('success')

    @pytest.mark.asyncio
    async def test_winddown_close_cancel_in_teardown_window_is_absorbed(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.0)
        ws = FakeWebSocket(hang_receive=True, close_error=asyncio.CancelledError())
        task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid', 8000))
        await asyncio.sleep(0.05)

        gate.flip_to_draining(drain_age=0.0)
        await task  # cancelled close on a lost transport is absorbed

        runtime[0].finish.assert_called_once_with('success')

    @pytest.mark.asyncio
    async def test_winddown_close_generic_fault_still_absorbed(self, runtime, monkeypatch):
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.0)
        ws = FakeWebSocket(hang_receive=True, close_error=RuntimeError('already closed'))
        task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid', 8000))
        await asyncio.sleep(0.05)

        gate.flip_to_draining(drain_age=0.0)
        await task

        runtime[0].finish.assert_called_once_with('success')

    @pytest.mark.asyncio
    async def test_disconnect_reason_in_winddown_round_stays_benign(self, runtime, monkeypatch):
        # Ordering: the client disconnect and the wind-down completing in the
        # same supervisor round — the disconnect owns the exit, no crash is
        # invented, the session closes normally.
        _set_gate(monkeypatch)

        async def supervise_disconnect_round(**kwargs):
            return MagicMock(reason='disconnect', task_name='ws:uid:drain_winddown')

        monkeypatch.setattr(pusher, 'supervise_tasks', supervise_disconnect_round)
        ws = FakeWebSocket()

        await pusher._websocket_util_trigger(ws, 'uid', 8000)

        runtime[0].finish.assert_called_once_with('success')
        assert ws.close_calls == [1000]

    @pytest.mark.asyncio
    async def test_exception_while_draining_stays_loud(self, runtime, monkeypatch):
        # An ordinary Exception (not a cancel) during a drain keeps the loud
        # path — absorption never widened past platform cancels.
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.0)
        calls = {'n': 0}

        async def _read(pool, fn, *args):
            calls['n'] += 1
            if calls['n'] == 1:
                gate.flip_to_draining(drain_age=0.0)
            raise RuntimeError('profile read exploded')

        monkeypatch.setattr(pusher, 'run_blocking', _read)
        ws = FakeWebSocket(hang_receive=True)

        with pytest.raises(RuntimeError):
            await pusher._websocket_util_trigger(ws, 'uid', 8000)

        runtime[0].finish.assert_called_once_with('failure')

    @pytest.mark.asyncio
    async def test_teardown_cancel_after_window_expiry_propagates(self, runtime, monkeypatch):
        # A cancel long after the flip (window elapsed, gate still DRAINING)
        # is no longer attributable to the teardown window. Reached through a
        # supervised cancel — a draining pod that is minutes past the flip.
        gate = _set_gate(monkeypatch)
        monkeypatch.setattr(pusher, 'PUSHER_DRAIN_WIND_DOWN_SECONDS', 0.0)

        async def _read(pool, fn, *args):
            gate.flip_to_draining(drain_age=1e9)
            return None

        monkeypatch.setattr(pusher, 'run_blocking', _read)

        async def supervise_late_cancel(**kwargs):
            asyncio.current_task().cancel()
            await asyncio.sleep(0)
            return MagicMock(reason='never')

        monkeypatch.setattr(pusher, 'supervise_tasks', supervise_late_cancel)
        ws = FakeWebSocket(hang_receive=True)

        with pytest.raises(asyncio.CancelledError):
            await pusher._websocket_util_trigger(ws, 'uid', 8000)


class TestClassifierWindowEdges:
    """Boundary ages of the teardown classification window."""

    def _set_gate_state(self, monkeypatch, serving, drain_age):
        stub = _GateStub()
        stub.serving = serving
        stub.drain_age = drain_age
        monkeypatch.setattr(pusher, 'ReadinessGate', stub)
        return stub

    def test_exact_window_age_is_teardown(self, monkeypatch):
        self._set_gate_state(monkeypatch, serving=False, drain_age=pusher.PUSHER_TEARDOWN_CANCEL_GRACE_SECONDS)
        assert pusher._teardown_cancel_observed() is True

    def test_just_past_window_is_not_teardown(self, monkeypatch):
        self._set_gate_state(monkeypatch, serving=False, drain_age=pusher.PUSHER_TEARDOWN_CANCEL_GRACE_SECONDS + 0.001)
        assert pusher._teardown_cancel_observed() is False

    def test_draining_with_unknown_age_is_teardown(self, monkeypatch):
        # Defensive branch: DRAINING but no recorded start (should not happen;
        # a cancel in that state still gets the teardown classification).
        self._set_gate_state(monkeypatch, serving=False, drain_age=None)
        assert pusher._teardown_cancel_observed() is True

    def test_serving_with_stale_age_is_not_teardown(self, monkeypatch):
        # A reset gate (tests, or a future un-drain) must win over the stale
        # age: the lifecycle predicate reads the live state first.
        self._set_gate_state(monkeypatch, serving=True, drain_age=0.0)
        assert pusher._teardown_cancel_observed() is False

    def test_grace_window_covers_the_wind_down(self):
        # A wind-down that overruns (slow queue flush) must still land inside
        # the classification window, so a cancel during the overrun is a
        # classified backstop, not a fresh fault.
        assert pusher.PUSHER_TEARDOWN_CANCEL_GRACE_SECONDS >= pusher.PUSHER_DRAIN_WIND_DOWN_SECONDS


class TestGateWaiterFanout:
    """The preStop hook is one HTTP call; every session must hear it."""

    def test_one_flip_wakes_all_registered_waiters(self):
        ReadinessGate.reset_for_test()
        first = ReadinessGate.drain_wait_event()
        second = ReadinessGate.drain_wait_event()
        assert len(ReadinessGate._drain_listeners) == 2
        ReadinessGate.begin_drain()
        assert first.is_set() is True
        assert second.is_set() is True
        ReadinessGate.remove_drain_wait_event(first)
        ReadinessGate.remove_drain_wait_event(second)
        ReadinessGate.reset_for_test()

    def test_second_begin_drain_is_noop_for_waiters(self):
        ReadinessGate.reset_for_test()
        event = ReadinessGate.drain_wait_event()
        ReadinessGate.begin_drain()
        first_set_at = event.is_set()
        ReadinessGate.begin_drain()  # idempotent: no error, no re-wake needed
        assert first_set_at is True and event.is_set() is True
        ReadinessGate.remove_drain_wait_event(event)
        ReadinessGate.reset_for_test()

    def test_registry_survives_concurrent_thread_registration(self):
        # The preStop drain runs on an HTTP handler thread; waiter
        # registration must be safe against that flip from another thread.
        import threading

        ReadinessGate.reset_for_test()
        registered = threading.Event()

        def _register():
            ReadinessGate.drain_wait_event()
            registered.set()

        thread = threading.Thread(target=_register)
        thread.start()
        ReadinessGate.begin_drain()
        thread.join(timeout=5.0)
        assert registered.is_set() is True
        ReadinessGate.reset_for_test()


class TestTerminalClassificationContract:
    """Outcome mapping stays honest: teardown never reclassifies to success."""

    def test_close_1006_maps_to_cancelled(self):
        assert pusher.pusher_session_outcome(1006) == 'cancelled'

    def test_close_1001_still_maps_to_success(self):
        # The absorbing branch deliberately keeps 1006; this pins 1001's
        # existing meaning so nobody 'fixes' the code upward later.
        assert pusher.pusher_session_outcome(1001) == 'success'

    def test_failure_outcome_unchanged_by_boundary(self):
        assert pusher.pusher_session_outcome(1011, application_failed=True) == 'failure'

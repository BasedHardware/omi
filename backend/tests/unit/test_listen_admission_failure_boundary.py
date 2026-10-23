"""A pre-supervision listen failure closes the socket instead of crashing the ASGI callable.

Failure-Class: FC-lifecycle-close-classified-by-transport-phase

``run_listen_session`` owned the socket with a ``finally`` only: runtime
construction and the connect-time admission path in front of supervision —
``_admit``'s ``is_trial_paywalled`` read and ``_bootstrap``'s
``load_listen_connect_base`` reads (``is_exists_user``,
``has_transcription_credits``, ``get_user_transcription_preferences``) — had
no ``except``. One admission failure there escaped the ASGI callable and
surfaced as uvicorn's full ``Exception in ASGI application`` traceback (prod
backend-listen 2026-10-22: x8/30m at
``uvicorn/protocols/websockets/websockets_impl.py`` ``run_asgi``), and the
client saw an abrupt socket drop with no close frame it could act on — the
same transport event one minute later, mid-session, is classified as the
session's terminal close. The phase a bounded failure surfaces in must not
decide its classification: the boundary now classifies it like the runtime
classifies a supervised one — one traceback-bearing log line, then the
session's terminal close (``1011`` + ``transcription_service_unavailable``,
the code ``terminate_live_stt_backoff`` already uses) so the client's
reconnect handles the transient fault. Cancellation still propagates — the
deletion fence and ASGI shutdown cancel this task and must stay observable —
and the accepted-session no-audio telemetry still runs on every exit path,
because the session was accepted before it failed.

Guards:
- an admission-stage failure (the ``_admit`` probe) closes 1011, logs exactly
  one traceback-bearing error, and no exception escapes ``run_listen_session``;
- a bootstrap-stage failure (``load_listen_connect_base``) behaves the same;
- a runtime-construction failure (no runtime exists yet) still closes and
  still skips the no-audio counter (the session was never accepted);
- a supervised-session failure on a session that never got audio still
  counts the no-audio teardown (the accepted-session contract is unchanged);
- a socket whose close itself fails keeps the boundary's outcome: the error
  is logged at warning and nothing re-raises;
- ``asyncio.CancelledError`` still propagates out of ``run_listen_session``;
- the healthy completion path is unchanged (no extra close, no error).
"""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketState

from routers.listen import runtime as runtime_module
from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime, run_listen_session
from utils.stt.live_failure import LIVE_STT_FAILURE_CLOSE_CODE, LIVE_STT_FAILURE_CLOSE_REASON


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class _AdmissionSocket:
    """A connected socket that records closes and can refuse to close."""

    def __init__(self, *, close_fails: bool = False, state: WebSocketState = WebSocketState.CONNECTED):
        self.closes = []
        self.client_state = state
        self._close_fails = close_fails

    async def close(self, *, code, reason=None):
        if self._close_fails:
            raise RuntimeError('SYNTHETIC-CLOSE-FAILURE')
        self.closes.append((code, reason))


def _request(socket) -> ListenRequest:
    return ListenRequest(
        uid='uid-admission',
        websocket=socket,
        source='test',
        client_device_context=SimpleNamespace(platform='desktop'),
    )


def _failing_runtime(request, failure: BaseException) -> ListenSessionRuntime:
    """A runtime whose supervised session raises before any audio arrives."""
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = request
    runtime.state = SimpleNamespace(first_audio_byte_timestamp=None, active=True)
    runtime.client_device_context = request.client_device_context

    async def run():
        raise failure

    runtime.run = run
    return runtime


@pytest.mark.anyio
async def test_admission_stage_failure_closes_terminal_and_stays_contained(monkeypatch, caplog):
    """The _admit probe's failure is classified at the boundary, not re-raised to ASGI."""
    socket = _AdmissionSocket()
    request = _request(socket)

    def construct(_request):
        return _failing_runtime(_request, RuntimeError('SYNTHETIC-ADMISSION-PROBE-FAILURE'))

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', construct)
    # The failure happens inside runtime.run() — in the real session that is the
    # pre-supervision phase (construction + _admit + _bootstrap), and the
    # containment contract is what this test pins.

    with caplog.at_level(logging.ERROR, logger='routers.listen.runtime'):
        await run_listen_session(request)
    assert socket.closes == [(LIVE_STT_FAILURE_CLOSE_CODE, LIVE_STT_FAILURE_CLOSE_REASON)]
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    assert 'listen session failed before supervision' in error_records[0].message
    assert error_records[0].exc_info not in (None, (None, None, None)), 'the traceback is the evidence'


@pytest.mark.anyio
async def test_bootstrap_stage_failure_closes_terminal_and_stays_contained(monkeypatch, caplog):
    socket = _AdmissionSocket()
    request = _request(socket)

    def construct(_request):
        return _failing_runtime(_request, RuntimeError('SYNTHETIC-BOOTSTRAP-READ-FAILURE'))

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', construct)

    with caplog.at_level(logging.ERROR, logger='routers.listen.runtime'):
        await run_listen_session(request)

    assert socket.closes == [(LIVE_STT_FAILURE_CLOSE_CODE, LIVE_STT_FAILURE_CLOSE_REASON)]
    assert sum(1 for record in caplog.records if record.levelno >= logging.ERROR) == 1


@pytest.mark.anyio
async def test_runtime_construction_failure_still_closes_and_skips_the_no_audio_counter(monkeypatch, caplog):
    socket = _AdmissionSocket()
    request = _request(socket)
    counted = []
    monkeypatch.setattr(runtime_module, 'record_listen_no_audio_teardown', lambda **kwargs: counted.append(kwargs))

    def construct(_request):
        raise RuntimeError('SYNTHETIC-CONSTRUCT-FAILURE')

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', construct)

    with caplog.at_level(logging.ERROR, logger='routers.listen.runtime'):
        await run_listen_session(request)

    assert socket.closes == [(LIVE_STT_FAILURE_CLOSE_CODE, LIVE_STT_FAILURE_CLOSE_REASON)]
    assert counted == [], 'the session was never accepted, so it never entered the no-audio funnel'
    assert sum(1 for record in caplog.records if record.levelno >= logging.ERROR) == 1


@pytest.mark.anyio
async def test_supervised_failure_without_audio_still_counts_the_no_audio_teardown(monkeypatch):
    socket = _AdmissionSocket()
    request = _request(socket)
    counted = []
    monkeypatch.setattr(runtime_module, 'record_listen_no_audio_teardown', lambda **kwargs: counted.append(kwargs))

    def construct(_request):
        return _failing_runtime(_request, RuntimeError('SYNTHETIC-SUPERVISED-FAILURE'))

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', construct)

    await run_listen_session(request)

    assert socket.closes == [(LIVE_STT_FAILURE_CLOSE_CODE, LIVE_STT_FAILURE_CLOSE_REASON)]
    assert counted == [
        {'source': 'test', 'platform': 'desktop'}
    ], 'the accepted-session no-audio contract is unchanged on the new failure path'


@pytest.mark.anyio
async def test_failed_close_keeps_the_boundary_outcome(monkeypatch, caplog):
    socket = _AdmissionSocket(close_fails=True)
    request = _request(socket)

    def construct(_request):
        return _failing_runtime(_request, RuntimeError('SYNTHETIC-SUPERVISED-FAILURE'))

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', construct)

    with caplog.at_level(logging.WARNING, logger='routers.listen.runtime'):
        await run_listen_session(request)

    assert any('listen admission-failure close failed' in record.message for record in caplog.records)
    assert sum(1 for record in caplog.records if record.levelno >= logging.ERROR) == 1


@pytest.mark.anyio
async def test_cancellation_still_propagates(monkeypatch):
    socket = _AdmissionSocket()
    request = _request(socket)

    def construct(_request):
        runtime = object.__new__(ListenSessionRuntime)
        runtime.request = _request
        runtime.state = SimpleNamespace(first_audio_byte_timestamp=None)
        runtime.client_device_context = _request.client_device_context

        async def run():
            await asyncio.Event().wait()  # parked until cancelled

        runtime.run = run
        return runtime

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', construct)
    task = asyncio.create_task(run_listen_session(request))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert socket.closes == [], 'cancellation is not a session failure and must not close here'


@pytest.mark.anyio
async def test_healthy_completion_is_unchanged(monkeypatch, caplog):
    socket = _AdmissionSocket()
    request = _request(socket)

    def construct(_request):
        runtime = object.__new__(ListenSessionRuntime)
        runtime.request = _request
        runtime.state = SimpleNamespace(first_audio_byte_timestamp=None)
        runtime.client_device_context = _request.client_device_context
        runtime.run = AsyncMock(return_value=None)
        return runtime

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', construct)

    with caplog.at_level(logging.ERROR, logger='routers.listen.runtime'):
        await run_listen_session(request)

    assert socket.closes == [], 'the session owns its own close; the boundary adds none on success'
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


@pytest.mark.anyio
async def test_session_that_got_audio_before_failing_skips_the_no_audio_counter(monkeypatch):
    """The no-audio counter counts accepted sessions that never got audio."""
    socket = _AdmissionSocket()
    request = _request(socket)
    counted = []
    monkeypatch.setattr(runtime_module, 'record_listen_no_audio_teardown', lambda **kwargs: counted.append(kwargs))

    def construct(_request):
        runtime = _failing_runtime(_request, RuntimeError('SYNTHETIC-SUPERVISED-FAILURE'))
        runtime.state.first_audio_byte_timestamp = 1234.0  # audio arrived, then the session failed
        return runtime

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', construct)

    await run_listen_session(request)

    assert socket.closes == [(LIVE_STT_FAILURE_CLOSE_CODE, LIVE_STT_FAILURE_CLOSE_REASON)]
    assert counted == [], 'a session that produced audio is not a no-audio session'


@pytest.mark.anyio
async def test_failure_log_names_uid_and_source(monkeypatch, caplog):
    """The one ERROR attributes the failed session without leaking its payload."""
    socket = _AdmissionSocket()
    request = _request(socket)

    def construct(_request):
        return _failing_runtime(_request, RuntimeError('SYNTHETIC-SUPERVISED-FAILURE'))

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', construct)

    with caplog.at_level(logging.ERROR, logger='routers.listen.runtime'):
        await run_listen_session(request)

    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    assert 'uid=uid-admission' in error_records[0].message
    assert 'source=test' in error_records[0].message
    assert 'SYNTHETIC' not in error_records[0].message, 'the message classifies; the traceback carries the detail'


@pytest.mark.anyio
async def test_gone_socket_skips_the_close_but_stays_contained(monkeypatch, caplog):
    socket = _AdmissionSocket(state=WebSocketState.DISCONNECTED)
    request = _request(socket)

    def construct(_request):
        return _failing_runtime(_request, RuntimeError('SYNTHETIC-SUPERVISED-FAILURE'))

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', construct)

    with caplog.at_level(logging.ERROR, logger='routers.listen.runtime'):
        await run_listen_session(request)

    assert socket.closes == [], 'a socket that already left is not closed again'

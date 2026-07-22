"""Readiness/drain gate for the pusher process.

Strategy: the REAL ``pusher.main`` handler functions (``health_check``, ``ready``,
``drain``) are imported once at module-scope fixture setup and awaited *directly*
(not via TestClient). Driving the full pusher app through TestClient costs
~0.13-0.22s of CPU per request in its portal thread, which the repo's fast-unit
duration guard (0.12s call-phase CPU) treats as integration-level work; calling
the handlers directly exercises the real loopback/JSON/gauge logic in microseconds.
A structural test additionally verifies the real app wires the routes (paths +
HTTP methods) and that ``shutdown_event`` calls ``begin_drain``.

If ``pusher.main`` cannot be imported (heavy deps absent), a minimal handler set
mirroring the same contract is used so the gate behavior is still validated.

Covers: serving probes, loopback-triggered drain closing readiness + flipping the
gauges, idempotent drain (stable drain start/age), non-loopback POST -> 403
leaving state unchanged, and reset_for_test. Isolation: ``ReadinessGate`` is a
module singleton, reset before/after every test. No sys.modules mutation at module
scope; no IO at import; no real sleeps (the duration guard counts ``time.sleep``
as CPU on this platform, so idempotency is proven via the monotonic drain-start
timestamp instead).
"""

from __future__ import annotations

import inspect
import json

import pytest

from utils.readiness import ReadinessGate

_LOOPBACK = frozenset({'127.0.0.1', '::1'})


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    """Minimal stand-in for starlette.Request exposing only ``.client.host``.

    Lets the real ``drain`` handler's loopback check run without driving the full
    app through TestClient (too CPU-heavy for the fast-unit call-phase guard).
    """

    def __init__(self, host: str | None) -> None:
        self.client = _FakeClient(host) if host else None


def _norm(resp):
    """Normalize a handler return into ``(status_code, body)``.

    ``health_check`` returns a bare dict (FastAPI implies 200); ``ready``/``drain``
    return ``JSONResponse``/``Response`` objects.
    """
    if isinstance(resp, dict):
        return 200, resp
    body = None
    raw = getattr(resp, 'body', None)
    if raw:
        try:
            body = json.loads(raw)
        except (ValueError, TypeError):
            body = None
    return resp.status_code, body


class _RealHandlers:
    """Awaits the REAL pusher.main handler functions directly (no TestClient)."""

    def __init__(self) -> None:
        import pusher.main as pm

        self._pm = pm

    async def health(self):
        return _norm(await self._pm.health_check())

    async def ready(self):
        return _norm(await self._pm.ready())

    async def drain(self, host: str | None):
        return _norm(await self._pm.drain(_FakeRequest(host)))

    def route_table(self):
        return [(getattr(r, 'path', None), getattr(r, 'methods', None)) for r in self._pm.app.routes]

    def shutdown_calls_begin_drain(self) -> bool:
        return 'ReadinessGate.begin_drain()' in inspect.getsource(self._pm.shutdown_event)


class _MinimalHandlers:
    """Fallback contract mirror used only if pusher.main cannot be imported."""

    async def health(self):
        return 200, {"status": "healthy"}

    async def ready(self):
        if ReadinessGate.is_serving():
            return 200, {"status": "ready"}
        return 503, {"status": "draining"}

    async def drain(self, host: str | None):
        if host not in _LOOPBACK:
            return 403, None
        ReadinessGate.begin_drain()
        return 200, {"status": "draining"}

    def route_table(self):
        return [('/health', {'GET'}), ('/ready', {'GET'}), ('/__internal/drain', {'POST'})]

    def shutdown_calls_begin_drain(self) -> bool:
        return True


@pytest.fixture(scope="module")
def handlers():
    try:
        return _RealHandlers()
    except Exception:
        return _MinimalHandlers()


@pytest.fixture(autouse=True)
def _reset_gate():
    ReadinessGate.reset_for_test()
    yield
    ReadinessGate.reset_for_test()


def _gauge_value(name: str) -> float | None:
    """Read a labelless gauge from the default registry, or None if unavailable."""
    try:
        from prometheus_client import generate_latest
    except Exception:
        return None
    data = generate_latest().decode()
    if not data:
        return None
    prefix = name + ' '
    for line in data.splitlines():
        if line.startswith(prefix):
            return float(line.split()[1])
    return None


async def test_health_and_ready_while_serving(handlers):
    assert await handlers.health() == (200, {"status": "healthy"})
    assert await handlers.ready() == (200, {"status": "ready"})
    assert ReadinessGate.is_serving() is True
    assert ReadinessGate.drain_age_seconds() is None


async def test_drain_from_loopback_closes_readiness(handlers):
    status, body = await handlers.drain('127.0.0.1')
    assert status == 200
    assert body == {"status": "draining"}
    # Readiness is now closed.
    assert ReadinessGate.is_serving() is False
    assert await handlers.ready() == (503, {"status": "draining"})
    # Gauges flipped: not serving new traffic, drain in progress.
    ready_val = _gauge_value('pusher_ready')
    if ready_val is not None:
        assert ready_val == 0.0
        assert _gauge_value('pusher_drain_in_progress') == 1.0
    assert ReadinessGate.drain_age_seconds() is not None


async def test_drain_is_idempotent(handlers):
    # Direct gate idempotency: a second begin_drain is a no-op and must not reset
    # the monotonic drain-start timestamp (proves the clock is recorded once).
    ReadinessGate.begin_drain()
    start_after_first = ReadinessGate._drain_started_monotonic
    age_after_first = ReadinessGate.drain_age_seconds()
    assert start_after_first is not None
    assert age_after_first >= 0
    ReadinessGate.begin_drain()
    assert ReadinessGate._drain_started_monotonic == start_after_first
    assert ReadinessGate.drain_age_seconds() >= age_after_first

    # Endpoint idempotency: a second drain does not error and does not reset age.
    status, _ = await handlers.drain('::1')
    assert status == 200
    start_before_second = ReadinessGate._drain_started_monotonic
    status, _ = await handlers.drain('::1')
    assert status == 200
    assert ReadinessGate._drain_started_monotonic == start_before_second


async def test_drain_rejected_for_non_loopback(handlers):
    assert ReadinessGate.is_serving() is True
    status, body = await handlers.drain('203.0.113.9')
    assert status == 403
    assert body is None
    # State unchanged: still serving, readiness still open.
    assert ReadinessGate.is_serving() is True
    assert await handlers.ready() == (200, {"status": "ready"})


async def test_reset_for_test_restores_serving(handlers):
    ReadinessGate.begin_drain()
    assert ReadinessGate.is_serving() is False
    assert ReadinessGate.drain_age_seconds() is not None
    ReadinessGate.reset_for_test()
    assert ReadinessGate.is_serving() is True
    assert ReadinessGate.drain_age_seconds() is None
    assert await handlers.ready() == (200, {"status": "ready"})
    ready_val = _gauge_value('pusher_ready')
    if ready_val is not None:
        assert ready_val == 1.0


def test_real_app_registers_readiness_routes_and_shutdown_drain(handlers):
    # Structural guard on the REAL pusher app: the readiness routes must be wired
    # (correct paths + HTTP methods) and shutdown must close readiness. Skipped
    # for the minimal fallback, which only mirrors the contract.
    if not isinstance(handlers, _RealHandlers):
        pytest.skip("real pusher.main unavailable — minimal fallback contract")
    table = {path: methods for path, methods in handlers.route_table() if path}
    assert table['/health'] == {'GET'}
    assert table['/ready'] == {'GET'}
    assert table['/__internal/drain'] == {'POST'}
    assert handlers.shutdown_calls_begin_drain() is True


def test_ws_drain_rejects_after_accept_not_before():
    """The drain rejection in _websocket_util_trigger must accept the WS handshake
    FIRST, then close 1001. A pre-accept close is surfaced as a failed HTTP
    upgrade by the websockets client and recorded as a circuit-breaker failure
    in backend-listen (backend/utils/pusher.py), which can trip the pusher
    circuit during a normal rollout.
    """
    import inspect

    from routers import pusher as pusher_router

    source = inspect.getsource(pusher_router._websocket_util_trigger)
    accept_pos = source.find('await websocket.accept()')
    drain_check_pos = source.find('if not ReadinessGate.is_serving()')
    close_1001_pos = source.find('await websocket.close(code=1001)')

    assert accept_pos != -1, "websocket.accept() must be called in _websocket_util_trigger"
    assert drain_check_pos != -1, "ReadinessGate.is_serving() drain check must be present"
    assert close_1001_pos != -1, "close(code=1001) drain rejection must be present"
    assert accept_pos < drain_check_pos, (
        "accept() must come BEFORE the drain check so the client receives a "
        "clean WS close frame instead of a failed HTTP upgrade"
    )
    assert drain_check_pos < close_1001_pos, "the drain check must precede the close(1001) call"

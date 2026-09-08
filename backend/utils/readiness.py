"""Reusable readiness/drain gate for the pusher process.

A module-level singleton (:data:`ReadinessGate`) tracks whether the process is
serving new traffic or draining for shutdown. It is intentionally dependency-free
so it can be reused by the pusher process (wired today) and, without pulling in
routers or database modules, the llm-gateway (planned) as well.

Honest availability model: flipping to DRAINING only stops NEW connections
(readiness fails so the LB stops sending new traffic; new WebSockets are rejected
at the app). In-flight WebSocket sessions are NOT migrated across a cutover over
the proxied ALB+NEG path; they are cut by the load balancer per BackendConfig
connectionDraining and reconnect through backend-listen. Never treat drain as
sub-second or zero-session-impact.
"""

import threading
import time

_STATE_SERVING = 'SERVING'
_STATE_DRAINING = 'DRAINING'


class _ReadinessGate:
    """Thread-safe singleton readiness/drain state.

    ``begin_drain`` is idempotent: the first call atomically flips SERVING ->
    DRAINING, records the monotonic drain start, and exports the gauge flip; every
    subsequent call is a no-op (NOT an error). Idempotency lets the preStop drain
    hook and the SIGTERM-driven lifespan shutdown both invoke it safely without
    coordinating.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = _STATE_SERVING
        self._drain_started_monotonic: float | None = None

    def is_serving(self) -> bool:
        with self._lock:
            return self._state == _STATE_SERVING

    def begin_drain(self) -> None:
        """Atomically flip SERVING -> DRAINING and export the gauge flip.

        Idempotent: a no-op (not an error) when already draining, so the preStop
        drain hook and the lifespan shutdown path can both call it. Records
        ``drain_started_monotonic`` exactly once.
        """
        with self._lock:
            if self._state == _STATE_DRAINING:
                return
            self._state = _STATE_DRAINING
            self._drain_started_monotonic = time.monotonic()
        # Emit the gauge flip outside the lock. prometheus_client is internally
        # thread-safe; the lazy import keeps this module dependency-free at import.
        self._export_drain_gauges()

    def drain_age_seconds(self) -> float | None:
        """Seconds since drain began (monotonic), or ``None`` while still serving."""
        with self._lock:
            if self._drain_started_monotonic is None:
                return None
            return time.monotonic() - self._drain_started_monotonic

    def reset_for_test(self) -> None:
        """Test-only: return to SERVING, clear the drain start, restore gauges."""
        with self._lock:
            self._state = _STATE_SERVING
            self._drain_started_monotonic = None
        self._export_serving_gauges()

    @staticmethod
    def _export_drain_gauges() -> None:
        try:
            from utils.metrics import PUSHER_DRAIN_IN_PROGRESS, PUSHER_READY
        except Exception:
            # ponytail: telemetry must never break the drain path. If the metrics
            # module is unavailable (minimal import context), the gate still flips;
            # the gauges simply don't emit. Acceptable: drain correctness does not
            # depend on Prometheus.
            return
        PUSHER_READY.set(0)
        PUSHER_DRAIN_IN_PROGRESS.set(1)

    @staticmethod
    def _export_serving_gauges() -> None:
        try:
            from utils.metrics import PUSHER_DRAIN_IN_PROGRESS, PUSHER_READY
        except Exception:
            return
        PUSHER_READY.set(1)
        PUSHER_DRAIN_IN_PROGRESS.set(0)


ReadinessGate = _ReadinessGate()

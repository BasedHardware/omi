"""Small process-local circuit used only to avoid repeated unhealthy STT connects.

Correct capacity ownership remains in the provider service. This circuit is a
latency optimization for each listener process, not a fleet-wide coordinator.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any, Callable, Final

logger = logging.getLogger(__name__)

EXPECTED_REJECTIONS = frozenset({'capacity_full', 'allocation_rejected'})

# A provider accepts the WebSocket upgrade before it applies account state, so the
# window has to outlast that rejection round trip (prod measured ~150ms).
STT_FALLBACK_LIVENESS_GRACE_SECONDS: Final[float] = float(os.getenv('STT_FALLBACK_LIVENESS_GRACE_SECONDS', '0.3'))
_FALLBACK_LIVENESS_POLL_SECONDS: Final[float] = 0.02


async def fallback_socket_is_serving(socket: Any) -> bool:
    """Return whether a freshly connected fallback socket is actually serving.

    Velma accepts the upgrade and only then rejects the stream — an over-quota
    account answers ``{"type":"error","error":"Monthly usage limit reached."}``
    about 150ms later, which the socket surfaces as ``is_connection_dead``.
    Treating that connect as a heal reports ``outcome='recovered'`` for a session
    that dies moments afterwards, so the outage never reaches ops (#11752).
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + STT_FALLBACK_LIVENESS_GRACE_SECONDS
    while True:
        if getattr(socket, 'is_connection_dead', False):
            return False
        if loop.time() >= deadline:
            return True
        await asyncio.sleep(_FALLBACK_LIVENESS_POLL_SECONDS)


def close_rejected_socket(socket: Any) -> None:
    """Release a fallback socket that never served.

    Deliberately the sync close and not the awaited tail drain: a rejected stream
    transcribed nothing, and the drain path is allowed to wait on a provider that
    has already gone away — which would stall session setup instead of failing it.
    """
    try:
        socket.finish()
    except Exception:
        logger.warning('Failed to close a rejected STT fallback socket')


class ProviderCircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        serve_error_cooldown_seconds: float | None = None,
        serve_error_successes_to_close: int = 3,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError('failure_threshold must be >= 1')
        if cooldown_seconds <= 0:
            raise ValueError('cooldown_seconds must be > 0')
        if serve_error_successes_to_close < 1:
            raise ValueError('serve_error_successes_to_close must be >= 1')
        # Serve-error storms accept connects then die (~1:1). The connect-path
        # 30s window flaps; default the serve-error bench to 180s.
        serve_cooldown = 180.0 if serve_error_cooldown_seconds is None else serve_error_cooldown_seconds
        if serve_cooldown <= 0:
            raise ValueError('serve_error_cooldown_seconds must be > 0')
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._serve_error_cooldown_seconds = serve_cooldown
        self._serve_error_successes_to_close = serve_error_successes_to_close
        self._clock = clock
        self._failures = 0
        self._opened_at = 0.0
        self._state = 'closed'
        self._probes_in_flight = 0
        self._opened_by_serve_error = False
        self._remaining_successes_to_close = 1
        self._account_cooldown: float | None = None
        self._generation = 0
        self._lock = threading.RLock()

    def _active_cooldown(self) -> float:
        if self._account_cooldown is not None:
            return self._account_cooldown
        if self._opened_by_serve_error:
            return self._serve_error_cooldown_seconds
        return self._cooldown_seconds

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def cooldown_elapsed(self) -> bool:
        """Read-only: whether a caller *would* be let through right now.

        Mirrors ``allow_request``'s open->half_open cooldown check without
        mutating state or claiming the single half-open probe slot, so a
        read-only pre-flight check can't itself flip the breaker or starve a
        real connection attempt of the probe.
        """
        with self._lock:
            if self._state != 'open':
                return True
            return self._clock() - self._opened_at >= self._active_cooldown()

    def allow_request(self, *, max_probes: int = 1, force: bool = False) -> bool:
        with self._lock:
            if self._state == 'closed':
                return True
            if self._state == 'open':
                # force never bypasses account-state; at most one probe per cooldown.
                if self._account_cooldown is not None and self._clock() - self._opened_at < self._account_cooldown:
                    return False
                if not force and self._clock() - self._opened_at < self._active_cooldown():
                    return False
                self._state = 'half_open'
                self._probes_in_flight = 0
            limit = 1 if self._account_cooldown is not None else max(1, max_probes)
            if self._probes_in_flight >= limit:
                return False
            self._probes_in_flight += 1
            return True

    def record_success(self, *, respect_open: bool = False) -> None:
        with self._lock:
            if respect_open and self._state == 'open':
                return
            self._probes_in_flight = max(0, self._probes_in_flight - 1)
            # Connect-path recovery still closes on the first probe success.
            # After a serve-error storm a single half-open connect is not
            # evidence of recovery (first transcript succeeds, then teardown
            # fails ~1:1), so stay half-open until enough consecutive successes.
            if self._opened_by_serve_error and self._remaining_successes_to_close > 1:
                self._remaining_successes_to_close -= 1
                return
            self._failures = 0
            self._state = 'closed'
            self._account_cooldown = None
            self._opened_by_serve_error = False
            self._remaining_successes_to_close = 1

    def record_failure(self) -> None:
        with self._lock:
            self._probes_in_flight = 0
            if self._state == 'half_open':
                self._state = 'open'
                self._generation += 1
                self._opened_at = self._clock()
                if self._opened_by_serve_error:
                    self._remaining_successes_to_close = self._serve_error_successes_to_close
                return
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._state = 'open'
                self._generation += 1
                self._opened_at = self._clock()
                self._opened_by_serve_error = False
                self._remaining_successes_to_close = 1

    def record_serve_failure(self) -> None:
        """Open the circuit after a provider died while serving a session.

        Serve-time deaths cannot flow through ``record_failure``: a provider
        that accepted the upgrade and served audio before dying passes the
        connect-time checks, and the next session's successful *connect* calls
        ``record_success``, resetting the failure counter. Under the reconnect
        load a mid-session outage produces (connect -> die -> reconnect ->
        die), the counter never reaches ``failure_threshold``, so selection
        keeps choosing the provider that stopped serving. A serve-time death
        is terminal evidence for the session it killed, so it opens the
        circuit for the serve-error cooldown. Re-admission requires more than
        one half-open success so a 5xx storm that still accepts connects
        cannot flap the breaker every 30s.
        """
        with self._lock:
            self._probes_in_flight = 0
            self._state = 'open'
            self._generation += 1
            self._opened_at = self._clock()
            self._opened_by_serve_error = True
            self._remaining_successes_to_close = self._serve_error_successes_to_close

    def record_rejection(self, reason: str) -> None:
        if reason in EXPECTED_REJECTIONS:
            self.record_success()
            return
        self.record_failure()

    def deferred_result_callbacks(self) -> tuple[Callable[[], None], Callable[[], None]]:
        """A batch adapter proves health on its first POST, not local construction."""
        with self._lock:
            generation = self._generation
            probe = self._state == 'half_open'
        settled = False

        def settle(success: bool) -> None:
            nonlocal settled
            with self._lock:
                if settled:
                    return
                settled = True
                if generation != self._generation:
                    return  # another death invalidated this admission's probe
                if success and (probe or self._state == 'closed'):
                    self.record_success(respect_open=True)
                elif probe:
                    self.release_probe()

        return lambda: settle(True), lambda: settle(False)

    def release_probe(self) -> None:
        """Cancellation is not provider failure and must not strand a probe slot."""
        with self._lock:
            self._probes_in_flight = max(0, self._probes_in_flight - 1)

    def record_account_failure(self, cooldown_seconds: float = 1800) -> None:
        with self._lock:
            self._probes_in_flight = 0
            self._state = 'open'
            self._generation += 1
            self._opened_at = self._clock()
            self._account_cooldown = max(1, cooldown_seconds)
            self._opened_by_serve_error = False
            self._remaining_successes_to_close = 1


def soniox_circuit_from_env() -> ProviderCircuitBreaker:
    """Keep the historical env lookup until the configured live chain is enabled."""
    from utils.stt.live_rollout import configured_chain_enabled

    if configured_chain_enabled():
        threshold = os.getenv('SONIOX_CIRCUIT_FAILURE_THRESHOLD', '3')
        cooldown = os.getenv('SONIOX_CIRCUIT_COOLDOWN_SECONDS', '30')
    else:
        threshold = os.getenv('MODULATE_CIRCUIT_FAILURE_THRESHOLD', '3')
        cooldown = os.getenv('MODULATE_CIRCUIT_COOLDOWN_SECONDS', '30')
    return ProviderCircuitBreaker(failure_threshold=int(threshold), cooldown_seconds=float(cooldown))

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
    ) -> None:
        if failure_threshold < 1:
            raise ValueError('failure_threshold must be >= 1')
        if cooldown_seconds <= 0:
            raise ValueError('cooldown_seconds must be > 0')
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at = 0.0
        self._state = 'closed'
        self._probe_in_flight = False
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def allow_request(self) -> bool:
        with self._lock:
            if self._state == 'closed':
                return True
            if self._state == 'open':
                if self._clock() - self._opened_at < self._cooldown_seconds:
                    return False
                self._state = 'half_open'
                self._probe_in_flight = False
            if self._probe_in_flight:
                return False
            self._probe_in_flight = True
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = 'closed'
            self._probe_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            self._probe_in_flight = False
            if self._state == 'half_open':
                self._state = 'open'
                self._opened_at = self._clock()
                return
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._state = 'open'
                self._opened_at = self._clock()

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
        circuit for the full cooldown; the half-open probe afterwards restores
        the provider as soon as one probe serves again.
        """
        with self._lock:
            self._probe_in_flight = False
            self._state = 'open'
            self._opened_at = self._clock()

    def record_rejection(self, reason: str) -> None:
        if reason in EXPECTED_REJECTIONS:
            self.record_success()
            return
        self.record_failure()

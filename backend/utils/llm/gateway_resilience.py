"""Bound gateway transport failures before they become user-visible stalls.

The gateway is an optional serving hop: a transport failure may use the legacy
provider, but it must never make every subsequent feature call wait for the
upstream client timeout.  This module owns the process-local circuit state and
the transport deadline used by every gateway-first client.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable

import httpx

from utils.metrics import LLM_GATEWAY_CIRCUIT_OPEN, LLM_GATEWAY_CLIENT_FIRST_BYTE_SECONDS

GATEWAY_CONNECT_TIMEOUT_SECONDS_ENV = 'OMI_LLM_GATEWAY_CONNECT_TIMEOUT_SECONDS'
GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS_ENV = 'OMI_LLM_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS'
GATEWAY_CIRCUIT_FAILURE_THRESHOLD_ENV = 'OMI_LLM_GATEWAY_CIRCUIT_FAILURE_THRESHOLD'
GATEWAY_CIRCUIT_COOLDOWN_SECONDS_ENV = 'OMI_LLM_GATEWAY_CIRCUIT_COOLDOWN_SECONDS'

DEFAULT_GATEWAY_CONNECT_TIMEOUT_SECONDS = 3.0
DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS = 15.0
DEFAULT_GATEWAY_CIRCUIT_FAILURE_THRESHOLD = 2
DEFAULT_GATEWAY_CIRCUIT_COOLDOWN_SECONDS = 30.0


def gateway_transport_timeout() -> httpx.Timeout:
    """Return the shared bounded gateway transport timeout.

    ``read`` is the SDK's first-response-byte deadline and also remains the
    maximum silent interval while a streamed response is active.  A successful
    stream is never replayed through the legacy provider after output begins.
    """

    connect = _positive_float(GATEWAY_CONNECT_TIMEOUT_SECONDS_ENV, DEFAULT_GATEWAY_CONNECT_TIMEOUT_SECONDS)
    first_byte = _positive_float(GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS_ENV, DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)
    return httpx.Timeout(connect=connect, read=first_byte, write=first_byte, pool=connect)


def gateway_connect_timeout_seconds() -> float:
    return _positive_float(GATEWAY_CONNECT_TIMEOUT_SECONDS_ENV, DEFAULT_GATEWAY_CONNECT_TIMEOUT_SECONDS)


def gateway_first_byte_timeout_seconds() -> float:
    return _positive_float(GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS_ENV, DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)


def observe_gateway_first_byte(*, feature: str, started_at: float, outcome: str) -> None:
    """Observe the bounded gateway hop without adding a serving dependency on metrics."""

    try:
        LLM_GATEWAY_CLIENT_FIRST_BYTE_SECONDS.labels(feature=feature, outcome=outcome).observe(
            max(0.0, time.monotonic() - started_at)
        )
    except Exception:
        return


class GatewayCircuitBreaker:
    """A small lock-protected circuit breaker for one backend process."""

    def __init__(
        self,
        *,
        failure_threshold: int | None = None,
        cooldown_seconds: float | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold or _positive_int(
            GATEWAY_CIRCUIT_FAILURE_THRESHOLD_ENV, DEFAULT_GATEWAY_CIRCUIT_FAILURE_THRESHOLD
        )
        self._cooldown_seconds = cooldown_seconds or _positive_float(
            GATEWAY_CIRCUIT_COOLDOWN_SECONDS_ENV, DEFAULT_GATEWAY_CIRCUIT_COOLDOWN_SECONDS
        )
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._open_until = 0.0

    def allow_request(self) -> bool:
        with self._lock:
            if self._monotonic() >= self._open_until:
                if self._open_until:
                    self._open_until = 0.0
                    self._consecutive_failures = 0
                    _set_circuit_metric(False)
                return True
            return False

    def record_transport_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._open_until = 0.0
            _set_circuit_metric(False)

    def record_transport_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures < self._failure_threshold:
                return
            self._open_until = self._monotonic() + self._cooldown_seconds
            _set_circuit_metric(True)

    def reset(self) -> None:
        """Clear state for hermetic process-local tests."""

        with self._lock:
            self._consecutive_failures = 0
            self._open_until = 0.0
            _set_circuit_metric(False)


def _positive_float(env_var: str, default: float) -> float:
    raw = os.getenv(env_var, '').strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_int(env_var: str, default: int) -> int:
    raw = os.getenv(env_var, '').strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        return default
    return value if value > 0 else default


def _set_circuit_metric(open_: bool) -> None:
    try:
        LLM_GATEWAY_CIRCUIT_OPEN.set(1 if open_ else 0)
    except Exception:
        # Resilience code must not make metrics availability part of serving.
        return


gateway_circuit = GatewayCircuitBreaker()

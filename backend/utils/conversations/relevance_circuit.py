"""Process-local cost fence for relevance's attempted paid decision arms.

Match the gateway's two-failure / 30-second defaults without a new config
surface. An open primary skips *all* paid arms; only one half-open probe runs
per cooldown, preventing a fleet outage from becoming sustained nano fan-out.
State is per primary arm, never per user. Generation tickets fence completions
from calls already in flight when another request opened the circuit.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from threading import Lock
import time
from typing import Callable, Iterator, Optional

import httpx

from utils.metrics import record_relevance_circuit_state

FAILURE_THRESHOLD = 2
COOLDOWN_SECONDS = 30.0

_outcome_observer: ContextVar[Optional[Callable[[str], None]]] = ContextVar('relevance_outcome_observer', default=None)


@contextmanager
def observe_scorer_outcomes(observer: Callable[[str], None]) -> Iterator[None]:
    token = _outcome_observer.set(observer)
    try:
        yield
    finally:
        _outcome_observer.reset(token)


def report_scorer_outcome(outcome: str) -> None:
    """Request-local failure category; outside a decision chain this is inert."""
    observer = _outcome_observer.get()
    if observer is not None:
        observer(outcome)


def scorer_error_outcome(error: Exception) -> str:
    if isinstance(error, (TimeoutError, httpx.TimeoutException)) or type(error).__name__ == 'APITimeoutError':
        return 'timeout'
    status = getattr(error, 'status_code', None)
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
    if status == 429:
        return 'http_429'
    if isinstance(status, int) and status >= 400:
        return 'http_error'
    return 'transport_error'


class RelevanceCircuit:
    def __init__(self, arm: str, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._arm = arm
        self._monotonic = monotonic
        self._lock = Lock()
        self._failures = 0
        self._open = False
        self._open_until = 0.0
        self._probing = False
        self._generation: int = 0

    def acquire(self) -> Optional[int]:
        """Admit closed requests or exactly one probe after an open cooldown."""
        with self._lock:
            if self._open:
                if self._probing or self._monotonic() < self._open_until:
                    return None
                self._probing = True
                record_relevance_circuit_state(self._arm, 'half_open')
            return self._generation

    def record(self, ticket: int, *, success: bool) -> bool:
        """Return whether the latch is open after this attempted primary result."""
        with self._lock:
            if ticket != self._generation:
                return self._open
            if success:
                self._failures = 0
                if self._open:
                    self._open = False
                    self._probing = False
                    self._generation += 1
                    record_relevance_circuit_state(self._arm, 'closed')
                return False
            self._failures += 1
            if self._open or self._failures >= FAILURE_THRESHOLD:
                self._open = True
                self._probing = False
                self._generation += 1
                self._open_until = self._monotonic() + COOLDOWN_SECONDS
                record_relevance_circuit_state(self._arm, 'open')
            return self._open


@lru_cache(maxsize=8)
def get_relevance_circuit(arm: str) -> RelevanceCircuit:
    return RelevanceCircuit(arm)

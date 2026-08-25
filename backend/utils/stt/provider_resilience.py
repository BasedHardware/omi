"""Small process-local circuit used only to avoid repeated unhealthy STT connects.

Correct capacity ownership remains in the provider service. This circuit is a
latency optimization for each listener process, not a fleet-wide coordinator.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

EXPECTED_REJECTIONS = frozenset({'capacity_full', 'allocation_rejected'})


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

    def record_rejection(self, reason: str) -> None:
        if reason in EXPECTED_REJECTIONS:
            self.record_success()
            return
        self.record_failure()

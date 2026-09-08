"""Parakeet-owned admission for live WebSocket streams.

Every backend-listen replica connects to this service, so the GPU owner is the
only repository-local layer that can enforce one shared boundary for all
listeners reaching a serving pod. The controller is intentionally
process-local: the Parakeet chart runs one Uvicorn worker per GPU pod, and each
pod owns its own capacity.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
import threading
from typing import Callable, Mapping

CAPACITY_ENV = 'PARAKEET_STREAM_CAPACITY'
ALLOCATION_ENV = 'PARAKEET_STREAM_ALLOCATION_PERCENT'


@dataclass(frozen=True)
class AdmissionResult:
    lease: StreamAdmissionLease | None
    reason: str


class StreamAdmissionLease:
    """An idempotent ownership token for one admitted stream."""

    def __init__(self, controller: StreamAdmissionController) -> None:
        self._controller = controller
        self._released = False
        self._lock = threading.Lock()

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        self._controller.release_lease()


class StreamAdmissionController:
    """Thread-safe hard capacity plus deployment-owned traffic allocation."""

    def __init__(
        self,
        *,
        capacity: int,
        allocation_percent: int,
        sample: Callable[[], float] = random.random,
    ) -> None:
        if capacity < 1:
            raise ValueError(f'{CAPACITY_ENV} must be an integer >= 1')
        if not 0 <= allocation_percent <= 100:
            raise ValueError(f'{ALLOCATION_ENV} must be an integer from 0 through 100')
        self.capacity = capacity
        self.allocation_percent = allocation_percent
        self._sample = sample
        self._active = 0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> StreamAdmissionController:
        capacity_raw = env.get(CAPACITY_ENV)
        if capacity_raw is None or not capacity_raw.strip():
            raise ValueError(f'{CAPACITY_ENV} is required')
        allocation_raw = env.get(ALLOCATION_ENV)
        if allocation_raw is None or not allocation_raw.strip():
            raise ValueError(f'{ALLOCATION_ENV} is required')
        try:
            capacity = int(capacity_raw)
        except ValueError as error:
            raise ValueError(f'{CAPACITY_ENV} must be an integer >= 1') from error
        try:
            allocation_percent = int(allocation_raw)
        except ValueError as error:
            raise ValueError(f'{ALLOCATION_ENV} must be an integer from 0 through 100') from error
        return cls(capacity=capacity, allocation_percent=allocation_percent)

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    def try_acquire(self) -> AdmissionResult:
        if self.allocation_percent < 100 and self._sample() >= self.allocation_percent / 100:
            return AdmissionResult(lease=None, reason='allocation_rejected')
        with self._lock:
            if self._active >= self.capacity:
                return AdmissionResult(lease=None, reason='capacity_full')
            self._active += 1
        return AdmissionResult(lease=StreamAdmissionLease(self), reason='admitted')

    def release_lease(self) -> None:
        with self._lock:
            if self._active <= 0:
                raise RuntimeError('Parakeet stream admission release without ownership')
            self._active -= 1

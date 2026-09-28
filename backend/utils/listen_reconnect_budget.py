"""Bounded process-local admission for rapid listen reconnects."""

from __future__ import annotations

import math
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class ListenReconnectBudget:
    """Token bucket keyed by uid with LRU and idle TTL bounds."""

    def __init__(
        self,
        *,
        per_minute: float = 6,
        burst: float = 3,
        max_entries: int = 20_000,
        ttl_seconds: float = 900,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.per_minute = max(0.0, per_minute)
        self.burst = max(1.0, burst)
        self.max_entries = max(1, max_entries)
        self.ttl_seconds = max(1.0, ttl_seconds)
        self._clock = clock
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
        self._lock = threading.Lock()

    def admit(self, uid: str) -> tuple[bool, int]:
        """Consume one token and return (admitted, retry_after_seconds)."""

        now = self._clock()
        rate = self.per_minute / 60.0
        if self.per_minute <= 0:
            return True, 0
        with self._lock:
            while self._buckets:
                _, oldest = next(iter(self._buckets.items()))
                if now - oldest.updated_at < self.ttl_seconds:
                    break
                self._buckets.popitem(last=False)

            bucket = self._buckets.get(uid)
            if bucket is None:
                bucket = _Bucket(tokens=self.burst, updated_at=now)
                self._buckets[uid] = bucket
            else:
                bucket.tokens = min(self.burst, bucket.tokens + max(0.0, now - bucket.updated_at) * rate)
                bucket.updated_at = now
                self._buckets.move_to_end(uid)

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                admitted, retry_after = True, 0
            else:
                admitted = False
                retry_after = max(1, math.ceil((1 - bucket.tokens) / rate)) if rate > 0 else 60
            while len(self._buckets) > self.max_entries:
                self._buckets.popitem(last=False)
            return admitted, retry_after

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._buckets)


def _configured_budget() -> ListenReconnectBudget:
    try:
        per_minute = float(os.getenv('LISTEN_RECONNECT_BUDGET_PER_MIN', '6'))
    except ValueError:
        per_minute = 6
    return ListenReconnectBudget(per_minute=per_minute)


listen_reconnect_budget = _configured_budget()

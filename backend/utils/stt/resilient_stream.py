"""Session-local, bounded PCM replay for a replaced live provider socket."""

from __future__ import annotations

import time
import os
from collections import deque

from utils.stt.live_metrics import RECONNECT, REPLAY_SECONDS

RING_SECONDS = 15
MAX_RECONNECTS = 3
MAX_RECONNECTS_PER_MINUTE = 2
MAX_REPLAY_SECONDS = 30


def enabled() -> bool:
    return os.getenv('STT_RESILIENT_RECONNECT', 'false').lower() == 'true'


class ResilientAudio:
    def __init__(self, sample_rate: int, *, ring_seconds: int = RING_SECONDS) -> None:
        self.sample_rate = sample_rate
        self.ring_seconds = ring_seconds
        self._chunks: deque[tuple[int, bytes]] = deque()
        self._end_sample = 0
        self.finalized_sample = 0
        self._attempts: deque[float] = deque()
        self._total_attempts = 0
        self._replayed_samples = 0

    @property
    def buffered_bytes(self) -> int:
        return sum(len(data) for _, data in self._chunks)

    def would_overflow(self, data: bytes, start_sample: int | None) -> bool:
        if start_sample is None or not data:
            return False
        first = self._chunks[0][0] if self._chunks else start_sample
        return start_sample + len(data) // 2 - first > self.ring_seconds * self.sample_rate

    def append(self, data: bytes, start_sample: int | None) -> None:
        if start_sample is None or not data:
            return
        self._chunks.append((start_sample, data))
        self._end_sample = max(self._end_sample, start_sample + len(data) // 2)
        self._trim()

    def finalize_through(self, sample: int) -> None:
        self.finalized_sample = max(self.finalized_sample, sample)
        self._trim()

    def _trim(self) -> None:
        first = max(self.finalized_sample, self._end_sample - self.ring_seconds * self.sample_rate)
        while self._chunks and self._chunks[0][0] + len(self._chunks[0][1]) // 2 <= first:
            self._chunks.popleft()
        if self._chunks and self._chunks[0][0] < first:
            start, data = self._chunks.popleft()
            self._chunks.appendleft((first, data[(first - start) * 2 :]))

    def snapshot(self) -> tuple[tuple[int, bytes], ...]:
        return tuple(self._chunks)

    def admit(self, provider: str, reason: str) -> bool:
        now = time.monotonic()
        while self._attempts and now - self._attempts[0] >= 60:
            self._attempts.popleft()
        samples = sum(len(data) // 2 for _, data in self._chunks)
        if (
            self._total_attempts >= MAX_RECONNECTS
            or len(self._attempts) >= MAX_RECONNECTS_PER_MINUTE
            or self._replayed_samples + samples > MAX_REPLAY_SECONDS * self.sample_rate
        ):
            RECONNECT.labels(provider=provider, reason=reason, outcome='limited').inc()
            return False
        self._total_attempts += 1
        self._attempts.append(now)
        RECONNECT.labels(provider=provider, reason=reason, outcome='attempt').inc()
        return True

    def record_replay(self, provider: str, samples: int) -> None:
        self._replayed_samples += samples
        REPLAY_SECONDS.labels(provider=provider).inc(samples / self.sample_rate)

    def close(self) -> None:
        self._chunks.clear()

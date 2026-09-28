"""Session-local, bounded PCM replay for a replaced live provider socket."""

from __future__ import annotations

import time
import os
from collections import deque
from typing import Any

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


def filter_replayed_segments(
    segments: list[dict[str, Any]],
    provider: str | None,
    *,
    soniox: ResilientAudio | None,
    window: ResilientAudio | None,
    window_model: bool,
    cutoff: int,
) -> list[dict[str, Any]]:
    if provider == 'parakeet' and window is not None and window_model:
        for segment in segments:
            end = segment.get('_capture_end_sample')
            if isinstance(end, int):
                window.finalize_through(end)
    if soniox is None or provider != 'soniox':
        return segments
    kept = []
    for segment in segments:
        end = segment.get('_capture_end_sample')
        if isinstance(end, int) and end <= cutoff:
            continue
        if isinstance(end, int):
            soniox.finalize_through(end)
        kept.append(segment)
    return kept


class ReplayFilterMixin:
    host: Any

    def _filter_replayed_segments(self, segments: list[dict[str, Any]], provider: str | None) -> list[dict[str, Any]]:
        return filter_replayed_segments(
            segments,
            provider,
            soniox=getattr(self, '_resilient_audio', None),
            window=getattr(self, '_window_replay_audio', None),
            window_model=getattr(self.host, 'stt_model', None) == 'parakeet-window',
            cutoff=getattr(self, '_replay_cutoff_sample', 0),
        )


def socket_is_finishing(socket: Any) -> bool:
    """Read the teardown latch through managed and legacy wrappers."""
    seen: set[int] = set()
    pending = [socket]
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        try:
            if getattr(current, '_finishing', False):
                return True
            pending.extend((getattr(current, '_conn', None), getattr(current, 'raw', None)))
        except Exception:
            continue
    return False


def replay_chunks(
    socket: Any,
    chunks: tuple[tuple[int, bytes], ...],
    *,
    source: ResilientAudio,
    provider: str,
    soniox: ResilientAudio | None,
) -> bool:
    for start, data in chunks:
        replay_send = getattr(socket, 'replay_send', None)
        accepted = replay_send(data, start) if callable(replay_send) else socket.send(data, start_sample=start)
        if not accepted:
            return False
        if soniox is not None:
            soniox.append(data, start)
        source.record_replay(provider, len(data) // 2)
    return True

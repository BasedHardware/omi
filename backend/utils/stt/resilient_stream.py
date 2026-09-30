"""Session-local, bounded PCM replay for a replaced live provider socket."""

from __future__ import annotations

import time
import os
from collections import deque
from typing import Any, Literal

from utils.stt.live_metrics import RECONNECT, REPLAY_SECONDS, WINDOW_REPLAY_SAFE_TRIMS

RING_SECONDS = 15
MAX_RECONNECTS = 3
MAX_RECONNECTS_PER_MINUTE = 2
MAX_REPLAY_SECONDS = 30


def enabled() -> bool:
    return os.getenv('STT_RESILIENT_RECONNECT', 'false').lower() == 'true'


class ResilientAudio:
    def __init__(self, sample_rate: int, *, ring_seconds: int = RING_SECONDS, strict_replay: bool = False) -> None:
        self.sample_rate = sample_rate
        self.ring_seconds = ring_seconds
        self.strict_replay = strict_replay
        self._chunks: deque[tuple[int, bytes]] = deque()
        self._end_sample = 0
        self.finalized_sample = 0
        self._attempts: deque[float] = deque()
        self._total_attempts = 0
        self._replayed_samples = 0

    @property
    def buffered_bytes(self) -> int:
        return sum(len(data) for _, data in self._chunks)

    @property
    def capture_bounds(self) -> tuple[int, int]:
        """Retained capture interval; an empty ring has equal boundaries."""
        return (self._chunks[0][0] if self._chunks else self._end_sample, self._end_sample)

    def projected_span_samples(self, data: bytes, start_sample: int | None) -> int:
        """Capture-time span after a send, including VAD-gated gaps."""
        if start_sample is None or not data:
            return 0
        first = self._chunks[0][0] if self._chunks else start_sample
        return max(0, start_sample + len(data) // 2 - first)

    def would_overflow(self, data: bytes, start_sample: int | None) -> bool:
        return self.projected_span_samples(data, start_sample) > self.ring_seconds * self.sample_rate

    def append(self, data: bytes, start_sample: int | None) -> None:
        if start_sample is None or not data:
            return
        self._chunks.append((start_sample, data))
        self._end_sample = max(self._end_sample, start_sample + len(data) // 2)
        self._trim()

    def finalize_through(self, sample: int) -> int:
        before = self.buffered_bytes
        self.finalized_sample = max(self.finalized_sample, sample)
        self._trim()
        return before - self.buffered_bytes

    def _trim(self) -> None:
        first = self.finalized_sample
        if not self.strict_replay:
            first = max(first, self._end_sample - self.ring_seconds * self.sample_rate)
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


def trim_window_replay_to_anchor(ring: ResilientAudio | None, socket: Any) -> None:
    """Discard only capture samples before the window's emitted sentence anchor."""
    if ring is None:
        return
    anchor = getattr(socket, 'window_replay_anchor_sample', None)
    sample = anchor() if callable(anchor) else None
    if isinstance(sample, int) and ring.finalize_through(sample):
        WINDOW_REPLAY_SAFE_TRIMS.inc()


def window_replay_action(
    ring: ResilientAudio | None, socket: Any, data: bytes, start_sample: int | None
) -> Literal['append', 'trim', 'failover']:
    """Reserve replay space after reconciling emitted text with the capture ring."""
    if ring is None:
        return 'append'
    trim_window_replay_to_anchor(ring, socket)
    raw = getattr(socket, 'raw', None)
    has_untranscribed_speech = getattr(raw, 'has_untranscribed_speech', None)
    speech_pending = callable(has_untranscribed_speech) and has_untranscribed_speech()
    request_cut = getattr(raw, 'request_replay_cut', None)
    if (
        speech_pending
        and callable(request_cut)
        and ring.projected_span_samples(data, start_sample) >= ring.ring_seconds * ring.sample_rate * 2 // 3
    ):
        # Provider PCM can advance slower than capture time when VAD gates
        # portions of a chunk. Ask the next successful POST to emit its held
        # tail while a third of the replay ring is still available.
        request_cut()
    if not ring.would_overflow(data, start_sample):
        return 'append'
    if (
        callable(has_untranscribed_speech)
        and not speech_pending
        and len(data) <= ring.ring_seconds * ring.sample_rate * 2
    ):
        assert start_sample is not None
        keep_from = start_sample + len(data) // 2 - ring.ring_seconds * ring.sample_rate
        if ring.finalize_through(keep_from):
            WINDOW_REPLAY_SAFE_TRIMS.inc()
        return 'trim'
    if raw is not None:
        snapshot = getattr(socket, 'window_replay_diagnostics', None)
        if callable(snapshot):
            first, end = ring.capture_bounds
            raw.replay_lag_diagnostics = snapshot(first, end, ring.projected_span_samples(data, start_sample))
        raw.fail('capacity_full', capacity_subtype='replay_ring_cap')
    return 'failover'


def filter_replayed_segments(
    segments: list[dict[str, Any]],
    provider: str | None,
    *,
    soniox: ResilientAudio | None,
    cutoff: int,
) -> list[dict[str, Any]]:
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

    def _window_ring(self) -> ResilientAudio | None:
        return (
            getattr(self, '_window_replay_audio', None)
            if getattr(self.host, 'stt_model', None) == 'parakeet-window'
            else None
        )

    def _filter_replayed_segments(self, segments: list[dict[str, Any]], provider: str | None) -> list[dict[str, Any]]:
        return filter_replayed_segments(
            segments,
            provider,
            soniox=getattr(self, '_resilient_audio', None),
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
    source: ResilientAudio | None,
    provider: str,
    soniox: ResilientAudio | None,
) -> int | None:
    """Return the first rejected sample, or None when the snapshot was accepted."""
    if source is None:
        return None
    accepted_chunks: list[tuple[int, bytes]] = []
    for start, data in chunks:
        replay_send = getattr(socket, 'replay_send', None)
        accepted = replay_send(data, start) if callable(replay_send) else socket.send(data, start_sample=start)
        if not accepted:
            return start
        accepted_chunks.append((start, data))
        source.record_replay(provider, len(data) // 2)
    if soniox is not None:
        for start, data in accepted_chunks:
            soniox.append(data, start)
    return None

"""Capacity models for the batch ASR provider (Parakeet) and the paid fallback (Modulate).

Both are MODELS. ``FakeSTT`` stands for the hosted Parakeet fleet: replicas x
per-pod concurrency, scaled by an HPA between ``min_replicas`` and
``max_replicas``, a FIFO queue with a timeout, a lognormal service time and
injectable failure, empty-result and exhaustion behaviour. ``FakeModulate`` is
the paid recovery provider called by the real ``QuarantineRecovery.recover``.

Outcomes are decided in virtual time (``request``) and then replayed by the
synchronous provider interfaces the real code calls (``PlannedWords`` for
``PipelineWorker`` and ``FakeModulate.__call__`` for ``QuarantineRecovery``).
"""

from __future__ import annotations

import asyncio
import collections
import math
import random
from dataclasses import dataclass, field
from typing import Any

from diarizer.batch_pipeline import padded_retry_fits, padded_retry_seconds
from utils.batch_pipeline.recovery_disposition import MultilingualEmpty

SAMPLE_RATE = 16000

WORDS = 'words'
EMPTY = 'empty'
ERROR = 'error'
TIMEOUT = 'timeout'

SPEECH = 'speech'
NEAR_SILENCE = 'near_silence'
SILENCE = 'silence'


class ProviderUnavailable(RuntimeError):
    """Synthetic provider failure; carries no content."""


@dataclass(frozen=True)
class ExhaustionWindow:
    """[start, end) seconds after simulation start. ``mode``: empty | error | zero_capacity."""

    start: float
    end: float
    mode: str = EMPTY

    def __post_init__(self):
        if self.mode not in {EMPTY, ERROR, 'zero_capacity'} or not 0 <= self.start < self.end:
            raise ValueError('invalid exhaustion window')


@dataclass
class STTProfile:
    min_replicas: int = 2
    max_replicas: int = 4
    per_pod_concurrency: int = 4
    scale_interval_seconds: float = 30.0
    scale_up_delay_seconds: float = 90.0
    scale_down_idle_seconds: float = 300.0
    base_latency_seconds: float = 0.5
    seconds_per_audio_second: float = 0.01
    latency_sigma: float = 0.3
    queue_timeout_seconds: float = 60.0
    failure_rate: float = 0.0
    near_silence_empty_rate: float = 0.29  # production: ~29% of near-silence jobs return empty ASR
    speech_empty_rate: float = 0.0
    exhaustion: tuple[ExhaustionWindow, ...] = ()


@dataclass
class STTStats:
    requests: int = 0
    words: int = 0
    empty: int = 0
    errors: int = 0
    timeouts: int = 0
    max_queue_depth: int = 0
    queue_wait_seconds: float = 0.0
    seconds_at_max_replicas: float = 0.0
    peak_replicas: int = 0
    by_purpose: dict = field(default_factory=lambda: collections.Counter())


class _Slots:
    """FIFO counting semaphore whose capacity can change while requests wait."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.in_use = 0
        self.waiters: collections.deque[asyncio.Future] = collections.deque()

    def set_capacity(self, capacity: int) -> None:
        self.capacity = max(0, capacity)
        self._dispatch()

    def _dispatch(self) -> None:
        while self.waiters and self.in_use < self.capacity:
            waiter = self.waiters.popleft()
            if not waiter.done():
                self.in_use += 1
                waiter.set_result(None)

    async def acquire(self, timeout: float | None) -> bool:
        if not self.waiters and self.in_use < self.capacity:
            self.in_use += 1
            return True
        waiter = asyncio.get_running_loop().create_future()
        self.waiters.append(waiter)
        try:
            await asyncio.wait_for(asyncio.shield(waiter), timeout)
            return True
        except asyncio.TimeoutError:
            if waiter.done() and not waiter.cancelled():
                # Granted in the same instant the timeout fired; give it back.
                self.release()
            else:
                waiter.cancel()
            return False

    def release(self) -> None:
        self.in_use -= 1
        self._dispatch()


class FakeSTT:
    """Parakeet-fleet capacity model (replicas x per-pod concurrency, HPA-bounded)."""

    def __init__(self, clock, profile: STTProfile, rng: random.Random):
        self.clock = clock
        self.profile = profile
        self.rng = rng
        self.replicas = profile.min_replicas
        self.slots = _Slots(self._capacity())
        self.stats = STTStats(peak_replicas=self.replicas)
        self._pending_scale_at: float | None = None
        self._idle_since: float | None = None
        self._last_tick = clock.now

    def _window(self) -> ExhaustionWindow | None:
        elapsed = self.clock.elapsed()
        for window in self.profile.exhaustion:
            if window.start <= elapsed < window.end:
                return window
        return None

    def _capacity(self) -> int:
        window = self._window()
        if window is not None and window.mode == 'zero_capacity':
            return 0
        return self.replicas * self.profile.per_pod_concurrency

    async def autoscaler(self) -> None:
        """HPA model: add one replica after a sustained queue, remove one after sustained idleness."""
        profile = self.profile
        while True:
            await asyncio.sleep(profile.scale_interval_seconds)
            now = self.clock.now
            if self.replicas >= profile.max_replicas:
                self.stats.seconds_at_max_replicas += now - self._last_tick
            self._last_tick = now
            busy = bool(self.slots.waiters) or self.slots.in_use >= self.slots.capacity > 0
            if busy and self.replicas < profile.max_replicas:
                self._idle_since = None
                if self._pending_scale_at is None:
                    self._pending_scale_at = now + profile.scale_up_delay_seconds
                elif now >= self._pending_scale_at:
                    self.replicas += 1
                    self._pending_scale_at = None
            elif not busy and self.slots.in_use == 0:
                self._pending_scale_at = None
                self._idle_since = self._idle_since if self._idle_since is not None else now
                if now - self._idle_since >= profile.scale_down_idle_seconds and self.replicas > profile.min_replicas:
                    self.replicas -= 1
                    self._idle_since = now
            self.stats.peak_replicas = max(self.stats.peak_replicas, self.replicas)
            self.slots.set_capacity(self._capacity())

    def refresh_capacity(self) -> None:
        self.slots.set_capacity(self._capacity())

    def service_seconds(self, audio_seconds: float) -> float:
        profile = self.profile
        mean = profile.base_latency_seconds + profile.seconds_per_audio_second * audio_seconds
        return mean * math.exp(self.rng.gauss(0, profile.latency_sigma) - profile.latency_sigma**2 / 2)

    async def request(self, kind: str, audio_seconds: float, *, purpose: str = 'batch') -> str:
        stats = self.stats
        stats.requests += 1
        stats.by_purpose[purpose] += 1
        self.refresh_capacity()
        window = self._window()
        if window is not None and window.mode == ERROR:
            stats.errors += 1
            return ERROR
        stats.max_queue_depth = max(stats.max_queue_depth, len(self.slots.waiters) + 1)
        queued_at = self.clock.now
        if not await self.slots.acquire(self.profile.queue_timeout_seconds):
            stats.queue_wait_seconds += self.clock.now - queued_at
            stats.timeouts += 1
            return TIMEOUT
        stats.queue_wait_seconds += self.clock.now - queued_at
        try:
            await asyncio.sleep(self.service_seconds(audio_seconds))
        finally:
            self.slots.release()
        window = self._window()
        if window is not None and window.mode == EMPTY:
            stats.empty += 1
            return EMPTY
        draw = self.rng.random()
        if draw < self.profile.failure_rate:
            stats.errors += 1
            return ERROR
        empty_rate = {
            NEAR_SILENCE: self.profile.near_silence_empty_rate,
            SPEECH: self.profile.speech_empty_rate,
            SILENCE: 1.0,
        }[kind]
        if self.rng.random() < empty_rate:
            stats.empty += 1
            return EMPTY
        stats.words += 1
        return WORDS


class SimSamples:
    """Sized stand-in for decoded PCM that remembers its synthetic segment."""

    def __init__(self, segment_id: str, kind: str, size: int):
        self.segment_id, self.kind, self.size = segment_id, kind, size

    @classmethod
    def for_seconds(cls, segment_id: str, kind: str, seconds: float) -> 'SimSamples':
        return cls(segment_id, kind, int(round(seconds * SAMPLE_RATE)))

    def __len__(self) -> int:
        return self.size

    def __getitem__(self, key: slice) -> 'SimSamples':
        start, stop, _ = key.indices(self.size)
        return SimSamples(self.segment_id, self.kind, max(0, stop - start))


def synthetic_words(duration: float, offset: float = 0.1) -> list[dict]:
    end = min(duration, offset + 0.2)
    return [{'word': 'synthetic', 'timestamp': [offset, end]}] if end > offset else []


def vad_spans(samples: SimSamples) -> list[tuple[float, float]]:
    """Synthetic VAD truth: silence -> no spans, near-silence -> one short span, speech -> whole unit."""
    duration = len(samples) / SAMPLE_RATE
    if samples.kind == SILENCE:
        return []
    if samples.kind == NEAR_SILENCE:
        return [(min(0.5, duration / 4), min(duration, 1.5))]
    return [(0.0, duration)]


class PlannedWords:
    """Words provider + padded-retry hook for the REAL ``PipelineWorker``.

    Each segment's ASR outcome was already decided in virtual time; a planned
    ``error``/``timeout`` fails the whole ``transcribe_batch`` call, exactly like a
    provider exception does in production (every window of that packed batch).
    """

    def __init__(self):
        self.plan: dict[str, dict[str, str | None]] = {}
        self.calls = 0

    def transcribe_batch(self, samples_list):
        self.calls += 1
        outcomes = [self.plan[s.segment_id]['first'] for s in samples_list]
        if any(outcome in {ERROR, TIMEOUT} for outcome in outcomes):
            raise ProviderUnavailable('synthetic provider failure')
        return [
            synthetic_words(len(s) / SAMPLE_RATE) if outcome == WORDS else []
            for s, outcome in zip(samples_list, outcomes)
        ]

    def recover_words(self, samples, max_padded_seconds, *, before_dispatch=None, after_dispatch=None):
        outcome = self.plan[samples.segment_id].get('retry')
        if outcome is None or not padded_retry_fits(samples, max_padded_seconds):
            return None  # Oversize for the padded retry: the worker records skipped_oversize.
        # Match ParakeetWords.recover_empty: refusal retains custody, and only
        # an accepted provider result reports the padded audio quantum.
        if before_dispatch is not None and not before_dispatch():
            return None
        if outcome in {ERROR, TIMEOUT}:
            raise ProviderUnavailable('synthetic padded retry failure')
        if after_dispatch is not None:
            after_dispatch(padded_retry_seconds(samples))
        return synthetic_words(len(samples) / SAMPLE_RATE) if outcome == WORDS else []


@dataclass
class ModulateProfile:
    concurrency: int = 16
    base_latency_seconds: float = 2.0
    seconds_per_audio_second: float = 0.05
    latency_sigma: float = 0.3
    failure_rate: float = 0.0
    speech_recover_rate: float = 0.995
    near_silence_recover_rate: float = 0.6


class FakeModulate:
    """Paid fallback used by the real ``QuarantineRecovery`` (its ``stt`` seam). Counts paid calls."""

    def __init__(self, clock, profile: ModulateProfile, rng: random.Random, truth: dict[str, dict]):
        self.clock = clock
        self.profile = profile
        self.rng = rng
        self.truth = truth
        self.slots = _Slots(profile.concurrency)
        self.calls = 0
        self.audio_seconds = 0.0
        self.calls_by_owner: collections.Counter = collections.Counter()
        self.calls_by_segment: collections.Counter = collections.Counter()
        self.call_times: dict[str, list[float]] = collections.defaultdict(list)
        self.outcomes: collections.Counter = collections.Counter()

    async def occupy(self, audio_seconds: float) -> None:
        """Virtual-time cost of one request, paid by the task handler before the sync call."""
        await self.slots.acquire(None)
        try:
            profile = self.profile
            mean = profile.base_latency_seconds + profile.seconds_per_audio_second * audio_seconds
            await asyncio.sleep(
                mean * math.exp(self.rng.gauss(0, profile.latency_sigma) - profile.latency_sigma**2 / 2)
            )
        finally:
            self.slots.release()

    def __call__(self, item, binding, audio) -> dict[str, Any]:
        self.calls += 1
        self.audio_seconds += item.duration_seconds
        self.calls_by_owner[item.owner_id] += 1
        self.calls_by_segment[item.segment_id] += 1
        self.call_times[item.segment_id].append(self.clock.now)
        kind = self.truth[item.segment_id]['kind']
        duration = item.duration_seconds
        spans = [{'start': start, 'end': end} for start, end in vad_spans(SimSamples.for_seconds('x', kind, duration))]
        if self.rng.random() < self.profile.failure_rate:
            self.outcomes['provider_failed'] += 1
            raise ProviderUnavailable('synthetic paid provider failure')
        rate = self.profile.near_silence_recover_rate if kind == NEAR_SILENCE else self.profile.speech_recover_rate
        if kind == SILENCE or self.rng.random() >= rate:
            self.outcomes['empty'] += 1
            raise MultilingualEmpty(duration, spans)
        self.outcomes['recovered'] += 1
        return {
            'audio_seconds': duration,
            'speech_seconds': sum(span['end'] - span['start'] for span in spans),
            'speech_spans': spans,
            'words': synthetic_words(duration),
            'diarization': {'turns': []},
            'words_provider': 'legacy_sync',
            'language': 'en',
            'recovery_version': 1,
        }

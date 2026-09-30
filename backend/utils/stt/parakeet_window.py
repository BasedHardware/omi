"""Bounded, speech-only live TDT over the healthy batch endpoint."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import socket
import threading
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable, cast

import httpx
import numpy as np

from utils.async_tasks import wait_for_event
from utils.executors import start_background_task
from utils.http_client import get_stt_client, get_stt_semaphore
from utils.observability.fallback import FirstTextDeadlineDiagnostics, ReplayLagDiagnostics, record_fallback
from utils.stt import streaming as st
from utils.stt.live_metrics import (
    WINDOW_ACTIVE,
    WINDOW_ADMISSION,
    WINDOW_CAP,
    WINDOW_CONTEXT,
    WINDOW_DECODER_LOOPS,
    WINDOW_EMISSION_DROPS,
    WINDOW_FORCED_CUTS,
    WINDOW_FIRST_TEXT,
    WINDOW_HEAD_RECOVERIES,
    WINDOW_LATENCY,
    WINDOW_POSTS,
    WINDOW_PRESSURE_REFRESH,
    WINDOW_PRESSURE_REFUSAL,
    WINDOW_SESSION_OUTCOME,
    WINDOW_REPLAY_CUT_REQUESTS,
    WINDOW_REPLAY_CUT_PERFORMED,
    WINDOW_REPLAY_CUT_SKIPPED,
    WINDOW_STRANDED_FLUSHES,
)
from utils.stt.streaming import ParakeetConnectionError, ParakeetStreamingSocket, _pcm16_to_wav_bytes  # type: ignore[reportPrivateUsage]  # shared WAV encoder
from utils.stt.window_anchor import (
    IDLE_FLUSH_SECONDS,
    LEAD_IN_SECONDS,
    SILENCE_FLUSH_SECONDS,
    RawSegment,
    buffer_cap_seconds,
    collapse_decoder_loops,
    decide_window,
    parse_tdt_segments,
    read_max_context_seconds,
    read_pace_seconds,
)

# Two jobs, two stages, same 0.8 / 4× bound (the cap RNNT's peak<1 skip lacks).
# Admission: LiveLegSocket gains a *copy* for Silero. Decoding: one uniform
# scale of the original-level buffer at POST time. The stored bytes are never
# gained, so the posted stage cannot compound with ingest.
WINDOW_AGC_TARGET_PEAK = 0.8
WINDOW_AGC_MAX_GAIN = 4.0
WINDOW_INGEST_AGC = True
# Deadband on the *posted* (decode) stage only, applied per window. Audio already
# peaking above this fraction of full scale is not quiet, and gaining it costs
# accuracy: on a dense-speech clip, gaining loud passages moved substitutions from
# 27 to 37, and reverting the VAD threshold never moved them back. Below the
# deadband the boost is worth its distortion; above it there is nothing to rescue.
# 0.4 is equivalent to "never apply less than 2x (6 dB)".
#
# It is judged per posted window, not on the session envelope. On the same clip,
# passages peaking at 0.37 and 0.39 were dropped entirely (37 reference words)
# when the session peak of 0.54 denied them gain, while every passage at 0.42 and
# above survived. Admission is deliberately NOT deadbanded — the copy Silero
# scores is still always gained, which is what admits quiet far-field.
WINDOW_AGC_DEADBAND_PEAK = 0.4
# How much of the end of a posted window decides its gain. A growing window
# re-posts audio that has already been transcribed; the newest seconds are what
# this POST is actually for, so they choose the level. Long enough to be a stable
# estimate, short enough not to be dominated by an earlier louder speaker.
WINDOW_AGC_TAIL_SECONDS = 10.0
_INT16_ABS_MAX = 32767.0
# TDT sometimes skips a whole leading utterance of a long window: on a public
# earnings clip, [34.9 s, 58.9 s] came back with text only from 15.1 s in, while
# [34.9 s, 50.0 s] and [36.0 s, 58.9 s] both transcribed that utterance in full.
# The leg would then emit the later text and anchor past the skipped speech, losing
# it for good. When the first segment starts this late AND the VAD saw at least
# HEAD_RECOVERY_MIN_SPEECH_SECONDS of speech before it, the head is posted again on
# its own — it still starts at the anchor's sentence boundary, the case TDT handles.
# Normal leading gaps are the 0.3 s lead-in plus a breath, far under 3 s.
HEAD_RECOVERY_MIN_GAP_SECONDS = 3.0
HEAD_RECOVERY_MIN_SPEECH_SECONDS = 2.0
# How far an empty window at max context slides. It was the pace, which was 6 s;
# with window size now set by a 15 s pace, sliding by pace would discard 15 s of
# speech the model returned nothing for. Keep the slide at the measured 6 s.
EMPTY_CAP_SLIDE_SECONDS = 6.0
# Longer than ordinary 1.5–4s pauses, with 7s left in the startup deadline.
STRANDED_SILENCE_SECONDS = 5.0
# Answered-empty context may leave TDT only after the 90s capture replay horizon.
ANSWERED_CONTEXT_RETENTION_SECONDS = 90.0
FIRST_TEXT_DEADLINE_SECONDS = 12.0
# Three times the observed 280ms admission; never suppress unresolved audio.
SHORT_SPEECH_EPISODE_SECONDS = 1.0
# Several short utterances may return empty; only emitted text renews this allowance.
ANSWERED_EMPTY_SPEECH_BUDGET_SECONDS = 3.0
MAX_EMPTY_STREAK = 4


def _positive_float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if math.isfinite(value) and value > 0 else default


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


logger = logging.getLogger(__name__)


def pcm16_peak(pcm: bytes) -> float:
    if len(pcm) < 2:
        return 0.0
    samples = np.frombuffer(pcm, dtype=np.int16)
    if samples.size == 0:
        return 0.0
    return float(np.max(np.abs(samples.astype(np.int32))))


def bounded_agc_pcm16(
    pcm: bytes,
    *,
    peak: float | None = None,
    target: float | None = None,
    max_gain: float | None = None,
) -> tuple[bytes, float]:
    """Boost PCM16 toward WINDOW_AGC_TARGET_PEAK of full scale, at most WINDOW_AGC_MAX_GAIN.

    Never attenuates. Digital silence (peak 0) is unchanged. `peak` is the session
    envelope; when omitted or not yet observed, this buffer's own peak is used.
    """
    if peak is None or peak <= 0.0:
        peak = pcm16_peak(pcm)
    if peak <= 0.0:
        return pcm, 1.0
    target_peak = WINDOW_AGC_TARGET_PEAK if target is None else target
    cap = WINDOW_AGC_MAX_GAIN if max_gain is None else max_gain
    gain = min(cap, (_INT16_ABS_MAX * target_peak) / peak)
    if gain <= 1.0:
        return pcm, 1.0
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    out = np.clip(samples * gain, -32768, 32767).astype(np.int16)
    return out.tobytes(), float(gain)


def window_needs_gain(peak: float) -> bool:
    """Whether the POSTED (decode) stage should gain a window with this peak.

    Judged per posted window, never on the session envelope: a loud session still
    contains quiet passages, and those need the boost. Admission does not consult
    this at all — the copy Silero scores is always gained, which is what admits
    quiet far-field.
    """
    return peak <= WINDOW_AGC_DEADBAND_PEAK * _INT16_ABS_MAX


def posted_window_gain(pcm: bytes, tail_bytes: int) -> float:
    """One uniform gain for a posted window: chosen by its tail, bounded by its whole.

    The tail is the newest audio, which is what this POST exists to transcribe, so it
    decides whether the window is quiet and how much boost it wants. The whole window
    then caps that boost at the point where it would clip, so rescuing a quiet passage
    never distorts a louder prefix. Returns 1.0 to mean "post untouched".
    """
    tail = pcm[-tail_bytes:] if tail_bytes and len(pcm) > tail_bytes else pcm
    tail_peak = pcm16_peak(tail)
    if tail_peak <= 0.0 or not window_needs_gain(tail_peak):
        return 1.0
    desired = (_INT16_ABS_MAX * WINDOW_AGC_TARGET_PEAK) / tail_peak
    whole_peak = pcm16_peak(pcm)
    headroom = (_INT16_ABS_MAX / whole_peak) if whole_peak > 0.0 else WINDOW_AGC_MAX_GAIN
    return max(1.0, min(WINDOW_AGC_MAX_GAIN, desired, headroom))


class SessionPcmGain:
    """Causal bounded peak AGC. Fast attack, no release, never attenuates.

    The first chunk uses its own peak (maximum immediate boost, up to the cap).
    Later chunks use the session running-max of *pre-gain* peaks. There is no
    warm-up and no initial peak guess: both would under-gain the opening
    utterance, which is when this decoder is most start-sensitive.
    """

    def __init__(self) -> None:
        self.peak = 0.0
        self.last_gain = 1.0

    def apply(self, pcm: bytes) -> bytes:
        chunk_peak = pcm16_peak(pcm)
        if chunk_peak > self.peak:
            self.peak = chunk_peak
        out, gain = bounded_agc_pcm16(pcm, peak=self.peak)
        self.last_gain = gain
        return out


class QueueTimeout(TimeoutError):
    """Deadline expired while waiting for the shared STT semaphore."""


@dataclass(frozen=True)
class _WindowJob:
    pcm: bytes
    start: float
    duration: float
    start_bytes: int
    end_bytes: int
    force: bool
    pause: bool
    stranded_flush: bool = False


class WindowAdmission:
    """Process admission; no await between checking and acquiring a slot."""

    def __init__(self) -> None:
        self.active = 0
        self._lock = threading.Lock()

    def acquire(self) -> Callable[[], None]:
        cap = max(0, int(os.getenv('PARAKEET_WINDOW_MAX_SESSIONS', '1')))
        with self._lock:
            WINDOW_CAP.set(cap)
            if self.active >= cap:
                WINDOW_ADMISSION.labels(outcome='overflow').inc()
                raise ParakeetConnectionError('capacity_full', capacity_subtype='admission')
            self.active += 1
            WINDOW_ACTIVE.inc()
        released = False

        def release() -> None:
            nonlocal released
            with self._lock:
                if not released:
                    released = True
                    self.active -= 1
                    WINDOW_ACTIVE.dec()

        return release


admission = WindowAdmission()


class BatchPressure:
    """Poll the shared GPU batch queue off the session-start path."""

    REFRESH_SECONDS = 5.0
    STALE_SECONDS = 15.0
    MAX_REPLICAS = 8
    MAX_LIVE_PENDING_PER_REPLICA = 4
    MAX_LIVE_OLDEST_SECONDS = 0.75

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._observed_at = 0.0
        self._busy = False

    def start_from_env(self) -> None:
        """Start one poller only on processes configured to serve window sessions."""
        if os.getenv('STT_CONNECT_ORDER_FROM_CONFIG', 'false').lower() != 'true':
            return
        try:
            allocation = float(os.getenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0'))
            min_replicas = int(os.getenv('PARAKEET_BATCH_PRESSURE_MIN_REPLICAS', '2'))
        except ValueError:
            return
        pool_host = os.getenv('PARAKEET_BATCH_PRESSURE_POOL_HOST', '')
        if not math.isfinite(allocation) or allocation <= 0 or not pool_host or min_replicas < 1:
            return
        self.start(pool_host, min_replicas)

    def start(self, pool_host: str, min_replicas: int) -> None:
        loop = asyncio.get_running_loop()
        if self._task is not None and not self._task.done():
            if self._task.get_loop() is not loop:
                raise RuntimeError('Batch pressure poller belongs to another running event loop')
            return
        self._observed_at = 0.0
        self._busy = False
        self._task = start_background_task(self._refresh_forever(pool_host, min_replicas), name='window_batch_pressure')

    async def stop(self) -> None:
        task = self._task
        if task is not None:
            if task.get_loop() is not asyncio.get_running_loop():
                raise RuntimeError('Batch pressure poller must stop on its owning event loop')
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._task = None
        self._observed_at = 0.0
        self._busy = False

    async def _refresh_forever(self, pool_host: str, min_replicas: int) -> None:
        while True:
            try:
                limits = httpx.Limits(
                    max_connections=self.MAX_REPLICAS,
                    max_keepalive_connections=self.MAX_REPLICAS,
                    keepalive_expiry=30.0,
                )
                async with httpx.AsyncClient(timeout=1.0, trust_env=False, limits=limits) as client:
                    while True:
                        try:
                            await self._refresh(pool_host, min_replicas, client)
                        except Exception:
                            # Even an unexpected refresh fault invalidates the sample, then retries.
                            self._observed_at = 0.0
                            WINDOW_PRESSURE_REFRESH.labels(outcome='unavailable').inc()
                        await asyncio.sleep(self.REFRESH_SECONDS)
            except Exception:
                # Client construction/closure can also fail; retry with a fresh client.
                self._observed_at = 0.0
                WINDOW_PRESSURE_REFRESH.labels(outcome='unavailable').inc()
                await asyncio.sleep(self.REFRESH_SECONDS)

    def allows(self, pool_host: str, min_replicas: int) -> bool:
        if not pool_host or min_replicas < 1:
            WINDOW_PRESSURE_REFUSAL.labels(reason='unconfigured').inc()
            return False
        now = time.monotonic()
        # Every listen process stands down when pool telemetry is missing/stale.
        if self._observed_at <= 0:
            WINDOW_PRESSURE_REFUSAL.labels(reason='missing').inc()
            return False
        if now - self._observed_at > self.STALE_SECONDS:
            WINDOW_PRESSURE_REFUSAL.labels(reason='stale').inc()
            return False
        if self._busy:
            WINDOW_PRESSURE_REFUSAL.labels(reason='pressure').inc()
            return False
        return True

    async def _refresh(self, pool_host: str, min_replicas: int, client: httpx.AsyncClient) -> None:
        try:
            if not pool_host or min_replicas < 1:
                raise ValueError('Parakeet batch pool discovery is not configured')
            addresses = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(pool_host, 8080, family=socket.AF_INET, type=socket.SOCK_STREAM),
                timeout=1.0,
            )
            ips = {address[4][0] for address in addresses}
            if len(ips) > self.MAX_REPLICAS:
                raise ValueError('Parakeet batch pool has more replicas than the poll cap')
            if len(ips) < min_replicas:
                raise ValueError('Parakeet batch pool has fewer ready replicas than expected')
            responses = await asyncio.gather(*(client.get(f'http://{ip}:8080/batch/metrics') for ip in ips))
            busiest_live_replica = 0.0
            oldest_live_wait = 0.0
            for response in responses:
                response.raise_for_status()
                metrics = response.json()
                # A mixed-revision pool lacks these fields. Stand down until
                # every ready GPU replica reports the live lane explicitly.
                pending = metrics['live_pending_requests']
                oldest = metrics['live_oldest_pending_seconds']
                if any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                    for value in (pending, oldest)
                ):
                    raise ValueError('Invalid Parakeet batch pressure sample')
                if int(pending) != pending:
                    raise ValueError('Invalid Parakeet live pending count')
                busiest_live_replica = max(busiest_live_replica, pending)
                oldest_live_wait = max(oldest_live_wait, oldest)
            self._busy = (
                busiest_live_replica >= self.MAX_LIVE_PENDING_PER_REPLICA
                or oldest_live_wait >= self.MAX_LIVE_OLDEST_SECONDS
            )
            self._observed_at = time.monotonic()
            WINDOW_PRESSURE_REFRESH.labels(outcome='pressure' if self._busy else 'healthy').inc()
        except Exception:
            # A failed replica query invalidates the fleet sample; admission stays local and nonblocking.
            self._observed_at = 0.0
            WINDOW_PRESSURE_REFRESH.labels(outcome='unavailable').inc()


batch_pressure = BatchPressure()


class WindowedParakeetSocket(ParakeetStreamingSocket):
    """One in-flight POST, sentence-anchored growing windows, no retries.

    The owner must supply only actively VAD-gated audio. A gate fault kills the
    socket before any raw audio reaches send(). All shutdown paths release admission.
    Buffer overflow sheds this pod's TDT circuit so new sessions skip the GPU.
    """

    def __init__(
        self,
        callback: Callable[[list[dict[str, Any]]], None],
        api_url: str,
        sample_rate: int,
        release: Callable[[], None],
    ) -> None:
        pace = read_pace_seconds()
        super().__init__(callback, api_url, sample_rate, window_seconds=pace)
        self._release = release
        self._health_success: Callable[[], None] = lambda: None
        self._health_close: Callable[[], None] = lambda: None
        self._first_speech_at: float | None = None
        self._first_text_recorded = False
        self._first_text_deadline = _positive_float_env(
            'PARAKEET_WINDOW_FIRST_TEXT_DEADLINE_SECONDS', FIRST_TEXT_DEADLINE_SECONDS
        )
        self._max_empty_streak = _positive_int_env('PARAKEET_WINDOW_MAX_EMPTY_STREAK', MAX_EMPTY_STREAK)
        self._empty_streak = 0
        self._first_text_timer: asyncio.TimerHandle | None = None
        self._deadline_speech_at: float | None = None
        self._deadline_speech_bytes = 0
        self._admitted_speech_bytes = 0
        self._answered_empty_stranded_flushes = 0
        self._answered_empty_speech_bytes = 0
        self._answered_empty_speech_end = 0
        self.first_text_diagnostics: FirstTextDeadlineDiagnostics | None = None
        self._session_outcome_recorded = False
        self._wake = asyncio.Event()
        self._pause_requested = False
        self._idle_flushed = False
        self._capture_seconds = 0.0
        self._answered_context_ends: deque[tuple[int, float]] = deque()
        self._capture_clock_seen = False
        self._capture_silence_seconds = 0.0
        self._capture_silence_flush = False
        self._stranded_flush_used = False
        self._stranded_fragment_answered = False
        self._accounted_speech_end = 0
        self._answered_empty_span: tuple[int, int] | None = None
        self._last_accepted_at = 0.0
        self._last_post_anchor = -1
        self._last_post_end = -1
        self._next_post = 0.0
        self._post_timeout = max(0.1, float(os.getenv('PARAKEET_WINDOW_POST_TIMEOUT_SECONDS', '8')))
        self._diarize = self._diarize and os.getenv('PARAKEET_WINDOW_DIARIZATION', 'false').lower() == 'true'
        self._embedded_this_window = False
        self._next_send_speech = False
        self._received_bytes = 0
        self._speech_spans: deque[tuple[int, int]] = deque()
        self._pace_seconds = pace
        self._max_context_seconds = read_max_context_seconds()
        self._pace_bytes = self._window_bytes
        self._max_context_bytes = int(self._max_context_seconds * sample_rate) * 2
        self._lead_in_bytes = int(LEAD_IN_SECONDS * sample_rate) * 2
        self._silence_bytes = int(SILENCE_FLUSH_SECONDS * sample_rate) * 2
        self._anchor_bytes = 0
        self._now_bytes = 0
        self._last_emitted_end = 0.0
        self._capacity_subtype: str | None = None
        self._replay_cut_requested = False
        self.replay_lag_diagnostics: ReplayLagDiagnostics | None = None
        self._post_in_flight = False
        self._pacing_wait = False
        self._last_text_at: float | None = None
        self._diagnostic_anchor_sample = 0
        self._posts_since_anchor = 0
        self._empty_posts_since_anchor = 0
        self._on_replay_progress: Callable[[], None] = lambda: None
        # Anchor bytes of the one window whose beyond-window drops are being
        # re-posted (see `_run_job`): bounded to a single retry per anchor.
        self._beyond_window_repost: int | None = None
        self._agc_peak = 0.0
        self._agc_last_gain = 1.0

    def set_health_callbacks(self, on_success: Callable[[], None], on_close: Callable[[], None]) -> None:
        self._health_success, self._health_close = on_success, on_close

    @property
    def typed_death_reason(self) -> str | None:
        return getattr(self, '_typed_death_reason', None)

    @property
    def capacity_subtype(self) -> str | None:
        return self._capacity_subtype

    def has_untranscribed_speech(self) -> bool:
        """Whether replay still protects speech that this leg has not emitted."""
        # finish() clears the PCM/spans. A failed or closing leg must still
        # protect its replay snapshot until the receiver replaces/drains it.
        if self._closed or self._dead:
            return True
        return (
            self._first_speech_at is not None and not self._first_text_recorded and not self._stranded_fragment_answered
        ) or self._has_unanswered_speech()

    def replay_anchor_sample(self) -> int | None:
        """Provider sample before which emitted text makes capture replay unnecessary."""
        if not self._first_text_recorded:
            return None
        with self._lock:
            # Empty forced cuts may slide the POST anchor without emitting text.
            return min(self._anchor_bytes, self._to_bytes(self._last_emitted_end)) // 2

    def set_replay_progress_callback(self, callback: Callable[[], None]) -> None:
        self._on_replay_progress = callback

    def replay_diagnostics(self, capture_seconds: float, admitted_seconds: float) -> ReplayLagDiagnostics:
        """Snapshot state before fail() cancels a POST or pacing wait."""
        return ReplayLagDiagnostics(
            capture_seconds=capture_seconds,
            admitted_seconds=admitted_seconds,
            seconds_since_text=-1.0 if self._last_text_at is None else max(0.0, time.monotonic() - self._last_text_at),
            posts_since_anchor=self._posts_since_anchor,
            empty_posts_since_anchor=self._empty_posts_since_anchor,
            post_in_flight=self._post_in_flight,
            empty_streak=self._empty_streak,
            cut_pending=self._replay_cut_requested,
            pacing_wait=self._pacing_wait,
        )

    def request_replay_cut(self) -> None:
        """Bound capture-ring lag on the next TDT result that contains text."""
        if self._closed or self._dead:
            return
        if not self._replay_cut_requested:
            WINDOW_REPLAY_CUT_REQUESTS.inc()
            if self._post_in_flight:
                WINDOW_REPLAY_CUT_SKIPPED.labels(reason='post_in_flight').inc()
            elif self._pacing_wait:
                WINDOW_REPLAY_CUT_SKIPPED.labels(reason='post_pacing').inc()
        self._replay_cut_requested = True
        self._wake.set()

    def start(self) -> None:
        super().start()
        assert self._pump_task is not None
        # Also releases if cancellation occurs before the coroutine's first step.
        self._pump_task.add_done_callback(self._on_pump_done)

    def _on_pump_done(self, task: asyncio.Task[None]) -> None:
        if not self._closed and not self._dead:
            self._dead = True
            self._dead_reason = 'cancelled' if task.cancelled() else 'connection_lost'
        try:
            self._record_session_outcome()
        finally:
            try:
                self._close_health()
            finally:
                self._release()

    def _close_health(self) -> None:
        try:
            self._health_close()
        except Exception:
            # A health callback is auxiliary; it cannot suppress session
            # telemetry or admission release after the pump has ended.
            logger.warning('Parakeet window health-close callback failed')

    def _record_session_outcome(self) -> None:
        if self._session_outcome_recorded or self._first_speech_at is None:
            return
        self._session_outcome_recorded = True
        reason = self._dead_reason if self._dead_reason in {'first_text_deadline', 'empty_streak'} else 'none'
        WINDOW_SESSION_OUTCOME.labels(outcome='text' if self._first_text_recorded else 'no_text', reason=reason).inc()

    def _cancel_first_text_timer(self) -> None:
        if self._first_text_timer is not None:
            self._first_text_timer.cancel()
            self._first_text_timer = None

    def _expire_first_text(self) -> None:
        self._first_text_timer = None
        if (
            self._deadline_speech_at is not None
            and not self._first_text_recorded
            and not self._closed
            and not self._dead
        ):
            now = time.monotonic()
            self.first_text_diagnostics = FirstTextDeadlineDiagnostics(
                admitted_seconds=self._to_seconds(self._admitted_speech_bytes),
                posts=self._posts_since_anchor,
                empty_posts=self._empty_posts_since_anchor,
                answered_empty_stranded_flushes=self._answered_empty_stranded_flushes,
                seconds_since_first_speech=max(0.0, now - cast(float, self._first_speech_at)),
                episode_admitted_seconds=self._to_seconds(self._deadline_speech_bytes),
                seconds_since_deadline_speech=max(0.0, now - self._deadline_speech_at),
                answered_empty_admitted_seconds=self._to_seconds(self._answered_empty_speech_bytes),
            )
            self.fail('first_text_deadline')

    def replay_accounted_span(self) -> tuple[int, int] | None:
        """Answered-empty audio remains eligible for replay until capture ages it out."""
        if self._answered_empty_span is None:
            return None
        start, end = self._answered_empty_span
        start = max(start, (self.replay_anchor_sample() or 0) * 2)
        return (start // 2, end // 2) if start < end else None

    def replay_pending_sample(self) -> int | None:
        """Separate unresolved speech capacity from retained answered-empty history."""
        if self._closed or self._dead:
            return None
        return max(self._accounted_speech_end // 2, self.replay_anchor_sample() or 0)

    def _has_unanswered_speech(self) -> bool:
        with self._lock:
            start = max(self._anchor_bytes, self._accounted_speech_end)
            return self._last_speech_end_locked(start, self._received_bytes) is not None

    def observe_capture(self, is_speech: bool, duration: float) -> None:
        """Only a long capture silence may resolve a stranded fragment."""
        if self._closed or self._dead:
            return
        self._capture_clock_seen = True
        self._capture_seconds += duration
        expired_end = None
        while (
            self._answered_context_ends
            and self._capture_seconds - self._answered_context_ends[0][1] >= ANSWERED_CONTEXT_RETENTION_SECONDS
        ):
            expired_end, _ = self._answered_context_ends.popleft()
        if expired_end is not None:
            # Only previously answered empty context expires, never an
            # unresolved/in-flight span. The replay copy ages independently.
            self._advance_anchor(max(self._anchor_bytes, expired_end))
            if self._answered_empty_span is not None:
                first, end = self._answered_empty_span
                self._answered_empty_span = (max(first, expired_end), end) if expired_end < end else None
        if is_speech:
            self._capture_silence_seconds = 0.0
            self._capture_silence_flush = False
            self._stranded_flush_used = False
        else:
            self._capture_silence_seconds = min(STRANDED_SILENCE_SECONDS, self._capture_silence_seconds + duration)
            if (
                self._capture_silence_seconds >= STRANDED_SILENCE_SECONDS
                and not self._stranded_flush_used
                and self._has_unanswered_speech()
            ):
                self._capture_silence_flush = True
                self._wake.set()

    def mark_speech(self) -> None:
        if not self._has_unemitted_speech():
            # A VAD finalize received with no pending speech belongs to the
            # previous utterance, not this new fragment.
            self._pause_requested = False
        self._next_send_speech = True
        if self._capture_silence_flush or self._stranded_flush_used or self._stranded_fragment_answered:
            # Re-arm within the original first-text budget even when speech
            # resumes before the stranded job is selected or answered.
            self._next_post = 0.0
        self._stranded_fragment_answered = False

    def _buffer_cap(self) -> int:
        return int(buffer_cap_seconds(self._pace_seconds, self._max_context_seconds) * self._sample_rate) * 2

    def _compact_speech_spans(self) -> None:
        """Keep VAD flicker bounded without forgetting speech or the POST anchor."""
        if len(self._speech_spans) <= 1024:
            return
        spans = list(self._speech_spans)
        pair = min(
            range(len(spans) - 1),
            key=lambda index: spans[index + 1][0] - spans[index][1],
        )
        spans[pair : pair + 2] = [(spans[pair][0], spans[pair + 1][1])]
        self._speech_spans = deque(spans)

    def send(self, data: bytes) -> bool:
        if self._closed or self._dead:
            return False
        if not data:
            return True
        if not self._next_send_speech:
            self._trim_idle_nonspeech()
        if len(self._buf) + len(data) > self._buffer_cap():
            self._shed_capacity()
            return False
        if self._next_send_speech and data:
            if self._first_speech_at is None:
                self._first_speech_at = time.monotonic()
            if not self._first_text_recorded and self._deadline_speech_at is None:
                self._deadline_speech_at = time.monotonic()
                self._first_text_timer = asyncio.get_running_loop().call_later(
                    self._first_text_deadline, self._expire_first_text
                )
            self._admitted_speech_bytes += len(data)
            if not self._first_text_recorded:
                self._deadline_speech_bytes += len(data)
            end = self._received_bytes + len(data)
            if self._speech_spans and self._speech_spans[-1][1] == self._received_bytes:
                start, _ = self._speech_spans.pop()
                self._speech_spans.append((start, end))
            else:
                self._speech_spans.append((self._received_bytes, end))
                self._compact_speech_spans()
        self._next_send_speech = False
        self._received_bytes += len(data)
        accepted = super().send(data)
        if accepted and data:
            self._observe_agc_peak(data)
            self._last_accepted_at = time.monotonic()
            self._idle_flushed = False
        self._wake.set()
        return accepted

    def observe_session_peak(self, peak: float) -> None:
        """Fold a pre-VAD incoming peak into the posted envelope.

        LiveLegSocket observes every chunk, including those the gate later
        drops. Posted AGC must use that same running-max so VAD and TDT share
        one session envelope. Does not mark the buffer as gained.
        """
        if peak > self._agc_peak:
            self._agc_peak = peak

    def _observe_agc_peak(self, data: bytes) -> None:
        peak = pcm16_peak(data)
        if peak > self._agc_peak:
            self._agc_peak = peak

    def _normalize_posted_pcm(self, pcm: bytes) -> bytes:
        # Buffer is original-level. One uniform scale for this window, taken from
        # *this window's* own peak — not the session envelope.
        #
        # The session envelope is the wrong reference for the deadband. A clip
        # whose loudest moment is 0.54 of full scale still contains passages at
        # 0.37, and judging those by the session peak denies them a boost they
        # do need: two such passages went missing entirely (37 reference words)
        # while every passage at 0.42 and above was captured. Scoring each window
        # on itself gains the quiet stretches and leaves the loud ones alone.
        #
        # Each POST remains internally uniform, which is the property that
        # matters — the failure mode fixed in #15566 was several gain levels
        # inside one posted window, not different gains between windows.
        #
        # The window's *whole* peak is still the wrong reference, for the same
        # reason one step down. A growing window that spans a level change reads
        # its loudest content, applies no gain, and loses the quiet part: on dev
        # the identical clip scored WER 0.155 or 0.262 depending only on where
        # the anchor fell (anchored at 53s the window peaks at 0.377 and is
        # gained; at 34s it peaks at 0.431 and is not). So the TAIL — the newest
        # audio, which is what this POST is for — chooses the gain, and the whole
        # window caps it at the clipping point. On the measured case the tail
        # wants 2.16x and the window allows 2.30x, so the quiet passage is
        # rescued with no distortion of the loud prefix.
        gain = posted_window_gain(pcm, self._to_bytes(WINDOW_AGC_TAIL_SECONDS))
        if gain <= 1.0:
            self._agc_last_gain = 1.0
            return pcm
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        out = np.clip(samples * gain, -32768, 32767).astype(np.int16)
        self._agc_last_gain = gain
        return out.tobytes()

    def finalize(self) -> None:
        self._pause_requested = True
        self._wake.set()

    def fail(self, reason: str, *, capacity_subtype: str | None = None) -> None:
        if self._dead:
            return
        self._dead, self._dead_reason = True, reason
        if reason == 'capacity_full':
            self._capacity_subtype = capacity_subtype
        if reason in {'first_text_deadline', 'empty_streak', 'capacity_full'}:
            self._typed_death_reason = reason
        self.finish()

    def _shed_capacity(self) -> None:
        st._parakeet_circuit.record_serve_failure()  # type: ignore[reportPrivateUsage]  # shared circuit owner
        self.fail('capacity_full', capacity_subtype='buffer_cap')

    def finish(self) -> None:
        self._closed = True
        self._cancel_first_text_timer()
        self._buf.clear()
        self._speech_spans.clear()
        self._answered_context_ends.clear()
        self._answered_empty_span = None
        self._wake.set()
        pump = self._pump_task
        if pump is not None and not pump.done() and pump is not asyncio.current_task():
            pump.cancel()
        try:
            self._close_health()
        finally:
            self._release()

    async def drain_and_close(self) -> None:
        self._closed = True
        self._cancel_first_text_timer()
        self._wake.set()
        self._release()
        try:
            if self._pump_task is not None:
                await self._pump_task
        finally:
            self.finish()

    async def _pump(self) -> None:
        try:
            while not self._dead:
                timeout = self._idle_wait_timeout()
                try:
                    if timeout is None:
                        await self._wake.wait()
                    elif timeout > 0.0:
                        await asyncio.wait_for(self._wake.wait(), timeout=timeout)
                except TimeoutError:
                    pass
                self._wake.clear()
                posted = False
                # Answered-empty PCM is retained context, not another pending POST.
                while not self._dead and not self._stranded_fragment_answered and self._has_unemitted_speech():
                    while not self._closed:
                        # Pace before selecting: a context captured before the wait would be stale.
                        delay = self._next_post - asyncio.get_running_loop().time()
                        if delay <= 0:
                            break
                        self._pacing_wait = True
                        self._wake.clear()
                        try:
                            if not await wait_for_event(self._wake, delay):
                                break
                        finally:
                            self._pacing_wait = False
                    job = self._next_job()
                    if job is None or self._dead:
                        break
                    posted = True
                    self._next_post = asyncio.get_running_loop().time() + self._pace_seconds
                    await self._run_job(job)
                if self._closed:
                    return
                if timeout == 0.0 and not posted:
                    await self._wake.wait()
                    self._wake.clear()
        except asyncio.CancelledError:
            # A deadline can cancel an in-flight POST through finish(). Preserve
            # that first failure so session telemetry matches the replay reason.
            if not self._dead:
                self._dead = True
                self._dead_reason = 'cancelled'
            raise
        except Exception:
            # Bounded reason only: never include audio, text or HTTP bodies in logs.
            self.fail('provider_5xx')
        finally:
            try:
                self._close_health()
            finally:
                self._release()

    async def _run_job(self, job: _WindowJob) -> None:
        posted_pcm = job.pcm
        if job.stranded_flush and len(posted_pcm) < self._silence_bytes:
            # Give a short completed fragment a silence envelope, retaining
            # the real duration for timestamps and the original PCM for replay.
            posted_pcm += bytes(self._silence_bytes - len(posted_pcm))
        if job.stranded_flush:
            WINDOW_STRANDED_FLUSHES.labels(outcome='performed').inc()
        segments = await self._post_and_parse(posted_pcm, job.duration)
        if self._dead:
            return
        if job.stranded_flush:
            WINDOW_STRANDED_FLUSHES.labels(outcome='answered_text' if segments else 'answered_empty').inc()
        if segments:
            self._empty_streak = 0
        else:
            with self._lock:
                has_speech = self._speech_bytes_locked(job.start_bytes, job.end_bytes) > 0
                # POSTs overlap retained context. Count each admitted sample
                # once, before anchor advancement can prune its VAD span.
                self._answered_empty_speech_bytes += self._speech_bytes_locked(
                    max(job.start_bytes, self._answered_empty_speech_end), job.end_bytes
                )
                self._answered_empty_speech_end = max(self._answered_empty_speech_end, job.end_bytes)
            if has_speech:
                self._empty_streak = min(1000000, self._empty_streak + 1)
                if not self._first_text_recorded and self._empty_streak >= self._max_empty_streak:
                    self.fail('empty_streak')
                    return
        segments = await self._recover_skipped_head(job, segments)
        if self._dead:
            return
        cut_requested = self._replay_cut_requested
        replay_anchor_before = self.replay_anchor_sample() or 0
        has_held_tail = cut_requested and len(
            decide_window(segments, job.duration, job.duration + 1.0, force=job.force, pause=job.pause).emit
        ) < len(segments)
        decision = decide_window(
            segments,
            job.duration,
            self._max_context_seconds,
            force=job.force,
            pause=job.pause,
            empty_cap_slide=EMPTY_CAP_SLIDE_SECONDS,
            # Preserve sentence anchoring while the buffer has room. Force
            # the long held tail only when another pace of audio would leave
            # too little room for the next POST to make progress.
            min_cap_progress=(self._pace_seconds if len(self._buf) >= self._buffer_cap() - self._pace_bytes else 0.0),
            force_replay_cut=self._replay_cut_requested,
        )
        if decision.forced_cut:
            WINDOW_FORCED_CUTS.inc()
        emitted, beyond_window = await self._materialize(decision.emit, job.pcm, job.start, job.duration)
        if emitted and not self._dead:
            if any(str(item.get('text', '')).strip() for item in emitted):
                # Parsed but held text cannot renew the allowance. Keep the
                # counted endpoint so old overlapping PCM is not counted again.
                self._answered_empty_speech_bytes = 0
                if not self._first_text_recorded:
                    self._first_text_recorded = True
                    self._cancel_first_text_timer()
                    if self._first_speech_at is not None:
                        WINDOW_FIRST_TEXT.observe(max(0.0, time.monotonic() - self._first_speech_at))
            # Snapshot the emission boundary in this socket's stream seconds
            # BEFORE the callback: downstream rewrites start/end in place onto
            # other clocks (the epoch translator projects wall-epoch seconds,
            # the legacy chain rebases by its own offset), and comparing
            # those against stream seconds made every later window clamp onto
            # its own edge as zero-length segments (dev 2026-09-26 v2 collapse).
            self._last_emitted_end = max(self._last_emitted_end, max(float(item['end']) for item in emitted))
            self._last_text_at = time.monotonic()
            self._stream_transcript(emitted)
        self._now_bytes = job.end_bytes
        self._last_post_anchor = job.start_bytes
        self._last_post_end = job.end_bytes
        new_anchor_bytes: int | None = None
        if decision.new_anchor is not None:
            rel_bytes = min(job.end_bytes - job.start_bytes, max(0, self._to_bytes(decision.new_anchor)))
            new_anchor_bytes = job.start_bytes + rel_bytes
        if beyond_window:
            # TDT timestamps at/beyond the posted duration are drift on
            # re-posted audio, not silence: the dropped segments are that
            # audio's only text, so never silently consume it. When nothing
            # was emitted, hold the anchor and re-post the window once (the
            # retry bound keeps a persistently drifting decoder from stalling
            # the buffer into a capacity shed); when something was emitted,
            # still stop the anchor at the last sample actually emitted. The
            # drop metric keeps counting either way.
            if emitted:
                self._beyond_window_repost = None
                if new_anchor_bytes is not None:
                    emitted_end = job.start_bytes + self._to_bytes(max(float(item['end']) for item in emitted))
                    new_anchor_bytes = min(new_anchor_bytes, emitted_end)
            elif self._beyond_window_repost != job.start_bytes:
                self._beyond_window_repost = job.start_bytes
                new_anchor_bytes = None
            else:
                self._beyond_window_repost = None
        elif emitted:
            self._beyond_window_repost = None
        if job.stranded_flush and not segments:
            self._answered_empty_stranded_flushes = min(1000000, self._answered_empty_stranded_flushes + 1)
            # Successful empty decoding after a long silence settles capacity
            # only. Keep the POST anchor/PCM and replay copy for later context.
            self._accounted_speech_end = max(self._accounted_speech_end, job.end_bytes)
            first = job.start_bytes if self._answered_empty_span is None else self._answered_empty_span[0]
            self._answered_empty_span = (first, self._accounted_speech_end)
            self._answered_context_ends.append((job.end_bytes, self._capture_seconds))
            self._stranded_fragment_answered = not self._has_unanswered_speech()
            new_anchor_bytes = None
            if self._stranded_fragment_answered:
                self._replay_cut_requested = False
                if (
                    not self._first_text_recorded
                    and self._capture_silence_seconds >= STRANDED_SILENCE_SECONDS
                    and self._deadline_speech_bytes < self._to_bytes(SHORT_SPEECH_EPISODE_SECONDS)
                    and self._answered_empty_speech_bytes < self._to_bytes(ANSWERED_EMPTY_SPEECH_BUDGET_SECONDS)
                ):
                    # Retire only isolated short, fully answered episodes.
                    # Their cumulative empty-answered speech never resets on
                    # cancellation, silence or PCM aging. At 3s, keep the
                    # current 12s rescue even when each episode was <1s.
                    self._cancel_first_text_timer()
                    self._deadline_speech_at = None
                    self._deadline_speech_bytes = 0
                    self._empty_streak = 0
        if new_anchor_bytes is not None:
            self._advance_anchor(new_anchor_bytes)
            if emitted:
                self._replay_cut_requested = False
        if cut_requested:
            if not segments:
                WINDOW_REPLAY_CUT_SKIPPED.labels(reason='no_text_yet').inc()
            elif not emitted or (self.replay_anchor_sample() or 0) <= replay_anchor_before:
                WINDOW_REPLAY_CUT_SKIPPED.labels(reason='other').inc()
            elif not has_held_tail:
                WINDOW_REPLAY_CUT_SKIPPED.labels(reason='no_held_tail').inc()
            elif (
                decision.forced_cut
                and (self.replay_anchor_sample() or 0) >= self._to_bytes(job.start + segments[-1].end) // 2
            ):
                WINDOW_REPLAY_CUT_PERFORMED.inc()
            else:
                WINDOW_REPLAY_CUT_SKIPPED.labels(reason='other').inc()

    async def _recover_skipped_head(self, job: _WindowJob, segments: list[RawSegment]) -> list[RawSegment]:
        if not segments or segments[0].start < HEAD_RECOVERY_MIN_GAP_SECONDS:
            return segments
        head = min(job.duration, segments[0].start)
        head_bytes = self._to_bytes(head)
        with self._lock:
            speech = self._to_seconds(self._speech_bytes_locked(job.start_bytes, job.start_bytes + head_bytes))
        if speech < HEAD_RECOVERY_MIN_SPEECH_SECONDS:
            return segments
        # One attempt, never recursive: a head that is skipped again stays skipped.
        recovered = await self._post_and_parse(job.pcm[:head_bytes], head)
        kept = [s for s in recovered if s.start < head]
        WINDOW_HEAD_RECOVERIES.labels(outcome='recovered' if kept else 'empty').inc()
        return [*kept, *segments]

    def _speech_bytes_locked(self, start: int, end: int) -> int:
        total = 0
        for a, b in self._speech_spans:
            lo, hi = max(a, start), min(b, end)
            if hi > lo:
                total += hi - lo
        return total

    def _idle_wait_timeout(self) -> float | None:
        if self._closed or self._dead or self._idle_flushed or self._capture_clock_seen:
            return None
        if not self._has_unemitted_speech():
            return None
        remaining = self._last_accepted_at + IDLE_FLUSH_SECONDS - time.monotonic()
        return max(0.0, remaining)

    def _has_unemitted_speech(self) -> bool:
        with self._lock:
            if self._received_bytes <= self._anchor_bytes:
                return False
            return self._last_speech_end_locked(self._anchor_bytes, self._received_bytes) is not None

    def _next_job(self) -> _WindowJob | None:
        with self._lock:
            self._trim_leading_nonspeech_locked()
            origin = self._origin_bytes()
            if self._anchor_bytes < origin:
                self._anchor_bytes = origin
            received = self._received_bytes
            if received <= self._anchor_bytes:
                self._pause_requested = False
                return None
            speech_end = self._last_speech_end_locked(self._anchor_bytes, received)
            if speech_end is None:
                self._pause_requested = False
                return None
            silence_flush = not self._capture_clock_seen and (received - speech_end) >= self._silence_bytes
            at_cap = (received - self._anchor_bytes) >= self._max_context_bytes
            idle_flush = (
                not self._capture_clock_seen
                and not self._idle_flushed
                and time.monotonic() - self._last_accepted_at >= IDLE_FLUSH_SECONDS
            )
            stranded_flush = self._capture_silence_flush and received - self._anchor_bytes <= self._max_context_bytes
            stepped = self._now_bytes + self._pace_bytes
            if self._now_bytes <= self._anchor_bytes:
                stepped = self._anchor_bytes + self._pace_bytes
            closing = self._closed
            pause = False
            if silence_flush or idle_flush or stranded_flush:
                end = min(received, self._anchor_bytes + self._max_context_bytes)
                force = True
            elif closing:
                end = min(received, self._anchor_bytes + self._max_context_bytes)
                force = end >= received
            elif at_cap:
                end = min(received, self._anchor_bytes + self._max_context_bytes)
                force = False
                pause = self._pause_requested
            elif self._pause_requested:
                end = min(received, self._anchor_bytes + self._max_context_bytes)
                force = False
                pause = True
            else:
                if received < stepped:
                    return None
                end = min(received, self._anchor_bytes + self._max_context_bytes)
                force = False
            if end <= self._anchor_bytes:
                return None
            if not force and self._anchor_bytes == self._last_post_anchor and end <= self._last_post_end:
                self._pause_requested = False
                return None
            if stranded_flush:
                self._stranded_flush_used = True
                self._capture_silence_flush = False
            if (silence_flush or idle_flush or stranded_flush) and end >= received:
                self._idle_flushed = True
                self._capture_silence_flush = False
            if self._pause_requested and (pause or force or end >= received):
                self._pause_requested = False
            pcm = self._pcm_range_locked(self._anchor_bytes, end)
            start = self._to_seconds(self._anchor_bytes)
            duration = self._to_seconds(end - self._anchor_bytes)
            return _WindowJob(
                pcm,
                start,
                duration,
                self._anchor_bytes,
                end,
                force,
                pause,
                stranded_flush=stranded_flush,
            )

    def _origin_bytes(self) -> int:
        return self._received_bytes - len(self._buf)

    def _to_seconds(self, n_bytes: int) -> float:
        return n_bytes / (2 * self._sample_rate)

    def _to_bytes(self, seconds: float) -> int:
        return int(seconds * self._sample_rate) * 2

    def _pcm_range_locked(self, start: int, end: int) -> bytes:
        origin = self._origin_bytes()
        a = max(0, start - origin)
        b = max(a, min(len(self._buf), end - origin))
        return bytes(self._buf[a:b])

    def _last_speech_end_locked(self, start: int, end: int) -> int | None:
        last: int | None = None
        for a, b in self._speech_spans:
            if b <= start or a >= end:
                continue
            clipped = min(end, b)
            last = clipped if last is None else max(last, clipped)
        return last

    def _trim_leading_nonspeech_locked(self) -> None:
        origin = self._origin_bytes()
        first: int | None = None
        for a, b in self._speech_spans:
            if b <= origin:
                continue
            onset = max(a, origin)
            first = onset if first is None else min(first, onset)
        if first is None:
            keep_from = max(origin, self._received_bytes - self._lead_in_bytes)
        else:
            keep_from = max(origin, first - self._lead_in_bytes)
        drop = keep_from - origin
        if drop > 0:
            del self._buf[: min(drop, len(self._buf))]
        origin = self._origin_bytes()
        if self._anchor_bytes < origin:
            self._anchor_bytes = origin
        while self._speech_spans and self._speech_spans[0][1] <= origin:
            self._speech_spans.popleft()

    def _trim_idle_nonspeech(self) -> None:
        with self._lock:
            if self._last_speech_end_locked(self._anchor_bytes, self._received_bytes) is not None:
                return
            self._trim_leading_nonspeech_locked()

    def _advance_anchor(self, new_anchor: int) -> None:
        with self._lock:
            previous = self._anchor_bytes
            origin = self._origin_bytes()
            drop = new_anchor - origin
            if drop > 0:
                del self._buf[: min(drop, len(self._buf))]
            origin = self._origin_bytes()
            self._anchor_bytes = max(new_anchor, origin)
            while self._speech_spans and self._speech_spans[0][1] <= self._anchor_bytes:
                self._speech_spans.popleft()
            if self._speech_spans and self._speech_spans[0][0] < self._anchor_bytes:
                _, end = self._speech_spans.popleft()
                self._speech_spans.appendleft((self._anchor_bytes, end))
        replay_anchor = self.replay_anchor_sample() or 0
        if replay_anchor > self._diagnostic_anchor_sample:
            self._diagnostic_anchor_sample = replay_anchor
            self._posts_since_anchor = 0
            self._empty_posts_since_anchor = 0
        if self._anchor_bytes > previous:
            try:
                self._on_replay_progress()
            except Exception:
                # Replay telemetry/compaction cannot turn a successful POST
                # into provider failure; the receiver checks again before send.
                logger.warning('Parakeet window replay anchor callback failed')

    async def _assign_speaker(self, seg_pcm: bytes) -> int:
        if self._embedded_this_window:
            return self._last_speaker
        if self._diarize and len(seg_pcm) >= int(self._sample_rate * 2 * 0.6):
            self._embedded_this_window = True
        try:
            return await asyncio.wait_for(super()._assign_speaker(seg_pcm), timeout=1.0)
        except TimeoutError:
            record_fallback(
                component='stt_selection',
                from_mode='speaker_embedding',
                to_mode='previous_speaker',
                reason='timeout',
                outcome='degraded',
            )
            return self._last_speaker

    async def _post_window(self, pcm: bytes) -> httpx.Response:
        # Snapshot the uniform scale before the first await so a later send
        # cannot change this POST's envelope. Overlapping later POSTs may use a
        # lower gain if the session peak grew; each POST stays internally flat.
        wav = _pcm16_to_wav_bytes(self._normalize_posted_pcm(pcm), self._sample_rate)
        acquired = False
        try:
            async with asyncio.timeout(self._post_timeout):
                async with get_stt_semaphore():
                    acquired = True
                    return await get_stt_client().post(
                        self._url,
                        files={'file': ('audio.wav', wav, 'audio/wav')},
                        headers={'X-Omi-STT-Surface': 'live-window'},
                    )
        except (TimeoutError, httpx.TimeoutException):
            if not acquired:
                raise QueueTimeout() from None
            raise

    async def _post_and_parse(self, pcm: bytes, dur: float) -> list[RawSegment]:
        started = time.monotonic()
        outcome = 'error'
        self._posts_since_anchor = min(1000000, self._posts_since_anchor + 1)
        self._post_in_flight = True
        try:
            try:
                response = await self._post_window(pcm)
            finally:
                self._post_in_flight = False
            if response.status_code >= 500:
                st._parakeet_circuit.record_serve_failure()  # type: ignore[reportPrivateUsage]  # shared circuit owner
                self.fail('provider_5xx')
                response.raise_for_status()
            if response.status_code == 413:
                self.fail('provider_5xx')
                raise ValueError('TDT payload too large')
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or ('text' not in data and 'segments' not in data):
                self.fail('provider_5xx')
                raise ValueError('Invalid TDT response')
            segments = [self._without_loops(seg) for seg in parse_tdt_segments(cast(dict[str, Any], data), dur)]
            outcome = 'success' if segments else 'empty'
            if not segments:
                self._empty_posts_since_anchor = min(1000000, self._empty_posts_since_anchor + 1)
            self._health_success()
            return segments
        except asyncio.CancelledError:
            outcome = 'cancelled'
            raise
        except QueueTimeout:
            outcome = 'queue_timeout'
            self.fail('timeout')
            raise
        except (TimeoutError, httpx.TimeoutException):
            st._parakeet_circuit.record_serve_failure()  # type: ignore[reportPrivateUsage]  # shared circuit owner
            self.fail('timeout')
            raise
        except Exception:
            if not self._dead:
                self.fail('provider_5xx')
            raise
        finally:
            WINDOW_POSTS.labels(outcome=outcome).inc()
            WINDOW_LATENCY.observe(time.monotonic() - started)
            WINDOW_CONTEXT.observe(dur)

    @staticmethod
    def _without_loops(segment: RawSegment) -> RawSegment:
        text, collapsed = collapse_decoder_loops(segment.text)
        if not collapsed:
            return segment
        WINDOW_DECODER_LOOPS.inc(collapsed)
        return RawSegment(text=text, start=segment.start, end=segment.end)

    async def _materialize(
        self, segments: tuple[RawSegment, ...] | list[RawSegment], pcm: bytes, start: float, dur: float
    ) -> tuple[list[dict[str, Any]], bool]:
        """Convert window-relative TDT segments to stream positions, honestly.

        Every emitted position is ``start + rel``: an endpoint never moves to
        satisfy monotonicity or the window bounds. TDT timestamps that fall at
        or beyond the posted window duration cannot be located in the posted
        audio at all (timestamp drift on re-posted windows), and a returned
        segment whose interval ends at or before the last emission is a
        re-detection of already-emitted audio; both are dropped and counted
        instead of being collapsed onto the window/anchor edge as a
        zero-length segment (dev 2026-09-26 v2 collapse).

        Returns the emitted segments plus whether any segment was dropped for
        timestamps at/beyond the window duration, so the caller can refuse to
        consume audio whose only text was dropped that way.
        """
        self._embedded_this_window = False
        out: list[dict[str, Any]] = []
        beyond_window = False
        for segment in segments:
            if not math.isfinite(segment.start) or not math.isfinite(segment.end):
                self.fail('provider_5xx')
                raise ValueError('Invalid TDT timestamps')
            if segment.start >= dur:
                WINDOW_EMISSION_DROPS.labels(reason='timestamp_beyond_window').inc()
                beyond_window = True
                continue
            rel_start = max(0.0, segment.start)
            rel_end = min(dur, max(segment.start, segment.end))
            abs_start = start + rel_start
            abs_end = start + rel_end
            if abs_end <= abs_start:
                WINDOW_EMISSION_DROPS.labels(reason='degenerate_timestamps').inc()
                continue
            if abs_end <= self._last_emitted_end:
                WINDOW_EMISSION_DROPS.labels(reason='already_emitted').inc()
                continue
            if abs_start < self._last_emitted_end:
                # A re-detection straddling the boundary: the prefix is a
                # duplicate but the tail is new audio, so trim instead of
                # re-emitting the whole overlap (or dropping the phrase).
                abs_start = self._last_emitted_end
            # Buffer is original-level capture. Embeddings slice that PCM, not
            # the posted uniform-gain copy the decoder hears.
            speaker = await self._assign_speaker(self._slice_pcm(pcm, abs_start - start, rel_end))
            out.append(
                {
                    'speaker': f'SPEAKER_{speaker}',
                    'start': abs_start,
                    'end': abs_end,
                    'text': segment.text,
                    'is_user': False,
                    'person_id': None,
                }
            )
        return out, beyond_window

    async def _transcribe_chunk(self, pcm: bytes, start: float, dur: float) -> list[dict[str, Any]]:
        segments = await self._post_and_parse(pcm, dur)
        if self._dead:
            return []
        emitted, _beyond_window = await self._materialize(segments, pcm, start, dur)
        return emitted


def connect_window(callback: Callable[[list[dict[str, Any]]], None], sample_rate: int) -> WindowedParakeetSocket:
    try:
        min_replicas = int(os.getenv('PARAKEET_BATCH_PRESSURE_MIN_REPLICAS', '2'))
    except ValueError:
        min_replicas = 0
    if not batch_pressure.allows(
        os.getenv('PARAKEET_BATCH_PRESSURE_POOL_HOST', ''),
        min_replicas,
    ):
        WINDOW_ADMISSION.labels(outcome='batch_pressure').inc()
        raise ParakeetConnectionError('capacity_full', capacity_subtype='admission')
    release = admission.acquire()
    try:
        socket = WindowedParakeetSocket(callback, os.environ['HOSTED_PARAKEET_API_URL'], sample_rate, release)
        socket.start()
        # Count only a socket whose pump started successfully. Keeping this at the
        # connection boundary makes the accepted outcome describe an actual
        # admission, rather than an acquired slot whose socket failed to start.
        WINDOW_ADMISSION.labels(outcome='accepted').inc()
        return socket
    except BaseException:
        release()
        raise

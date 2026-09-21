"""Bounded, speech-only live TDT over the healthy batch endpoint."""

from __future__ import annotations

import asyncio
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, cast

import httpx

from utils.http_client import get_stt_client, get_stt_semaphore
from utils.observability.fallback import record_fallback
from utils.stt import streaming as st
from utils.stt.live_metrics import (
    WINDOW_ACTIVE,
    WINDOW_ADMISSION,
    WINDOW_CAP,
    WINDOW_CONTEXT,
    WINDOW_FORCED_CUTS,
    WINDOW_LATENCY,
    WINDOW_POSTS,
)
from utils.stt.streaming import ParakeetConnectionError, ParakeetStreamingSocket, _pcm16_to_wav_bytes  # type: ignore[reportPrivateUsage]  # shared WAV encoder
from utils.stt.window_anchor import (
    IDLE_FLUSH_SECONDS,
    LEAD_IN_SECONDS,
    SILENCE_FLUSH_SECONDS,
    RawSegment,
    buffer_cap_seconds,
    decide_window,
    parse_tdt_segments,
    read_max_context_seconds,
    read_pace_seconds,
)


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
                raise ParakeetConnectionError('capacity_full')
            self.active += 1
            WINDOW_ACTIVE.inc()
            WINDOW_ADMISSION.labels(outcome='accepted').inc()
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
        self._wake = asyncio.Event()
        self._pause_requested = False
        self._idle_flushed = False
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

    def set_health_callbacks(self, on_success: Callable[[], None], on_close: Callable[[], None]) -> None:
        self._health_success, self._health_close = on_success, on_close

    def start(self) -> None:
        super().start()
        assert self._pump_task is not None
        # Also releases if cancellation occurs before the coroutine's first step.
        self._pump_task.add_done_callback(self._on_pump_done)

    def _on_pump_done(self, task: asyncio.Task[None]) -> None:
        if not self._closed:
            self._dead = True
            self._dead_reason = 'cancelled' if task.cancelled() else 'connection_lost'
        self._health_close()
        self._release()

    def mark_speech(self) -> None:
        self._next_send_speech = True

    def _buffer_cap(self) -> int:
        return int(buffer_cap_seconds(self._pace_seconds, self._max_context_seconds) * self._sample_rate) * 2

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
            end = self._received_bytes + len(data)
            if self._speech_spans and self._speech_spans[-1][1] == self._received_bytes:
                start, _ = self._speech_spans.pop()
                self._speech_spans.append((start, end))
            elif len(self._speech_spans) < 1024:
                self._speech_spans.append((self._received_bytes, end))
            else:
                self.fail('capacity_full')
                return False
        self._next_send_speech = False
        self._received_bytes += len(data)
        accepted = super().send(data)
        if accepted and data:
            self._last_accepted_at = time.monotonic()
            self._idle_flushed = False
        self._wake.set()
        return accepted

    def finalize(self) -> None:
        self._pause_requested = True
        self._wake.set()

    def fail(self, reason: str) -> None:
        if self._dead:
            return
        self._dead, self._dead_reason = True, reason
        self.finish()

    def _shed_capacity(self) -> None:
        st._parakeet_circuit.record_serve_failure()  # type: ignore[reportPrivateUsage]  # shared circuit owner
        self.fail('capacity_full')

    def finish(self) -> None:
        self._closed = True
        self._buf.clear()
        self._speech_spans.clear()
        self._wake.set()
        pump = self._pump_task
        if pump is not None and not pump.done() and pump is not asyncio.current_task():
            pump.cancel()
        self._health_close()
        self._release()

    async def drain_and_close(self) -> None:
        self._closed = True
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
                while not self._dead and self._has_unemitted_speech():
                    if not self._closed:
                        # Pace before selecting: a context captured before the wait would be stale.
                        delay = self._next_post - asyncio.get_running_loop().time()
                        if delay > 0:
                            await asyncio.sleep(delay)
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
            self._dead = True
            self._dead_reason = 'cancelled'
            raise
        except Exception:
            # Bounded reason only: never include audio, text or HTTP bodies in logs.
            self.fail('provider_5xx')
        finally:
            self._health_close()
            self._release()

    async def _run_job(self, job: _WindowJob) -> None:
        segments = await self._post_and_parse(job.pcm, job.duration)
        if self._dead:
            return
        decision = decide_window(
            segments,
            job.duration,
            self._max_context_seconds,
            force=job.force,
            pause=job.pause,
            empty_cap_slide=self._pace_seconds,
        )
        if decision.forced_cut:
            WINDOW_FORCED_CUTS.inc()
        emitted = await self._materialize(decision.emit, job.pcm, job.start, job.duration)
        if emitted and not self._dead:
            self._stream_transcript(emitted)
            self._last_emitted_end = max(self._last_emitted_end, max(float(item['end']) for item in emitted))
        self._now_bytes = job.end_bytes
        self._last_post_anchor = job.start_bytes
        self._last_post_end = job.end_bytes
        if decision.new_anchor is not None:
            rel_bytes = min(job.end_bytes - job.start_bytes, max(0, self._to_bytes(decision.new_anchor)))
            self._advance_anchor(job.start_bytes + rel_bytes)

    def _idle_wait_timeout(self) -> float | None:
        if self._closed or self._dead or self._idle_flushed:
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
            silence_flush = (received - speech_end) >= self._silence_bytes
            at_cap = (received - self._anchor_bytes) >= self._max_context_bytes
            idle_flush = (not self._idle_flushed) and (time.monotonic() - self._last_accepted_at >= IDLE_FLUSH_SECONDS)
            stepped = self._now_bytes + self._pace_bytes
            if self._now_bytes <= self._anchor_bytes:
                stepped = self._anchor_bytes + self._pace_bytes
            closing = self._closed
            pause = False
            if silence_flush or idle_flush:
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
            if idle_flush and end >= received:
                self._idle_flushed = True
            if self._pause_requested and (pause or force or end >= received):
                self._pause_requested = False
            pcm = self._pcm_range_locked(self._anchor_bytes, end)
            start = self._to_seconds(self._anchor_bytes)
            duration = self._to_seconds(end - self._anchor_bytes)
            return _WindowJob(pcm, start, duration, self._anchor_bytes, end, force, pause)

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
            origin = self._origin_bytes()
            drop = new_anchor - origin
            if drop > 0:
                del self._buf[: min(drop, len(self._buf))]
            origin = self._origin_bytes()
            self._anchor_bytes = max(new_anchor, origin)
            while self._speech_spans and self._speech_spans[0][1] <= self._anchor_bytes:
                self._speech_spans.popleft()

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
        acquired = False
        try:
            async with asyncio.timeout(self._post_timeout):
                async with get_stt_semaphore():
                    acquired = True
                    return await get_stt_client().post(
                        self._url,
                        files={'file': ('audio.wav', _pcm16_to_wav_bytes(pcm, self._sample_rate), 'audio/wav')},
                    )
        except (TimeoutError, httpx.TimeoutException):
            if not acquired:
                raise QueueTimeout() from None
            raise

    async def _post_and_parse(self, pcm: bytes, dur: float) -> list[RawSegment]:
        started = time.monotonic()
        outcome = 'error'
        try:
            response = await self._post_window(pcm)
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
            segments = parse_tdt_segments(cast(dict[str, Any], data), dur)
            outcome = 'success' if segments else 'empty'
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

    async def _materialize(
        self, segments: tuple[RawSegment, ...] | list[RawSegment], pcm: bytes, start: float, dur: float
    ) -> list[dict[str, Any]]:
        self._embedded_this_window = False
        now = start + dur
        out: list[dict[str, Any]] = []
        for segment in segments:
            if not math.isfinite(segment.start) or not math.isfinite(segment.end):
                self.fail('provider_5xx')
                raise ValueError('Invalid TDT timestamps')
            rel_start = min(dur, max(0.0, segment.start))
            rel_end = min(dur, max(rel_start, segment.end))
            speaker = await self._assign_speaker(self._slice_pcm(pcm, rel_start, rel_end))
            abs_start = min(now, max(start, self._last_emitted_end, start + rel_start))
            abs_end = min(now, max(abs_start, start + rel_end))
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
        return out

    async def _transcribe_chunk(self, pcm: bytes, start: float, dur: float) -> list[dict[str, Any]]:
        segments = await self._post_and_parse(pcm, dur)
        if self._dead:
            return []
        return await self._materialize(segments, pcm, start, dur)


def connect_window(callback: Callable[[list[dict[str, Any]]], None], sample_rate: int) -> WindowedParakeetSocket:
    release = admission.acquire()
    try:
        socket = WindowedParakeetSocket(callback, os.environ['HOSTED_PARAKEET_API_URL'], sample_rate, release)
        socket.start()
        return socket
    except BaseException:
        release()
        raise

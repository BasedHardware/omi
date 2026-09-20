"""Bounded, speech-only live TDT over the healthy batch endpoint."""

from __future__ import annotations

import asyncio
import os
import math

import httpx
import threading
import time
from collections import deque
from typing import Any, Callable, cast

from utils.http_client import get_stt_client, get_stt_semaphore
from utils.stt import streaming as st
from utils.stt.live_metrics import WINDOW_ACTIVE, WINDOW_ADMISSION, WINDOW_CAP, WINDOW_LATENCY, WINDOW_POSTS
from utils.stt.streaming import ParakeetConnectionError, ParakeetStreamingSocket, _pcm16_to_wav_bytes  # type: ignore[reportPrivateUsage]  # shared WAV encoder

BUFFER_WINDOWS = 3
PACE_SECONDS = 6.0


class QueueTimeout(TimeoutError):
    """Deadline expired while waiting for the shared STT semaphore."""


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
    """One pump/POST, <=18 seconds buffered, paced silence flushes, no retries.

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
        super().__init__(callback, api_url, sample_rate, window_seconds=6.0)
        self._release = release
        self._health_success: Callable[[], None] = lambda: None
        self._health_close: Callable[[], None] = lambda: None
        self._wake = asyncio.Event()
        self._flush_requested = False
        self._next_post = 0.0
        self._post_timeout = max(0.1, float(os.getenv('PARAKEET_WINDOW_POST_TIMEOUT_SECONDS', '8')))
        self._diarize = self._diarize and os.getenv('PARAKEET_WINDOW_DIARIZATION', 'false').lower() == 'true'
        self._embedded_this_window = False
        self._next_send_speech = False
        self._received_bytes = 0
        self._speech_spans: deque[tuple[int, int]] = deque()

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
        return BUFFER_WINDOWS * self._window_bytes

    def send(self, data: bytes) -> bool:
        if self._closed or self._dead:
            return False
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
        self._wake.set()
        return accepted

    def finalize(self) -> None:
        self._flush_requested = True
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
                await self._wake.wait()
                self._wake.clear()
                while self._buf and (self._closed or self._flush_requested or len(self._buf) >= self._window_bytes):
                    take = min(len(self._buf), self._window_bytes)
                    chunk = bytes(self._buf[:take])
                    del self._buf[:take]
                    end_byte = self._received_bytes - len(self._buf)
                    start = self._emitted_seconds
                    duration = len(chunk) / (2 * self._sample_rate)
                    self._emitted_seconds += duration
                    self._flush_requested = False
                    has_speech = any(a < end_byte and b > end_byte - take for a, b in self._speech_spans)
                    while self._speech_spans and self._speech_spans[0][1] <= end_byte:
                        self._speech_spans.popleft()
                    if not has_speech:
                        continue
                    if not self._closed:
                        delay = self._next_post - asyncio.get_running_loop().time()
                        if delay > 0:
                            await asyncio.sleep(delay)
                        self._next_post = asyncio.get_running_loop().time() + PACE_SECONDS
                    segments = await self._transcribe_chunk(chunk, start, duration)
                    if segments and not self._dead:
                        self._stream_transcript(segments)
                if self._closed:
                    return
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

    async def _assign_speaker(self, seg_pcm: bytes) -> int:
        if self._embedded_this_window:
            return self._last_speaker
        if self._diarize and len(seg_pcm) >= int(self._sample_rate * 2 * 0.6):
            self._embedded_this_window = True
        try:
            return await asyncio.wait_for(super()._assign_speaker(seg_pcm), timeout=1.0)
        except TimeoutError:
            from utils.observability.fallback import record_fallback

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

    async def _transcribe_chunk(self, pcm: bytes, start: float, dur: float) -> list[dict[str, Any]]:
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
            self._embedded_this_window = False
            segments = await self._normalize_chunk(cast(dict[str, Any], data), pcm, start, dur)
            for segment in segments:
                if not all(math.isfinite(float(segment[key])) for key in ('start', 'end')):
                    self.fail('provider_5xx')
                    raise ValueError('Invalid TDT timestamps')
                segment['start'] = min(start + dur, max(start, segment['start']))
                segment['end'] = min(start + dur, max(segment['start'], segment['end']))
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


def connect_window(callback: Callable[[list[dict[str, Any]]], None], sample_rate: int) -> WindowedParakeetSocket:
    release = admission.acquire()
    try:
        socket = WindowedParakeetSocket(callback, os.environ['HOSTED_PARAKEET_API_URL'], sample_rate, release)
        socket.start()
        return socket
    except BaseException:
        release()
        raise

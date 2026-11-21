"""Last-speech clock for batch-only listen sockets.

Batch-only sockets run no live STT, so the lifecycle loop only had the audio
clock, and a pendant that keeps streaming through silence never reached its
quiet timeout: separate conversations merged until the device disconnected.
This runs the local Silero model the VAD gate and sync segmentation already use
and records the wall time of the latest sustained speech. A model failure marks
the clock failed, and the caller falls back to the audio clock.
"""

from __future__ import annotations

import audioop
import logging
import math
import time
from datetime import datetime
from typing import Any, Optional

import numpy as np

from utils.observability.fallback import record_fallback
from utils.observability.listen_loop import listen_loop_metrics_enabled, record_vad_windows
from utils.stt.local_vad import VAD_SAMPLE_RATE, VAD_WINDOW_SAMPLES, make_fresh_state, run_vad_window

logger = logging.getLogger(__name__)

SPEECH_THRESHOLD = 0.5  # the sync segmentation threshold (local_vad.segments_from_16khz_samples)
MIN_SPEECH_WINDOWS = 3  # ~96 ms of consecutive speech; a click or a cough does not hold a conversation open


class SpeechClock:
    def __init__(self, sample_rate: int, *, opened_at: float) -> None:
        self.sample_rate = sample_rate
        self.opened_at = opened_at
        self.started_at: Optional[float] = None
        self.last_speech_at: Optional[float] = None
        self.failed = False
        self._state, self._context = make_fresh_state()
        self._samples = np.zeros(0, dtype=np.float32)
        self._remainder = b''
        self._ratecv: Any = None
        self._run = 0

    def accept(self, pcm16: bytes, at: float) -> None:
        """Score decoded mono PCM16 received at wall time `at`. Never raises."""
        if self.failed or not pcm16:
            return
        if self.started_at is None:
            self.started_at = at
        started, windows = time.perf_counter(), 0
        try:
            data = self._remainder + pcm16
            self._remainder = data[-1:] if len(data) % 2 else b''
            data = data[: len(data) - len(self._remainder)]
            if self.sample_rate != VAD_SAMPLE_RATE:
                data, self._ratecv = audioop.ratecv(data, 2, 1, self.sample_rate, VAD_SAMPLE_RATE, self._ratecv)
            fresh = np.frombuffer(data, dtype='<i2').astype(np.float32) / 32768
            samples = np.concatenate([self._samples, fresh]) if self._samples.size else fresh
            offset = 0
            while offset + VAD_WINDOW_SAMPLES <= len(samples):
                prob, self._state, self._context = run_vad_window(
                    samples[offset : offset + VAD_WINDOW_SAMPLES], self._state, self._context
                )
                if not math.isfinite(prob):
                    raise ValueError('non-finite VAD probability')
                self._run = self._run + 1 if prob > SPEECH_THRESHOLD else 0
                if self._run >= MIN_SPEECH_WINDOWS:
                    self.last_speech_at = at
                offset += VAD_WINDOW_SAMPLES
                windows += 1
            self._samples = samples[offset:].copy()
            if listen_loop_metrics_enabled():
                record_vad_windows(windows, time.perf_counter() - started)
        except Exception as error:
            self.failed = True
            record_fallback(
                component='vad',
                from_mode='speech_clock',
                to_mode='audio_clock',
                reason='vad_failed',
                outcome='degraded',
                log=logger,
            )
            logger.warning('Speech clock disabled for this socket type=%s', type(error).__name__)


def quiet_since(clock: Optional[SpeechClock], row_created_at: Optional[datetime], now: float) -> Optional[float]:
    """Wall time a batch-owned row's quiet timeout counts from.

    None means no trustworthy speech clock (use the audio clock). A row created
    by this socket that has heard no speech returns `now`: an
    all-silent row stays open rather than closing into an empty recording every
    timeout. A row resumed from an earlier socket may hold speech this clock
    never heard, so its resume counts as speech: the row stays open for one
    full timeout after each reconnect.
    """
    if clock is None or clock.failed:
        return None
    created = row_created_at.timestamp() if row_created_at is not None else None
    marks = []
    if clock.last_speech_at is not None and (created is None or clock.last_speech_at >= created):
        marks.append(clock.last_speech_at)
    if created is not None and created < clock.opened_at and clock.started_at is not None:
        marks.append(clock.started_at)
    return max(marks) if marks else now


def rotation_due(
    clock: Optional[SpeechClock],
    row_created_at: Optional[datetime],
    now: float,
    *,
    min_age: float,
    pause: float,
    max_age: float,
) -> bool:
    """Whether a v3 recording should seal now so its transcript keeps flowing during a long capture.

    It seals at the first short pause once `min_age` old, or at `max_age` without one. A row
    with no speech heard by this clock never rotates. Without a trustworthy clock only the cap
    applies.
    """
    if row_created_at is None:
        return False
    created = row_created_at.timestamp()
    age = now - created
    if clock is None or clock.failed:
        return age >= max_age
    if clock.last_speech_at is None or clock.last_speech_at < max(created, clock.opened_at):
        return False
    return age >= max_age or (age >= min_age and now - clock.last_speech_at >= pause)

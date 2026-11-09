"""Listen event-loop health: loop lag, per-frame processing time and VAD inference rate.

These are the signals the listen HPA retune (D0b: CPU 55%, more sockets per pod) is watched on.
Labels are closed vocabularies only; never uid, session or conversation identifiers.

Kill switch: ``LISTEN_LOOP_METRICS_ENABLED`` (default on; ``false``/``0``/``off``/``no``
disables). It is read at the call boundary: once per probe start, once per session for
frame timing and once per VAD gate for window counting, so a rollback needs only an env
change and pod restart.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import time
from typing import Optional

from prometheus_client import Counter, Histogram

from utils.executors import start_background_task

logger = logging.getLogger(__name__)

ENABLED_ENV = 'LISTEN_LOOP_METRICS_ENABLED'
_OFF_VALUES = frozenset({'false', '0', 'off', 'no'})

# Sleep-drift probe period. Four wakeups a second per process is negligible next to the
# ~50 frames/s each active session delivers, and gives ~1.2k samples per pod per 5m.
LOOP_LAG_PROBE_INTERVAL_SECONDS = 0.25

FRAME_CODECS = ('opus', 'aac', 'lc3', 'pcm8', 'pcm16', 'multi_channel', 'other')

LISTEN_EVENT_LOOP_LAG_SECONDS = Histogram(
    'omi_listen_event_loop_lag_seconds',
    'Event-loop scheduling lag measured as asyncio.sleep drift beyond the probe interval, per listen process',
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
LISTEN_FRAME_PROCESSING_SECONDS = Histogram(
    'omi_listen_frame_processing_seconds',
    'Wall time from receiving one client audio frame to being ready for the next receive, by bounded codec',
    ['codec'],
    buckets=(0.0001, 0.00025, 0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 1.0),
)
VAD_WINDOWS_TOTAL = Counter(
    'omi_vad_windows_total',
    'Silero VAD windows inferred by the streaming VAD gate; rate() gives VAD inferences per second',
)
VAD_INFERENCE_SECONDS_TOTAL = Counter(
    'omi_vad_inference_seconds_total',
    'Wall seconds spent inside streaming VAD gate inference (conversion, buffering and ONNX windows)',
)


def listen_loop_metrics_enabled() -> bool:
    return os.getenv(ENABLED_ENV, '').strip().lower() not in _OFF_VALUES


def frame_codec_label(codec: Optional[str], *, multi_channel: bool = False) -> str:
    if multi_channel:
        return 'multi_channel'
    return codec if codec in FRAME_CODECS else 'other'


class FrameTimer:
    """Times one audio frame at a time for a single listen session. No-op when disabled."""

    __slots__ = ('_child', '_started')

    def __init__(self, codec: Optional[str], *, multi_channel: bool = False, enabled: Optional[bool] = None):
        if enabled is None:
            enabled = listen_loop_metrics_enabled()
        self._child = (
            LISTEN_FRAME_PROCESSING_SECONDS.labels(codec=frame_codec_label(codec, multi_channel=multi_channel))
            if enabled
            else None
        )
        self._started: Optional[float] = None

    def start(self) -> None:
        if self._child is not None:
            self._started = time.perf_counter()

    def stop(self) -> None:
        started = self._started
        if started is None:
            return
        self._started = None
        try:
            self._child.observe(time.perf_counter() - started)  # type: ignore[union-attr]
        except Exception:
            pass


def record_vad_windows(windows: int, seconds: float) -> None:
    try:
        # Seconds count even when the call only converted and buffered (no full window yet).
        if seconds > 0:
            VAD_INFERENCE_SECONDS_TOTAL.inc(seconds)
        if windows > 0:
            VAD_WINDOWS_TOTAL.inc(windows)
    except Exception:
        pass


async def _probe_loop_lag(interval: float) -> None:
    clock = time.monotonic
    while True:
        started = clock()
        await asyncio.sleep(interval)
        try:
            LISTEN_EVENT_LOOP_LAG_SECONDS.observe(max(0.0, clock() - started - interval))
        except Exception:
            pass


_probe: Optional[tuple[asyncio.AbstractEventLoop, asyncio.Task]] = None


def ensure_loop_lag_probe(interval: float = LOOP_LAG_PROBE_INTERVAL_SECONDS) -> Optional[asyncio.Task]:
    """Start one lag probe per running loop; idempotent and safe to call on every session."""
    global _probe
    if not listen_loop_metrics_enabled():
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    current = _probe
    if current is not None and current[0] is loop and not current[1].done():
        return current[1]
    # Start from an empty context: the first session's context carries its uid and
    # validated BYOK keys, and a lifetime task would otherwise pin them for the pod.
    task = contextvars.Context().run(start_background_task, _probe_loop_lag(interval), name='listen_loop_lag_probe')
    _probe = (loop, task)
    return task

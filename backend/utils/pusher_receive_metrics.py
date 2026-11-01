"""Closed-label socket observations; timers never interrupt the observed work."""

import asyncio
import time
from contextlib import contextmanager
from typing import Iterator, Literal

from prometheus_client import Counter, Gauge, Histogram

Stage = Literal['record_begin', 'custody_commit', 'projection_enqueue', 'inline_finish', 'drain']
CloseReason = Literal[
    'peer', 'receive_timeout', 'queue_wait_timeout', 'application_error', 'cancelled', 'protocol_error', 'rejected'
]
STAGES = ('record_begin', 'custody_commit', 'projection_enqueue', 'inline_finish', 'drain')
AGE_BUCKETS = ('<5m', '5m_to_30m', '30m_plus')
FRAME_KINDS = ('heartbeat', 'audio', 'control', 'invalid')
CLOSE_REASONS = (
    'peer',
    'receive_timeout',
    'queue_wait_timeout',
    'application_error',
    'cancelled',
    'protocol_error',
    'rejected',
)
FRAMES_SEEN = ('none', 'control_only', 'audio')
WORK_STALL_SECONDS = 300.0
WORK_BUCKETS = (0.5, 1, 5, 30, 60, 300, 600, 3600)

SOCKET_FRAMES = Counter('pusher_socket_frames_total', 'Frames actually received by socket age', ['kind', 'age_bucket'])
WORK_STALLS = Counter('pusher_receive_work_stalls_total', 'Receive work waits crossing 300 seconds', ['stage'])
WORK_STALLED = Gauge('pusher_receive_work_stalled_handlers', 'Current receive work waits beyond 300 seconds', ['stage'])
WORK_DURATION = Histogram(
    'pusher_receive_work_duration_seconds',
    'Receive work duration on completion or cancellation',
    ['stage'],
    buckets=WORK_BUCKETS,
)
SOCKET_CLOSED = Counter(
    'pusher_socket_closed_total',
    'Handler exits, including drain, by socket age and received frame class',
    ['reason', 'age_bucket', 'frames_seen'],
)

# Zero baselines distinguish an observed zero from a missing scrape. Maximum
# exposition: 225 series/process, including *_created and histogram +Inf.
for _kind in FRAME_KINDS:
    for _age in AGE_BUCKETS:
        SOCKET_FRAMES.labels(_kind, _age)
for _stage in STAGES:
    WORK_STALLS.labels(_stage)
    WORK_STALLED.labels(_stage)
    WORK_DURATION.labels(_stage)
for _reason in CLOSE_REASONS:
    for _age in AGE_BUCKETS:
        for _frames in FRAMES_SEEN:
            SOCKET_CLOSED.labels(_reason, _age, _frames)


def age_bucket(seconds: float) -> str:
    return '<5m' if seconds < 300 else '5m_to_30m' if seconds < 1800 else '30m_plus'


@contextmanager
def observe_work(stage: Stage) -> Iterator[None]:
    """One crossing per wait, with synchronous unwind even during cancellation."""
    if stage not in STAGES:
        raise ValueError('unknown pusher receive stage')
    started = time.monotonic()
    stalled = False

    def crossed() -> None:
        nonlocal stalled
        stalled = True
        WORK_STALLS.labels(stage).inc()
        WORK_STALLED.labels(stage).inc()

    timer = asyncio.get_running_loop().call_later(WORK_STALL_SECONDS, crossed)
    try:
        yield
    finally:
        timer.cancel()
        duration = time.monotonic() - started
        # The loop can resume this waiter before an overdue timer callback.
        if not stalled and duration >= WORK_STALL_SECONDS:
            crossed()
        if stalled:
            WORK_STALLED.labels(stage).dec()
        WORK_DURATION.labels(stage).observe(duration)


class SocketObservation:
    def __init__(self) -> None:
        self.started = time.monotonic()
        self.reason: CloseReason = 'rejected'
        self.frames_seen = 'none'
        self.closed = False

    def frame(self, header: int | None) -> None:
        kind = (
            'heartbeat'
            if header == 100
            else 'audio' if header == 101 else 'control' if header in (102, 103, 104, 105) else 'invalid'
        )
        if kind == 'audio':
            self.frames_seen = 'audio'
        elif self.frames_seen == 'none':
            self.frames_seen = 'control_only'
        SOCKET_FRAMES.labels(kind, age_bucket(time.monotonic() - self.started)).inc()

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            SOCKET_CLOSED.labels(self.reason, age_bucket(time.monotonic() - self.started), self.frames_seen).inc()

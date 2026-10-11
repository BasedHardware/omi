"""Aggregate sync-attempt timing; context follows the existing executor dispatch."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterator, ParamSpec, TypeVar
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
import asyncio
import inspect
import logging
import os
import queue
import uuid
from datetime import datetime, timezone
import threading
import time

from prometheus_client import Histogram

PHASES = ('decode_vad', 'gcs', 'parakeet', 'speaker_id', 'firestore')
DURATION = Histogram(
    'omi_sync_phase_duration_seconds',
    'Sync phase operation latency including failures; overlapping operations are not job wall time',
    ['lane', 'phase'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 5, 15, 60, 180, 600),
)
CALLS = Histogram(
    'omi_sync_phase_calls_per_job',
    'Phase operation calls per sync pipeline attempt including zero calls and retries',
    ['lane', 'phase'],
    buckets=(0, 1, 2, 4, 8, 16, 32, 64, 128, 512),
)

_logger = logging.getLogger(__name__)
P = ParamSpec('P')
R = TypeVar('R')
_attempt: ContextVar[_Attempt | None] = ContextVar('sync_metrics_attempt', default=None)


class _Attempt:
    def __init__(self, lane: str):
        self.lane = lane if lane in ('fresh', 'backfill') else 'unknown'
        self.counts: dict[str, int] = dict.fromkeys(PHASES, 0)
        self.lock = threading.Lock()
        self.closed = False

    def record(self, phase: str, elapsed: float) -> None:
        with self.lock:
            if self.closed:
                return
            self.counts[phase] += 1
            DURATION.labels(self.lane, phase).observe(elapsed)

    def finish(self) -> None:
        with self.lock:
            self.closed = True
            for phase, count in self.counts.items():
                CALLS.labels(self.lane, phase).observe(count)


def sync_phase(phase: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Time a leaf operation only within a sync attempt; never inspect its data."""
    if phase not in PHASES:
        raise ValueError('unknown sync metrics phase')

    def decorate(fn: Callable[P, R]) -> Callable[P, R]:
        @wraps(fn)
        def observed(*args: P.args, **kwargs: P.kwargs) -> R:
            attempt = _attempt.get()
            if attempt is None:
                return fn(*args, **kwargs)
            started = time.monotonic()
            try:
                return fn(*args, **kwargs)
            finally:
                attempt.record(phase, time.monotonic() - started)

        return observed

    return decorate


def sync_attempt(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Emit calls once on success, failure or cancellation, then reset context."""
    signature = inspect.signature(fn)

    @wraps(fn)
    async def observed(*args: P.args, **kwargs: P.kwargs) -> R:
        if _attempt.get() is not None:
            return await fn(*args, **kwargs)
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        attempt = _Attempt(bound.arguments.get('sync_lane', 'unknown'))
        token = _attempt.set(attempt)
        try:
            return await fn(*args, **kwargs)
        finally:
            attempt.finish()
            _attempt.reset(token)
            _enqueue_export()

    return observed


class _BackgroundFlush:
    """One worker and one pending signal, regardless of request volume."""

    def __init__(self) -> None:
        self.pending: queue.Queue[None] = queue.Queue(maxsize=1)
        self._admission_lock = threading.Lock()
        self._stopping = threading.Event()
        self.worker = threading.Thread(target=self._run, name='sync-metrics-export', daemon=True)
        self.worker.start()

    def enqueue(self) -> None:
        if not self._admission_lock.acquire(blocking=False):
            return
        try:
            if self._stopping.is_set():
                return
            try:
                self.pending.put_nowait(None)
            except queue.Full:
                pass  # Cumulative histograms retain samples; redundant signals may be dropped.
        finally:
            self._admission_lock.release()

    def stop(self) -> None:
        """Close admission; the worker's timed queue wait also wakes it when idle."""
        self._stopping.set()

    def _run(self) -> None:
        while True:
            try:
                self.pending.get(timeout=0.05)
            except queue.Empty:
                with self._admission_lock:
                    if self._stopping.is_set() and self.pending.empty():
                        return
                continue
            try:
                export_snapshot()
            except Exception:
                # Keep the worker alive even if a future exporter implementation raises.
                _logger.warning('event=sync_phase_metrics_export outcome=failed')
            finally:
                self.pending.task_done()
            with self._admission_lock:
                if self._stopping.is_set() and self.pending.empty():
                    return


_flush: _BackgroundFlush | None = None
_flush_start_lock = threading.Lock()
_flush_shutdown = threading.Event()


def _enqueue_export() -> None:
    """No network/ADC, waits, or export exceptions on the request path."""
    global _flush
    if _flush_shutdown.is_set() or os.getenv('SYNC_PHASE_METRICS_EXPORT_ENABLED', 'false').lower() != 'true':
        return
    try:
        if _flush is None:
            if not _flush_start_lock.acquire(blocking=False):
                return
            try:
                if _flush is None and not _flush_shutdown.is_set():
                    _flush = _BackgroundFlush()
                    if _flush_shutdown.is_set():
                        _flush.stop()  # Shutdown may have raced with thread startup.
            finally:
                _flush_start_lock.release()
        if _flush is not None:
            _flush.enqueue()
    except Exception:
        # Starting a diagnostic worker must never fail a successful sync request.
        pass


async def shutdown_sync_metrics(timeout: float = 2.0) -> bool:
    """Stop/drain the exporter, waiting at most two seconds without blocking the loop.

    An exporter still stuck at the deadline remains daemonized; it exits after
    draining when the export returns, but cannot hold process shutdown open.
    """
    _flush_shutdown.set()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + min(2.0, max(0.0, timeout))
    while _flush is None and _flush_start_lock.locked():
        remaining = deadline - loop.time()
        if remaining <= 0:
            _logger.warning('event=sync_phase_metrics_shutdown outcome=timeout')
            return False
        await asyncio.sleep(min(0.01, remaining))
    flush = _flush
    if flush is None:
        return True
    flush.stop()
    while flush.worker.is_alive():
        remaining = deadline - loop.time()
        if remaining <= 0:
            _logger.warning('event=sync_phase_metrics_shutdown outcome=timeout')
            return False
        await asyncio.sleep(min(0.01, remaining))
    flush.worker.join(timeout=0)
    return True


_export_lock = threading.Lock()
_started = datetime.now(timezone.utc).isoformat()
_instance = uuid.uuid4().hex
_last_export = 0.0
_session = None


def _distribution(metric: Histogram, lane: str, phase: str) -> dict[str, Any] | None:
    samples = next(iter(metric.collect())).samples
    labels = {'lane': lane, 'phase': phase}
    buckets = sorted(
        (float(s.labels['le']), s.value)
        for s in samples
        if s.name.endswith('_bucket') and all(s.labels.get(k) == v for k, v in labels.items())
    )
    if not buckets:
        return None
    count = next(s.value for s in samples if s.name.endswith('_count') and s.labels == labels)
    total = next(s.value for s in samples if s.name.endswith('_sum') and s.labels == labels)
    previous = 0
    counts = []
    for _, value in buckets:
        counts.append(int(value - previous))
        previous = value
    return {
        'count': str(int(count)),
        'mean': total / count if count else 0,
        'bucketOptions': {'explicitBuckets': {'bounds': [b for b, _ in buckets[:-1]]}},
        'bucketCounts': [str(c) for c in counts],
    }


def export_snapshot() -> None:
    """Best-effort cumulative distributions, at most once/five minutes per instance.

    Runtime ADC needs monitoring.timeSeries.create. Only fixed metric labels and
    platform process identity leave the instance. Failed writes are retried on
    the next request; no provider payloads, exceptions or credentials are logged.
    """
    global _last_export, _session
    if not _export_lock.acquire(blocking=False):
        return
    try:
        now = time.monotonic()
        if now - _last_export < 300:
            return
        project = os.getenv('SYNC_PHASE_METRICS_PROJECT', '')
        service = os.getenv('K_SERVICE', '')
        if not project or service not in ('backend-sync', 'backend-sync-backfill'):
            return
        _last_export = now
        if _session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/monitoring.write'])
            _session = AuthorizedSession(credentials, max_refresh_attempts=0, refresh_timeout=2)
        ended = datetime.now(timezone.utc).isoformat()
        resource = {
            'type': 'generic_task',
            'labels': {
                'project_id': project,
                'location': os.getenv('SYNC_PHASE_METRICS_LOCATION', 'us-central1'),
                'namespace': os.getenv('K_REVISION', 'unknown'),
                'job': service,
                'task_id': _instance,
            },
        }
        series = []
        for metric, name in ((DURATION, 'duration_seconds'), (CALLS, 'calls_per_job')):
            for lane in ('fresh', 'backfill', 'unknown'):
                for phase in PHASES:
                    distribution = _distribution(metric, lane, phase)
                    if distribution is None or distribution['count'] == '0':
                        continue
                    series.append(
                        {
                            'metric': {
                                'type': 'custom.googleapis.com/omi_sync_phase_' + name,
                                'labels': {'lane': lane, 'phase': phase},
                            },
                            'resource': resource,
                            'metricKind': 'CUMULATIVE',
                            'valueType': 'DISTRIBUTION',
                            'points': [
                                {
                                    'interval': {'startTime': _started, 'endTime': ended},
                                    'value': {'distributionValue': distribution},
                                }
                            ],
                        }
                    )
        if not series:
            return
        response = _session.post(
            f'https://monitoring.googleapis.com/v3/projects/{project}/timeSeries',
            json={'timeSeries': series},
            timeout=(1, 2),
        )
        response.raise_for_status()
        _last_export = now
    except Exception:
        _logger.warning('event=sync_phase_metrics_export outcome=failed')
    finally:
        _export_lock.release()


def observe_sync_call(phase: str, fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    """Instrument the actual outbound operation, including each retry/fallback."""
    return sync_phase(phase)(fn)(*args, **kwargs)


@contextmanager
def sync_phase_timer(phase: str) -> Iterator[None]:
    if phase not in PHASES:
        raise ValueError('unknown sync metrics phase')
    attempt = _attempt.get()
    started = time.monotonic()
    try:
        yield
    finally:
        if attempt is not None:
            attempt.record(phase, time.monotonic() - started)


def set_sync_metrics_lane(lane: str) -> None:
    attempt = _attempt.get()
    if attempt is not None:
        attempt.lane = lane if lane in ('fresh', 'backfill') else 'unknown'

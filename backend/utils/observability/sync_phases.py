"""Aggregate sync-attempt timing; context follows the existing executor dispatch."""

from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
import inspect
import logging
import os
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
_attempt = ContextVar('sync_metrics_attempt', default=None)


class _Attempt:
    def __init__(self, lane):
        self.lane = lane if lane in ('fresh', 'backfill') else 'unknown'
        self.counts = dict.fromkeys(PHASES, 0)
        self.lock = threading.Lock()
        self.closed = False

    def record(self, phase, elapsed):
        with self.lock:
            if self.closed:
                return
            self.counts[phase] += 1
            DURATION.labels(self.lane, phase).observe(elapsed)

    def finish(self):
        with self.lock:
            self.closed = True
            for phase, count in self.counts.items():
                CALLS.labels(self.lane, phase).observe(count)


def sync_phase(phase):
    """Time a leaf operation only within a sync attempt; never inspect its data."""
    if phase not in PHASES:
        raise ValueError('unknown sync metrics phase')

    def decorate(fn):
        @wraps(fn)
        def observed(*args, **kwargs):
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


def sync_attempt(fn):
    """Emit calls once on success, failure or cancellation, then reset context."""
    signature = inspect.signature(fn)

    @wraps(fn)
    async def observed(*args, **kwargs):
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
            # Await the offloaded export before the handler returns. No idle CPU required.
            if os.getenv('SYNC_PHASE_METRICS_EXPORT_ENABLED', 'false').lower() == 'true':
                from utils.executors import run_blocking, db_executor

                await run_blocking(db_executor, export_snapshot)

    return observed


_export_lock = threading.Lock()
_started = datetime.now(timezone.utc).isoformat()
_instance = uuid.uuid4().hex
_last_export = 0.0
_session = None


def _distribution(metric, lane, phase):
    samples = metric.collect()[0].samples
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


def export_snapshot():
    """Best-effort cumulative distributions, at most once/minute per instance.

    Runtime ADC needs monitoring.timeSeries.create. Only fixed metric labels and
    platform process identity leave the instance. Failed writes are retried on
    the next request; no provider payloads, exceptions or credentials are logged.
    """
    global _last_export, _session
    if not _export_lock.acquire(blocking=False):
        return
    try:
        now = time.monotonic()
        if now - _last_export < 60:
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
            _session = AuthorizedSession(credentials)
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


def observe_sync_call(phase, fn, *args, **kwargs):
    """Instrument the actual outbound operation, including each retry/fallback."""
    return sync_phase(phase)(fn)(*args, **kwargs)


@contextmanager
def sync_phase_timer(phase):
    if phase not in PHASES:
        raise ValueError('unknown sync metrics phase')
    attempt = _attempt.get()
    started = time.monotonic()
    try:
        yield
    finally:
        if attempt is not None:
            attempt.record(phase, time.monotonic() - started)


def set_sync_metrics_lane(lane):
    attempt = _attempt.get()
    if attempt is not None:
        attempt.lane = lane if lane in ('fresh', 'backfill') else 'unknown'

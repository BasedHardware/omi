import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from utils.observability import sync_phases as metrics


def _count(metric, lane, phase):
    metric.labels(lane, phase)
    return int(metrics._distribution(metric, lane, phase)['count'])


def test_attempt_counts_threads_failures_and_zero_calls():
    before = _count(metrics.CALLS, 'backfill', 'gcs')
    duration_before = _count(metrics.DURATION, 'backfill', 'gcs')

    @metrics.sync_phase('gcs')
    def operation():
        raise ValueError('synthetic')

    @metrics.sync_attempt
    async def pipeline(sync_lane='backfill'):
        # Same context propagation used by run_blocking; do not import its heavy pools.
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(contextvars.copy_context().run, operation)
            with pytest.raises(ValueError):
                future.result()

    asyncio.run(pipeline())
    assert _count(metrics.DURATION, 'backfill', 'gcs') == duration_before + 1
    assert _count(metrics.CALLS, 'backfill', 'gcs') == before + 1
    assert metrics._attempt.get() is None
    assert metrics._distribution(metrics.CALLS, 'backfill', 'gcs')['count'] != '0'


def test_nested_attempt_emits_once_and_cancellation_resets_context():
    before = _count(metrics.CALLS, 'unknown', 'speaker_id')

    @metrics.sync_attempt
    async def nested(sync_lane='fresh'):
        raise asyncio.CancelledError()

    @metrics.sync_attempt
    async def pipeline(sync_lane='not-a-label'):
        await nested()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(pipeline())
    assert metrics._attempt.get() is None
    assert _count(metrics.CALLS, 'unknown', 'speaker_id') == before + 1


def test_no_job_context_does_not_observe_and_labels_are_closed():
    before = _count(metrics.DURATION, 'fresh', 'firestore')
    assert metrics.sync_phase('firestore')(lambda: 42)() == 42
    assert _count(metrics.DURATION, 'fresh', 'firestore') == before
    with pytest.raises(ValueError):
        metrics.sync_phase('user-supplied')


def test_bucket_conversion_preserves_total_and_overflow():
    metric = metrics.CALLS
    metric.labels('fresh', 'parakeet').observe(1000)
    distribution = metrics._distribution(metric, 'fresh', 'parakeet')
    assert sum(map(int, distribution['bucketCounts'])) == int(distribution['count'])
    assert len(distribution['bucketCounts']) == len(distribution['bucketOptions']['explicitBuckets']['bounds']) + 1
    assert int(distribution['bucketCounts'][-1]) >= 1


def test_export_is_aggregate_rate_limited_and_best_effort(monkeypatch):
    writes = []
    monkeypatch.setenv('SYNC_PHASE_METRICS_PROJECT', 'test-project')
    monkeypatch.setenv('K_SERVICE', 'backend-sync-backfill')
    monkeypatch.setenv('K_REVISION', 'synthetic-revision')
    monkeypatch.setattr(metrics, '_last_export', 0)
    monkeypatch.setattr(metrics.time, 'monotonic', lambda: 1000)
    monkeypatch.setattr(
        metrics,
        '_session',
        SimpleNamespace(
            post=lambda url, **kwargs: writes.append((url, kwargs)) or SimpleNamespace(raise_for_status=lambda: None)
        ),
    )
    metrics.CALLS.labels('backfill', 'decode_vad').observe(0)
    metrics.export_snapshot()
    metrics.export_snapshot()
    assert len(writes) == 1
    url, kwargs = writes[0]
    assert url.endswith('/test-project/timeSeries')
    assert kwargs['timeout'] == (1, 2)
    for series in kwargs['json']['timeSeries']:
        assert set(series['metric']['labels']) == {'lane', 'phase'}
        assert series['metricKind'] == 'CUMULATIVE'
        assert series['resource']['labels']['job'] == 'backend-sync-backfill'
        value = series['points'][0]['value']['distributionValue']
        assert sum(map(int, value['bucketCounts'])) == int(value['count'])

    monkeypatch.setattr(metrics.time, 'monotonic', lambda: 1061)
    monkeypatch.setattr(
        metrics, '_session', SimpleNamespace(post=lambda *a, **kw: (_ for _ in ()).throw(RuntimeError()))
    )
    metrics.export_snapshot()  # export failure cannot turn a successful job into a retry
    assert metrics._last_export == 1061

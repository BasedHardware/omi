import ast
import asyncio
import contextvars
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from utils.observability import sync_phases as metrics


@pytest.fixture(autouse=True)
def fresh_shutdown_state(monkeypatch):
    monkeypatch.setattr(metrics, '_flush_shutdown', threading.Event())


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

    monkeypatch.setattr(metrics.time, 'monotonic', lambda: 1301)
    monkeypatch.setattr(
        metrics, '_session', SimpleNamespace(post=lambda *a, **kw: (_ for _ in ()).throw(RuntimeError()))
    )
    metrics.export_snapshot()  # export failure cannot turn a successful job into a retry
    assert metrics._last_export == 1301


def test_request_completes_while_export_is_blocked_and_queue_is_bounded(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocked_export():
        entered.set()
        release.wait(timeout=2)
        finished.set()

    monkeypatch.setenv('SYNC_PHASE_METRICS_EXPORT_ENABLED', 'true')
    monkeypatch.setattr(metrics, 'export_snapshot', blocked_export)
    monkeypatch.setattr(metrics, '_flush', None)

    @metrics.sync_attempt
    async def request(sync_lane='backfill'):
        return 'completed'

    try:
        assert asyncio.run(request()) == 'completed'
        assert entered.wait(timeout=1)
        assert not finished.is_set()  # A real export is in flight, still blocked.
        flush = metrics._flush
        for _ in range(10):
            assert asyncio.run(request()) == 'completed'
        assert flush.pending.qsize() == 1  # Overflow signals are dropped.
        assert metrics._attempt.get() is None
    finally:
        release.set()
        if metrics._flush is not None:
            assert asyncio.run(metrics.shutdown_sync_metrics())
            assert not metrics._flush.worker.is_alive()
            assert metrics._flush.pending.unfinished_tasks == 0


def test_shutdown_drains_in_flight_and_queued_exports_and_joins_worker(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    exports = []

    def blocked_export():
        exports.append(True)
        entered.set()
        assert release.wait(timeout=2)

    monkeypatch.setenv('SYNC_PHASE_METRICS_EXPORT_ENABLED', 'true')
    monkeypatch.setattr(metrics, 'export_snapshot', blocked_export)
    monkeypatch.setattr(metrics, '_flush', None)
    metrics._enqueue_export()
    assert entered.wait(timeout=1)
    metrics._enqueue_export()
    flush = metrics._flush

    async def shutdown():
        task = asyncio.create_task(metrics.shutdown_sync_metrics())
        await asyncio.sleep(0.02)
        assert not task.done()
        assert flush.worker.is_alive()
        metrics._enqueue_export()  # Admission is closed while draining.
        assert flush.pending.qsize() == 1
        release.set()
        assert await task

    try:
        asyncio.run(shutdown())
        assert exports == [True, True]
        assert not flush.worker.is_alive()
        assert flush.pending.unfinished_tasks == 0
        assert asyncio.run(metrics.shutdown_sync_metrics())  # Idempotent.
    finally:
        release.set()
        flush.stop()
        flush.worker.join(timeout=2)


def test_shutdown_wakes_idle_worker_without_exporting(monkeypatch):
    monkeypatch.setattr(metrics, 'export_snapshot', lambda: pytest.fail('idle shutdown exported'))
    flush = metrics._BackgroundFlush()
    monkeypatch.setattr(metrics, '_flush', flush)
    try:
        assert asyncio.run(metrics.shutdown_sync_metrics())
        assert not flush.worker.is_alive()
        flush.enqueue()
        assert flush.pending.unfinished_tasks == 0
    finally:
        flush.stop()
        flush.worker.join(timeout=2)


@pytest.mark.parametrize('timeout, bound', [(0.05, 0.5), (20.0, 2.3)])
def test_shutdown_deadline_does_not_wait_for_stuck_export(monkeypatch, timeout, bound):
    entered = threading.Event()
    release = threading.Event()

    def stuck_export():
        entered.set()
        release.wait(timeout=3)

    monkeypatch.setattr(metrics, 'export_snapshot', stuck_export)
    flush = metrics._BackgroundFlush()
    monkeypatch.setattr(metrics, '_flush', flush)
    flush.enqueue()
    assert entered.wait(timeout=1)
    try:
        started = time.monotonic()
        assert not asyncio.run(metrics.shutdown_sync_metrics(timeout=timeout))
        assert time.monotonic() - started < bound
        assert flush.worker.is_alive()
    finally:
        release.set()
        flush.worker.join(timeout=2)
    assert not flush.worker.is_alive()
    assert flush.pending.unfinished_tasks == 0


def test_shutdown_without_worker_prevents_late_start(monkeypatch):
    monkeypatch.setenv('SYNC_PHASE_METRICS_EXPORT_ENABLED', 'true')
    monkeypatch.setattr(metrics, '_flush', None)
    monkeypatch.setattr(metrics, '_BackgroundFlush', lambda: pytest.fail('shutdown started a worker'))
    assert asyncio.run(metrics.shutdown_sync_metrics())
    metrics._enqueue_export()


def test_shutdown_racing_worker_start_stops_and_joins_worker(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    constructor = metrics._BackgroundFlush

    def delayed_start():
        entered.set()
        assert release.wait(timeout=2)
        return constructor()

    monkeypatch.setenv('SYNC_PHASE_METRICS_EXPORT_ENABLED', 'true')
    monkeypatch.setattr(metrics, '_flush', None)
    monkeypatch.setattr(metrics, '_BackgroundFlush', delayed_start)
    monkeypatch.setattr(metrics, 'export_snapshot', lambda: pytest.fail('shutdown admitted an export'))
    starter = threading.Thread(target=metrics._enqueue_export)
    starter.start()

    async def shutdown():
        task = asyncio.create_task(metrics.shutdown_sync_metrics())
        await asyncio.sleep(0.02)
        assert not task.done()
        release.set()
        assert await task

    try:
        assert entered.wait(timeout=1)
        asyncio.run(shutdown())
        assert not metrics._flush.worker.is_alive()
    finally:
        release.set()
        starter.join(timeout=2)
        if metrics._flush is not None:
            metrics._flush.stop()
            metrics._flush.worker.join(timeout=2)
    assert not starter.is_alive()


def test_app_shutdown_stops_and_joins_metrics_worker(monkeypatch):
    # Execute the real handler with unrelated service cleanups replaced, avoiding
    # main's credential/client initialization and router imports in this unit test.
    main_path = Path(__file__).resolve().parents[2] / 'main.py'
    tree = ast.parse(main_path.read_text())
    handler = next(
        node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'shutdown_event'
    )
    handler.decorator_list = []
    namespace = {
        'batch_pressure': SimpleNamespace(stop=AsyncMock()),
        'drain_background_tasks': AsyncMock(),
        'shutdown_managed_spend_ledger': AsyncMock(),
        'shutdown_sync_metrics': metrics.shutdown_sync_metrics,
        'close_all_clients': AsyncMock(),
        'close_posthog_control_plane': Mock(),
        'close_free_tier_control_plane': Mock(),
        'stop_metrics_sidecar_server': Mock(),
    }
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(main_path), 'exec'), namespace)
    flush = metrics._BackgroundFlush()
    monkeypatch.setattr(metrics, '_flush', flush)
    try:
        asyncio.run(namespace['shutdown_event']())
        assert metrics._flush_shutdown.is_set()
        assert not flush.worker.is_alive()
        assert flush.pending.unfinished_tasks == 0
        namespace['close_all_clients'].assert_awaited_once()
    finally:
        flush.stop()
        flush.worker.join(timeout=2)


def test_export_disabled_records_metrics_without_starting_worker(monkeypatch):
    monkeypatch.setenv('SYNC_PHASE_METRICS_EXPORT_ENABLED', 'false')
    monkeypatch.setattr(metrics, '_flush', None)
    monkeypatch.setattr(metrics, '_BackgroundFlush', lambda: pytest.fail('disabled export started a worker'))
    before = _count(metrics.CALLS, 'backfill', 'firestore')

    @metrics.sync_attempt
    async def request(sync_lane='backfill'):
        return 42

    assert asyncio.run(request()) == 42
    assert metrics._flush is None
    assert _count(metrics.CALLS, 'backfill', 'firestore') == before + 1


def test_worker_start_failure_does_not_fail_success_or_replace_request_error(monkeypatch):
    monkeypatch.setenv('SYNC_PHASE_METRICS_EXPORT_ENABLED', 'true')
    monkeypatch.setattr(metrics, '_flush', None)

    def failed_start():
        raise RuntimeError('synthetic thread-start failure')

    monkeypatch.setattr(metrics, '_BackgroundFlush', failed_start)

    @metrics.sync_attempt
    async def request(sync_lane='fresh', fail=False):
        if fail:
            raise ValueError('request error')
        return 42

    assert asyncio.run(request()) == 42
    with pytest.raises(ValueError, match='request error'):
        asyncio.run(request(fail=True))
    assert metrics._attempt.get() is None

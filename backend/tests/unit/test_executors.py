"""Tests for utils/executors.py run_blocking, submit_with_context, and MonitoredThreadPoolExecutor."""

import asyncio
import contextvars
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from utils.executors import (
    MonitoredThreadPoolExecutor,
    _background_tasks,
    drain_background_tasks,
    get_background_task_count,
    get_executor_metrics,
    log_executor_health,
    run_blocking,
    start_background_task,
    submit_with_context,
    _ALL_EXECUTORS,
)

_test_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test")
_test_ctxvar = contextvars.ContextVar("test_key", default=None)


@pytest.mark.asyncio
async def test_cancelled_db_call_never_starts_late_post_commit_io(monkeypatch):
    from utils import executors

    started = asyncio.Event()
    release = threading.Event()
    called = []
    loop = asyncio.get_running_loop()

    async def provider():
        called.append('provider')

    def late_commit():
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
        assert executors.after_db_call(provider)

    with ThreadPoolExecutor(max_workers=1) as pool:
        monkeypatch.setattr(executors, 'db_executor', pool)
        task = asyncio.create_task(run_blocking(pool, late_commit))
        try:
            await asyncio.wait_for(started.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
        await run_blocking(pool, lambda: None)
    assert not called


@pytest.mark.asyncio
async def test_run_blocking_uses_provided_executor():
    """run_blocking must execute fn on the given executor, not the default pool."""
    captured = {}

    def capture_thread():
        captured["thread"] = threading.current_thread().name

    await run_blocking(_test_executor, capture_thread)
    assert captured["thread"].startswith("test"), f"Expected 'test' prefix, got {captured['thread']}"


@pytest.mark.asyncio
async def test_run_blocking_passes_args_and_kwargs():
    """Positional and keyword arguments must reach the target function."""

    def adder(a, b, multiplier=1):
        return (a + b) * multiplier

    result = await run_blocking(_test_executor, adder, 3, 4, multiplier=2)
    assert result == 14


@pytest.mark.asyncio
async def test_run_blocking_propagates_exceptions():
    """Exceptions raised inside the executor must propagate to the caller."""

    def boom():
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        await run_blocking(_test_executor, boom)


@pytest.mark.asyncio
async def test_run_blocking_propagates_contextvars():
    """ContextVars set before run_blocking must be visible inside the executor."""
    token = _test_ctxvar.set("hello-from-caller")
    captured = {}

    def read_ctxvar():
        captured["value"] = _test_ctxvar.get()

    try:
        await run_blocking(_test_executor, read_ctxvar)
    finally:
        _test_ctxvar.reset(token)

    assert captured["value"] == "hello-from-caller"


def test_submit_with_context_propagates_contextvars():
    """submit_with_context must propagate ContextVars to the submitted function."""
    token = _test_ctxvar.set("submit-test")
    captured = {}

    def read_ctxvar():
        captured["value"] = _test_ctxvar.get()

    try:
        future = submit_with_context(_test_executor, read_ctxvar)
        future.result(timeout=5)
    finally:
        _test_ctxvar.reset(token)

    assert captured["value"] == "submit-test"


def test_submit_with_context_returns_future_with_result():
    """submit_with_context must return a Future whose result matches fn's return."""

    def double(x):
        return x * 2

    future = submit_with_context(_test_executor, double, 21)
    assert future.result(timeout=5) == 42


# ---------------------------------------------------------------------------
# MonitoredThreadPoolExecutor tests
# ---------------------------------------------------------------------------


def test_monitored_executor_is_threadpoolexecutor():
    """MonitoredThreadPoolExecutor must be a proper ThreadPoolExecutor subclass."""
    assert issubclass(MonitoredThreadPoolExecutor, ThreadPoolExecutor)


def test_monitored_executor_tracks_active_count():
    """active_count must increment during task execution and decrement after."""
    executor = MonitoredThreadPoolExecutor(name="test-active", max_workers=2)
    assert executor.active_count == 0
    event = threading.Event()
    captured = {}

    def block_and_capture():
        captured['active'] = executor.active_count
        event.wait(timeout=5)

    future = executor.submit(block_and_capture)
    time.sleep(0.05)
    assert executor.active_count >= 1
    event.set()
    future.result(timeout=5)
    time.sleep(0.05)
    assert executor.active_count == 0
    assert captured['active'] >= 1
    executor.shutdown(wait=False)


def test_monitored_executor_has_name():
    """MonitoredThreadPoolExecutor must expose its name attribute."""
    executor = MonitoredThreadPoolExecutor(name="my-pool", max_workers=1)
    assert executor.name == "my-pool"
    executor.shutdown(wait=False)


def test_monitored_executor_submit_returns_result():
    """submit must still return a working Future with the correct result."""
    executor = MonitoredThreadPoolExecutor(name="test-result", max_workers=1)
    future = executor.submit(lambda x: x * 3, 7)
    assert future.result(timeout=5) == 21
    executor.shutdown(wait=False)


def test_monitored_executor_propagates_exceptions():
    """Exceptions in submitted tasks must propagate through the Future."""
    executor = MonitoredThreadPoolExecutor(name="test-exc", max_workers=1)

    def fail():
        raise RuntimeError("boom")

    future = executor.submit(fail)
    with pytest.raises(RuntimeError, match="boom"):
        future.result(timeout=5)
    assert executor.active_count == 0
    executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# get_executor_metrics tests
# ---------------------------------------------------------------------------


def test_get_executor_metrics_returns_all_pools():
    """get_executor_metrics must return one entry per registered executor."""
    metrics = get_executor_metrics()
    assert len(metrics) == len(_ALL_EXECUTORS)
    names = {m['name'] for m in metrics}
    expected = {
        'quiet_replay',
        'critical',
        'db',
        'llm',
        'stripe',
        'sync',
        'postprocess',
        'cleanup',
        'storage',
        'speaker_tag_verify',
        'cimd',
        'open_loops',
    }
    assert names == expected


def test_get_executor_metrics_fields():
    """Each metric entry must have the required fields."""
    metrics = get_executor_metrics()
    for m in metrics:
        assert 'name' in m
        assert 'max_workers' in m
        assert 'active_count' in m
        assert 'queue_depth' in m
        assert 'utilization_pct' in m
        assert isinstance(m['utilization_pct'], float)


def test_get_executor_metrics_idle_utilization():
    """Idle executors must report 0% utilization."""
    metrics = get_executor_metrics()
    for m in metrics:
        assert m['active_count'] >= 0
        assert m['utilization_pct'] >= 0.0


def test_all_executors_are_monitored():
    """All registered executors must be MonitoredThreadPoolExecutor instances."""
    for executor in _ALL_EXECUTORS:
        assert isinstance(executor, MonitoredThreadPoolExecutor), f'{executor} is not MonitoredThreadPoolExecutor'


# ---------------------------------------------------------------------------
# log_executor_health tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# start_background_task tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_background_task_runs_coroutine():
    """start_background_task must execute the coroutine and return a Task."""
    result = {}

    async def work():
        result['done'] = True
        return 42

    task = start_background_task(work(), name='test-run')
    assert isinstance(task, asyncio.Task)
    assert task.get_name() == 'test-run'
    await task
    assert result['done'] is True
    assert task.result() == 42


@pytest.mark.asyncio
async def test_start_background_task_tracks_and_removes():
    """Task must be in _background_tasks while running, removed after completion."""
    event = asyncio.Event()

    async def wait_for_signal():
        await event.wait()

    task = start_background_task(wait_for_signal(), name='test-track')
    assert task in _background_tasks
    assert get_background_task_count() >= 1
    event.set()
    await task
    await asyncio.sleep(0)  # let done callback fire
    assert task not in _background_tasks


@pytest.fixture
def destructive_operation_error():
    # Dependency initialization is setup, outside the fast-unit call budget.
    from database.legal_holds import DestructiveOperationInProgress

    return DestructiveOperationInProgress


def test_submit_with_context_defers_destructive_operation_fence_without_traceback(caplog, destructive_operation_error):
    """A live account gate refuses the write. That is not a background crash."""

    def blocked():
        raise destructive_operation_error('external data write blocked by destructive operation')

    with caplog.at_level(logging.INFO, logger='utils.executors'):
        future = submit_with_context(_test_executor, blocked)
        with pytest.raises(destructive_operation_error):
            future.result(timeout=2)
        time.sleep(0.05)

    assert any('deferred reason=destructive_operation' in record.message for record in caplog.records)
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    assert not any(record.exc_info not in (None, (None, None, None)) for record in caplog.records)


def test_submit_with_context_still_logs_unexpected_background_failures(caplog):
    def boom():
        raise RuntimeError('bg-boom')

    with caplog.at_level(logging.ERROR, logger='utils.executors'):
        future = submit_with_context(_test_executor, boom)
        with pytest.raises(RuntimeError):
            future.result(timeout=2)
        time.sleep(0.05)

    assert any(record.levelno >= logging.ERROR and 'bg-boom' in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_start_background_task_logs_exceptions(caplog):
    """Exceptions in background tasks must be logged, not silently swallowed."""

    async def fail():
        raise RuntimeError('bg-boom')

    with caplog.at_level(logging.ERROR, logger='utils.executors'):
        task = start_background_task(fail(), name='test-exc')
        await asyncio.sleep(0.05)
    assert any('background_task failed: test-exc' in r.message for r in caplog.records)
    assert task not in _background_tasks


@pytest.mark.asyncio
async def test_start_background_task_logs_cancellation(caplog):
    """Cancelled background tasks must log info, not error."""

    async def forever():
        await asyncio.sleep(3600)

    with caplog.at_level(logging.INFO, logger='utils.executors'):
        task = start_background_task(forever(), name='test-cancel')
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0)
    assert any('background_task cancelled: test-cancel' in r.message for r in caplog.records)
    assert task not in _background_tasks


@pytest.mark.asyncio
async def test_drain_background_tasks_cancels_all():
    """drain_background_tasks must cancel and await all tracked tasks."""
    events = [asyncio.Event() for _ in range(3)]

    async def wait(e):
        await e.wait()

    tasks = [start_background_task(wait(e), name=f'drain-{i}') for i, e in enumerate(events)]
    assert get_background_task_count() >= 3
    cancelled = await drain_background_tasks(timeout=2.0)
    assert cancelled == 3
    for t in tasks:
        assert t.done()


# ---------------------------------------------------------------------------
# log_executor_health tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_executor_health_warns_above_threshold(caplog):
    """log_executor_health must emit a warning when any pool exceeds the threshold."""
    saturated_metrics = [
        {'name': 'test-pool', 'max_workers': 4, 'active_count': 4, 'queue_depth': 0, 'utilization_pct': 100.0},
    ]
    with patch('utils.executors.get_executor_metrics', return_value=saturated_metrics):
        with patch('utils.executors.asyncio.sleep', side_effect=[None, asyncio.CancelledError]):
            with caplog.at_level(logging.WARNING, logger='utils.executors'):
                try:
                    await log_executor_health(interval_seconds=1, utilization_threshold_pct=70.0)
                except asyncio.CancelledError:
                    pass
    assert any('executor_pool_health' in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_log_executor_health_warns_above_queue_depth_threshold(caplog):
    """log_executor_health must warn when queued work grows even if active workers are below threshold."""
    queued_metrics = [
        {'name': 'test-pool', 'max_workers': 8, 'active_count': 2, 'queue_depth': 11, 'utilization_pct': 25.0},
    ]
    with patch('utils.executors.get_executor_metrics', return_value=queued_metrics):
        with patch('utils.executors.asyncio.sleep', side_effect=[None, asyncio.CancelledError]):
            with caplog.at_level(logging.WARNING, logger='utils.executors'):
                try:
                    await log_executor_health(
                        interval_seconds=1,
                        utilization_threshold_pct=70.0,
                        queue_depth_threshold=10,
                    )
                except asyncio.CancelledError:
                    pass
    assert any('executor_pool_health' in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_log_executor_health_silent_below_threshold(caplog):
    """log_executor_health must not log when all pools are below the threshold."""
    idle_metrics = [
        {'name': 'test-pool', 'max_workers': 8, 'active_count': 1, 'queue_depth': 9, 'utilization_pct': 12.5},
    ]
    with patch('utils.executors.get_executor_metrics', return_value=idle_metrics):
        with patch('utils.executors.asyncio.sleep', side_effect=[None, asyncio.CancelledError]):
            with caplog.at_level(logging.WARNING, logger='utils.executors'):
                try:
                    await log_executor_health(
                        interval_seconds=1,
                        utilization_threshold_pct=70.0,
                        queue_depth_threshold=10,
                    )
                except asyncio.CancelledError:
                    pass
    assert not any('executor_pool_health' in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_log_executor_health_silent_at_exact_threshold(caplog):
    """Metrics at exactly their thresholds must NOT trigger a warning (> not >=)."""
    at_threshold_metrics = [
        {'name': 'test-pool', 'max_workers': 10, 'active_count': 7, 'queue_depth': 10, 'utilization_pct': 70.0},
    ]
    with patch('utils.executors.get_executor_metrics', return_value=at_threshold_metrics):
        with patch('utils.executors.asyncio.sleep', side_effect=[None, asyncio.CancelledError]):
            with caplog.at_level(logging.WARNING, logger='utils.executors'):
                try:
                    await log_executor_health(
                        interval_seconds=1,
                        utilization_threshold_pct=70.0,
                        queue_depth_threshold=10,
                    )
                except asyncio.CancelledError:
                    pass
    assert not any('executor_pool_health' in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_log_executor_health_swallows_exceptions(caplog):
    """log_executor_health must swallow exceptions from get_executor_metrics and keep looping."""
    call_count = 0

    def _exploding_metrics():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("boom")

    side_effects = [None, None, asyncio.CancelledError]
    with patch('utils.executors.get_executor_metrics', side_effect=_exploding_metrics):
        with patch('utils.executors.asyncio.sleep', side_effect=side_effects):
            try:
                await log_executor_health(interval_seconds=1)
            except asyncio.CancelledError:
                pass
    assert call_count == 2, f"Expected 2 calls before cancel, got {call_count}"


def test_task_gauges_include_queued_cancelled_and_failed_work():
    from utils.executors import EXECUTOR_ACTIVE, EXECUTOR_QUEUED

    pool = MonitoredThreadPoolExecutor('test-task-gauges', max_workers=1, max_queue_size=1)
    started, release = threading.Event(), threading.Event()

    def record_moment():
        started.set()
        release.wait(5)
        raise ValueError('fixture failure')

    active = EXECUTOR_ACTIVE.labels(executor=pool.name, task='record_moment')
    queued = EXECUTOR_QUEUED.labels(executor=pool.name, task='record_moment')
    try:
        first = pool.submit(record_moment)
        assert started.wait(2)
        second = pool.submit(record_moment)
        assert active._value.get() == 1
        assert queued._value.get() == 1
        assert second.cancel()
        assert queued._value.get() == 0
        release.set()
        with pytest.raises(ValueError):
            first.result(2)
        assert active._value.get() == 0
    finally:
        release.set()
        pool.shutdown()


@pytest.mark.asyncio
async def test_backpressure_waits_for_capacity_and_preserves_work():
    pool = MonitoredThreadPoolExecutor('test-backpressure', max_workers=1, max_queue_size=0, wait_on_saturation=True)
    release, started = threading.Event(), threading.Event()

    def hold():
        started.set()
        release.wait(5)

    try:
        first = pool.submit(hold)
        assert started.wait(2)
        waiting = asyncio.create_task(run_blocking(pool, lambda: 42))
        await asyncio.sleep(0.06)
        assert not waiting.done()
        assert pool._work_queue.qsize() == 0
        release.set()
        assert await asyncio.wait_for(waiting, 2) == 42
        first.result(2)
    finally:
        release.set()
        pool.shutdown()


def test_lifecycle_pool_isolation_and_shadow_rollback(monkeypatch):
    from utils.executors import lifecycle_executor, postprocess_executor

    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'off')
    assert lifecycle_executor('test-account', episode=True) is postprocess_executor
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'shadow')
    assert lifecycle_executor('test-account', episode=True) is postprocess_executor
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'serve')
    episode = lifecycle_executor('test-account', episode=True)
    postprocess = lifecycle_executor('test-account')
    assert episode is not postprocess
    assert (episode._max_workers, episode.max_queue_size) == (2, 8)
    assert (postprocess._max_workers, postprocess.max_queue_size) == (24, 96)


def test_cancelled_queue_payloads_do_not_escape_the_bound():
    pool = MonitoredThreadPoolExecutor('test-cancel-bound', max_workers=1, max_queue_size=1)
    release, started = threading.Event(), threading.Event()

    def hold():
        started.set()
        release.wait(5)

    try:
        running = pool.submit(hold)
        assert started.wait(2)
        for _ in range(100):
            queued = pool.submit(lambda: None)
            assert queued.cancel()
            assert pool._work_queue.qsize() == 0
        release.set()
        running.result(2)
    finally:
        release.set()
        pool.shutdown()

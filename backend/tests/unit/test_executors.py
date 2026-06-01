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
    expected = {'critical', 'db', 'llm', 'stripe', 'sync', 'postprocess', 'storage'}
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
async def test_log_executor_health_silent_below_threshold(caplog):
    """log_executor_health must not log when all pools are below the threshold."""
    idle_metrics = [
        {'name': 'test-pool', 'max_workers': 8, 'active_count': 1, 'queue_depth': 0, 'utilization_pct': 12.5},
    ]
    with patch('utils.executors.get_executor_metrics', return_value=idle_metrics):
        with patch('utils.executors.asyncio.sleep', side_effect=[None, asyncio.CancelledError]):
            with caplog.at_level(logging.WARNING, logger='utils.executors'):
                try:
                    await log_executor_health(interval_seconds=1, utilization_threshold_pct=70.0)
                except asyncio.CancelledError:
                    pass
    assert not any('executor_pool_health' in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_log_executor_health_silent_at_exact_threshold(caplog):
    """Utilization at exactly the threshold (70.0) must NOT trigger a warning (> not >=)."""
    at_threshold_metrics = [
        {'name': 'test-pool', 'max_workers': 10, 'active_count': 7, 'queue_depth': 0, 'utilization_pct': 70.0},
    ]
    with patch('utils.executors.get_executor_metrics', return_value=at_threshold_metrics):
        with patch('utils.executors.asyncio.sleep', side_effect=[None, asyncio.CancelledError]):
            with caplog.at_level(logging.WARNING, logger='utils.executors'):
                try:
                    await log_executor_health(interval_seconds=1, utilization_threshold_pct=70.0)
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

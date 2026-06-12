"""Async concurrency utilities for production WebSocket and HTTP fan-out patterns.

Implements structured concurrency primitives that replace raw asyncio.gather():
- supervise_tasks(): FIRST_COMPLETED supervisor loop for WS handlers
- drain_tasks(): timeout-bounded task cancellation
- gather_safe(): bounded fan-out with exception observability
- gather_chunked(): chunked fan-out for large coroutine lists
- create_named_task(): tracked task creation with done-callback cleanup
- wait_for_event(): interruptible sleep that wakes on shutdown event

These replace ad-hoc asyncio.gather() patterns that cause:
1. Silent exception swallowing (return_exceptions=True with no inspection)
2. Orphaned tasks on first failure (gather without sibling cancellation)
3. Unbounded fan-out (50+ concurrent outbound connections per session)

Same pattern as utils/executors.py (thread pools) and utils/http_client.py (HTTP clients):
named utilities with bounded resources, clean shutdown, and observability.
"""

import asyncio
import logging
import sys
import threading
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Awaitable, Generic, Iterable, TypeVar

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

T = TypeVar('T')

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

_METRIC_CACHE_MODULE = 'utils._async_tasks_metric_cache'


def _new_metric_cache_module():
    module = ModuleType(_METRIC_CACHE_MODULE)
    module.cache = {}
    module.lock = threading.Lock()
    return module


def _metric_cache_state():
    state = sys.modules.get(_METRIC_CACHE_MODULE)
    if state is None:
        state = sys.modules.setdefault(_METRIC_CACHE_MODULE, _new_metric_cache_module())
    return state


def _metric_cache():
    return _metric_cache_state().cache


def _cacheable_value(value):
    if isinstance(value, list):
        return tuple(_cacheable_value(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((key, _cacheable_value(item)) for key, item in value.items()))
    return value


def _metric_cache_key(metric_class, name, labelnames=(), **kwargs):
    return (
        metric_class,
        name,
        tuple(labelnames),
        tuple(sorted((key, _cacheable_value(value)) for key, value in kwargs.items())),
    )


def _get_or_create_metric(metric_class, name, documentation, labelnames=(), **kwargs):
    state = _metric_cache_state()
    cache_key = _metric_cache_key(metric_class, name, labelnames, **kwargs)
    with state.lock:
        cache = state.cache
        existing = cache.get(cache_key)
        if existing is not None:
            return existing
        metric = metric_class(name, documentation, labelnames, **kwargs)
        cache[cache_key] = metric
        return metric


SUPERVISOR_EXIT_TOTAL = _get_or_create_metric(
    Counter,
    'async_supervisor_exit_total',
    'Supervisor loop exits by reason',
    ['label', 'reason'],
)

DRAIN_TIMEOUT_TOTAL = _get_or_create_metric(
    Counter,
    'async_drain_timeout_total',
    'Task drain operations that hit timeout',
    ['label'],
)

DRAIN_DURATION = _get_or_create_metric(
    Histogram,
    'async_drain_duration_seconds',
    'Time spent draining tasks',
    ['label'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

GATHER_FAILURES_TOTAL = _get_or_create_metric(
    Counter,
    'async_gather_failures_total',
    'Individual coroutine failures in gather_safe',
    ['label'],
)

GATHER_DURATION = _get_or_create_metric(
    Histogram,
    'async_gather_duration_seconds',
    'Total duration of gather_safe calls',
    ['label'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class GatherResult(Generic[T]):
    """Result of a single coroutine in gather_safe."""

    index: int
    ok: bool
    value: T | None = None
    exception: BaseException | None = None
    cancelled: bool = False


@dataclass(slots=True)
class SupervisorResult:
    """Result of supervise_tasks indicating why the supervisor loop exited."""

    reason: str  # "disconnect", "crash", "lifetime_done"
    task_name: str
    exception: BaseException | None = None


# ---------------------------------------------------------------------------
# supervise_tasks — WebSocket task supervision
# ---------------------------------------------------------------------------


async def supervise_tasks(
    *,
    receive_task: asyncio.Task,
    bg_tasks: list[asyncio.Task],
    finite_tasks: set[asyncio.Task] | None = None,
    label: str,
) -> SupervisorResult:
    """Supervisor loop using asyncio.wait(FIRST_COMPLETED).

    Monitors receive_task + bg_tasks. Exits when:
    - receive_task completes (disconnect)
    - Any task raises an exception (crash)
    - A lifetime task (not in finite_tasks) completes normally (session ending)

    Re-waits when a finite task completes normally.
    """
    if finite_tasks is None:
        finite_tasks = set()

    monitored = {receive_task, *bg_tasks}
    if not monitored:
        return SupervisorResult(reason="empty", task_name="none")

    while monitored:
        done, monitored = await asyncio.wait(monitored, return_when=asyncio.FIRST_COMPLETED)

        exit_result = None
        for task in done:
            if task is receive_task:
                exit_result = SupervisorResult(reason="disconnect", task_name=task.get_name())
                break
            if not task.cancelled():
                try:
                    exc = task.exception()
                except asyncio.CancelledError:
                    continue
                if exc is not None:
                    logger.error("BG task %s crashed: %r [%s]", task.get_name(), exc, label)
                    exit_result = SupervisorResult(reason="crash", task_name=task.get_name(), exception=exc)
                    break
                if task not in finite_tasks:
                    logger.info("Lifetime task %s completed, tearing down [%s]", task.get_name(), label)
                    exit_result = SupervisorResult(reason="lifetime_done", task_name=task.get_name())
                    break

        if exit_result:
            SUPERVISOR_EXIT_TOTAL.labels(label=label, reason=exit_result.reason).inc()
            return exit_result

    return SupervisorResult(reason="all_done", task_name="none")


# ---------------------------------------------------------------------------
# drain_tasks — timeout-bounded cancellation
# ---------------------------------------------------------------------------


async def drain_tasks(
    tasks: Iterable[asyncio.Task],
    *,
    timeout: float = 30.0,
    label: str = "drain",
    cancel: bool = True,
) -> int:
    """Cancel and wait for tasks to finish within timeout.

    Returns the number of tasks that had to be force-cancelled after timeout.
    """
    pending = [t for t in tasks if not t.done()]
    if not pending:
        return 0

    if cancel:
        for task in pending:
            task.cancel()

    with DRAIN_DURATION.labels(label=label).time():
        done, still_pending = await asyncio.wait(pending, timeout=timeout)

    for task in done:
        if not task.cancelled():
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                continue
            if exc is not None:
                logger.debug("Task %s raised during drain [%s]: %r", task.get_name(), label, exc)

    force_cancelled = 0
    if still_pending:
        DRAIN_TIMEOUT_TOTAL.labels(label=label).inc()
        logger.warning("Drain timeout (%.1fs), force-cancelling %d tasks [%s]", timeout, len(still_pending), label)
        for task in still_pending:
            task.cancel()
        # Bounded wait for cancel acknowledgement — never block indefinitely
        _, truly_stuck = await asyncio.wait(still_pending, timeout=5.0)
        force_cancelled = len(still_pending)
        if truly_stuck:
            logger.error(
                "drain_tasks: %d tasks ignored cancellation after 5s [%s]: %s",
                len(truly_stuck),
                label,
                [t.get_name() for t in truly_stuck],
            )

    return force_cancelled


# ---------------------------------------------------------------------------
# gather_safe — bounded fan-out with observability
# ---------------------------------------------------------------------------


async def gather_safe(
    *coros: Awaitable[T],
    label: str,
    max_concurrency: int = 10,
    timeout: float | None = None,
) -> list[GatherResult[T]]:
    """Fan-out coroutines with bounded concurrency and exception logging.

    - Semaphore limits concurrent execution
    - Exceptions are logged (not silently swallowed)
    - Returns GatherResult list preserving order
    - Cancellation of parent propagates to all children
    """
    if not coros:
        return []

    sem = asyncio.Semaphore(max_concurrency)

    async def _run_one(index: int, coro: Awaitable[T]) -> GatherResult[T]:
        async with sem:
            try:
                if timeout is not None:
                    value = await asyncio.wait_for(coro, timeout=timeout)
                else:
                    value = await coro
                return GatherResult(index=index, ok=True, value=value)
            except asyncio.CancelledError:
                return GatherResult(index=index, ok=False, cancelled=True)
            except Exception as e:
                GATHER_FAILURES_TOTAL.labels(label=label).inc()
                logger.warning("gather_safe[%s] item %d failed: %r", label, index, e)
                return GatherResult(index=index, ok=False, exception=e)

    tasks = [asyncio.create_task(_run_one(i, coro), name=f"{label}:{i}") for i, coro in enumerate(coros)]

    try:
        with GATHER_DURATION.labels(label=label).time():
            results = await asyncio.gather(*tasks)
        return list(results)
    except asyncio.CancelledError:
        await drain_tasks(tasks, timeout=5.0, label=f"{label}:cancel", cancel=True)
        raise


# ---------------------------------------------------------------------------
# gather_chunked — chunked fan-out for large lists
# ---------------------------------------------------------------------------


async def gather_chunked(
    coros: Iterable[Awaitable[T]],
    *,
    chunk_size: int = 10,
    label: str,
    max_concurrency: int | None = None,
    timeout: float | None = None,
) -> list[GatherResult[T]]:
    """Execute coroutines in chunks with bounded concurrency.

    Processes chunk_size coroutines at a time, waiting for each chunk
    to complete before starting the next. Useful for large fan-outs
    where even semaphore-bounded gather creates too many pending tasks.
    """
    results: list[GatherResult[T]] = []
    chunk: list[Awaitable[T]] = []
    concurrency = max_concurrency if max_concurrency is not None else chunk_size

    for coro in coros:
        chunk.append(coro)
        if len(chunk) >= chunk_size:
            chunk_results = await gather_safe(
                *chunk,
                label=label,
                max_concurrency=concurrency,
                timeout=timeout,
            )
            results.extend(chunk_results)
            chunk = []

    if chunk:
        chunk_results = await gather_safe(
            *chunk,
            label=label,
            max_concurrency=concurrency,
            timeout=timeout,
        )
        results.extend(chunk_results)

    return results


# ---------------------------------------------------------------------------
# create_named_task — tracked task creation
# ---------------------------------------------------------------------------


async def wait_for_event(event: asyncio.Event, seconds: float) -> bool:
    """Sleep for `seconds` but wake immediately if `event` is set.

    Returns True if woken early by the event (shutdown requested),
    False if the full sleep elapsed normally.
    """
    if event.is_set():
        return True
    if seconds <= 0:
        return False
    try:
        await asyncio.wait_for(event.wait(), timeout=seconds)
        return True
    except asyncio.TimeoutError:
        return False


def create_named_task(
    coro: Awaitable[Any],
    *,
    name: str,
    task_set: set[asyncio.Task] | None = None,
) -> asyncio.Task:
    """Create a named task with optional tracking set.

    - Names the task for debugging (visible in asyncio.all_tasks())
    - Adds to task_set if provided
    - Registers done callback to auto-remove from task_set
    """
    task = asyncio.create_task(coro, name=name)

    if task_set is not None:
        task_set.add(task)
        task.add_done_callback(task_set.discard)

    return task

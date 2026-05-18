"""Dedicated ThreadPoolExecutors for Lane 2 of the 3-lane async architecture (issue #6369).

Provides shared executors with strict separation (bulkhead pattern):
- critical_executor: auth verification, rate limiting, hard restriction checks,
  small session/code cache reads. Must never starve — gates every request.
- db_executor: Firestore CRUD and Redis data mutations. High volume, moderate latency.
- llm_executor: persona generation, onboarding LLM, slow model-backed work. Bulkhead
  to prevent slow LLM retries from blocking DB or auth operations.
- stripe_executor: Stripe API calls (Subscription.retrieve, etc.). External network I/O
  with unpredictable latency, isolated from everything else.
- sync_executor: sync pipeline VAD/STT/segment processing.
- postprocess_executor: best-effort post-processing (memories, trends, vectors,
  action items, goals, conversation processing, webhook delivery).
- storage_executor: audio file precaching, GCS operations.

These replace ad-hoc ThreadPoolExecutor creation throughout the codebase,
preventing thread proliferation and providing bounded concurrency.
"""

import asyncio
import atexit
import contextvars
import functools
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor

logger = logging.getLogger(__name__)


class MonitoredThreadPoolExecutor(ThreadPoolExecutor):
    """ThreadPoolExecutor with active-task tracking for observability."""

    def __init__(self, name: str, **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self._active_count = 0
        self._active_lock = threading.Lock()

    @property
    def active_count(self) -> int:
        return self._active_count

    def submit(self, fn, /, *args, **kwargs):
        future = super().submit(self._tracked, fn, *args, **kwargs)
        return future

    def _tracked(self, fn, *args, **kwargs):
        with self._active_lock:
            self._active_count += 1
        try:
            return fn(*args, **kwargs)
        finally:
            with self._active_lock:
                self._active_count -= 1


critical_executor = MonitoredThreadPoolExecutor(name="critical", max_workers=8, thread_name_prefix="critical")
db_executor = MonitoredThreadPoolExecutor(name="db", max_workers=16, thread_name_prefix="db")
llm_executor = MonitoredThreadPoolExecutor(name="llm", max_workers=4, thread_name_prefix="llm")
stripe_executor = MonitoredThreadPoolExecutor(name="stripe", max_workers=4, thread_name_prefix="stripe")
sync_executor = MonitoredThreadPoolExecutor(name="sync", max_workers=12, thread_name_prefix="sync")
postprocess_executor = MonitoredThreadPoolExecutor(name="postprocess", max_workers=8, thread_name_prefix="postproc")
storage_executor = MonitoredThreadPoolExecutor(name="storage", max_workers=32, thread_name_prefix="storage")

_ALL_EXECUTORS = [
    critical_executor,
    db_executor,
    llm_executor,
    stripe_executor,
    sync_executor,
    postprocess_executor,
    storage_executor,
]


async def run_blocking(executor: ThreadPoolExecutor, fn, *args, **kwargs):
    """Offload *fn* to *executor*, propagating ContextVars."""
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    call = functools.partial(ctx.run, functools.partial(fn, *args, **kwargs))
    return await loop.run_in_executor(executor, call)


def submit_with_context(executor: ThreadPoolExecutor, fn, *args, **kwargs) -> Future:
    """Submit *fn* to *executor*, propagating the current contextvars (BYOK keys, etc.)."""
    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, fn, *args, **kwargs)


def get_executor_metrics() -> list:
    """Return health metrics for all named executor pools."""
    metrics = []
    for executor in _ALL_EXECUTORS:
        max_w = executor._max_workers
        active = executor.active_count
        queue_depth = executor._work_queue.qsize()
        utilization = round((active / max_w) * 100, 1) if max_w else 0.0
        metrics.append(
            {
                'name': executor.name,
                'max_workers': max_w,
                'active_count': active,
                'queue_depth': queue_depth,
                'utilization_pct': utilization,
            }
        )
    return metrics


async def log_executor_health(interval_seconds: int = 60, utilization_threshold_pct: float = 70.0):
    """Periodically log pool metrics when any pool exceeds the utilization threshold."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            metrics = get_executor_metrics()
            saturated = [p for p in metrics if p['utilization_pct'] > utilization_threshold_pct]
            if saturated:
                logger.warning('executor_pool_health: %s', saturated)
        except Exception:
            pass


_background_tasks: set[asyncio.Task] = set()


def start_background_task(coro, *, name: str) -> asyncio.Task:
    """Schedule *coro* as a tracked background task with exception logging.

    Use this instead of bare ``asyncio.create_task()`` for production
    fire-and-forget work.  Bare ``create_task`` silently drops exceptions
    and can be garbage-collected if the caller doesn't keep a reference.
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if t.cancelled():
            logger.info('background_task cancelled: %s', t.get_name())
            return
        exc = t.exception()
        if exc:
            logger.error('background_task failed: %s — %s: %s', t.get_name(), type(exc).__name__, exc)

    task.add_done_callback(_done)
    return task


def get_background_task_count() -> int:
    """Return the number of currently tracked background tasks."""
    return len(_background_tasks)


async def drain_background_tasks(timeout: float = 10.0) -> int:
    """Cancel and await all tracked background tasks at shutdown. Returns count cancelled."""
    tasks = list(_background_tasks)
    if not tasks:
        return 0
    for t in tasks:
        t.cancel()
    await asyncio.wait(tasks, timeout=timeout)
    return len(tasks)


def shutdown_executors():
    """Shut down all shared executors. Called at app shutdown."""
    for executor in _ALL_EXECUTORS:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            logger.warning(f"Error shutting down {executor.name} executor: {e}")


atexit.register(shutdown_executors)

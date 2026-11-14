"""Dedicated ThreadPoolExecutors for Lane 2 of the 3-lane async architecture (issue #6369).

Provides shared executors with strict separation (bulkhead pattern):
- critical_executor: auth verification, rate limiting, hard restriction checks,
  small session/code cache reads. Must never starve — gates every request.
- quiet_replay_executor: bounded quiet-check replay leaves, separate from the DB coordinator.
- db_executor: Firestore CRUD and Redis data mutations. High volume, moderate latency.
- record_barrier_executor: pusher recording custody transactions, isolated from
  integrations and webhook DB work even during Firestore retries.
- context_executor: optional context reads and fresh mount fences, four workers,
  zero queue, isolated from setup's Firestore work even after caller cancellation.
- llm_executor: persona generation, onboarding LLM, slow model-backed work. Bulkhead
  to prevent slow LLM retries from blocking DB or auth operations.
- stripe_executor: Stripe API calls (Subscription.retrieve, etc.). External network I/O
  with unpredictable latency, isolated from everything else.
- sync_executor: sync pipeline VAD/STT/segment processing.
- postprocess_executor: best-effort post-processing (memories, trends, vectors,
  action items, goals, conversation processing, webhook delivery).
- cleanup_executor: long-running account-deletion wipes (vectors, recordings,
  Firestore subcollections). Bulkheaded so bursts of account deletions cannot
  starve normal post-processing.
- erasure_executor: conversation batch purges and accepted-delete erasures
  (conversation-erasure queue), apart from account-deletion wipes.
- storage_executor: audio file precaching, GCS operations.
- pinecone_shutdown: lazy single-worker mutation settlement, isolated from
  provider calls and the event loop's default executor during termination.
- cimd_executor: hosted-MCP OAuth client-metadata (CIMD) lookups — DNS,
  connect, and body reads to arbitrary unauthenticated-supplied hosts, all
  inside one hard monotonic deadline. Bulkheaded so hostile client_id floods
  cannot starve Firestore or any shared pool.
- cimd_dns (module-local in database/mcp_client_metadata.py): the getaddrinfo
  hop inside a CIMD lookup, split out so a
  stalled resolver cannot hold a fetch worker hostage.

These replace ad-hoc ThreadPoolExecutor creation throughout the codebase,
preventing thread proliferation and providing bounded concurrency.
"""

import asyncio
import atexit
import contextvars
import functools
import importlib
import logging
import os
import queue
import threading
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Callable, Coroutine, Dict, List, ParamSpec, TypeVar, cast

from prometheus_client import REGISTRY, Gauge
from config.occasion_conversations import LIFECYCLE_V2_MODE_ENV
from config.refactor_modes import serving_for

logger = logging.getLogger(__name__)
_worker_context = threading.local()


def in_db_worker() -> bool:
    """Identify the shared DB pool even for synchronous submissions."""
    return getattr(_worker_context, 'executor', None) is db_executor


P = ParamSpec("P")
T = TypeVar("T")


# Static task vocabulary: never derive metric labels from arguments or task IDs.
_TASKS = frozenset(
    {
        'record_episode_finalized',
        'record_moment',
        'attach_conversation',
        'process_with_episode_budget',
        'process_conversation',
        'extract_memories',
        '_save_summary_vector_fail_soft',
        'trigger_realtime_integrations',
        'finish_absorb',
        'decide_and_apply',
        '_reconcile_quiet_candidate',
    }
)


def _gauge(name: str, description: str, labelnames: tuple[str, ...] = ('executor', 'task')) -> Gauge:
    try:
        return Gauge(name, description, labelnames)
    except ValueError:
        existing = getattr(REGISTRY, '_names_to_collectors', {}).get(name)
        if getattr(existing, '_type', None) != 'gauge' or getattr(existing, '_labelnames', None) != labelnames:
            raise ValueError(f'executor metric {name} already has a different shape')
        return cast(Gauge, existing)


EXECUTOR_ACTIVE = _gauge('omi_executor_task_active', 'Active worker tasks by bounded task kind.')
EXECUTOR_QUEUED = _gauge('omi_executor_task_queued', 'Queued worker tasks by bounded task kind.')
EXECUTOR_MAX_WORKERS = _gauge('omi_executor_max_workers', 'Configured worker capacity.', ('executor',))


def _task_label(fn, args=()) -> str:
    while isinstance(fn, functools.partial):
        args, fn = fn.args, fn.func
    if getattr(fn, '__name__', '') == 'run' and args:
        return _task_label(args[0])
    name = getattr(fn, '__name__', '')
    return name if name in _TASKS else 'other'


class ExecutorSaturatedError(RuntimeError):
    """Raised when a bounded executor has no worker or queue capacity left."""


class MonitoredThreadPoolExecutor(ThreadPoolExecutor):
    """ThreadPoolExecutor with active-task tracking and optional backpressure."""

    def __init__(
        self, name: str, *, max_queue_size: int | None = None, wait_on_saturation: bool = False, **kwargs: Any
    ):
        super().__init__(**kwargs)
        self.name = name
        EXECUTOR_MAX_WORKERS.labels(executor=name).set(self._max_workers)
        self._active_count = 0
        self._active_lock = threading.Lock()
        self.max_queue_size = max_queue_size
        self._bounded_queue: queue.Queue[Any] | None = queue.Queue() if max_queue_size is not None else None
        if self._bounded_queue is not None:
            # A cancelled Future must not leave its payload in SimpleQueue
            # while its semaphore slot is reused by a later submission.
            setattr(self, "_work_queue", self._bounded_queue)
        self.wait_on_saturation = wait_on_saturation
        max_workers = self._max_workers
        self._submission_slots = (
            threading.BoundedSemaphore(max_workers + max_queue_size) if max_queue_size is not None else None
        )
        self._deferred_condition = threading.Condition(threading.RLock())
        self._deferred: deque[tuple[Future[Any], Callable[..., Any], tuple, dict]] = deque()
        self._deferred_shutdown = False

    @property
    def active_count(self) -> int:
        return self._active_count

    def submit(self, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> Future[T]:
        slots = self._submission_slots
        if slots is not None and not slots.acquire(blocking=False):
            if not self.wait_on_saturation:
                logger.warning(
                    'executor_saturated executor=%s workers=%s queue_capacity=%s',
                    self.name,
                    self._max_workers,
                    self.max_queue_size,
                )
            raise ExecutorSaturatedError(
                f'{self.name} executor is saturated ({self._max_workers} workers, {self.max_queue_size} queued)'
            )
        task = _task_label(fn, args)
        queued = EXECUTOR_QUEUED.labels(executor=self.name, task=task)
        queued.inc()
        started = threading.Event()
        try:
            future = super().submit(self._tracked, fn, task, started, *args, **kwargs)
        except BaseException:
            queued.dec()
            if slots is not None:
                slots.release()
            raise

        def cancelled(future):
            if future.cancelled() and not started.is_set():
                queued.dec()
                if slots is not None:
                    # Queue's mutex serializes removal against the worker get.
                    # A worker that already dequeued it will observe cancellation.
                    bounded = self._bounded_queue
                    if bounded is None:
                        raise RuntimeError('bounded executor has no queue')
                    with bounded.mutex:
                        pending = bounded.queue
                        for item in pending:
                            if getattr(item, 'future', None) is future:
                                pending.remove(item)
                                break

        future.add_done_callback(cancelled)
        if slots is not None:
            future.add_done_callback(self._release_slot)
        return future

    def _release_slot(self, _future: Future[Any]) -> None:
        if self._submission_slots is not None:
            self._submission_slots.release()
        with self._deferred_condition:
            self._drain_deferred()

    def submit_when_available(self, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> Future[T]:
        """Queue a saturated sync submission, retried by capacity-release callbacks.

        No retry thread or other feature pool is borrowed. At 64 deferred calls,
        synchronous producers backpressure until an entry is admitted. Call only
        from synchronous producers outside this executor, never the event loop.
        Like the executor's ordinary queue this queue is process-local.
        """
        future: Future[T] = Future()
        with self._deferred_condition:
            while len(self._deferred) >= 64 and not self._deferred_shutdown:
                self._deferred_condition.wait()
            if self._deferred_shutdown:
                raise RuntimeError('cannot schedule new futures after shutdown')
            self._deferred.append((future, fn, args, kwargs))
            self._drain_deferred()
        return future

    def _drain_deferred(self) -> None:
        # Caller owns the reentrant condition: a very short task can finish before
        # submit attaches its release callback, which then runs on this thread.
        while self._deferred and not self._deferred_shutdown:
            outer, fn, args, kwargs = self._deferred.popleft()
            if outer.cancelled():
                self._deferred_condition.notify_all()
                continue
            try:
                inner = self.submit(fn, *args, **kwargs)
            except ExecutorSaturatedError:
                self._deferred.appendleft((outer, fn, args, kwargs))
                return
            except BaseException as error:
                outer.set_exception(error)
                self._deferred_condition.notify_all()
                continue
            self._deferred_condition.notify_all()

            def completed(done: Future[Any], target: Future[Any] = outer) -> None:
                if not target.set_running_or_notify_cancel():
                    return
                if done.cancelled():
                    target.set_exception(RuntimeError('deferred executor work cancelled during shutdown'))
                elif (error := done.exception()) is not None:
                    target.set_exception(error)
                else:
                    target.set_result(done.result())

            inner.add_done_callback(completed)

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        with self._deferred_condition:
            if wait and not cancel_futures:
                while self._deferred:
                    self._deferred_condition.wait()
            self._deferred_shutdown = True
            while self._deferred:
                self._deferred.popleft()[0].cancel()
            self._deferred_condition.notify_all()
        super().shutdown(wait=wait, cancel_futures=cancel_futures)

    def _tracked(self, fn: Callable[..., T], task: str, started: threading.Event, *args: Any, **kwargs: Any) -> T:
        started.set()
        EXECUTOR_QUEUED.labels(executor=self.name, task=task).dec()
        active = EXECUTOR_ACTIVE.labels(executor=self.name, task=task)
        active.inc()
        with self._active_lock:
            self._active_count += 1
        prior_executor = getattr(_worker_context, 'executor', None)
        _worker_context.executor = self
        try:
            return fn(*args, **kwargs)
        finally:
            _worker_context.executor = prior_executor
            active.dec()
            with self._active_lock:
                self._active_count -= 1


# Authentication and rate-limit work gates every request. Bound the outstanding
# work so a slow identity provider cannot turn a burst into an unbounded memory
# queue (#6753); callers receive an explicit saturation failure instead.
critical_executor = MonitoredThreadPoolExecutor(
    name="critical", max_workers=8, max_queue_size=64, thread_name_prefix="critical"
)
# Before the record-barrier rollout the measured DB peak was 20/24 workers.
# Isolate barrier retries and retain 12 workers of headroom over that peak.
db_executor = MonitoredThreadPoolExecutor(
    name="db", max_workers=int(os.getenv('PUSHER_DB_EXECUTOR_WORKERS', '32')), thread_name_prefix="db"
)
# Optional read-cache checks cannot queue behind, or consume, serving DB workers.
# Shadow allowance IO cannot occupy the serving DB pool or grow an unbounded queue.
free_allowance_executor = MonitoredThreadPoolExecutor(
    name="free_allowance", max_workers=2, max_queue_size=4, thread_name_prefix="free-allowance"
)
read_cache_shadow_executor = MonitoredThreadPoolExecutor(
    name="read_cache_shadow",
    max_workers=2,
    max_queue_size=0,
    wait_on_saturation=True,  # submit still raises immediately; suppress expected rejection warnings.
    thread_name_prefix="read-cache-shadow",
)
record_barrier_executor = MonitoredThreadPoolExecutor(
    name="record_barrier",
    max_workers=int(os.getenv('PUSHER_RECORD_BARRIER_EXECUTOR_WORKERS', '16')),
    max_queue_size=64,
    wait_on_saturation=True,
    thread_name_prefix="record-barrier",
)
llm_executor = MonitoredThreadPoolExecutor(name="llm", max_workers=6, thread_name_prefix="llm")
# Batch policy HTTP leaves only; coordinators stay in async Pump code.
admission_executor = MonitoredThreadPoolExecutor(name="admission", max_workers=4, thread_name_prefix="admission")
stripe_executor = MonitoredThreadPoolExecutor(name="stripe", max_workers=4, thread_name_prefix="stripe")
sync_executor = MonitoredThreadPoolExecutor(name="sync", max_workers=16, thread_name_prefix="sync")
# Optional per-window LID must not hold the shared sync coordination pool.
# Bound outstanding calls; run_blocking awaits capacity without blocking a loop.
record_language_executor = MonitoredThreadPoolExecutor(
    name="record_language",
    max_workers=4,
    max_queue_size=8,
    wait_on_saturation=True,
    thread_name_prefix="record-language",
)
postprocess_executor = MonitoredThreadPoolExecutor(
    name="postprocess",
    # backend-integration raises this: its enrichment handler holds a thread per LLM-bound request.
    max_workers=int(os.getenv('POSTPROCESS_EXECUTOR_WORKERS', '24')),
    thread_name_prefix="postproc",
)
cleanup_executor = MonitoredThreadPoolExecutor(name="cleanup", max_workers=4, thread_name_prefix="cleanup")
# Sized to the conversation-erasure queue's maxConcurrentDispatches: a delivered task
# never waits here against its dispatch deadline, and a cleanup burst never waits in
# front of account wipes on cleanup's four workers.
erasure_executor = MonitoredThreadPoolExecutor(name="erasure", max_workers=20, thread_name_prefix="erasure")
storage_executor = MonitoredThreadPoolExecutor(name="storage", max_workers=128, thread_name_prefix="storage")
# Prompt-list verification may outlive its caller while a provider finishes.
# Keep both the clip cut and inline STT away from shared feature pools.
speaker_tag_verify_executor = MonitoredThreadPoolExecutor(
    name="speaker_tag_verify", max_workers=2, max_queue_size=2, thread_name_prefix="tagverify"
)
# URL-form OAuth client_ids let an unauthenticated caller name an arbitrary
# host to fetch. The pool stays tiny and strictly queued so a flood fails
# fast with ExecutorSaturatedError instead of holding shared workers. The DNS
# hop inside a lookup lives on a module-local pool in
# database/mcp_client_metadata.py — database must not import this module.
cimd_executor = MonitoredThreadPoolExecutor(name="cimd", max_workers=4, max_queue_size=8, thread_name_prefix="cimd")

quiet_replay_executor = MonitoredThreadPoolExecutor(
    name="quiet_replay", max_workers=16, max_queue_size=16, thread_name_prefix="quiet-replay"
)

# Open-loops daily pass: one structured LLM call per user per local day,
# dispatched by the recap job only after a user's recap work (push, backfill,
# webhook) is fully done. Off postprocess so a slow pass can never hold or
# delay a recap worker, and off llm so it cannot starve user-facing generation.
open_loops_executor = MonitoredThreadPoolExecutor(
    name="open_loops", max_workers=4, max_queue_size=64, thread_name_prefix="openloops"
)

_ALL_EXECUTORS = [
    quiet_replay_executor,
    critical_executor,
    db_executor,
    free_allowance_executor,
    read_cache_shadow_executor,
    record_barrier_executor,
    llm_executor,
    stripe_executor,
    admission_executor,
    sync_executor,
    record_language_executor,
    postprocess_executor,
    cleanup_executor,
    erasure_executor,
    storage_executor,
    speaker_tag_verify_executor,
    cimd_executor,
    open_loops_executor,
]

# refactor: superseded by bounded lifecycle pools when LIFECYCLE_V2_MODE=serve
_lifecycle_pools: dict[str, MonitoredThreadPoolExecutor] = {}
_lifecycle_pools_lock = threading.Lock()


def lifecycle_executor(uid: str, *, episode: bool = False) -> MonitoredThreadPoolExecutor:
    """Isolate episode bookkeeping first; backpressure admitted postprocessing.

    The legacy pool remains unchanged for shadow and off users. Async callers
    await capacity on these pools; sync submission fails explicitly on saturation.
    """
    if not serving_for(LIFECYCLE_V2_MODE_ENV, uid):
        return postprocess_executor
    name = 'episode' if episode else 'postprocess_v2'
    with _lifecycle_pools_lock:
        if name not in _lifecycle_pools:
            pool = MonitoredThreadPoolExecutor(
                name,
                max_workers=2 if episode else 24,
                max_queue_size=8 if episode else 96,
                wait_on_saturation=True,
                thread_name_prefix=name,
            )
            _lifecycle_pools[name] = pool
            _ALL_EXECUTORS.append(pool)
        return _lifecycle_pools[name]


_context_executor: MonitoredThreadPoolExecutor | None = None
_context_executor_lock = threading.Lock()


_pinecone_shutdown_executor: MonitoredThreadPoolExecutor | None = None
_pinecone_shutdown_executor_lock = threading.Lock()


def get_pinecone_shutdown_executor() -> MonitoredThreadPoolExecutor:
    """One shutdown worker plus one retry slot; created only when draining."""
    global _pinecone_shutdown_executor
    with _pinecone_shutdown_executor_lock:
        if _pinecone_shutdown_executor is None:
            _pinecone_shutdown_executor = MonitoredThreadPoolExecutor(
                name='pinecone_shutdown', max_workers=1, max_queue_size=1, thread_name_prefix='pinecone-shutdown'
            )
            _ALL_EXECUTORS.append(_pinecone_shutdown_executor)
        return _pinecone_shutdown_executor


def get_context_executor() -> MonitoredThreadPoolExecutor:
    """Lazy optional-read pool: four workers, no queue, true worker-lifetime slots."""
    global _context_executor
    with _context_executor_lock:
        if _context_executor is None:
            _context_executor = MonitoredThreadPoolExecutor(
                name='context', max_workers=4, max_queue_size=0, thread_name_prefix='context'
            )
            _ALL_EXECUTORS.append(_context_executor)
        return _context_executor


_rollout_executor: MonitoredThreadPoolExecutor | None = None
_rollout_executor_lock = threading.Lock()


def get_rollout_executor() -> MonitoredThreadPoolExecutor:
    """Small isolated pool for optional cohort reads; bounded during Firestore outages."""
    global _rollout_executor
    with _rollout_executor_lock:
        if _rollout_executor is None:
            _rollout_executor = MonitoredThreadPoolExecutor(
                name='rollout', max_workers=4, max_queue_size=64, thread_name_prefix='rollout'
            )
            _ALL_EXECUTORS.append(_rollout_executor)
        return _rollout_executor


_after_db = contextvars.ContextVar[list[Callable[[], Coroutine[Any, Any, Any]]] | None]('after_db', default=None)


def after_db_call(callback: Callable[[], Coroutine[Any, Any, Any]]) -> bool:
    """Await post-commit IO in the async caller after its DB worker is released.

    No task is detached. Cancellation leaves durable work for its retry owner.
    A synchronous caller without a DB offload scope keeps its ordinary path.
    """
    callbacks = _after_db.get()
    if callbacks is None:
        return False
    callbacks.append(callback)
    return True


_future_tracker: contextvars.ContextVar['ExecutorFutureTracker | None'] = contextvars.ContextVar(
    'executor_future_tracker', default=None
)


class ExecutorFutureTracker:
    """Session-scoped completion proof, independent of caller cancellation.

    Only selected pools are shielded. Completed futures are immediately removed,
    so a long-lived socket retains neither results nor upload arguments.
    """

    def __init__(self, *pools):
        self.pools = pools
        self.pending: set[asyncio.Future] = set()

    @contextmanager
    def scope(self):
        token = _future_tracker.set(self)
        try:
            yield
        finally:
            _future_tracker.reset(token)

    async def wait(self):
        # Call only after all submitting tasks have stopped. asyncio.wait never
        # propagates this coordinator's cancellation into the underlying work.
        while self.pending:
            await asyncio.wait(list(self.pending))

    def observe(self, executor, future):
        if executor not in self.pools:
            return False
        self.pending.add(future)

        def settled(done):
            self.pending.discard(done)
            if not done.cancelled():
                done.exception()

        future.add_done_callback(settled)
        return True


def track_executor_future(executor, future):
    """Include direct metadata submissions in the same session completion proof."""
    tracker = _future_tracker.get()
    return tracker is not None and tracker.observe(executor, future)


async def run_blocking(executor: ThreadPoolExecutor, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Offload *fn* to *executor*, propagating ContextVars."""
    loop = asyncio.get_running_loop()
    callbacks: list[Callable[[], Coroutine[Any, Any, Any]]] = []
    token = _after_db.set(callbacks) if executor is db_executor else None
    ctx = contextvars.copy_context()
    call = functools.partial(ctx.run, functools.partial(fn, *args, **kwargs))
    try:
        while True:
            try:
                future = loop.run_in_executor(executor, call)
                break
            except ExecutorSaturatedError:
                if not getattr(executor, 'wait_on_saturation', False):
                    raise
                # Backpressure stays in the async caller, without occupying another worker.
                await asyncio.sleep(0.05)
        result = await asyncio.shield(future) if track_executor_future(executor, future) else await future
    finally:
        if token is not None:
            _after_db.reset(token)
    # The worker has returned before any provider wait. Each callback owns its
    # deadline/error policy; never start it in a cancelled or failed DB call.
    for callback in callbacks:
        await callback()
    return result


def _byok_detail_code(error: BaseException) -> str | None:
    """Read the byok failure class off an already-mapped HTTPException detail.

    Structural mirror of ``utils.llm.gateway_error_contract.byok_failure_class_of``
    without importing it: this module sits below utils.byok in the import graph
    (gateway_error_contract reads the BYOK contextvars), so an import here would
    be circular. Only the typed conversation-processing boundary produces these
    details.
    """
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        detail = getattr(current, 'detail', None)
        if isinstance(detail, dict):
            code = detail.get('code')
            if isinstance(code, str) and code.startswith('byok_'):
                return code
        current = current.__cause__ or current.__context__
    return None


def _log_background_failure(name: str, future: "Future[Any]") -> None:
    if future.cancelled():
        return
    error = future.exception()
    if error is None:
        return
    # external_write_fence raises this while a deletion or retention cleanup
    # owns the account. The write is refused on purpose. A traceback here is
    # what Cloud Error Reporting groups as a crash at legal_holds.py.
    if type(error).__name__ == 'DestructiveOperationInProgress':
        logger.info('background task %s deferred reason=destructive_operation', name)
        return
    # A spent BYOK provider account (direct OpenRouter answers 402 'requires
    # more credits') is user account state, not a defect: retries can never
    # succeed and the provider's error body must not reach logs. The task body
    # classified the raw provider error inside the propagated BYOK context
    # (see _classify_byok_halt_in_context); the quota classification needs the
    # request's validated key, and this callback thread has no task context.
    # Logging the bounded class without a traceback keeps Error Reporting from
    # grouping the account state as a crash at the openai SDK frame.
    halt_class = getattr(error, 'omi_byok_halt_class', None)
    if isinstance(halt_class, str) and halt_class:
        logger.warning('background task %s halted reason=%s', name, halt_class)
        return
    # A BYOK provider failure is the user's own provider account state, not a
    # server fault: one structured WARNING, never a traceback at ERROR.
    byok_class = _byok_detail_code(error)
    if byok_class is not None:
        logger.warning(
            'byok provider failure is user account state, not a server fault: byok=true failure_class=%s '
            'route=background_task/%s',
            byok_class,
            name,
        )
        return
    logger.error("background task %s failed: %s", name, error, exc_info=error)


def _classify_byok_halt_in_context(fn: Callable[P, T]) -> Callable[P, T]:
    """Run *fn* and, on failure, classify a raw BYOK quota halt while the
    task's propagated contextvars (validated BYOK keys) are still live.

    The conversation boundary answers the same classification as a typed 429;
    tagging the exception here lets the done callback log the bounded halt
    without a traceback. A server-key error (no validated key in context)
    stays untagged and remains a loud server fault.
    """

    @functools.wraps(fn)
    def run(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return fn(*args, **kwargs)
        except BaseException as error:
            # Late-bound like merge_before_processing.py: executors sits below
            # utils.byok in the import graph (see _byok_detail_code), so a
            # static gateway_error_contract import would drag utils.cloud_tasks
            # into the GPU worker runtime image closure.
            gateway_error_contract = importlib.import_module('utils.llm.gateway_error_contract')

            if gateway_error_contract.is_byok_quota_error(error):
                setattr(error, 'omi_byok_halt_class', 'byok_quota')
            raise

    return run


def submit_with_context(
    executor: ThreadPoolExecutor, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> Future[T]:
    """Submit *fn* to *executor*, propagating the current contextvars (BYOK keys, etc.).

    Callers overwhelmingly discard the Future, so a raised exception would otherwise
    be retained on it and never surface. The done callback logs it instead; callers
    that do read the Future keep their own handling.
    """
    ctx = contextvars.copy_context()
    future = executor.submit(ctx.run, _classify_byok_halt_in_context(fn), *args, **kwargs)
    future.add_done_callback(functools.partial(_log_background_failure, getattr(fn, '__name__', repr(fn))))
    return future


def submit_with_context_retry(
    executor: MonitoredThreadPoolExecutor, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> Future[T]:
    """Sync fire-and-forget admission with a bounded retry queue on saturation."""
    ctx = contextvars.copy_context()
    future = cast(Future[T], executor.submit_when_available(ctx.run, fn, *args, **kwargs))
    future.add_done_callback(functools.partial(_log_background_failure, getattr(fn, '__name__', repr(fn))))
    return future


def get_executor_metrics() -> List[Dict[str, Any]]:
    """Return health metrics for all named executor pools."""
    metrics: List[Dict[str, Any]] = []
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
                'queue_capacity': executor.max_queue_size,
                'utilization_pct': utilization,
            }
        )
    return metrics


async def log_executor_health(
    interval_seconds: int = 60,
    utilization_threshold_pct: float = 70.0,
    queue_depth_threshold: int = 100,
):
    """Periodically log pool metrics when any pool exceeds a health threshold."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            metrics = get_executor_metrics()
            unhealthy = [
                p
                for p in metrics
                if p['utilization_pct'] > utilization_threshold_pct or p['queue_depth'] > queue_depth_threshold
            ]
            if unhealthy:
                logger.warning('executor_pool_health: %s', unhealthy)
        except Exception:
            pass


_background_tasks: set[asyncio.Task[Any]] = set()


def start_background_task(coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
    """Schedule *coro* as a tracked background task with exception logging.

    Use this instead of bare ``asyncio.create_task()`` for production
    fire-and-forget work.  Bare ``create_task`` silently drops exceptions
    and can be garbage-collected if the caller doesn't keep a reference.
    """
    from database.firestore_read_origin import background_task_read_origin

    # Task creation copies context; keep the original coroutine/task semantics.
    with background_task_read_origin(name):
        task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)

    def _done(t: asyncio.Task[Any]) -> None:
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

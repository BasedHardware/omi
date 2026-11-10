"""Supervised dedicated GPU loop. Admission rollback never stops durable draining."""

import asyncio
import contextlib
import logging
import math
import time
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from database.batch_privacy_attempt import with_batch_privacy_attempt
from database.firestore_transaction_retry import FirestoreContentionExhausted, is_transaction_contention

from config.batch_pipeline import (
    MAX_PUBLISH_CONCURRENCY,
    publish_concurrency as configured_publish_concurrency,
    admission_parallel_calls_enabled,
    idle_poll_max_seconds,
    maintenance_contention_continuation_enabled,
    publication_restrike_enabled,
)
from config.stt_cap_dispatch import offline_admission_enabled as cap_dispatch_enabled
from utils.batch_pipeline.contracts import (
    BatchWorker,
    HEARTBEAT_SECONDS,
    LeasedWork,
    PoolCapacity,
    HeldWork,
    FailedWork,
    RecoveryWork,
    ValidationFailureWork,
)
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.errors import FatalGpuError, error_site_field
from utils.batch_pipeline.compute_client import from_env as compute_client_from_env, failure_outcome
from utils.batch_pipeline import worker_metrics
from utils.batch_pipeline.leader import LeaderLease
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.stage_timings import StageTimings
from utils.executors import admission_executor, db_executor, run_blocking, sync_executor

logger = logging.getLogger(__name__)

# Maintenance re-reads every result_ready job each sweep to find its owner;
# jobs blocked behind an ordered predecessor would otherwise cost one read
# per sweep. Bounded well above the 100-row sweep page.
SEGMENT_OWNER_MEMO = 4096
# Bound on one lease-renewal round trip; a timeout marks the lease lost but the
# blocking DB leaf may still land later, fenced by its token.
HEARTBEAT_TIMEOUT_SECONDS = 8
# Spend admission checks leases serially under the server deadline, so one call
# carries at most this many leases; leases a call cannot reach come back
# unevaluated and wait out the admission backoff (32% of leases at 25%,
# 2026-11-02). Each call gets its own wait, above the client HTTP timeout.
ADMISSION_LEASES_PER_CALL = 4
ADMISSION_CALL_TIMEOUT_SECONDS = 10

# Deferred publication-drain convergence. A publication drain that loses to
# Firestore contention used to be swallowed at the catch site: convergence
# waited on an incidental later drain (a sibling's next publication or the
# leader-gated maintenance ready page), so an owner whose last results raced
# a hot document could sit merged-but-unprojected for a full sweep while the
# only trace was an ``event=batch_merge outcome=retry`` error line. The pump
# now re-offers the owner itself on a bounded lane: exponential backoff from
# DRAIN_RETRY_BASE_SECONDS capped at DRAIN_RETRY_MAX_SECONDS, at most
# DRAIN_RETRY_MAX_ATTEMPTS armed re-drains per owner per publication episode,
# and the durable maintenance sweep as the backstop behind the lane.
DRAIN_RETRY_BASE_SECONDS = 0.5
DRAIN_RETRY_MAX_SECONDS = 8.0
DRAIN_RETRY_MAX_ATTEMPTS = 6
# A drain that ends at the 100-commit bound with the owner's log possibly
# still pending re-offers immediately (no backoff): the bound exists to keep
# one drain call short, not to declare the owner converged. The continuation
# is capped so an endlessly-fed owner cannot pin the lane; maintenance
# converges whatever a capped continuation leaves.
DRAIN_BACKLOG_CONTINUATION_ATTEMPTS = 4
# Armed owners are a bounded map: a storm must not grow pump state without
# bound. Eviction is oldest-armed-first; an evicted owner keeps its durable
# result_ready rows and the maintenance ready page still converges it.
DRAIN_RETRY_LEDGER_CAP = 512


def deferred_drain_delay(attempt: int) -> float:
    """Backoff before the owner's ``attempt``-th armed re-drain (1-based).

    The first re-offer waits one base step, then doubles, bounded at the max:
    a contention wave is seconds-wide, so the schedule spends its first two
    steps inside the wave and never exceeds the sweep cadence that backstops
    it.
    """
    if attempt <= 1:
        return DRAIN_RETRY_BASE_SECONDS
    if attempt > DRAIN_RETRY_MAX_ATTEMPTS:
        # Clamp before raising 2 ** (attempt - 1): a huge attempt count is
        # caller data, and the schedule's shape past the cap is just the cap.
        return DRAIN_RETRY_MAX_SECONDS
    return min(DRAIN_RETRY_MAX_SECONDS, DRAIN_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))


def contention_retry_after(error: BaseException | None) -> float:
    """The storm damper's applied retry-after carried on a contention exhaustion.

    ``FirestoreStore.run`` stamps the window its storm damper actually armed
    for the drain's label onto the exhausted chain's ``retry_after``. On that
    measured signal the deferred lane lands its next re-drain after the armed
    window instead of colliding inside it: a fixed 0.5s re-offer against a
    document the damper just spaced waits out the same window inside
    ``store.run`` and burns a full five-attempt chain — the lockstep burn the
    damper exists to prevent — once per lane attempt until the budget dies.
    Only a positive finite number counts; a foreign exception, an exhaustion
    raised with no damper in scope, hostile or malformed input all keep the
    legacy fixed ladder. Never raises. The clamp keeps the lane's documented
    horizon (the max backoff step) unchanged: a storm shifts WHEN the next
    attempt lands, never the attempt budget or its ceiling.
    """
    value = getattr(error, 'retry_after', None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        return 0.0
    return min(value, DRAIN_RETRY_MAX_SECONDS)


# Bounded publication re-strike lane. A publication transition that exhausts
# its store-level contention budget today discards a completed GPU result:
# the pump marks the segment lost, the lease expires, and lease recovery
# re-leases the unit for a full GPU re-run — minutes of added latency and a
# whole inference pass spent re-producing a result this pump already held.
# The lane gives the same lease-fenced transition a bounded in-process
# re-strike with the documented doubling backoff before that fallback. Every
# re-strike rides the production lease fence (``owns_lease`` inside each
# scheduler transition), so a lease that died mid-lane is rejected exactly
# like a stale replay and the durable decision stands; only the bounded
# contention budget classifies as a re-strikeable loss
# (``publication_loss_is_contention``), and every other exception aborts the
# lane to the legacy catch site byte-for-byte. The terminal
# ``event=batch_completion outcome=retry`` ERROR line fires only past the
# lane, so the sensor's true-loss semantics are unchanged; a lane that lands
# the result reports ``restrike_committed`` at INFO and the owner's ordered
# drain proceeds as with any accepted publication.
#
# Failure-Class: FC-publication-contention-discards-completed-gpu-results
PUBLICATION_RESTRIKE_BASE_SECONDS = 0.25
PUBLICATION_RESTRIKE_MAX_SECONDS = 2.0
PUBLICATION_RESTRIKE_MAX_ATTEMPTS = 3


def publication_restrike_delay(attempt: int) -> float:
    """Backoff before the lane's ``attempt``-th re-strike (1-based).

    The first re-strike waits one base step, then doubles, bounded at the
    max: a contention wave is seconds-wide, so the schedule spends its
    first steps inside the wave and the whole lane stays an order of
    magnitude under the 120-second lease the fence still honors when the
    lane ends. Past the cap the shape is just the cap, so a caller-counted
    attempt number can never grow the schedule.
    """
    if attempt <= 1:
        return PUBLICATION_RESTRIKE_BASE_SECONDS
    if attempt > PUBLICATION_RESTRIKE_MAX_ATTEMPTS:
        return PUBLICATION_RESTRIKE_MAX_SECONDS
    return min(PUBLICATION_RESTRIKE_MAX_SECONDS, PUBLICATION_RESTRIKE_BASE_SECONDS * (2 ** (attempt - 1)))


def publication_loss_is_contention(error: BaseException) -> bool:
    """True for exactly the bounded contention budget a re-strike may replay.

    ``FirestoreContentionExhausted`` — including the Postgres job-store
    subclass — and any exception whose cause chain classifies as atomic
    transaction contention. Everything else (a revoked lease, an admission
    refusal, a real write failure) is the durable fallback's decision, not
    a lost race, and re-striking it would only replay the same refusal.
    """
    if isinstance(error, FirestoreContentionExhausted):
        return True
    return is_transaction_contention(error)


async def _drain_task(task):
    """Repeated caller cancellation cannot orphan a non-preemptible IO leaf."""
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                raise


class Pump:
    def __init__(
        self,
        scheduler: Scheduler,
        worker: BatchWorker,
        *,
        merge: OrderedMerge | None = None,
        metrics: QueueMetrics | None = None,
        batch_size: int = 8,
        poll_seconds: float = 2,
        on_committed: Callable[[dict], Any] | None = None,
        capacity: Callable[[], PoolCapacity] | None = None,
        project_pending: Callable[[], Any] | None = None,
        authorize_compute: Callable[[list[LeasedWork]], dict] | None = None,
        publish_concurrency: int | None = None,
        leader: LeaderLease | None = None,
        inline_metrics: bool = True,
        flights: int = 1,
        shadow=None,
        timings: StageTimings | None = None,
    ):
        if publish_concurrency is None:
            publish_concurrency = configured_publish_concurrency()
        if (
            not 1 <= batch_size <= 32
            or not 0 < poll_seconds <= 30
            or not 1 <= publish_concurrency <= MAX_PUBLISH_CONCURRENCY
            or not 1 <= flights <= 4
        ):
            raise ValueError('invalid bounded pump configuration')
        self.scheduler = scheduler
        self.worker = worker
        self.merge = merge or OrderedMerge(scheduler.store, metrics=metrics, commit_source='gpu_pump')
        self.metrics = metrics
        self.batch_size = batch_size
        self.poll_seconds = poll_seconds
        self.on_committed = on_committed
        self.capacity = capacity
        self.project_pending = project_pending
        self.authorize_compute = authorize_compute
        # Shared across flights and the synchronous dispatch re-check. Locks
        # live until the actual HTTP leaf returns, even if its async wait times out.
        self._admission_locks: dict[str, list] = {}
        self._admission_lock_guard = threading.Lock()
        # Optional single-owner lease for the recovery/drain tick. None keeps
        # every pump running it (single-replica and test behaviour).
        self.leader = leader
        # False when a supervisor samples queue metrics on its own task, so
        # gauges stay fresh while this pump awaits a long GPU batch.
        self.inline_metrics = inline_metrics
        self._last_recovery = float('-inf')
        self._last_metrics = float('-inf')
        self.publish_concurrency = publish_concurrency
        self._owner_locks: dict[str, list] = {}
        self._segment_owners: OrderedDict[str, str] = OrderedDict()
        # ``flights`` pump lanes overlap claim/admission and result publication
        # with another lane's GPU chain. The chain itself (decode through
        # persist and CUDA quiescence) stays exclusive under ``_gpu``, so device
        # and host memory remain those of one flight.
        self.flights = flights
        self._gpu = asyncio.Lock()
        self._maintenance = asyncio.Lock()
        # Deferred publication-drain convergence: owners whose ordered drain
        # lost to contention, awaiting a bounded re-offer (constants above).
        # The lane task exists only while the ledger is non-empty.
        self._deferred_drains: OrderedDict[str, dict] = OrderedDict()
        self._deferred_lane: asyncio.Task | None = None
        self._deferred_wake = asyncio.Event()
        self._deferred_stopped = False
        self._deferred_evictions = 0
        # Injectable monotone clock so suites can step the backoff schedule.
        self._monotonic = time.monotonic
        # Injectable lane delay so suites can step the publication re-strike
        # schedule without waiting out the real one.
        self._publication_sleep = asyncio.sleep
        self.shadow = shadow
        self._normal_flights = 0
        self.timings = timings or StageTimings()

    async def run(self, stop_event: asyncio.Event) -> None:
        """SIGTERM sets stop_event; in-flight chains drain with heartbeats intact."""
        halt = asyncio.Event()

        async def relay():
            await stop_event.wait()
            halt.set()

        relaying = asyncio.create_task(relay())
        # Periodic recovery and queue sampling get their own cadence so no
        # lane spends a claim/publication window on them between flights.
        maintaining = asyncio.create_task(self._maintain_loop(halt))
        lanes = [asyncio.create_task(self._lane(halt, maintain=False)) for _ in range(self.flights)]
        try:
            await asyncio.wait(lanes, return_when=asyncio.FIRST_EXCEPTION)
        finally:
            # One lane's fatal GPU error stops every sibling from pulling; a
            # sibling already holding leases refunds them instead of computing.
            halt.set()
            outcomes = await asyncio.gather(*lanes, return_exceptions=True)
            relaying.cancel()
            await asyncio.gather(maintaining, relaying, return_exceptions=True)
            await self.flush_deferred_drains()
        errors = [v for v in outcomes if isinstance(v, BaseException)]
        for error in errors:
            if isinstance(error, FatalGpuError):
                raise error
        if errors:
            raise errors[0]

    async def _maintain_loop(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                async with self._maintenance:
                    await self._maintain()
            except Exception as error:
                logger.error(
                    'event=batch_maintenance outcome=retry exception_type=%s%s',
                    type(error).__name__,
                    error_site_field(error),
                )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass

    async def _lane(self, stop_event: asyncio.Event, *, maintain: bool = True) -> None:
        idle_delay = self.poll_seconds
        while not stop_event.is_set():
            try:
                count = await self.run_once(stop_event=stop_event, maintain=maintain)
            except FatalGpuError:
                raise  # Fatal CUDA requires process replacement, never another pull.
            except Exception as error:
                logger.error(
                    'event=batch_pump outcome=retry exception_type=%s%s',
                    type(error).__name__,
                    error_site_field(error),
                )
                count = 0
            if not count:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=idle_delay)
                except asyncio.TimeoutError:
                    pass
                idle_delay = min(max(self.poll_seconds, idle_poll_max_seconds()), idle_delay * 2)
            else:
                idle_delay = self.poll_seconds

    async def _renew(self, leases: list[LeasedWork], done: asyncio.Event, lost: set[str]) -> None:
        while not done.is_set():
            try:
                await asyncio.wait_for(done.wait(), timeout=HEARTBEAT_SECONDS)
                return
            except asyncio.TimeoutError:
                pass

            async def renew_one(lease: LeasedWork):
                try:
                    valid = await asyncio.wait_for(
                        self._run_blocking(
                            'renew',
                            db_executor,
                            self.scheduler.heartbeat,
                            lease.item.segment_id,
                            lease.token,
                            time.time(),
                        ),
                        timeout=HEARTBEAT_TIMEOUT_SECONDS,
                    )
                except Exception:
                    # Ambiguous renewal cannot authorize publication. A late
                    # DB leaf is fenced by its original token; CUDA still drains.
                    valid = False
                if valid:
                    lost.discard(lease.item.segment_id)
                else:
                    lost.add(lease.item.segment_id)

            await asyncio.gather(*(renew_one(lease) for lease in leases))

    async def _run_blocking(self, stage, executor, function, *args, **kwargs):
        with self.timings.measure(stage):
            return await run_blocking(executor, function, *args, **kwargs)

    async def run_once(self, *, stop_event: asyncio.Event | None = None, maintain: bool = True) -> int:
        with self.timings.measure('pump_cycle'):
            if maintain and not self._maintenance.locked():
                async with self._maintenance:
                    await self._maintain()
            if stop_event is not None and stop_event.is_set():
                return 0
            return await self._flight(stop_event)

    async def _maintain(self) -> None:
        if self.shadow is not None:
            try:
                await self.shadow.maintain()
            except Exception:
                pass
        sampled_at = time.monotonic()
        if sampled_at - self._last_recovery >= 5:
            # Expired-lease recovery and the global result_ready drain are
            # idempotent and transaction-fenced; with several replicas one
            # leader runs them per tick. Each pump still drains the owners of
            # its own completions after each flight. The lease fails open on
            # store errors.
            if self.leader is None or await self._run_blocking('maintenance', db_executor, self.leader.acquire):
                if maintenance_contention_continuation_enabled():
                    await self._maintain_leader_steps()
                else:
                    if self.project_pending:
                        await self._run_blocking('projection', sync_executor, self.project_pending)
                    await self._run_blocking('maintenance', db_executor, self.scheduler.recover, time.time())
                    ready = await self._run_blocking(
                        'maintenance', db_executor, self.scheduler.store.due, 'result_ready', time.time(), 100
                    )
                    try:
                        await self._drain_ready_owners(ready)
                    except Exception as error:
                        # A fenced head on the page must not stop the held-owner re-offer below.
                        self._log_held_retry('ready_page', error)
                    # Durable hold markers outlive the in-memory set below (restarts).
                    marked = await self._run_blocking('maintenance', db_executor, self.merge.marked_page, 50)
                    for key, owner_id in marked:
                        try:
                            if owner_id:
                                await self.drain_owner(owner_id)
                            await self._run_blocking(
                                'maintenance', db_executor, self.merge.release_hold, key, force=not owner_id
                            )
                        except Exception as error:
                            self._log_held_retry('marker', error)
            # Every pump re-offers the owners its merge held for projection
            # depth; their rows may never surface in the 100-row page above.
            for owner_id in list(self.merge.held_owners):
                try:
                    await self.drain_owner(owner_id)
                except Exception as error:
                    self._log_held_retry('held', error)
            self._last_recovery = sampled_at
        if self.inline_metrics and self.metrics and sampled_at - self._last_metrics >= 15:
            await self.sample_metrics()
            self._last_metrics = sampled_at

    async def _maintenance_step(self, log_step: str, stage: str, executor, function, *args):
        """Run one maintenance step under its own outcome; a loss never suppresses siblings.

        The loss is logged under the step's stable name and retried at the next
        sweep (>=5s later): the sweep cadence bounds the re-strike and the
        store-level storm damper spaces it, so a hot document costs one bounded
        wait instead of a 1s whole-sweep re-strike that starves every later
        step. Returns the step's result, or None when the step lost.
        """
        try:
            return await self._run_blocking(stage, executor, function, *args)
        except Exception as error:
            logger.error(
                'event=batch_maintenance outcome=retry step=%s exception_type=%s%s',
                log_step,
                type(error).__name__,
                error_site_field(error),
            )
            return None

    async def _maintain_leader_steps(self) -> None:
        """The leader-gated maintenance steps, each under its own outcome."""
        if self.project_pending is not None:
            await self._maintenance_step('projection', 'projection', sync_executor, self.project_pending)
        await self._maintenance_step('recover', 'maintenance', db_executor, self.scheduler.recover, time.time())
        ready = await self._maintenance_step(
            'ready_due', 'maintenance', db_executor, self.scheduler.store.due, 'result_ready', time.time(), 100
        )
        if ready is not None:
            try:
                await self._drain_ready_owners(ready)
            except Exception as error:
                # A fenced head on the page must not stop the held-owner re-offer below.
                self._log_held_retry('ready_page', error)
        # Durable hold markers outlive the in-memory set below (restarts).
        marked = await self._maintenance_step('marked_page', 'maintenance', db_executor, self.merge.marked_page, 50)
        for key, owner_id in marked or []:
            try:
                if owner_id:
                    await self.drain_owner(owner_id)
                await self._run_blocking('maintenance', db_executor, self.merge.release_hold, key, force=not owner_id)
            except Exception as error:
                self._log_held_retry('marker', error)

    def _authorize_call(self, leases: list[LeasedWork]) -> dict:
        """One fail-closed HTTP leaf; serialize shared owners across all flights."""
        owners = sorted({v.item.owner_id for v in leases})
        with self._admission_lock_guard:
            entries = []
            for owner in owners:
                entry = self._admission_locks.setdefault(owner, [threading.Lock(), 0])
                entry[1] += 1
                entries.append((owner, entry))
        try:
            with contextlib.ExitStack() as stack:
                for _, entry in entries:
                    stack.enter_context(entry[0])
                try:
                    authorize = self.authorize_compute
                    part = (authorize(leases) or {}) if authorize else {}
                    result = {
                        'allowed': list(part.get('allowed') or []),
                        'retry_after': dict(part.get('retry_after') or {}),
                        'held_reason': dict(part.get('held_reason') or {}),
                    }
                except Exception as error:
                    worker_metrics.admission(failure_outcome(error))
                    return {}
                worker_metrics.admission('received')
                return result
        finally:
            with self._admission_lock_guard:
                for owner, entry in entries:
                    entry[1] -= 1
                    if not entry[1]:
                        del self._admission_locks[owner]

    @staticmethod
    def _merge_admission(parts: list[dict]) -> dict:
        allowed, retry_after, held_reason = [], {}, {}
        for part in parts:
            allowed += part.get('allowed', [])
            retry_after.update(part.get('retry_after', {}))
            held_reason.update(part.get('held_reason', {}))
        return {'allowed': allowed, 'retry_after': retry_after, 'held_reason': held_reason}

    def _authorize_in_calls(self, leases: list[LeasedWork]) -> dict:
        """Serial capped calls for the synchronous provider dispatch re-check."""
        return self._merge_admission(
            [
                self._authorize_call(leases[start : start + ADMISSION_LEASES_PER_CALL])
                for start in range(0, len(leases), ADMISSION_LEASES_PER_CALL)
            ]
        )

    async def _authorize_flight_timed(self, leases: list[LeasedWork]) -> dict:
        with self.timings.measure('admission'):
            return await self._authorize_flight(leases)

    async def _authorize_flight(self, leases: list[LeasedWork]) -> dict:
        """Pack first-seen owners; run only owner-disjoint calls together.

        Orchestration stays on the event loop, with at most four HTTP leaves
        in the dedicated pool. The number of calls and serial timeout bound
        remain ceil(leases / cap), including a single owner's large flight.
        """
        parallel = admission_parallel_calls_enabled()
        ordered = leases
        if parallel:
            groups: dict[str, list[LeasedWork]] = {}
            for lease in leases:
                groups.setdefault(lease.item.owner_id, []).append(lease)
            ordered = [lease for group in groups.values() for lease in group]
        pending = [
            ordered[start : start + ADMISSION_LEASES_PER_CALL]
            for start in range(0, len(ordered), ADMISSION_LEASES_PER_CALL)
        ]
        parts = []
        while pending:
            wave, remaining, owners = [], [], set()
            for call in pending:
                call_owners = {v.item.owner_id for v in call}
                if len(wave) < (4 if parallel else 1) and owners.isdisjoint(call_owners):
                    wave.append(call)
                    owners.update(call_owners)
                else:
                    remaining.append(call)
            parts.extend(
                await asyncio.gather(*(run_blocking(admission_executor, self._authorize_call, call) for call in wave))
            )
            pending = remaining
        return self._merge_admission(parts)

    @staticmethod
    def _log_held_retry(scope: str, error: Exception) -> None:
        logger.warning(
            'event=batch_merge action=held_reoffer outcome=retry scope=%s exception_type=%s count=1',
            scope,
            type(error).__name__,
        )

    @with_batch_privacy_attempt
    async def _flight(self, stop_event: asyncio.Event | None) -> int:
        now = time.time()
        snapshot = (
            self.capacity()
            if self.capacity
            else PoolCapacity(observed_at=now, available_slots=self.batch_size, reserved_fresh_slots=self.batch_size)
        )

        def claim():
            if stop_event is not None and stop_event.is_set():
                return []
            return self.scheduler.pull(time.time(), self.batch_size, capacity=snapshot)

        leases = await self._run_blocking('pull', db_executor, claim)
        if not leases:
            if self.shadow is not None:
                try:
                    return await self.shadow.run_once(self, capacity=snapshot)
                except FatalGpuError:
                    raise
                except Exception as error:
                    logger.info('event=batch_shadow_worker outcome=error exception_type=%s', type(error).__name__)
            return 0
        self._normal_flights += 1
        claimed = leases
        done = asyncio.Event()
        lost: set[str] = set()
        renew = asyncio.create_task(self._renew(leases, done, lost))
        prepared = None
        watching = None
        try:
            if self.shadow is not None:
                try:
                    await self.shadow.close()
                except Exception:
                    pass  # Shadow control failure cannot interrupt ordinary work.
            required = [
                v for v in leases if v.item.requires_compute_admission or cap_dispatch_enabled(v.item.owner_id, 'batch')
            ]
            if required:
                receipt = {}
                try:
                    if self.authorize_compute is None:
                        self.authorize_compute = compute_client_from_env()
                except Exception:
                    pass  # Missing configuration is a policy denial, never GPU permission.
                if self.authorize_compute:
                    calls = -(-len(required) // ADMISSION_LEASES_PER_CALL)
                    try:
                        receipt = await asyncio.wait_for(
                            self._authorize_flight_timed(required),
                            timeout=ADMISSION_CALL_TIMEOUT_SECONDS * calls,
                        )
                    except Exception as error:
                        worker_metrics.admission(failure_outcome(error))
                        receipt = {}
                else:
                    worker_metrics.admission('unconfigured')
                permitted = set(receipt.get('allowed') or [])
                retries = receipt.get('retry_after') or {}
                held_reason = receipt.get('held_reason') or {}
                for lease in required:
                    if lease.item.segment_id not in permitted:
                        lost.add(lease.item.segment_id)
                        await self._run_blocking(
                            'publication',
                            db_executor,
                            self.scheduler.defer,
                            lease.item.segment_id,
                            lease.token,
                            time.time(),
                            retries.get(lease.item.segment_id, 30),
                            held_reason=held_reason.get(lease.item.segment_id),
                            admission_refused=True,
                        )
                leases = [v for v in leases if v.item.segment_id not in lost]
                if not leases:
                    return 0
            dispatch_kwargs = {}
            dispatch_retries = {}
            if any(cap_dispatch_enabled(v.item.owner_id, 'batch') for v in leases):

                def authorize_dispatch(segments):
                    """Map each requested segment to its bounded hold reason.

                    ``None`` is an allow; any string, including '' for an
                    unevaluated unit, is a hold: missing policy authority never
                    becomes provider permission.
                    """
                    selected = [v for v in leases if v.item.segment_id in segments]
                    receipt = {}
                    if self.authorize_compute is not None:
                        receipt = self._authorize_in_calls(selected)
                    else:
                        worker_metrics.admission('unconfigured')
                    permitted = set(receipt.get('allowed') or [])
                    held = receipt.get('held_reason') or {}
                    retries = receipt.get('retry_after') or {}
                    for segment in segments:
                        if segment not in permitted and segment in retries:
                            dispatch_retries[segment] = retries[segment]
                    return {segment: (None if segment in permitted else held.get(segment, '')) for segment in segments}

                dispatch_kwargs['authorize_dispatch'] = authorize_dispatch
            prepare = getattr(self.worker, 'prepare_first', None)
            if prepare is not None and not (stop_event is not None and stop_event.is_set()):
                prepared = prepare([v.item for v in leases if v.item.segment_id not in lost])
            if prepared is not None:

                async def discard_invalid_preparation(handle):
                    while lost.isdisjoint(handle.segment_ids) and not (stop_event is not None and stop_event.is_set()):
                        await asyncio.sleep(0.1)
                    # Cancellation is immediate for queued work. Running SDK
                    # calls retain their reservation until the lane's final
                    # drain, and cannot be reused by a replacement attempt.
                    handle.cancel()

                watching = asyncio.create_task(discard_invalid_preparation(prepared))
            skipped: set[str] = set()
            try:
                async with self._gpu:
                    # Preparation belongs to the waiting lane. Once dispatch
                    # starts, the current bounded chain drains on stop/loss;
                    # cancelling a queued first fetch here would fake a failure.
                    if watching is not None:
                        watching.cancel()
                        watched = asyncio.gather(watching, return_exceptions=True)
                        try:
                            await asyncio.shield(watched)
                        except asyncio.CancelledError:
                            await _drain_task(watched)
                            raise
                        watching = None
                    if stop_event is not None and stop_event.is_set() and self.flights > 1:
                        # Claimed behind a sibling's chain when SIGTERM or a
                        # fatal GPU error arrived: refund without an attempt
                        # charge rather than start another chain. Leases marked
                        # lost by a timed-out renewal are refunded too: the
                        # token may still be ours, and defer is fenced by
                        # owns_lease, so another owner's job is never touched.
                        for lease in leases:
                            try:
                                await self._run_blocking(
                                    'publication',
                                    db_executor,
                                    self.scheduler.defer,
                                    lease.item.segment_id,
                                    lease.token,
                                    time.time(),
                                    1,
                                )
                            except Exception as error:
                                logger.error(
                                    'event=batch_flight outcome=lease_recovery exception_type=%s',
                                    type(error).__name__,
                                )
                        return 0
                    skipped = set(lost)
                    if prepared is not None:
                        # A queued decode may have been cancelled on stop/lease
                        # loss. Never let it become this or a replacement attempt.
                        if prepared.cancelled or not skipped.isdisjoint(prepared.segment_ids):
                            skipped.update(prepared.segment_ids)
                            # The fetch may already be running and cannot be
                            # cancelled. Final cleanup drains it after GPU unlock,
                            # with its reservation and lease renewal still held.
                            prepared.cancel()
                        else:
                            dispatch_kwargs['prepared'] = prepared
                    process = getattr(self.worker, 'process_batch_deferred', self.worker.process_batch)
                    compute = asyncio.create_task(
                        self._run_blocking(
                            # The HPA sizes on worker_flight: idle-only release must not buy a GPU.
                            (
                                'worker_flight_deep'
                                if all(v.item.priority == Priority.DEEP for v in leases)
                                else 'worker_flight'
                            ),
                            sync_executor,
                            process,
                            [v.item for v in leases if v.item.segment_id not in skipped],
                            **dispatch_kwargs,
                        )
                    )
                    # Cancelling an asyncio wrapper does not stop CUDA. Keep renewal
                    # and the GPU slot until the bounded model operation finishes.
                    try:
                        results = await asyncio.shield(compute)
                    except asyncio.CancelledError:
                        results = await _drain_task(compute)
                        if callable(getattr(results, 'close', None)):
                            await _drain_task(
                                asyncio.shield(asyncio.create_task(run_blocking(sync_executor, results.close)))
                            )
                        raise
                # CUDA is quiescent and the next lane may compute. Leases stay
                # renewed until every write and fenced publication has settled.
                if callable(getattr(results, 'settle', None)):
                    settling = asyncio.create_task(self._run_blocking('persist_settle', sync_executor, results.settle))
                    try:
                        results = await asyncio.shield(settling)
                    except asyncio.CancelledError:
                        await _drain_task(settling)
                        raise
            except FatalGpuError:
                # The whole GPU flight is uncertain. Return every owned lease
                # without charging an attempt; preserve its ordered position.
                for lease in leases:
                    try:
                        await self._run_blocking(
                            'publication',
                            db_executor,
                            self.scheduler.defer,
                            lease.item.segment_id,
                            lease.token,
                            time.time(),
                        )
                    except Exception as error:
                        # A revoked owner / ambiguous DB response must not stop
                        # us refunding siblings. Lease recovery remains durable.
                        logger.error(
                            'event=batch_gpu_restart outcome=lease_recovery exception_type=%s', type(error).__name__
                        )
                raise
            except Exception as error:
                logger.error('event=batch_chain outcome=retry exception_type=%s', type(error).__name__)
                results = []
            result_map = {v.segment_id: v for v in results}
            for segment, result in result_map.items():
                if isinstance(result, HeldWork) and segment in dispatch_retries:
                    result_map[segment] = replace(result, retry_after=dispatch_retries[segment])
            if len(result_map) != len(results) or not set(result_map).issubset(v.item.segment_id for v in leases):
                raise ValueError('worker returned duplicate or foreign results')
            # A renewal may recover after a waiting attempt was cancelled.
            # Never interpret its intentionally absent result as a GPU failure.
            for lease in leases:
                if lease.item.segment_id in skipped:
                    try:
                        await self._run_blocking(
                            'publication',
                            db_executor,
                            self.scheduler.defer,
                            lease.item.segment_id,
                            lease.token,
                            time.time(),
                            1,
                        )
                    except Exception as error:
                        logger.error(
                            'event=batch_flight outcome=lease_recovery exception_type=%s', type(error).__name__
                        )
            active = [v for v in leases if v.item.segment_id not in skipped]
            await self._publish_flight(active, result_map, lost)
            return len(active)
        except FatalGpuError:
            raise  # Its handler already refunded every lease without an attempt charge.
        except Exception:
            # Nothing else will touch these leases before LEASE_SECONDS expiry.
            # Release is fenced, so published, deferred or re-leased work is untouched.
            await self._release(claimed)
            raise
        finally:
            try:
                if watching is not None:
                    watching.cancel()
                    await _drain_task(asyncio.gather(watching, return_exceptions=True))
                if prepared is not None:
                    cleanup = asyncio.create_task(run_blocking(sync_executor, prepared.close))
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        await _drain_task(cleanup)
                        raise
            finally:
                self._normal_flights -= 1
                done.set()
                await _drain_task(asyncio.shield(renew))

    async def _release(self, leases: list[LeasedWork]) -> None:
        for lease in leases:
            try:
                await self._run_blocking(
                    'publication', db_executor, self.scheduler.release, lease.item.segment_id, lease.token, time.time()
                )
            except Exception as error:
                # Ambiguous release leaves lease expiry as the durable fallback.
                logger.error('event=batch_flight outcome=lease_release exception_type=%s', type(error).__name__)

    @contextlib.asynccontextmanager
    async def _owner_serial(self, owner_id: str):
        """Per-owner mutual exclusion; the entry lives only while someone holds or waits."""
        entry = self._owner_locks.get(owner_id)
        if entry is None:
            entry = self._owner_locks[owner_id] = [asyncio.Lock(), 0]
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if not entry[1]:
                self._owner_locks.pop(owner_id, None)

    async def _bounded_map(self, function, values) -> list:
        """Run ``function`` over ``values`` with at most publish_concurrency in flight."""
        gate = asyncio.Semaphore(self.publish_concurrency)

        async def one(value):
            async with gate:
                return await function(value)

        # Every sibling settles before an error propagates: no orphaned drains.
        outcomes = await asyncio.gather(*(one(value) for value in values), return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
        return outcomes

    async def _drain_ready_owners(self, ready: list[str]) -> None:
        """Maintenance: discover owners with result_ready work, drain each once."""

        async def owner_of(segment: str) -> str | None:
            if self.publish_concurrency > 1 and segment in self._segment_owners:
                return self._segment_owners[segment]
            job = await self._run_blocking('maintenance', db_executor, self.scheduler.store.probe, 'jobs', segment)
            owner_id = job.get('owner_id') if job else None
            if owner_id:
                self._remember_owner(segment, owner_id)
            return owner_id

        if self.publish_concurrency <= 1:
            owners: list[str] = []
            for segment in ready:
                owner_id = await owner_of(segment)
                if owner_id and owner_id not in owners:
                    owners.append(owner_id)
                    await self.drain_owner(owner_id)
            return
        found = await self._bounded_map(owner_of, ready)
        # First-seen order; one drain per owner, owners drained concurrently.
        await self._bounded_map(self.drain_owner, list(dict.fromkeys(v for v in found if v)))

    def _remember_owner(self, segment_id: str, owner_id: str) -> None:
        """Bounded segment -> owner memo. A segment's owner is immutable after
        admission, so a stale entry can only cause a harmless fenced drain probe."""
        self._segment_owners[segment_id] = owner_id
        self._segment_owners.move_to_end(segment_id)
        while len(self._segment_owners) > SEGMENT_OWNER_MEMO:
            self._segment_owners.popitem(last=False)

    async def _publish(self, lease: LeasedWork, result_map: dict, lost: set[str]) -> bool:
        """One fenced transition. True only when the owner's ordered merge may advance."""
        segment = lease.item.segment_id
        if segment in lost:
            try:
                current = await asyncio.wait_for(
                    self._run_blocking(
                        'renew', db_executor, self.scheduler.heartbeat, segment, lease.token, time.time()
                    ),
                    timeout=HEARTBEAT_TIMEOUT_SECONDS,
                )
            except Exception:
                current = False
            if not current:
                return False
            lost.discard(segment)
        try:
            return await self._publish_transition(lease, result_map)
        except Exception as error:
            # One revoked owner or ambiguous DB reply cannot suppress
            # unrelated results in the same compute batch. Durable
            # lease/log recovery decides this item's next transition.
            # A contention loss is different: the completed result is
            # still in hand and the lease fence is still valid, so the
            # bounded lane re-strikes the same fenced transition before
            # falling back to lease-expiry recovery. A non-contention
            # failure aborts the lane on the spot and the legacy catch
            # site below runs byte-for-byte as before.
            if publication_restrike_enabled():
                settled, accepted, error = await self._restrike_publication(lease, result_map, error)
                if settled:
                    return accepted
            lost.add(segment)
            logger.error('event=batch_completion outcome=retry exception_type=%s', type(error).__name__)
            return False

    async def _publish_transition(self, lease: LeasedWork, result_map: dict) -> bool:
        """The one lease-fenced transition ``_publish`` runs for a result.

        Extracted verbatim from the legacy ``_publish`` try block so the
        re-strike lane replays exactly the transition that lost, never a
        re-derived one. Every branch stays a single scheduler call fenced
        by ``owns_lease`` inside the transaction.
        """
        segment = lease.item.segment_id
        result = result_map.get(segment)
        if isinstance(result, HeldWork):
            await self._run_blocking(
                'publication',
                db_executor,
                self.scheduler.defer,
                segment,
                lease.token,
                time.time(),
                result.retry_after,
                held_reason=result.reason or None,
                admission_refused=True,
            )
            return False
        if isinstance(result, ValidationFailureWork):
            return bool(
                await self._run_blocking(
                    'publication',
                    db_executor,
                    self.scheduler.fail,
                    segment,
                    lease.token,
                    time.time(),
                    worker_failure={'stage': result.stage, 'reason': result.reason},
                    measured_held_vad_speech_seconds=result.measured_held_vad_speech_seconds,
                    worker_vad_receipt=result.worker_vad_receipt,
                )
            )
        if isinstance(result, RecoveryWork):
            return bool(
                await self._run_blocking(
                    'publication',
                    db_executor,
                    self.scheduler.fail,
                    segment,
                    lease.token,
                    time.time(),
                    quarantine=True,
                    padded_retry_empty=result.padded_retry_empty,
                    padded_retry=result.padded_retry,
                    worker_failure={'stage': 'assemble_words', 'reason': result.reason},
                    measured_held_vad_speech_seconds=result.measured_held_vad_speech_seconds,
                    worker_vad_receipt=result.worker_vad_receipt,
                )
            )
        if result is None or isinstance(result, FailedWork):
            return bool(
                await self._run_blocking(
                    'publication',
                    db_executor,
                    self.scheduler.fail,
                    segment,
                    lease.token,
                    time.time(),
                    measured_held_vad_speech_seconds=(
                        result.measured_held_vad_speech_seconds if result is not None else None
                    ),
                    worker_vad_receipt=result.worker_vad_receipt if result is not None else None,
                    worker_failure_evidence=result.worker_failure if isinstance(result, FailedWork) else None,
                )
            )
        return bool(
            await self._run_blocking(
                'publication', db_executor, self.scheduler.complete, result, lease.token, time.time()
            )
        )

    async def _restrike_publication(self, lease: LeasedWork, result_map: dict, first_error: Exception):
        """Bounded re-strike lane for one contention-lost publication transition.

        Returns ``(settled, accepted, error)``: ``settled`` means the
        fenced transition ran again and ``accepted`` is its authoritative
        answer (a lease that died mid-lane is rejected exactly like a
        stale replay — the durable decision, not a lane failure).
        ``settled`` is False when the loss is not contention (re-striking
        would only replay the same refusal) or when every re-strike also
        lost; ``error`` then carries the final exception for the legacy
        catch site, whose lost-marker and ERROR line are unchanged.
        """
        error = first_error
        for attempt in range(1, PUBLICATION_RESTRIKE_MAX_ATTEMPTS + 1):
            if not publication_loss_is_contention(error):
                return False, False, error
            delay = publication_restrike_delay(attempt)
            logger.info(
                'event=batch_publication outcome=restrike_wait attempt=%d delay_ms=%d exception_type=%s',
                attempt,
                round(delay * 1000),
                type(error).__name__,
            )
            await self._publication_sleep(delay)
            try:
                accepted = await self._publish_transition(lease, result_map)
            except Exception as retry_error:
                error = retry_error
                continue
            logger.info(
                'event=batch_publication outcome=restrike_committed attempt=%d accepted=%s',
                attempt,
                'true' if accepted else 'false',
            )
            return True, accepted, error
        return False, False, error

    async def _drain_after_publication(self, owner_id: str) -> None:
        try:
            await self.drain_owner(owner_id)
        except Exception as error:
            # The transition is durable. Convergence is no longer left to an
            # incidental later drain: this pump re-offers the owner on the
            # bounded deferred lane, and the maintenance ready page stays the
            # durable backstop behind it. Only a lane already at its attempt
            # cap falls back to the historical error line.
            if self._defer_drain(owner_id, retry_after=contention_retry_after(error)):
                logger.info(
                    'event=batch_merge_drain outcome=deferred exception_type=%s',
                    type(error).__name__,
                )
            else:
                logger.error('event=batch_merge outcome=retry exception_type=%s', type(error).__name__)

    async def _publish_flight(self, leases: list[LeasedWork], result_map: dict, lost: set[str]) -> None:
        """Publish one flight's results.

        Each transition stays an independent lease-fenced transaction. Owners
        publish concurrently (bounded); an owner's transitions all land before
        its single ordered drain, which the per-owner lock serializes with every
        other drain this pump runs. ``publish_concurrency == 1`` is the legacy
        serial path: lease order, one drain after each accepted transition.
        """
        if self.publish_concurrency <= 1:
            for lease in leases:
                if await self._publish(lease, result_map, lost):
                    await self._drain_after_publication(lease.item.owner_id)
            return
        gate = asyncio.Semaphore(self.publish_concurrency)
        by_owner: dict[str, list[LeasedWork]] = {}
        for lease in leases:
            self._remember_owner(lease.item.segment_id, lease.item.owner_id)
            by_owner.setdefault(lease.item.owner_id, []).append(lease)

        async def publish_one(lease: LeasedWork) -> bool:
            async with gate:
                return await self._publish(lease, result_map, lost)

        async def publish_owner(owner_id: str, owned: list[LeasedWork]) -> None:
            accepted = await asyncio.gather(*(publish_one(lease) for lease in owned))
            if any(accepted):
                async with gate:
                    await self._drain_after_publication(owner_id)

        await asyncio.gather(*(publish_owner(owner_id, owned) for owner_id, owned in by_owner.items()))

    def _defer_drain(
        self, owner_id: str, *, continuation: bool = False, attempts: int | None = None, retry_after: float = 0.0
    ) -> bool:
        """Arm one owner's deferred re-drain. True when armed, False at the cap.

        ``attempts`` counts armed re-drains this owner's episode already spent;
        ``None`` carries the ledger's count forward, so successive losses
        converge on one budget instead of resetting it at every catch site. A continuation (a drain that hit
        the 100-commit bound with work possibly pending) re-offers at once and
        spends a smaller budget.

        ``retry_after`` is the storm window the store's damper applied to the
        drain's label when the re-offered chain lost (0.0 when the loss was
        not contention or no damper ran): the re-drain then waits out that
        measured window instead of colliding inside it on the fixed ladder.
        The budget is unchanged — a storm shifts when the next attempt lands,
        never how many attempts remain.
        """
        if attempts is None:
            armed = self._deferred_drains.get(owner_id)
            attempts = armed['attempts'] if armed else 0
        cap = DRAIN_BACKLOG_CONTINUATION_ATTEMPTS if continuation else DRAIN_RETRY_MAX_ATTEMPTS
        next_attempt = attempts + 1
        if next_attempt > cap:
            self._deferred_drains.pop(owner_id, None)
            return False
        delay = 0.0 if continuation else deferred_drain_delay(next_attempt)
        if retry_after > 0.0:
            # Storm alignment: land the re-drain after the damper's armed
            # window, clamped to the lane's documented max step.
            delay = max(delay, min(float(retry_after), DRAIN_RETRY_MAX_SECONDS))
        self._deferred_drains.pop(owner_id, None)
        self._deferred_drains[owner_id] = {
            'attempts': next_attempt,
            'due_at': self._monotonic() + delay,
            'continuation': continuation,
        }
        while len(self._deferred_drains) > DRAIN_RETRY_LEDGER_CAP:
            self._deferred_drains.popitem(last=False)
            self._deferred_evictions += 1
        self._deferred_wake.set()
        self._ensure_deferred_lane()
        return True

    def _ensure_deferred_lane(self) -> None:
        if self._deferred_stopped:
            return
        if self._deferred_lane is None or self._deferred_lane.done():
            self._deferred_lane = asyncio.create_task(self._deferred_drain_lane())

    async def _drain_deferred_due(self) -> int:
        """Re-drain every armed owner whose backoff has elapsed; returns the count.

        The entry STAYS armed while its drain runs: a drain that ends at the
        100-commit bound re-offers the remainder itself through the same
        carried budget (popping first would reset that budget every round and
        let an endlessly-fed owner pin the lane), and a drain lost to
        contention re-arms through it too. The owner leaves the ledger only on
        a real convergence — the drain returned and did not re-offer — or when
        the attempt cap refuses a further re-offer. A sibling convergence just
        empties the slot; the loser moves on.
        """
        now = self._monotonic()
        due = [owner_id for owner_id, armed in self._deferred_drains.items() if armed['due_at'] <= now]
        drained = 0
        for owner_id in due:
            entry = self._deferred_drains.get(owner_id)
            if entry is None:
                continue
            attempt_no = entry['attempts']  # the armed re-drain this round consumes
            try:
                await self.drain_owner(owner_id)
            except asyncio.CancelledError:
                armed = self._deferred_drains.get(owner_id)
                if armed is not None:
                    armed['due_at'] = self._monotonic()  # retrigger as soon as the lane can
                raise
            except Exception as error:
                armed = self._deferred_drains.get(owner_id)
                if armed is not None and self._defer_drain(
                    owner_id,
                    attempts=armed['attempts'],
                    continuation=armed['continuation'],
                    retry_after=contention_retry_after(error),
                ):
                    logger.info(
                        'event=batch_merge_drain outcome=deferred exception_type=%s attempt=%d',
                        type(error).__name__,
                        attempt_no,
                    )
                else:
                    logger.error(
                        'event=batch_merge outcome=retry exception_type=%s attempt=%d',
                        type(error).__name__,
                        attempt_no,
                    )
                continue
            fresh = self._deferred_drains.get(owner_id)
            if fresh is entry:
                # drain_owner neither re-offered nor re-armed: the owner's log
                # is empty and the episode is over.
                self._deferred_drains.pop(owner_id, None)
                drained += 1
                logger.info('event=batch_merge_drain outcome=converged attempt=%d', entry['attempts'])
            elif fresh is None:
                # A healthy drain ends the episode inside drain_owner itself;
                # the lane only credits the convergence here.
                drained += 1
                logger.info('event=batch_merge_drain outcome=converged attempt=%d', entry['attempts'])
        return drained

    async def _deferred_drain_lane(self) -> None:
        """Wake at the earliest armed due time; exit only when the ledger empties."""
        try:
            while self._deferred_drains and not self._deferred_stopped:
                if not await self._drain_deferred_due():
                    if not self._deferred_drains:
                        continue  # the sweep drained or refused the last armed owner
                    wake = asyncio.ensure_future(self._deferred_wake.wait())
                    try:
                        next_due = min(armed['due_at'] for armed in self._deferred_drains.values())
                        await asyncio.wait_for(asyncio.shield(wake), timeout=max(0.0, next_due - self._monotonic()))
                    except asyncio.TimeoutError:
                        pass
                    finally:
                        wake.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await wake
        finally:
            self._deferred_lane = None
            if self._deferred_drains and not self._deferred_stopped:
                try:
                    # A lane cancelled by loop teardown must not resurrect
                    # itself: durability (the maintenance sweep) owns the rest.
                    self._ensure_deferred_lane()
                except RuntimeError:
                    pass

    async def flush_deferred_drains(self) -> None:
        """One last bounded re-offer for every armed owner when the pump stops.

        ``drain_owner`` state is durable: a flush loss leaves the owner to the
        maintenance sweep after restart, so a failing owner is logged and the
        flush continues; nothing here raises into shutdown.
        """
        self._deferred_stopped = True
        lane, self._deferred_lane = self._deferred_lane, None
        if lane is not None and not lane.done():
            lane.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lane
        # Entries STAY armed while their flush drain runs, exactly like the
        # lane's due sweep: a drain that ends at the 100-commit bound keeps
        # re-offering through its own continuation budget (bounded, so an
        # endlessly-fed owner cannot pin shutdown), and a healthy drain ends
        # its episode inside drain_owner. A drain that raises is terminal for
        # the flush: the owner is dropped with the historical error line and
        # the durable maintenance sweep converges it after restart.
        while self._deferred_drains:
            owner_id, entry = next(iter(self._deferred_drains.items()))
            try:
                await self.drain_owner(owner_id)
            except Exception as error:
                self._deferred_drains.pop(owner_id, None)
                logger.error(
                    'event=batch_merge outcome=retry exception_type=%s attempt=%d',
                    type(error).__name__,
                    entry['attempts'],
                )
        self._deferred_drains.clear()

    async def sample_metrics(self) -> None:
        """One complete queue-age sample; failures keep the last values and freshness."""
        if self.metrics:
            await run_blocking(db_executor, self.metrics.refresh, self.scheduler.store, time.time())

    async def drain_owner(self, owner_id: str) -> None:
        # Same-owner commits are strictly serial and capture-ordered: the merge
        # transaction picks the owner's first pending entry, and this lock keeps
        # two drains in this pump from racing on the owner's log tail.
        async with self._owner_serial(owner_id):
            for _ in range(100):
                entry = await self._run_blocking(
                    'ordered_merge', db_executor, self.merge.commit_next, owner_id, time.time()
                )
                if entry is None:
                    # A healthy drain proves the owner's log is empty: any
                    # armed deferred episode is over, armed budget spent or
                    # not. The maintenance sweep needs no second probe.
                    self._deferred_drains.pop(owner_id, None)
                    return
                if self.on_committed:
                    await self._run_blocking('projection', sync_executor, self.on_committed, entry)
            # The 100-commit bound keeps one drain call short; reaching it with
            # the owner's log possibly still pending is not convergence. The
            # remaining log re-offers immediately on the deferred lane (no
            # backoff: the bound, not contention, ended this drain), up to
            # DRAIN_BACKLOG_CONTINUATION_ATTEMPTS, then maintenance sweeps it.
            self._defer_drain(owner_id, continuation=True)

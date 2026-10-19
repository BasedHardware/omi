"""Supervised dedicated GPU loop. Admission rollback never stops durable draining."""

import asyncio
import contextlib
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from config.batch_pipeline import MAX_PUBLISH_CONCURRENCY, publish_concurrency as configured_publish_concurrency
from config.stt_cap_dispatch import execution_admission_enabled as cap_dispatch_enabled
from utils.batch_pipeline.contracts import (
    BatchWorker,
    HEARTBEAT_SECONDS,
    LeasedWork,
    PoolCapacity,
    HeldWork,
    RecoveryWork,
    ValidationFailureWork,
)
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.errors import FatalGpuError
from utils.batch_pipeline.compute_client import from_env as compute_client_from_env
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler
from utils.executors import db_executor, run_blocking, sync_executor

logger = logging.getLogger(__name__)

# Maintenance re-reads every result_ready job each sweep to find its owner;
# jobs blocked behind an ordered predecessor would otherwise cost one read
# per sweep. Bounded well above the 100-row sweep page.
SEGMENT_OWNER_MEMO = 4096


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
    ):
        if publish_concurrency is None:
            publish_concurrency = configured_publish_concurrency()
        if (
            not 1 <= batch_size <= 32
            or not 0 < poll_seconds <= 30
            or not 1 <= publish_concurrency <= MAX_PUBLISH_CONCURRENCY
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
        self._last_recovery = float('-inf')
        self._last_metrics = float('-inf')
        self.publish_concurrency = publish_concurrency
        self._owner_locks: dict[str, list] = {}
        self._segment_owners: OrderedDict[str, str] = OrderedDict()

    async def run(self, stop_event: asyncio.Event) -> None:
        """SIGTERM sets stop_event; the current chain drains with heartbeats intact."""
        while not stop_event.is_set():
            try:
                count = await self.run_once(stop_event=stop_event)
            except FatalGpuError:
                raise  # Fatal CUDA requires process replacement, never another pull.
            except Exception as error:
                logger.error('event=batch_pump outcome=retry exception_type=%s', type(error).__name__)
                count = 0
            if not count:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=self.poll_seconds)
                except asyncio.TimeoutError:
                    pass

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
                        run_blocking(
                            db_executor, self.scheduler.heartbeat, lease.item.segment_id, lease.token, time.time()
                        ),
                        timeout=8,
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

    async def run_once(self, *, stop_event: asyncio.Event | None = None) -> int:
        sampled_at = time.monotonic()
        if sampled_at - self._last_recovery >= 5:
            if self.project_pending:
                await run_blocking(sync_executor, self.project_pending)
            await run_blocking(db_executor, self.scheduler.recover, time.time())
            ready = await run_blocking(db_executor, self.scheduler.store.due, 'result_ready', time.time(), 100)
            await self._drain_ready_owners(ready)
            self._last_recovery = sampled_at
        if self.metrics and sampled_at - self._last_metrics >= 15:
            await run_blocking(db_executor, self.metrics.refresh, self.scheduler.store, time.time())
            self._last_metrics = sampled_at
        if stop_event is not None and stop_event.is_set():
            return 0
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

        leases = await run_blocking(db_executor, claim)
        if not leases:
            return 0
        done = asyncio.Event()
        lost: set[str] = set()
        renew = asyncio.create_task(self._renew(leases, done, lost))
        try:
            required = [v for v in leases if v.item.requires_compute_admission or cap_dispatch_enabled()]
            if required:
                receipt = {}
                try:
                    if self.authorize_compute is None:
                        self.authorize_compute = compute_client_from_env()
                except Exception:
                    pass  # Missing configuration is a policy denial, never GPU permission.
                if self.authorize_compute:
                    try:
                        receipt = await asyncio.wait_for(
                            run_blocking(db_executor, self.authorize_compute, required), timeout=10
                        )
                    except Exception:
                        receipt = {}
                permitted = set(receipt.get('allowed') or [])
                retries = receipt.get('retry_after') or {}
                for lease in required:
                    if lease.item.segment_id not in permitted:
                        lost.add(lease.item.segment_id)
                        await run_blocking(
                            db_executor,
                            self.scheduler.defer,
                            lease.item.segment_id,
                            lease.token,
                            time.time(),
                            retries.get(lease.item.segment_id, 30),
                        )
                leases = [v for v in leases if v.item.segment_id not in lost]
                if not leases:
                    return 0
            dispatch_kwargs = {}
            if cap_dispatch_enabled():

                def authorize_dispatch(segments):
                    selected = [v for v in leases if v.item.segment_id in segments]
                    receipt = self.authorize_compute(selected) if self.authorize_compute is not None else {}
                    return set(receipt.get('allowed') or [])

                dispatch_kwargs['authorize_dispatch'] = authorize_dispatch
            compute = asyncio.create_task(
                run_blocking(sync_executor, self.worker.process_batch, [v.item for v in leases], **dispatch_kwargs)
            )
            # Cancelling an asyncio wrapper does not stop CUDA. Keep renewal and
            # wait for the bounded model operation before leaving this process.
            try:
                results = await asyncio.shield(compute)
            except asyncio.CancelledError:
                results = await compute
                raise
            except FatalGpuError:
                # The whole GPU flight is uncertain. Return every owned lease
                # without charging an attempt; preserve its ordered position.
                for lease in leases:
                    try:
                        await run_blocking(
                            db_executor, self.scheduler.defer, lease.item.segment_id, lease.token, time.time()
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
            if len(result_map) != len(results) or not set(result_map).issubset(v.item.segment_id for v in leases):
                raise ValueError('worker returned duplicate or foreign results')
            await self._publish_flight(leases, result_map, lost)
            return len(leases)
        finally:
            done.set()
            await renew

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
            job = await run_blocking(db_executor, self.scheduler.store.run, lambda tx: tx.get('jobs', segment))
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
                    run_blocking(db_executor, self.scheduler.heartbeat, segment, lease.token, time.time()),
                    timeout=8,
                )
            except Exception:
                current = False
            if not current:
                return False
            lost.discard(segment)
        try:
            result = result_map.get(segment)
            if isinstance(result, HeldWork):
                await run_blocking(
                    db_executor, self.scheduler.defer, segment, lease.token, time.time(), result.retry_after
                )
                return False
            if isinstance(result, ValidationFailureWork):
                return bool(
                    await run_blocking(
                        db_executor,
                        self.scheduler.fail,
                        segment,
                        lease.token,
                        time.time(),
                        worker_failure={'stage': result.stage, 'reason': result.reason},
                    )
                )
            if isinstance(result, RecoveryWork):
                return bool(
                    await run_blocking(
                        db_executor,
                        self.scheduler.fail,
                        segment,
                        lease.token,
                        time.time(),
                        quarantine=True,
                        padded_retry_empty=result.padded_retry_empty,
                        padded_retry=result.padded_retry,
                        worker_failure={'stage': 'assemble_words', 'reason': result.reason},
                    )
                )
            if result is None:
                return bool(await run_blocking(db_executor, self.scheduler.fail, segment, lease.token, time.time()))
            return bool(await run_blocking(db_executor, self.scheduler.complete, result, lease.token, time.time()))
        except Exception as error:
            # One revoked owner or ambiguous DB reply cannot suppress
            # unrelated results in the same compute batch. Durable
            # lease/log recovery decides this item's next transition.
            lost.add(segment)
            logger.error('event=batch_completion outcome=retry exception_type=%s', type(error).__name__)
            return False

    async def _drain_after_publication(self, owner_id: str) -> None:
        try:
            await self.drain_owner(owner_id)
        except Exception as error:
            # The transition is durable; maintenance and serving drain later.
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

    async def drain_owner(self, owner_id: str) -> None:
        # Same-owner commits are strictly serial and capture-ordered: the merge
        # transaction picks the owner's first pending entry, and this lock keeps
        # two drains in this pump from racing on the owner's log tail.
        async with self._owner_serial(owner_id):
            for _ in range(100):
                entry = await run_blocking(db_executor, self.merge.commit_next, owner_id, time.time())
                if entry is None:
                    return
                if self.on_committed:
                    await run_blocking(sync_executor, self.on_committed, entry)

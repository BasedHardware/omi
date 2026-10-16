"""Supervised dedicated GPU loop. Admission rollback never stops durable draining."""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from config.stt_cap_dispatch import enabled as cap_dispatch_enabled
from utils.batch_pipeline.contracts import BatchWorker, HEARTBEAT_SECONDS, LeasedWork, PoolCapacity, HeldWork
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.errors import FatalGpuError
from utils.batch_pipeline.compute_client import from_env as compute_client_from_env
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler
from utils.executors import db_executor, run_blocking, sync_executor

logger = logging.getLogger(__name__)


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
    ):
        if not 1 <= batch_size <= 32 or not 0 < poll_seconds <= 30:
            raise ValueError('invalid bounded pump configuration')
        self.scheduler = scheduler
        self.worker = worker
        self.merge = merge or OrderedMerge(scheduler.store, metrics=metrics)
        self.metrics = metrics
        self.batch_size = batch_size
        self.poll_seconds = poll_seconds
        self.on_committed = on_committed
        self.capacity = capacity
        self.project_pending = project_pending
        self.authorize_compute = authorize_compute
        self._last_recovery = float('-inf')
        self._last_metrics = float('-inf')

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
            owners = set()
            for segment in ready:
                job = await run_blocking(db_executor, self.scheduler.store.run, lambda tx: tx.get('jobs', segment))
                if job and job['owner_id'] not in owners:
                    owners.add(job['owner_id'])
                    await self.drain_owner(job['owner_id'])
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
            for lease in leases:
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
                        continue
                    lost.discard(segment)
                try:
                    result = result_map.get(segment)
                    if isinstance(result, HeldWork):
                        await run_blocking(
                            db_executor, self.scheduler.defer, segment, lease.token, time.time(), result.retry_after
                        )
                        continue
                    if result is None:
                        if await run_blocking(db_executor, self.scheduler.fail, segment, lease.token, time.time()):
                            await self.drain_owner(lease.item.owner_id)
                        continue
                    accepted = await run_blocking(
                        db_executor, self.scheduler.complete, result, lease.token, time.time()
                    )
                    if accepted:
                        await self.drain_owner(lease.item.owner_id)
                except Exception as error:
                    # One revoked owner or ambiguous DB reply cannot suppress
                    # unrelated results in the same compute batch. Durable
                    # lease/log recovery decides this item's next transition.
                    lost.add(segment)
                    logger.error('event=batch_completion outcome=retry exception_type=%s', type(error).__name__)
            return len(leases)
        finally:
            done.set()
            await renew

    async def drain_owner(self, owner_id: str) -> None:
        for _ in range(100):
            entry = await run_blocking(db_executor, self.merge.commit_next, owner_id, time.time())
            if entry is None:
                return
            if self.on_committed:
                await run_blocking(sync_executor, self.on_committed, entry)

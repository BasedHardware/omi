"""Idle-only use of the existing pump's exclusive GPU chain and model instances."""

import asyncio
import hashlib
import os
import time

from config.batch_pipeline_shadow import shadow_percent
from utils.batch_pipeline.contracts import WorkResult, HeldWork
from utils.batch_pipeline.shadow_metrics import GPU
from utils.executors import db_executor, sync_executor, run_blocking, start_background_task


class ShadowRunner:
    def __init__(self, repository, recovery):
        self.repository, self.recovery = repository, recovery
        self.worker_id = hashlib.sha256(os.getenv('POD_NAME', os.getenv('HOSTNAME', '')).encode()).hexdigest()
        self._reap_at = 0.0
        self._recovering = False
        self._taking = False

    async def maintain(self):
        if shadow_percent() and time.monotonic() >= self._reap_at:
            self._reap_at = time.monotonic() + 60
            await asyncio.wait_for(run_blocking(db_executor, self.repository.reap), timeout=1)

    async def close(self):
        if shadow_percent():
            await asyncio.wait_for(
                run_blocking(db_executor, self.repository.offer, self.worker_id, close=True), timeout=0.25
            )

    async def run_once(self, pump):
        if not shadow_percent() or pump._gpu.locked() or pump._normal_flights or self._recovering or self._taking:
            return 0
        self._taking = True
        try:
            return await self._run_idle(pump)
        finally:
            self._taking = False

    async def _run_idle(self, pump):
        # Admission IO must not hold the ordinary GPU lock.
        item = await asyncio.wait_for(run_blocking(db_executor, self.repository.take, self.worker_id), timeout=1)
        if item is None:
            await asyncio.wait_for(run_blocking(db_executor, self.repository.offer, self.worker_id), timeout=1)
            return 0
        busy = await asyncio.wait_for(run_blocking(db_executor, self.repository.busy), timeout=1)
        if pump._gpu.locked() or pump._normal_flights or not shadow_percent() or busy:
            await run_blocking(db_executor, self.repository.finish, item.segment_id, 'dropped')
            return 0
        # No await between this final idle check and acquiring an unlocked lock.
        # Shadow never waits behind, batches with, or prefetches ordinary work.
        started = time.monotonic()
        try:
            async with pump._gpu:
                compute = asyncio.create_task(run_blocking(sync_executor, pump.worker.process_batch, [item]))
                try:
                    results = await asyncio.shield(compute)
                except asyncio.CancelledError:
                    await compute
                    raise
        except Exception:
            await run_blocking(db_executor, self.repository.finish, item.segment_id, 'error')
            raise
        finally:
            GPU.inc(time.monotonic() - started)
        # Result payloads already terminated at the shadow sink. Nothing enters
        # _publish_flight, OrderedMerge, projection, enrichment or usage.
        if results and isinstance(results[0], WorkResult):
            return 1
        if results and isinstance(results[0], HeldWork):
            await run_blocking(db_executor, self.repository.finish, item.segment_id, 'dropped')
        else:
            # At-most-once recovery is a CPU backend RPC, never imports the
            # legacy/provider dependency graph into the GPU image.
            self._recovering = True
            start_background_task(self._recover(item.segment_id), name='batch_shadow_recovery')
        return 1

    async def _recover(self, segment):
        try:
            await run_blocking(sync_executor, self.recovery, segment)
        except Exception:
            await run_blocking(db_executor, self.repository.finish, segment, 'error')
        finally:
            self._recovering = False

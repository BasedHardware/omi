"""Serving-side lease API. Authentication is at the router; all IO is lazy."""

import asyncio
from functools import lru_cache
from datetime import datetime, timezone
import logging
import os
import time

from config.batch_pipeline import live_record_admission_enabled, async_projection_enabled
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_staging import reap
from utils.batch_pipeline.intake import artifacts_for
from utils.batch_pipeline.live import drain_recordings
from utils.batch_pipeline.projection import Projector
from utils.executors import run_blocking, start_background_task, sync_executor
from utils.batch_pipeline.contracts import PoolCapacity, WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.retention import cleanup_completed_artifacts
from utils.sync.stage import current_stage
from utils.sync import reprocess


class Serving:
    def __init__(
        self,
        store,
        *,
        metrics=None,
        projector=None,
        cleanup=None,
        reap_staging=None,
        enrichment_sweep=None,
        recovery=None,
    ):
        self.store = store
        self.metrics = metrics
        self.projector = projector
        self.cleanup = cleanup
        self.reap_staging = reap_staging
        self.enrichment_sweep = enrichment_sweep
        self.recovery = recovery
        self.merge = OrderedMerge(store, metrics=metrics)

    def queue(self, pool='batch'):
        return Scheduler(self.store, metrics=self.metrics, pool=pool)

    def pull(self, limit: int, capacity: PoolCapacity, *, pool: str = 'batch'):
        return self.queue(pool).pull(time.time(), limit, capacity=capacity)

    def complete(self, result: WorkResult, token: str) -> bool:
        accepted = self.queue().complete(result, token, time.time())
        if accepted:
            job = self.store.run(lambda tx: tx.get('jobs', result.segment_id))
            if job:
                self.drain_owner(job['owner_id'])
        return accepted

    def drain_owner(self, owner_id: str):
        for _ in range(100):
            if self.merge.commit_next(owner_id, time.time()) is None:
                break

    async def reconcile_async(self, *, recover_quarantine=False):
        await run_blocking(sync_executor, self.reconcile, recover_quarantine=recover_quarantine)
        if async_projection_enabled() and self.projector:
            await self.projector.start_followups()

    def reconcile(self, *, recover_quarantine=False):
        if self.cleanup:
            try:
                if self.reap_staging:
                    self.reap_staging(self.store, datetime.now(timezone.utc))
                self.cleanup(self.store, datetime.now(timezone.utc))
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_cleanup outcome=retry exception_type=%s', type(error).__name__
                )
        if self.enrichment_sweep:
            self.enrichment_sweep()
        if recover_quarantine and self.recovery:
            self.recovery.sweep()
        self.queue().recover(time.time())
        owners = set()
        for segment in self.store.due('result_ready', time.time(), 100):
            job = self.store.run(lambda tx: tx.get('jobs', segment))
            if job and job['owner_id'] not in owners:
                owners.add(job['owner_id'])
                self.drain_owner(job['owner_id'])
        if self.projector:
            self.projector.sweep()
        if self.metrics:
            self.metrics.refresh(self.store, time.time())


@lru_cache(maxsize=2)
def serving_for_stage(stage: str) -> Serving:
    if stage != current_stage():
        raise ValueError('worker and serving stages must match')
    store = FirestoreStore(f'batch_pipeline_{stage}')
    artifacts = artifacts_for(store)
    projector = Projector(store, artifacts.load_result, fetch_audio=artifacts.fetch_audio)
    from utils.batch_pipeline.quarantine_recovery import QuarantineRecovery

    return Serving(
        store,
        recovery=QuarantineRecovery(store, artifacts),
        metrics=_metrics(),
        projector=projector,
        cleanup=cleanup_completed_artifacts,
        reap_staging=reap,
        enrichment_sweep=reprocess.sweep,
    )


@lru_cache(maxsize=1)
def _metrics() -> QueueMetrics:
    return QueueMetrics()


def start_serving_from_env():
    """Separate drain switch stays on when BATCH_PIPELINE_ENABLED rolls back."""
    if os.getenv('BATCH_PIPELINE_SERVING_ENABLED', 'false').strip().lower() != 'true':
        return None
    stop = asyncio.Event()

    async def supervise():
        while not stop.is_set():
            try:
                service = await run_blocking(sync_executor, serving_for_stage, current_stage())
                await service.reconcile_async(recover_quarantine=True)
                if live_record_admission_enabled():
                    await drain_recordings(service.store)
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_serving outcome=retry exception_type=%s', type(error).__name__
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=20)
            except asyncio.TimeoutError:
                pass

    return stop, start_background_task(supervise(), name='batch_pipeline_serving')


async def stop_serving(runtime):
    if runtime is None:
        return
    stop, task = runtime
    stop.set()
    # Allow any transactional projection to finish; retries are durable if the
    # process shutdown budget ends first. Recovery may await a bounded legacy STT request; its durable started intent
    # prevents a replacement process from issuing it again.
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=5)
    except asyncio.TimeoutError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

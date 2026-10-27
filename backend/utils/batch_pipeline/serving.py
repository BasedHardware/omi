"""Serving-side lease API. Authentication is at the router; all IO is lazy."""

import asyncio
from functools import lru_cache
from datetime import datetime, timezone
import logging
import os
import time

from config.batch_pipeline import (
    held_partial_enabled,
    owner_chain_projection_enabled,
    recovered_merge_release_enabled,
    recovery_dispatch_interval_seconds,
)
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_shadow_hook import shadow_from_env
from database.batch_pipeline_staging import reap
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.live import drain_recordings
from utils.batch_pipeline.projection import HELD_PARTIAL_PAGE, Projector, error_type
from utils.executors import run_blocking, start_background_task, sync_executor
from utils.batch_pipeline.contracts import PoolCapacity, WorkResult
from utils.batch_pipeline.leader import SERVING_MAINTENANCE, LeaderLease
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.retention import cleanup_completed_artifacts
from utils.sync.stage import current_stage
from utils.sync import reprocess

HELD_PARTIAL_INTERVAL_SECONDS = 300
# One maintenance tick chains held-partial pages into at most this much sweep
# time; a pass stopped by either budget keeps its cursor and resumes on the
# next supervisor tick instead of waiting out the interval above.
HELD_PARTIAL_TICK_SECONDS = 20.0
# Hourly read governor for the held sweep. The sweep charges its exact
# code-derived read count (one per examined document plus 5 per sibling and 7
# per attempted upload); this per-unit figure is only the pacing estimate for
# the page cap and the fallback for projector models that report no reads.
# 16 is the measured worst case for an upload per held unit (15 attempt reads
# + the query read; steady replays cost 14).
HELD_PARTIAL_READS_PER_HOUR = 120_000
HELD_PARTIAL_READS_PER_UNIT = 16
HELD_PARTIAL_WINDOW_SECONDS = 3600.0


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
        leader=None,
    ):
        self.store = store
        self.metrics = metrics
        self.projector = projector
        self.cleanup = cleanup
        self.reap_staging = reap_staging
        self.enrichment_sweep = enrichment_sweep
        self.recovery = recovery
        # Optional single-owner lease for periodic maintenance (see reconcile).
        self.leader = leader
        self.merge = OrderedMerge(store, metrics=metrics)
        # Held units change only on a recovery or operator settle: scan them
        # at a slow cadence, not every maintenance pass.
        self.held_partial_due = 0.0
        # (monotonic instant, reads charged) pairs: the hourly read governor.
        # Per serving instance; the maintenance lease usually pins one leader.
        self.held_partial_reads: list[tuple[float, int]] = []

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

    def drain_owner(self, owner_id: str, *, recovered: str | None = None):
        """Commit the owner's ready rows. ``recovered`` (a recovery wake) also
        releases that unit and its content's ready siblings past the head wait
        (the unit itself also past the catch-up depth hold)."""
        release = (
            self.merge.release_set(recovered) if recovered is not None and recovered_merge_release_enabled() else None
        )
        for _ in range(100):
            if self.merge.commit_next(owner_id, time.time(), release=release) is None:
                break

    async def reconcile_async(self, *, recover_quarantine=False, periodic=False, owner_id=None, recovered=None):
        priority = await run_blocking(
            sync_executor,
            self.reconcile,
            recover_quarantine=recover_quarantine,
            periodic=periodic,
            owner_id=owner_id,
            recovered=recovered,
        )
        # Walk-owed follow-ups keep the drain scheduled until they are queued.
        owes = getattr(self.projector, 'owes_followups', False) is True
        if self.projector and (priority or self.projector.has_async_followups or owes):
            await self.projector.start_followups(priority or ())
        # Owners the sweep or a wake discovered drain continuously in this process.
        if self.projector and getattr(self.projector, 'owes_drains', False) is True:
            self.projector.start_drains()
        # Deferred search/people-stats work left by walks converges off the chain.
        if self.projector and getattr(self.projector, 'owes_index', False) is True:
            self.projector.schedule_index_flush()

    def _leads(self, periodic: bool) -> bool:
        # Explicit RPC callers (POST /reconcile, post-recovery drain) always
        # run. Periodic ticks (supervisor, metrics scrape) run maintenance on
        # one serving instance per lease TTL; the lease fails open.
        return not periodic or self.leader is None or self.leader.acquire()

    def reconcile(self, *, recover_quarantine=False, periodic=False, owner_id=None, recovered=None) -> list[str]:
        """Returns async follow-ups an owner-chain wake wants run first."""
        if self._leads(periodic):
            self._maintain(recover_quarantine=recover_quarantine)
        priority = []
        if owner_id is not None and self.projector and owner_chain_projection_enabled():
            # A settled recovery commits at this owner's log tail. Walk the
            # owner's chain now instead of waiting for the global cursor. The
            # wake is only a hint: on failure the generic sweep still runs.
            try:
                self.drain_owner(owner_id, recovered=recovered)
                priority = self.projector.project_owner(owner_id, recovered=recovered)
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_projection action=owner_chain outcome=retry exception_type=%s', error_type(error)
                )
        # Projection and the local gauges stay per instance: projection is
        # throughput (ordered and fenced in its own transactions) and every
        # instance exports its own queue sample.
        if self.projector:
            self.projector.sweep()
        # Catch-up rows this instance held for projection depth may now fit.
        for held_owner in list(self.merge.held_owners):
            try:
                self.drain_owner(held_owner)
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_merge action=held_drain outcome=retry exception_type=%s', type(error).__name__
                )
        if self.metrics:
            self.metrics.refresh(self.store, time.time())
        return priority

    def dispatch_recovery(self):
        """Dispatch-loop tick: quarantine recovery only, on the maintenance leader."""
        if self.recovery is None or not self._leads(True):
            return None
        return self.recovery.sweep()

    def _charge_held_partial_reads(self, counts: dict) -> None:
        reads = counts.get('reads')
        if not isinstance(reads, int) or reads < 0:
            reads = counts.get('units', 0) * HELD_PARTIAL_READS_PER_UNIT
        if reads > 0:
            self.held_partial_reads.append((time.monotonic(), reads))

    def _held_partial_page_budget(self) -> int:
        """Full pages this tick may still examine under the hourly read governor."""
        now = time.monotonic()
        self.held_partial_reads = [
            charged for charged in self.held_partial_reads if now - charged[0] < HELD_PARTIAL_WINDOW_SECONDS
        ]
        spent = sum(reads for _, reads in self.held_partial_reads)
        return (HELD_PARTIAL_READS_PER_HOUR - spent) // (HELD_PARTIAL_PAGE * HELD_PARTIAL_READS_PER_UNIT)

    def _maintain(self, *, recover_quarantine: bool):
        """Idempotent, transaction-fenced maintenance: cleanup, sweeps, discovery, recovery, drain."""
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
        sweep_held = getattr(self.projector, 'sweep_held', None)
        if sweep_held is not None and time.monotonic() >= self.held_partial_due and held_partial_enabled():
            self.held_partial_due = time.monotonic() + HELD_PARTIAL_INTERVAL_SECONDS
            try:
                pages = self._held_partial_page_budget()
                if pages < 1:
                    # The hourly read governor is spent; rechecking it next tick
                    # costs no reads, and the backlog resumes as it refills.
                    self.held_partial_due = time.monotonic()
                else:
                    counts = sweep_held(deadline=time.monotonic() + HELD_PARTIAL_TICK_SECONDS, max_pages=pages)
                    if isinstance(counts, dict):
                        self._charge_held_partial_reads(counts)
                        if counts.get('more'):
                            # The tick or read budget stopped the pass mid-backlog.
                            self.held_partial_due = time.monotonic()
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_held_partial action=sweep outcome=retry exception_type=%s', type(error).__name__
                )
        self.queue().recover(time.time())
        owners = set()
        for segment in self.store.due('result_ready', time.time(), 100):
            job = self.store.run(lambda tx: tx.get('jobs', segment))
            if job and job['owner_id'] not in owners:
                owners.add(job['owner_id'])
                try:
                    self.drain_owner(job['owner_id'])
                except Exception as error:
                    # One fenced head must not stop the other owners or the held re-offer.
                    logging.getLogger(__name__).warning(
                        'event=batch_merge action=ready_drain outcome=retry exception_type=%s count=1',
                        type(error).__name__,
                    )
        # Held owners by durable marker: the page above can be all one held backlog.
        self.merge.reoffer_marked(self.drain_owner)


@lru_cache(maxsize=2)
def serving_for_stage(stage: str) -> Serving:
    if stage != current_stage():
        raise ValueError('worker and serving stages must match')
    store = shadow_from_env(FirestoreStore(f'batch_pipeline_{stage}'))
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
        # Supervisor ticks every 20s; a lapsed holder hands over within 60s.
        leader=LeaderLease(store, SERVING_MAINTENANCE, ttl_seconds=60),
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
                await service.reconcile_async(recover_quarantine=True, periodic=True)
                await drain_recordings(service.store)
            except Exception as error:
                logging.getLogger(__name__).error(
                    'event=batch_serving outcome=retry exception_type=%s', type(error).__name__
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=20)
            except asyncio.TimeoutError:
                pass

    async def dispatch_recovery():
        # Quarantine -> recovery start rode the whole serving pass plus its 20 s
        # sleep; this loop dispatches on its own short cadence.
        while not stop.is_set():
            interval = recovery_dispatch_interval_seconds()
            if interval > 0:
                try:
                    service = await run_blocking(sync_executor, serving_for_stage, current_stage())
                    await run_blocking(sync_executor, service.dispatch_recovery)
                except Exception as error:
                    logging.getLogger(__name__).error(
                        'event=batch_serving action=recovery_dispatch outcome=retry exception_type=%s',
                        type(error).__name__,
                    )
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval if interval > 0 else 20)
            except asyncio.TimeoutError:
                pass

    async def run():
        await asyncio.gather(supervise(), dispatch_recovery())

    return stop, start_background_task(run(), name='batch_pipeline_serving')


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

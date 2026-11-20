"""Post-commit hints and one elected due-page reader per batch namespace."""

import asyncio
import logging

from prometheus_client import Counter

from config.batch_pipeline import projection_followup_slots, projection_outbox_enabled, serving_sweep_page_rows
from database import batch_pipeline_projection_outbox as rows
from database.batch_pipeline_leader import LeaseLost
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked, ProjectionPredecessorPending
from database.batch_privacy_attempt import with_batch_privacy_attempt
from database.firestore_transaction_retry import FirestoreAborted
from utils.batch_pipeline.leader import PROJECTION_OUTBOX_SCAN, TABLE, LeaderLease
from utils.batch_pipeline.projection import Projector, error_type
from utils.batch_pipeline.projection_delivery import fenced_delivery
from utils.batch_pipeline.projection_followup import MAX_FOLLOWUPS, ProjectionFollowups
from utils.executors import db_executor, run_blocking, sync_executor
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
SCAN_INTERVAL = 5.0
COVERAGE_SECONDS = 30.0
MAX_SCAN_LAG = 60.0
MAX_PENDING = 200
ATTEMPT_SECONDS = 150.0  # Leave time to settle before the durable claim expires.
OUTCOMES = Counter(
    'omi_batch_pipeline_projection_outbox_total',
    'Durable projection scheduling outcomes',
    ['outcome'],
)


class ProjectionOutbox:
    def __init__(self, store, projector: Projector, *, clock):
        self.store, self.projector, self.clock = store, projector, clock
        self.leader = LeaderLease(store, PROJECTION_OUTBOX_SCAN, ttl_seconds=60, clock=clock)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queue: asyncio.Queue[rows.Obligation] = asyncio.Queue(MAX_PENDING)
        self.queued: set[rows.Obligation] = set()
        self.followups = ProjectionFollowups(projector)
        self.coverage_until = 0.0
        self.check_after = 0.0
        projector.outbox_coverage = self.has_coverage

    def wake(self, entry: dict) -> None:
        loop = self.loop
        if loop is None or not projection_outbox_enabled():
            return
        due = rows.due_obligation(entry['segment_id'], entry)
        if due is not None:
            try:
                loop.call_soon_threadsafe(self._enqueue, due.key, True)
            except RuntimeError:
                # The event loop closed after the commit. The indexed row remains due.
                return

    def _enqueue(self, key: rows.Obligation, hinted: bool = False) -> None:
        # Post-commit hints leave half the queue for lost-wake recovery.
        capacity = self.queue.maxsize // 2 if hinted else self.queue.maxsize
        if key not in self.queued and self.queue.qsize() < capacity:
            self.queue.put_nowait(key)
            self.queued.add(key)

    def scan(self, limit: int) -> list[rows.DueObligation]:
        if not projection_outbox_enabled() or not self.leader.acquire():
            return []
        guard = self.leader.guard()
        page = self.store.projection_outbox_page(self.clock(), limit)

        def confirm(tx):
            guard.check(tx)
            lease = tx.get(TABLE, PROJECTION_OUTBOX_SCAN)
            now = self.clock()
            healthy = not page or now - page[0].due_at <= MAX_SCAN_LAG
            current = lease.get('projection_scan_ready_until', 0.0)
            if (healthy and current <= now + SCAN_INTERVAL) or (not healthy and current > now):
                lease['projection_scan_ready_until'] = now + COVERAGE_SECONDS if healthy else 0.0
                tx.put(TABLE, PROJECTION_OUTBOX_SCAN, lease)

        # The immutable token must still own this page after the query returns.
        # Accepted keys become normal deliveries and can finish across failover.
        self.store.run(confirm)
        return page

    def has_coverage(self) -> bool:
        if not projection_outbox_enabled():
            return False
        now = self.clock()
        if now >= self.check_after:
            self.check_after = now + SCAN_INTERVAL
            self.coverage_until = 0.0
            try:
                lease = self.store.run(lambda tx: tx.get(TABLE, PROJECTION_OUTBOX_SCAN))
                ready_until = lease.get('projection_scan_ready_until', 0)
                if lease.get('token') and now < ready_until <= now + COVERAGE_SECONDS:
                    self.coverage_until = min(ready_until, lease['expires_at'])
            except Exception:
                self._fallback()
        return now < self.coverage_until

    @staticmethod
    def _fallback() -> None:
        record_fallback(
            component='firestore_read',
            from_mode='projection_outbox',
            to_mode='legacy_discovery',
            reason='unavailable',
            outcome='degraded',
            log=logger,
        )

    @with_batch_privacy_attempt
    async def deliver(self, key: rows.Obligation) -> None:
        token = await run_blocking(db_executor, rows.claim, self.store, key, self.clock)
        if token is None:
            return
        OUTCOMES.labels('claimed').inc()
        try:
            with fenced_delivery(key, token, self.clock):
                async with asyncio.timeout(ATTEMPT_SECONDS):
                    outcome = await run_blocking(sync_executor, self._assign_or_project, key, token)
                    if outcome == 'followup':
                        outcome = await self.followups.run(key.segment_id, track_backoff=False)
        except ProjectionPredecessorPending:
            outcome = 'predecessor'
        except (ProjectionBlocked, BatchPrivacyBlocked):
            outcome = 'blocked'
        except Exception as error:
            # Covered rows are skipped by legacy discovery. An aborted commit
            # should get a fresh claim before the generic follow-up backoff.
            exception_type = error_type(error)
            contention = isinstance(error, FirestoreAborted) or exception_type == 'FirestoreContentionExhausted'
            outcome = 'contention' if contention else 'retry'
            logger.warning('event=batch_projection_outbox outcome=%s exception_type=%s', outcome, exception_type)
        settled = await run_blocking(db_executor, rows.settle, self.store, key, token, self.clock, outcome)
        if settled is not None:
            OUTCOMES.labels(settled).inc()

    def _assign_or_project(self, key: rows.Obligation, token: str) -> str:
        segment = key.segment_id
        job, entry, binding = self.projector.store.read(segment)
        if not rows.holds_claim(entry, key, token, self.clock()) or rows.disposition(entry) is not None:
            return 'stale'
        try:
            return self.projector.apply_outbox_snapshot(segment, job, entry, binding)
        except (ProjectionBlocked, BatchPrivacyBlocked):
            raise
        except Exception as error:
            if self.projector.resolve_failing_head(segment, job, entry, binding, error):
                return 'blocked'
            raise

    async def _work(self) -> None:
        while True:
            key = await self.queue.get()
            try:
                await self.deliver(key)
                # The outbox also runs without a legacy sweep to launch work
                # owed by predecessor replay. Handoff after the claim context exits.
                if self.projector.owes_drains:
                    self.projector.start_drains()
                if self.projector.owes_followups:
                    await self.projector.start_followups(discover=False, include_walk=True)
                if self.projector.owes_index:
                    self.projector.schedule_index_flush()
            except Exception as error:
                # A possibly committed claim is left to expire. Do not retry a
                # settlement without the same revision and token.
                logger.warning(
                    'event=batch_projection_outbox outcome=store_retry exception_type=%s', type(error).__name__
                )
            finally:
                self.queued.discard(key)
                self.queue.task_done()

    async def _discover(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            limit = min(serving_sweep_page_rows(), self.queue.maxsize - self.queue.qsize())
            if limit > 0:
                try:
                    page = await run_blocking(db_executor, self.scan, limit)
                    for entry in page:
                        self._enqueue(entry.key)
                except LeaseLost:
                    pass  # The successor will rediscover the unclaimed page.
                except Exception:
                    self._fallback()
            try:
                await asyncio.wait_for(stop.wait(), timeout=SCAN_INTERVAL)
            except TimeoutError:
                pass

    async def run(self, stop: asyncio.Event) -> None:
        self.loop = asyncio.get_running_loop()
        slots = projection_followup_slots(MAX_FOLLOWUPS)
        self.projector.outbox_followup_slots = asyncio.Semaphore(slots)
        try:
            async with asyncio.TaskGroup() as group:
                workers = [group.create_task(self._work(), name='batch_projection_outbox') for _ in range(slots)]
                try:
                    await self._discover(stop)
                finally:
                    self.loop = None
                    for worker in workers:
                        worker.cancel()
        finally:
            self.projector.outbox_followup_slots = None
            while not self.queue.empty():
                self.queue.get_nowait()
                self.queue.task_done()
            self.queued.clear()

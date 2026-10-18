"""Bounded async drain of persisted projection receipts, independent of assignment.

The result log is the durable outbox. Tasks are only wakeups: restart, failure or
flag rollback leaves the same persisted/ready rows for the next sweep. The
existing ready/enrichment transaction and content ledger own idempotency.
"""

from __future__ import annotations

import asyncio
from collections import deque
import logging
from typing import TYPE_CHECKING

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay
from database.batch_pipeline_projection_claim import projection_claim
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.projection import projection_phase
from utils.batch_pipeline.scheduler import owner_key
from utils.executors import db_executor, postprocess_executor, run_blocking, start_background_task

if TYPE_CHECKING:
    from utils.batch_pipeline.projection import Projector

logger = logging.getLogger(__name__)
MAX_FOLLOWUPS = 4
FOLLOWUP_TIMEOUT_SECONDS = 120.0
CLAIM_RELEASE_TIMEOUT_SECONDS = 2.0


class ProjectionFollowups:
    def __init__(self, projector: Projector):
        self.projector = projector
        self.tasks: dict[str, asyncio.Task] = {}
        self.after: str | None = None
        self.pending: deque[str] = deque()
        self.closed = False

    def candidates(self):
        store = self.projector.store
        # Assignment failures/partial multipart output must not consume the
        # follow-up slots ahead of rows that have actually persisted.
        return [
            sid
            for sid in store.store.projection_pending(limit=100)
            if (store.ref('results', sid).get().to_dict() or {}).get('projection')
        ]

    async def schedule(self):
        # No await of slow follow-ups in the serving pass. Bound in-memory work;
        # unfinished rows remain in the existing 100-row query after restart.
        segments = await run_blocking(db_executor, self.candidates)
        if self.after in segments:
            offset = segments.index(self.after) + 1
            segments = segments[offset:] + segments[:offset]
        self.pending = deque(segment for segment in segments if segment not in self.tasks)
        self.launch()

    def launch(self):
        while self.pending and len(self.tasks) < MAX_FOLLOWUPS and not self.closed:
            segment = self.pending.popleft()
            task = start_background_task(self.run(segment), name='batch_projection_followup')
            self.tasks[segment] = task
            self.after = segment
            task.add_done_callback(lambda done, sid=segment: self.finished(sid, done))

    def finished(self, segment, task):
        self.tasks.pop(segment, None)
        if task.cancelled():
            # Global background-task shutdown must not replenish a cancelled
            # worker with another task after the shutdown snapshot was taken.
            self.closed = True
            self.pending.clear()
        self.launch()  # Refill immediately, without another 20s serving sleep.

    def read_persisted(self, segment):
        store = self.projector.store
        _, _, binding = store.read(segment)
        session = store.session(segment, binding, self.projector.clock())
        try:
            store.check(session)
        except ProjectionReplay:
            # Use the validated transaction snapshot, never the initial fetch hint.
            if session.entry.get('projection'):
                return session.job, session.entry, binding
        raise ProjectionBlocked('complete ordered assignment required before follow-up')

    async def run(self, segment):
        try:
            # Cancel this coordinator, not the drain. The persisted/ready outbox
            # row remains eligible for a later sweep, including a lost reply
            # after a side effect committed. Receipt transactions fence retries.
            async with asyncio.timeout(FOLLOWUP_TIMEOUT_SECONDS):
                await self._run(segment)
        except TimeoutError:
            logger.warning('event=batch_projection_followup outcome=timeout')

    async def _run(self, segment):
        # This is a segment claim, never the owner's assignment claim. Redis
        # remains advisory; identical side effects are replay-safe if unavailable.
        store = self.projector.store
        claim = await run_blocking(
            db_executor, projection_claim, store.store.namespace + ':followup', owner_key(segment)
        )
        entered = False
        try:
            acquired = await run_blocking(db_executor, claim.__enter__)
            entered = True
            if not acquired:
                return
            job, entry, binding = await run_blocking(db_executor, self.read_persisted, segment)
            item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
            parts = entry.get('projection_parts')
            for index, receipt in (
                sorted(parts.items(), key=lambda pair: int(pair[0])) if parts else [(None, entry['projection'])]
            ):
                await self.finish_part(item, binding, receipt, int(index) if index is not None else None)
            # Usage is resolved only when every sibling has ready receipts;
            # complete() atomically fences ledger/usage/client status as before.
            await run_blocking(postprocess_executor, self.projector.complete_content, segment, binding)
        except (ProjectionBlocked, BatchPrivacyBlocked):
            logger.info('event=batch_projection_followup outcome=blocked')
        except Exception as error:
            logger.error('event=batch_projection_followup outcome=retry exception_type=%s', type(error).__name__)
        finally:
            if entered:
                # Cleanup must not hold a follow-up slot if Redis/the DB pool
                # stalls. The advisory claim also has its own bounded TTL.
                try:
                    async with asyncio.timeout(CLAIM_RELEASE_TIMEOUT_SECONDS):
                        await run_blocking(db_executor, claim.__exit__, None, None, None)
                except TimeoutError:
                    logger.warning('event=batch_projection_followup action=release outcome=timeout')

    async def step(self, phase, executor, function, *args, **kwargs):
        with projection_phase(phase):
            return await run_blocking(executor, function, *args, **kwargs)

    async def finish_part(self, item, binding, receipt, index):
        if receipt['state'] == 'ready':
            return
        if receipt.get('conversation_id'):
            from utils.sync.bridge import finish_sync_bridges

            canonical = receipt['conversation_id']
            if not binding.record_origin:
                canonical = await self.step(
                    'bridge', postprocess_executor, finish_sync_bridges, binding.owner_id, canonical
                )
            if receipt.get('audio_required') and not binding.native_record:
                if self.projector.playback is not None:
                    await self.step('playback', postprocess_executor, self.projector.playback, item, canonical)
                else:
                    await self.step(
                        'playback',
                        postprocess_executor,
                        self.projector.persist_playback,
                        item,
                        binding,
                        canonical,
                        receipt,
                    )
                if not binding.record_origin:
                    # A later assignment can bridge this target while audio is
                    # being stored. Follow its redirect and recopy late donor
                    # audio even if an earlier bridge already checkpointed it.
                    canonical = await self.step(
                        'bridge',
                        postprocess_executor,
                        finish_sync_bridges,
                        binding.owner_id,
                        canonical,
                        audio_source_id=canonical,
                    )
            if receipt['enrichment_required']:
                await self.step(
                    'enrichment',
                    db_executor,
                    self.projector.store.mark_enrichment,
                    item.segment_id,
                    binding,
                    self.projector.clock(),
                    canonical,
                    receipt['language'],
                    part_index=index,
                )
                return
        await run_blocking(
            db_executor, self.projector.store.ready, item.segment_id, binding, self.projector.clock(), part_index=index
        )

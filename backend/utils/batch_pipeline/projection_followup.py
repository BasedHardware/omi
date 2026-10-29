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
from config.policy import ProjectionPolicy
from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay
from database.batch_pipeline_projection_claim import projection_claim
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.projection import error_site_field, error_type, projection_phase
from utils.batch_pipeline.scheduler import owner_key
from utils.executors import db_executor, postprocess_executor, run_blocking, start_background_task
from utils.batch_pipeline.projection_discovery import ProjectionDiscovery

if TYPE_CHECKING:
    from utils.batch_pipeline.projection import Projector

logger = logging.getLogger(__name__)
MAX_FOLLOWUPS = 4
# Walk-owed rows held between discovery passes. Dropped rows stay durable and
# are rediscovered; the bound only caps memory.
MAX_OWED = 256
FOLLOWUP_TIMEOUT_SECONDS = 120.0
CLAIM_RELEASE_TIMEOUT_SECONDS = 2.0


class ProjectionFollowups:
    def __init__(self, projector: Projector):
        self.projector = projector
        self.tasks: dict[str, asyncio.Task] = {}
        self.after: str | None = None
        self.pending: deque[str] = deque()
        self.prioritized: set[str] = set()
        self.owed: dict[str, None] = {}
        self.closed = False
        self.discovery = ProjectionDiscovery(projector.store.store)

    def candidates(self):
        store = self.projector.store
        # Assignment failures/partial multipart output must not consume the
        # follow-up slots ahead of rows that have actually persisted.
        candidates = []
        for sid in self.discovery.next(limit=100):
            if not (store.ref('results', sid).get().to_dict() or {}).get('projection'):
                continue
            policy = ProjectionPolicy.from_dict(store.read(sid)[0]['policy_parts']['projection'])
            if policy.async_projection:
                candidates.append(sid)
        return candidates

    async def schedule(self, priority=(), *, tail=()):
        # Rows a sweep's chain walk persisted, possibly behind the discovery
        # cursor. They wait for the next discovery pass and join behind its page,
        # so they never jump discovered work and never keep discovery from running.
        for segment in tail:
            if segment in self.owed:
                continue
            if len(self.owed) < MAX_OWED:
                self.owed[segment] = None
            else:
                # Over the bound: restart discovery at the head once so the next
                # page rediscovers the durable rows we could not hold.
                self.discovery.after = None
        if priority:
            # A targeted owner-chain wake goes ahead of discovered rows. Slots,
            # segment claims and receipt fences are unchanged; discovery resumes
            # once the queue drains.
            first = [segment for segment in dict.fromkeys(priority) if segment not in self.tasks]
            self.prioritized.update(first)
            self.pending = deque(first + [segment for segment in self.pending if segment not in first])
            self.launch()
            if self.pending or not self.owed:
                return
        # Finish launching this bounded page before advancing discovery. Slow
        # tasks must not cause the next serving pass to discard queued rows.
        # Owed rows fall through to discovery once the queue has launched.
        elif self.pending:
            self.launch()
            if self.pending or not self.owed:
                return
        # No await of slow follow-ups. Durable rows are rediscovered after restart.
        segments = await run_blocking(db_executor, self.candidates)
        if self.after in segments:
            offset = segments.index(self.after) + 1
            segments = segments[offset:] + segments[:offset]
        # A wake may have queued rows while this read was suspended; keep them
        # ahead of the discovered page instead of replacing the queue.
        queued = list(self.pending)
        discovered = [segment for segment in segments if segment not in self.tasks and segment not in queued]
        owed = [
            segment
            for segment in self.owed
            if segment not in self.tasks and segment not in queued and segment not in discovered
        ]
        self.owed.clear()
        # Owed rows are out of discovery order: they must not move the rotation.
        self.prioritized.update(owed)
        self.pending = deque(queued + discovered + owed)
        self.launch()

    def launch(self):
        while self.pending and len(self.tasks) < MAX_FOLLOWUPS and not self.closed:
            segment = self.pending.popleft()
            task = start_background_task(self.run(segment), name='batch_projection_followup')
            self.tasks[segment] = task
            if segment in self.prioritized:
                # Out-of-order wake rows must not move the discovery rotation.
                self.prioritized.discard(segment)
            else:
                self.after = segment
            task.add_done_callback(lambda done, sid=segment: self.finished(sid, done))

    def finished(self, segment, task):
        self.tasks.pop(segment, None)
        if task.cancelled():
            # Global background-task shutdown must not replenish a cancelled
            # worker with another task after the shutdown snapshot was taken.
            self.closed = True
            self.pending.clear()
            self.owed.clear()
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
            logger.error(
                'event=batch_projection_followup outcome=retry exception_type=%s%s',
                error_type(error),
                error_site_field(error),
            )
        finally:
            if entered:
                # Cleanup must not hold a follow-up slot if Redis/the DB pool
                # stalls. The advisory claim also has its own bounded TTL.
                try:
                    async with asyncio.timeout(CLAIM_RELEASE_TIMEOUT_SECONDS):
                        await run_blocking(db_executor, claim.__exit__, None, None, None)
                except TimeoutError:
                    logger.warning('event=batch_projection_followup action=release outcome=timeout')

    async def step(self, policy, phase, executor, function, *args, **kwargs):
        with projection_phase(phase, policy):
            return await run_blocking(executor, function, *args, **kwargs)

    async def finish_part(self, item, binding, receipt, index):
        policy = await run_blocking(db_executor, self.projector.store.policy, item.segment_id)
        if receipt['state'] in {'ready', 'quarantined'}:
            return
        if receipt.get('conversation_id'):
            from utils.sync.bridge import finish_sync_bridges

            outputs = receipt.get('size_rollover_outputs') or [{'conversation_id': receipt['conversation_id']}]
            canonicals = []
            for output in outputs:
                canonical = output['conversation_id']
                if not binding.record_origin:
                    canonical = await self.step(
                        policy,
                        'bridge',
                        postprocess_executor,
                        finish_sync_bridges,
                        binding.owner_id,
                        canonical,
                        **({'silent': True} if receipt.get('silent_redrive') else {}),
                    )
                if receipt.get('audio_required') and not binding.native_record:
                    if self.projector.playback is not None:
                        await self.step(
                            policy, 'playback', postprocess_executor, self.projector.playback, item, canonical
                        )
                    else:
                        await self.step(
                            policy,
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
                            policy,
                            'bridge',
                            postprocess_executor,
                            finish_sync_bridges,
                            binding.owner_id,
                            canonical,
                            audio_source_id=canonical,
                            **({'silent': True} if receipt.get('silent_redrive') else {}),
                        )
                canonicals.append(canonical)
            canonical = canonicals[0]
            if receipt['enrichment_required']:
                await self.step(
                    policy,
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

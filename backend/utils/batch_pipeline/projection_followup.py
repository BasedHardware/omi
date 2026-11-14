"""Bounded async drain of persisted projection receipts, independent of assignment.

The result log is the durable outbox. Tasks are only wakeups: restart, failure or
flag rollback leaves the same persisted/ready rows for the next sweep. The
existing ready/enrichment transaction and content ledger own idempotency.
"""

from __future__ import annotations

import asyncio
from collections import deque
import hashlib
import logging
import os
import socket
import time
from typing import TYPE_CHECKING

from prometheus_client import Counter

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_privacy_attempt import with_batch_privacy_attempt
from config.batch_pipeline import (
    projection_followup_backoff_seconds,
    projection_followup_page_enabled,
    projection_followup_slots,
    projection_pagination_enabled,
)
from config.policy import ProjectionPolicy
from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay
from database.batch_pipeline_store import PROJECTION_FINISH_STATES
from database.batch_pipeline_projection_claim import projection_claim
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem
from utils.batch_pipeline.projection import (
    error_site_field,
    error_type,
    fence_reason_field,
    projection_block_reason,
    projection_phase,
)
from utils.batch_pipeline.scheduler import owner_key
from utils.executors import db_executor, postprocess_executor, run_blocking, start_background_task
from utils.batch_pipeline.projection_discovery import ProjectionDiscovery

if TYPE_CHECKING:
    from utils.batch_pipeline.projection import Projector

logger = logging.getLogger(__name__)
# Default slot count; BATCH_PIPELINE_PROJECTION_FOLLOWUP_SLOTS tunes it per process.
MAX_FOLLOWUPS = 4
# Desync (BATCH_PIPELINE_PROJECTION_FOLLOWUP_BACKOFF_SECONDS > 0): a process that
# saw a row blocked, failed, timed out or claimed elsewhere skips it in its own
# discovery for BACKOFF_BASE_SECONDS, doubling per repeat up to the configured
# ceiling. Process memory only: the durable row is never skipped by anyone else,
# targeted/owed wakes bypass it, and a restart forgets it.
BACKOFF_BASE_SECONDS = 60.0


def instance_fraction() -> float:
    """Stable per-process point in [0, 1) from host, pid and process start time."""
    key = f'{socket.gethostname()}:{os.getpid()}:{_STARTED_NS}'
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big') / 2**64


_STARTED_NS = time.time_ns()
# Patchable: backoff is process-local monotonic time; the wall clock backs up the pass mark.
_monotonic = time.monotonic
_wall = time.time
MAX_BACKOFF_ROWS = 20_000
BACKOFF_OUTCOMES = frozenset({'blocked', 'retry', 'timeout', 'claim_busy', 'incomplete'})
OUTCOMES = Counter(
    'omi_batch_pipeline_projection_followup_outcomes_total',
    'Async projection follow-up attempts and discovery skips by outcome',
    ['outcome'],
)
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
        # Recovery requests may wake one owner's persisted receipts while a
        # periodic discovery page is already queued. Keep those wakeups apart
        # so a request cannot spend a slot on another owner's pending work.
        self.targeted_pending: deque[str] = deque()
        self.prioritized: set[str] = set()
        self.owed: dict[str, None] = {}
        self.closed = False
        self.discovery = ProjectionDiscovery(projector.store.store)
        self.page = 0
        self.pages: dict[str, int] = {}
        self.completion_attempts: set[tuple[int, ProjectionBinding]] = set()
        self.backoff_ceiling = projection_followup_backoff_seconds()
        # Desync needs the keyset cursor: with pagination off every page is the
        # head, so offset, backoff and pass bounds stay off (the legacy path).
        self.desync = self.backoff_ceiling > 0 and projection_pagination_enabled()
        self.backoff: dict[str, tuple[float, float]] = {}
        self.seeded = not self.desync
        # The current pass's mark (projector clock when it began); see begin_pass.
        self.wrap_at: float | None = None

    def seed_offset(self):
        """Start this process's first pass at a hashed point between the oldest receipt and now.

        Every process otherwise pages the same global head in lockstep after a
        roll. The cursor is a discovery hint only: the page wraps to the head at
        its end, so one full cycle still visits every row.
        """
        self.seeded = True
        if self.discovery.after is not None:
            return  # Never move a cursor discovery already holds.
        try:
            _, head = self.projector.store.store.projection_page(limit=1, states=PROJECTION_FINISH_STATES)
            oldest = float(head[0]) if head else None
            # committed_at is stamped with the projector's clock.
            now = float(self.projector.clock())
        except Exception as error:  # fail open: head-first discovery as before
            logger.warning(
                'event=batch_projection_followup action=seed outcome=error exception_type=%s', error_type(error)
            )
            return
        if oldest is None or not oldest < now:
            return
        self.discovery.after = (oldest + instance_fraction() * (now - oldest), '')
        self.wrap_at = now
        OUTCOMES.labels('seeded').inc()

    def backed_off(self, segment) -> bool:
        entry = self.backoff.get(segment)
        if entry is None:
            return False
        if entry[0] <= _monotonic():
            return False
        OUTCOMES.labels('backoff_skipped').inc()
        return True

    def note(self, segment, outcome):
        OUTCOMES.labels(outcome).inc()
        if not self.desync:
            return
        if outcome not in BACKOFF_OUTCOMES:
            self.backoff.pop(segment, None)
            return
        previous = self.backoff.pop(segment, (0.0, 0.0))[1]
        # A row claimed by another process is progress elsewhere: never escalate it.
        delay = max(BACKOFF_BASE_SECONDS, previous if outcome == 'claim_busy' else previous * 2)
        delay = min(delay, self.backoff_ceiling)
        self.backoff[segment] = (_monotonic() + delay, delay)
        if len(self.backoff) > MAX_BACKOFF_ROWS:
            # Dropping an entry only retries that row sooner.
            now = _monotonic()
            self.backoff = {sid: e for sid, e in self.backoff.items() if e[0] > now}
            while len(self.backoff) > MAX_BACKOFF_ROWS:
                self.backoff.pop(next(iter(self.backoff)))

    def discovered(self):
        page = None
        if not self.seeded:
            held = self.discovery.after
            self.seed_offset()  # a seeded pass starts mid-backlog with its mark set
            if self.discovery.after is not None and held is None:
                page = self.discovery.next(limit=100)
                if not page:
                    # A seed past the newest row (clock skew): wrap to the head now, not a tick later.
                    page = None
        if page is None:
            self.begin_pass()
            page = self.discovery.next(limit=100)
        self.end_pass_past_mark()
        return [sid for sid in page if not self.backed_off(sid)]

    # Desync coverage invariant (backoff > 0): every row committed at or before
    # a pass's mark is offered within that pass, ties at the mark included.
    # A pass begins at the head (or at the seed) with mark = projector clock,
    # and ends at the keyset page's own wrap or once its cursor is strictly
    # past the mark. So a tail that keeps every page full cannot extend a pass,
    # and a row skipped in backoff is offered again by a later bounded pass.

    def begin_pass(self):
        """A page fetched from the head (or with no mark yet) starts a pass: mark it now."""
        if self.desync and (self.discovery.after is None or self.wrap_at is None):
            self.wrap_at = self.clock_now()

    def end_pass_past_mark(self):
        after = self.discovery.after
        if not self.desync or after is None or self.wrap_at is None:
            return
        if after[0] > self.wrap_at:
            # Strictly past: ties at the mark order by key and finish first.
            self.discovery.after = None

    def clock_now(self) -> float | None:
        try:
            return float(self.projector.clock())
        except Exception:
            # The bound must not depend on the projector clock staying healthy.
            return _wall()

    def candidates(self):
        if projection_followup_page_enabled():
            # The query is already the durable receipt hint. Do not refetch
            # each result twice just to choose work. Filter pinned sync policy
            # before queueing so it cannot delay async recovery/owed rows.
            # Keep retrying unchanged receipts: a sibling or destination can
            # unblock them without changing this result's version.
            self.discovery.states = PROJECTION_FINISH_STATES
            candidates = []
            for sid in self.discovered():
                job = self.projector.store.ref('jobs', sid).get().to_dict() or {}
                raw = (job.get('policy_parts') or {}).get('projection')
                if raw is None:
                    # Legacy unpinned policy follows the same privacy-aware
                    # resolution as before. The common pinned path is one read.
                    raw = self.projector.store.read(sid)[0]['policy_parts']['projection']
                if ProjectionPolicy.from_dict(raw).async_projection:
                    candidates.append(sid)
            return candidates
        self.discovery.states = None
        store = self.projector.store
        # Assignment failures/partial multipart output must not consume the
        # follow-up slots ahead of rows that have actually persisted.
        candidates = []
        for sid in self.discovered():
            if not (store.ref('results', sid).get().to_dict() or {}).get('projection'):
                continue
            policy = ProjectionPolicy.from_dict(store.read(sid)[0]['policy_parts']['projection'])
            if policy.async_projection:
                candidates.append(sid)
        return candidates

    async def schedule(self, priority=(), *, tail=(), discover=True):
        # Rows a sweep's chain walk persisted, possibly behind the discovery
        # cursor. They wait for the next discovery pass and join behind its page,
        # so they never jump discovered work and never keep discovery from running.
        for segment in tail:
            self.forget_page(segment)  # Owed recovery work always probes completion.
            if segment in self.owed:
                continue
            if len(self.owed) < MAX_OWED:
                self.owed[segment] = None
            else:
                # Over the bound: restart discovery at the head once so the next
                # page rediscovers the durable rows we could not hold.
                self.discovery.after = None
        if not discover:
            first = [segment for segment in dict.fromkeys(priority) if segment not in self.tasks]
            if first:
                for segment in first:
                    self.forget_page(segment)  # Targeted recovery wakes always probe completion.
                selected = set(first)
                self.pending = deque(segment for segment in self.pending if segment not in selected)
                queued = set(self.targeted_pending)
                self.targeted_pending.extend(segment for segment in first if segment not in queued)
            self.launch_targeted()
            return
        if priority:
            # A targeted owner-chain wake goes ahead of discovered rows. Slots,
            # segment claims and receipt fences are unchanged; discovery resumes
            # once the queue drains.
            first = [segment for segment in dict.fromkeys(priority) if segment not in self.tasks]
            for segment in first:
                self.forget_page(segment)  # Targeted recovery wakes always probe completion.
            self.prioritized.update(first)
            self.pending = deque(first + [segment for segment in self.pending if segment not in first])
            self.launch()
            if not discover or self.pending or not self.owed:
                return
        # Finish launching this bounded page before advancing discovery. Slow
        # tasks must not cause the next serving pass to discard queued rows.
        # Owed rows fall through to discovery once the queue has launched.
        elif self.pending:
            self.launch()
            if self.pending or not self.owed:
                return
        if not discover:
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
        # Each discovered page gets fresh probes. Keep older page markers
        # until its queued/running tasks finish; they never suppress a new page.
        self.page += 1
        for segment in discovered:
            if segment not in self.owed:
                self.pages[segment] = self.page
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
        self.launch_targeted()
        while self.pending and len(self.tasks) < projection_followup_slots(MAX_FOLLOWUPS) and not self.closed:
            segment = self.pending.popleft()
            task = start_background_task(self.run(segment), name='batch_projection_followup')
            self.tasks[segment] = task
            if segment in self.prioritized:
                # Out-of-order wake rows must not move the discovery rotation.
                self.prioritized.discard(segment)
            else:
                self.after = segment
            task.add_done_callback(lambda done, sid=segment: self.finished(sid, done, targeted=False))

    def launch_targeted(self):
        while self.targeted_pending and len(self.tasks) < projection_followup_slots(MAX_FOLLOWUPS) and not self.closed:
            segment = self.targeted_pending.popleft()
            if segment in self.tasks:
                continue
            task = start_background_task(self.run(segment), name='batch_projection_followup')
            self.tasks[segment] = task
            task.add_done_callback(lambda done, sid=segment: self.finished(sid, done, targeted=True))

    def forget_page(self, segment):
        page = self.pages.pop(segment, None)
        if page is not None and page not in self.pages.values():
            self.completion_attempts = {key for key in self.completion_attempts if key[0] != page}

    def finished(self, segment, task, *, targeted=False):
        self.tasks.pop(segment, None)
        self.forget_page(segment)
        if task.cancelled():
            # Global background-task shutdown must not replenish a cancelled
            # worker with another task after the shutdown snapshot was taken.
            self.closed = True
            self.pending.clear()
            self.targeted_pending.clear()
            self.owed.clear()
            self.pages.clear()
            self.completion_attempts.clear()
        if targeted:
            self.launch_targeted()
        else:
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

    @with_batch_privacy_attempt
    async def run(self, segment):
        try:
            # Cancel this coordinator, not the drain. The persisted/ready outbox
            # row remains eligible for a later sweep, including a lost reply
            # after a side effect committed. Receipt transactions fence retries.
            async with asyncio.timeout(FOLLOWUP_TIMEOUT_SECONDS):
                outcome = await self._run(segment)
        except TimeoutError:
            logger.warning('event=batch_projection_followup outcome=timeout unit=%s', self.unit_key(segment))
            outcome = 'timeout'
        self.note(segment, outcome)

    @staticmethod
    def unit_key(segment: str) -> str:
        """Correlate attempts without emitting arbitrary source IDs or content."""
        return hashlib.sha256(segment.encode()).hexdigest()[:16]

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
                return 'claim_busy'
            job, entry, binding = await run_blocking(db_executor, self.read_persisted, segment)
            if projection_followup_page_enabled():
                policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                if not policy.async_projection:
                    return 'sync_owned'  # The synchronous sweep owns these receipts.
            was_ready = entry['projection']['state'] == 'ready' and all(
                part.get('state') == 'ready' for part in (entry.get('projection_parts') or {}).values()
            )
            item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
            parts = entry.get('projection_parts')
            for index, receipt in (
                sorted(parts.items(), key=lambda pair: int(pair[0])) if parts else [(None, entry['projection'])]
            ):
                await self.finish_part(item, binding, receipt, int(index) if index is not None else None)
            # Usage is resolved only when every sibling has ready receipts;
            # complete() atomically fences ledger/usage/client status as before.
            page = self.pages.get(segment, 0)
            key = (page, binding)
            coalesce = projection_followup_page_enabled() and was_ready and page != 0
            if coalesce:
                if key in self.completion_attempts:
                    return 'coalesced'
                self.completion_attempts.add(key)
            try:
                result = await run_blocking(postprocess_executor, self.projector.complete_content, segment, binding)
            except BaseException:
                # Failure/cancellation is not a readiness result. Another
                # sibling in this page may immediately retry the probe.
                if coalesce:
                    self.completion_attempts.discard(key)
                raise
            # None: the content is not finishable yet (a sibling is still owed or
            # a partial holds). The sibling's own follow-up probes completion.
            if result is not None and result.get('reason_code') == 'source_deleted':
                return 'source_deleted'
            return 'completed' if result is not None else 'incomplete'
        except (ProjectionBlocked, BatchPrivacyBlocked) as error:
            logger.info(
                'event=batch_projection_followup outcome=blocked unit=%s block_reason=%s%s%s',
                self.unit_key(segment),
                projection_block_reason(error),
                fence_reason_field(error),
                error_site_field(error),
            )
            return 'blocked'
        except Exception as error:
            logger.error(
                'event=batch_projection_followup outcome=retry unit=%s exception_type=%s%s',
                self.unit_key(segment),
                error_type(error),
                error_site_field(error),
            )
            return 'retry'
        finally:
            if entered:
                # Cleanup must not hold a follow-up slot if Redis/the DB pool
                # stalls. The advisory claim also has its own bounded TTL.
                try:
                    async with asyncio.timeout(CLAIM_RELEASE_TIMEOUT_SECONDS):
                        await run_blocking(db_executor, claim.__exit__, None, None, None)
                except TimeoutError:
                    logger.warning(
                        'event=batch_projection_followup action=release outcome=timeout unit=%s', self.unit_key(segment)
                    )

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

"""Bounded async drain of persisted projection receipts, independent of assignment.

The result log is the durable outbox. Tasks are only wakeups: restart, failure or
flag rollback leaves the same persisted/ready rows for the next sweep. The
existing ready/enrichment transaction and content ledger own idempotency.
"""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import nullcontext
from dataclasses import dataclass, field
import hashlib
import logging
import os
import socket
import time
from typing import TYPE_CHECKING

from prometheus_client import Counter, Histogram

from database.batch_pipeline_privacy import BatchPrivacyBlocked, matches_live_privacy_version
from database.batch_privacy_attempt import with_batch_privacy_attempt
from config.batch_pipeline import (
    projection_followup_backoff_seconds,
    projection_followup_discovery_interval_seconds,
    projection_followup_claimed_sibling_skip_enabled,
    projection_followup_early_coalesce_enabled,
    projection_followup_page_enabled,
    projection_followup_slots,
    projection_pagination_enabled,
)
from config.policy import ProjectionPolicy
from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay
from database.batch_pipeline_store import PROJECTION_FINISH_STATES
from database.batch_pipeline_projection_claim import projection_claim
from database.batch_pipeline_projection_session import FollowupPrivacyProof, ready_followup_privacy_ids
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
from utils.batch_pipeline.projection_followup_clock import FollowupClock
from utils.batch_pipeline.projection_overlap import observer_for_store

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
TARGETED_START_SECONDS = Histogram(
    'omi_batch_pipeline_projection_followup_targeted_start_seconds',
    'Targeted follow-up wake to actual attempt start (including slot wait), per serving process',
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600, 1800),
)
MAX_WAKE_MARKS = 20_000
# Walk-owed rows held between discovery passes. Dropped rows stay durable and
# are rediscovered; the bound only caps memory.
MAX_OWED = 256
FOLLOWUP_TIMEOUT_SECONDS = 120.0
CLAIM_RELEASE_TIMEOUT_SECONDS = 2.0


# How long a ready sibling waits for its same-page claimant's live privacy proof.
CLAIM_PROOF_WAIT_SECONDS = 5.0


@dataclass
class SiblingClaim:
    """The first ready sibling for a (page, binding) and the siblings skipped behind it.

    ``proof`` is the claimant's live privacy proof from its own session check,
    published before its completion attempt. A sibling may coalesce on it only
    through the existing C1 verification (covered ids, expiry, live token).
    """

    ready: asyncio.Event = field(default_factory=asyncio.Event)
    proof: FollowupPrivacyProof | None = None
    waiting: list = field(default_factory=list)
    # True once this claimant itself registered the completion attempt; only then
    # may its release leave skipped siblings coalesced.
    attempted: bool = False


@dataclass(frozen=True)
class PersistedFollowup:
    job: dict
    entry: dict
    binding: ProjectionBinding
    proof: FollowupPrivacyProof | None = None
    coalesced: bool = False


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
        store = projector.store.store
        # Only existing periodic Firestore discovery pages, before local backoff.
        # Targeted/owed repairs and simulated/Postgres stores are outside this measurement.
        self.discovery = ProjectionDiscovery(
            store, on_page=observer_for_store(store), outbox_coverage=getattr(projector, 'has_outbox_coverage', None)
        )
        self.due_clock = FollowupClock(projector)
        self.due_pass_before: float | None = None
        self.page = 0
        self.pages: dict[str, int] = {}
        self.completion_attempts: set[tuple[int, ProjectionBinding]] = set()
        # (page, binding) -> ready siblings that skipped behind the first claimant (SCA-3508).
        self.sibling_claims: dict[tuple[int, ProjectionBinding], SiblingClaim] = {}
        # Skipped siblings still finishing when their claimant gave up: re-queue on finish.
        self.sibling_requeue: set[str] = set()
        self.completed_probes: dict[int, dict[ProjectionBinding, FollowupPrivacyProof]] = {}
        # Targeted wake time per segment, for wake-to-attempt-start latency (SCA-3120).
        self.wake_marks: dict[str, float] = {}
        # Monotonic time of this process's last periodic discovery read (pacing only).
        self.last_discovery: float | None = None
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
        due = self.due_clock.before(self.desync and projection_followup_page_enabled())
        if due is not None:
            # Durable due selection replaces local sleeping. A row due elsewhere
            # (or reset by a state move) must not wait on this process's old cache.
            # Freeze eligibility for this pass. A stream of new due rows must
            # not extend the tail forever and starve rows behind the cursor.
            if self.discovery.clock_mode != 'followup' or self.due_pass_before is None:
                self.due_pass_before = due
            page = self.discovery.next(limit=100, followup_due_before=self.due_pass_before)
            if self.discovery.after is None:
                self.due_pass_before = None
            return page
        self.due_pass_before = None
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
                self.mark_wakes(first)
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
            self.mark_wakes(first)
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
        # Pace only the periodic sweep (SCA-3120). Targeted wakes and queued rows
        # were handled above; owed rows wait for the next paced discovery.
        interval = projection_followup_discovery_interval_seconds()
        now = _monotonic()
        if interval > 0 and self.last_discovery is not None and now - self.last_discovery < interval:
            OUTCOMES.labels('discovery_paced').inc()
            return
        self.last_discovery = now
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

    def mark_wakes(self, segments):
        now = _monotonic()
        for segment in segments:
            self.wake_marks.setdefault(segment, now)
        while len(self.wake_marks) > MAX_WAKE_MARKS:
            self.wake_marks.pop(next(iter(self.wake_marks)))

    def observe_wake(self, segment):
        marked = self.wake_marks.pop(segment, None)
        if marked is not None:
            TARGETED_START_SECONDS.observe(max(0.0, _monotonic() - marked))

    def launch(self):
        self.launch_targeted()
        while self.pending and len(self.tasks) < projection_followup_slots(MAX_FOLLOWUPS) and not self.closed:
            segment = self.pending.popleft()
            if segment in self.tasks:
                # One task owns a segment's custody accounting; never overwrite it.
                self.prioritized.discard(segment)
                self.wake_marks.pop(segment, None)  # the running attempt absorbs the wake
                continue
            self.observe_wake(segment)
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
                self.wake_marks.pop(segment, None)  # the running attempt absorbs the wake
                continue
            self.observe_wake(segment)
            task = start_background_task(self.run(segment), name='batch_projection_followup')
            self.tasks[segment] = task
            task.add_done_callback(lambda done, sid=segment: self.finished(sid, done, targeted=True))

    def forget_page(self, segment):
        page = self.pages.pop(segment, None)
        if page is not None and page not in self.pages.values():
            self.completion_attempts = {key for key in self.completion_attempts if key[0] != page}
            self.completed_probes.pop(page, None)

    def finished(self, segment, task, *, targeted=False):
        self.tasks.pop(segment, None)
        self.forget_page(segment)
        if segment in self.sibling_requeue and not task.cancelled():
            self.sibling_requeue.discard(segment)
            self.requeue_sibling(segment)
        if task.cancelled():
            # Global background-task shutdown must not replenish a cancelled
            # worker with another task after the shutdown snapshot was taken.
            self.closed = True
            self.pending.clear()
            self.targeted_pending.clear()
            self.owed.clear()
            self.pages.clear()
            self.completion_attempts.clear()
            self.completed_probes.clear()
            self.sibling_claims.clear()
            self.sibling_requeue.clear()
        if targeted:
            self.launch_targeted()
        else:
            self.launch()  # Refill immediately, without another 20s serving sleep.

    @staticmethod
    def privacy_ids(segment, binding, job, entry):
        try:
            return ready_followup_privacy_ids(segment, binding, job, entry)
        except (TypeError, ValueError, KeyError, AttributeError):
            # Malformed or partially migrated hints still take the authoritative path.
            return None

    @staticmethod
    def ready_sibling_key(page, hints):
        """The coalesce key for a hint that the existing path would coalesce, else None.

        Mirrors the legacy test exactly: async projection, the projection and every
        part ``ready``. Malformed hints return None and take the authoritative path.
        """
        try:
            job, entry, binding = hints
            if entry['projection']['state'] != 'ready' or not all(
                part.get('state') == 'ready' for part in (entry.get('projection_parts') or {}).values()
            ):
                return None
            if not ProjectionPolicy.from_dict(job['policy_parts']['projection']).async_projection:
                return None
            hash(binding)
            return (page, binding)
        except (TypeError, ValueError, KeyError, AttributeError):
            return None

    def release_sibling_claim(self, key):
        """End a claim. Siblings that skipped behind a claimant that never reached the
        completion attempt run again on the ordinary path, so none loses its probe."""
        claim = self.sibling_claims.pop(key, None)
        if claim is None:
            return
        claim.ready.set()
        waiting = claim.waiting
        if not waiting or (claim.attempted and key in self.completion_attempts) or self.closed:
            return
        for sibling in waiting:
            if sibling in self.tasks:
                # Its skip is still unwinding; finished() re-queues it.
                self.sibling_requeue.add(sibling)
            else:
                self.requeue_sibling(sibling)

    def requeue_sibling(self, sibling):
        # Already queued (ordinary or targeted recovery) or running: that copy owns
        # the segment's probe. A second queue entry would launch a duplicate task.
        if self.closed or sibling in self.pending or sibling in self.targeted_pending or sibling in self.tasks:
            return
        self.pending.appendleft(sibling)
        self.prioritized.add(sibling)
        OUTCOMES.labels('claimed_sibling_requeued').inc()

    def read_persisted(self, segment, *, prior=None, hints=None):
        store = self.projector.store
        job, entry, binding = hints if hints is not None else store.read(segment)
        ids = self.privacy_ids(segment, binding, job, entry) if prior is not None else None
        if prior is not None and ids is not None:
            proof = prior.get(binding)
            if (
                proof is not None
                and proof.client is store.client
                and ids <= proof.ids
                and time.monotonic() < proof.expires_at
                and matches_live_privacy_version(
                    store.client, binding.owner_id, binding.privacy_generation, proof.version
                )
            ):
                return PersistedFollowup(job, entry, binding, proof, coalesced=True)
        session = store.session(segment, binding, self.projector.clock())
        session.capture_followup_privacy = ids is not None
        try:
            store.check(session)
        except ProjectionReplay:
            # Use the validated transaction snapshot, never the initial fetch hint.
            if session.entry.get('projection'):
                proof = getattr(session, 'followup_privacy_proof', None)
                if proof is not None:
                    verified = self.privacy_ids(segment, binding, session.job, session.entry)
                    if verified is None or not verified <= proof.ids:
                        proof = None
                return PersistedFollowup(session.job, session.entry, binding, proof)
        raise ProjectionBlocked('complete ordered assignment required before follow-up')

    @with_batch_privacy_attempt
    async def run(self, segment, *, track_backoff=True):
        slots = getattr(self.projector, 'outbox_followup_slots', None)
        # During mixed discovery both queues share one process-wide effect
        # budget. Queueing for it does not spend the follow-up attempt clock.
        async with slots if isinstance(slots, asyncio.Semaphore) else nullcontext():
            return await self.run_attempt(segment, track_backoff=track_backoff)

    async def run_attempt(self, segment, *, track_backoff):
        try:
            # Cancel this coordinator, not the drain. The persisted/ready outbox
            # row remains eligible for a later sweep, including a lost reply
            # after a side effect committed. Receipt transactions fence retries.
            async with asyncio.timeout(FOLLOWUP_TIMEOUT_SECONDS):
                outcome = await self._run(segment)
                # Hint persistence shares the attempt's original deadline. A
                # slow DB must not pin a follow-up slot after useful work ended.
                if track_backoff and outcome == 'incomplete' and segment in self.due_clock.entries:
                    deferred = await run_blocking(
                        db_executor, self.due_clock.settle, segment, outcome, projection_followup_backoff_seconds()
                    )
                    if deferred:
                        OUTCOMES.labels('durable_deferred').inc()
        except TimeoutError:
            logger.warning('event=batch_projection_followup outcome=timeout unit=%s', self.unit_key(segment))
            outcome = 'timeout'
        finally:
            self.due_clock.entries.pop(segment, None)
        if track_backoff:
            self.note(segment, outcome)
        else:
            OUTCOMES.labels(outcome).inc()
        return outcome

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
        completed_probe: tuple[int, ProjectionBinding, FollowupPrivacyProof] | None = None
        sibling_key: tuple[int, ProjectionBinding] | None = None
        try:
            acquired = await run_blocking(db_executor, claim.__enter__)
            entered = True
            if not acquired:
                return 'claim_busy'
            page = self.pages.get(segment)
            early = (
                page is not None and projection_followup_page_enabled() and projection_followup_early_coalesce_enabled()
            )
            hints = None
            persisted = None
            if early and page and projection_followup_claimed_sibling_skip_enabled():
                # The same hint read read_persisted would issue; reused below.
                hints = await run_blocking(db_executor, store.read, segment)
                key = self.ready_sibling_key(page, hints)
                if key is not None and self.pages.get(segment) == page:
                    sibling_claim = self.sibling_claims.get(key)
                    if sibling_claim is None:
                        self.sibling_claims[key] = SiblingClaim()
                        sibling_key = key
                    else:
                        # Wait (bounded) for the claimant's live privacy proof, then
                        # verify it exactly as C1 does: this sibling's own privacy ids
                        # must be covered, unexpired, with the live token unchanged.
                        # Any miss returns this run's own full-path result instead.
                        try:
                            await asyncio.wait_for(sibling_claim.ready.wait(), CLAIM_PROOF_WAIT_SECONDS)
                        except TimeoutError:
                            pass
                        proof = sibling_claim.proof
                        if proof is not None and self.pages.get(segment) == page:
                            persisted = await run_blocking(
                                db_executor, self.read_persisted, segment, prior={key[1]: proof}, hints=hints
                            )
                            if persisted.coalesced:
                                live = self.sibling_claims.get(key) is sibling_claim
                                if (
                                    persisted.proof is proof
                                    and (live or key in self.completion_attempts)
                                    and self.pages.get(segment) == page
                                    and time.monotonic() < proof.expires_at
                                    and not self.closed
                                ):
                                    if live:
                                        sibling_claim.waiting.append(segment)
                                    OUTCOMES.labels('claimed_sibling_skipped').inc()
                                    return 'coalesced'
                                persisted = None  # Claim ended without an attempt: take the full path.
            if persisted is not None:
                pass  # This run's own full-path result from the proof check above.
            elif early and page is not None:
                prior = self.completed_probes.get(page, {}).copy()
                persisted = await run_blocking(db_executor, self.read_persisted, segment, prior=prior, hints=hints)
            else:
                persisted = await run_blocking(db_executor, self.read_persisted, segment, hints=hints)
            if sibling_key is not None:
                # Publish this claimant's live proof before its completion attempt.
                own = self.sibling_claims.get(sibling_key)
                if own is not None:
                    if not persisted.coalesced and persisted.proof is not None:
                        own.proof = persisted.proof
                    own.ready.set()
            job, entry, binding = persisted.job, persisted.entry, persisted.binding
            if persisted.coalesced:
                # A recovery wake, page cleanup or shutdown may have invalidated
                # the process-local witness while the token read was in flight.
                if (
                    page is not None
                    and self.pages.get(segment) == page
                    and persisted.proof is not None
                    and self.completed_probes.get(page, {}).get(binding) is persisted.proof
                    and time.monotonic() < persisted.proof.expires_at
                    and not self.closed
                    and projection_followup_page_enabled()
                    and projection_followup_early_coalesce_enabled()
                ):
                    OUTCOMES.labels('early_check_skipped').inc()
                    return 'coalesced'
                persisted = await run_blocking(db_executor, self.read_persisted, segment, hints=(job, entry, binding))
                job, entry, binding = persisted.job, persisted.entry, persisted.binding
            if projection_followup_page_enabled():
                policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                if not policy.async_projection:
                    return 'sync_owned'  # The synchronous sweep owns these receipts.
            self.due_clock.observe(segment, entry)
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
            current_page = self.pages.get(segment, 0)
            key = (current_page, binding)
            coalesce = projection_followup_page_enabled() and was_ready and current_page != 0
            if coalesce:
                if key in self.completion_attempts:
                    return 'coalesced'
                self.completion_attempts.add(key)
                if sibling_key == key and (own := self.sibling_claims.get(key)) is not None:
                    own.attempted = True
            try:
                result = await run_blocking(
                    postprocess_executor,
                    self.projector.complete_content,
                    segment,
                    binding,
                    silence=entry.get('result', {}).get('outcome') == 'silence',
                )
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
            if (
                early
                and page is not None
                and coalesce
                and result is not None
                and result.get('reason_code') is None
                and persisted.proof is not None
                and page == self.pages.get(segment)
                and not self.closed
            ):
                completed_probe = (page, binding, persisted.proof)
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
            if sibling_key is not None:
                # Before the claim exit, so a release failure cannot strand skipped siblings.
                self.release_sibling_claim(sibling_key)
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
                else:
                    if completed_probe is not None:
                        probe_page, binding, proof = completed_probe
                        if probe_page == self.pages.get(segment) and not self.closed:
                            self.completed_probes.setdefault(probe_page, {})[binding] = proof

    async def step(self, segment_id, policy, phase, executor, function, *args, **kwargs):
        with projection_phase(phase, policy, unit_key=segment_id):
            return await run_blocking(executor, function, *args, **kwargs)

    async def finish_part(self, item, binding, receipt, index):
        if receipt['state'] in {'ready', 'quarantined'}:
            return
        policy = await run_blocking(db_executor, self.projector.store.policy, item.segment_id)
        if receipt.get('conversation_id'):
            from utils.sync.bridge import finish_sync_bridges

            outputs = receipt.get('size_rollover_outputs') or [{'conversation_id': receipt['conversation_id']}]
            canonicals = []
            for output in outputs:
                canonical = output['conversation_id']
                if not binding.record_origin:
                    canonical = await self.step(
                        item.segment_id,
                        policy,
                        'bridge',
                        postprocess_executor,
                        finish_sync_bridges,
                        binding.owner_id,
                        canonical,
                        require_python_owner=True,
                        **({'silent': True} if receipt.get('silent_redrive') else {}),
                    )
                if receipt.get('audio_required') and not binding.native_record:
                    if self.projector.playback is not None:
                        await self.step(
                            item.segment_id,
                            policy,
                            'playback',
                            postprocess_executor,
                            self.projector.playback,
                            item,
                            canonical,
                        )
                    else:
                        await self.step(
                            item.segment_id,
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
                            item.segment_id,
                            policy,
                            'bridge',
                            postprocess_executor,
                            finish_sync_bridges,
                            binding.owner_id,
                            canonical,
                            audio_source_id=canonical,
                            require_python_owner=True,
                            **({'silent': True} if receipt.get('silent_redrive') else {}),
                        )
                canonicals.append(canonical)
            canonical = canonicals[0]
            if receipt['enrichment_required']:
                await self.step(
                    item.segment_id,
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

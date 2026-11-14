"""Continuous, fair per-owner projection drains inside one serving process.

The sweep only discovers owners whose chain head it could advance. Each owner
then drains here, in chain order, without sharing a per-sweep walk budget with
every other owner. The result log stays the durable outbox: a drain task is only
a wakeup, and restart, failure or rollback leaves the same pending rows for the
next sweep. Ordering is still the assignment transaction's predecessor fence;
the advisory owner claim, held per step, keeps one walker per owner.
"""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import random
import time
from typing import TYPE_CHECKING

from config.batch_pipeline import (
    max_owner_drains,
    owner_drain_first_turn_seconds,
    projection_drain_claim_aware_enabled,
    projection_drain_live_target_backoff_enabled,
    projection_drain_privacy_backoff_enabled,
    projection_drain_privacy_backoff_seconds,
    serving_projection_sweep_enabled,
)

# Which recurring projection sweep this process runs, set by the serving
# runtime while its loop is alive: 'pump', 'serving' (its sweep still obeys
# BATCH_PIPELINE_SERVING_PROJECTION_SWEEP each tick) or None. A passive owner
# hold is safe only while one of them will re-request the owner.
_recurring_sweep: str | None = None


def set_recurring_sweep(mode: str | None) -> None:
    global _recurring_sweep
    _recurring_sweep = mode


def recurring_sweep_active() -> bool:
    return _recurring_sweep == 'pump' or (_recurring_sweep == 'serving' and serving_projection_sweep_enabled())


from database.batch_pipeline_projection_claim import projection_claim_held
from utils.batch_pipeline.metrics import (
    PROJECTION_DRAIN_CLAIM_HELD,
    PROJECTION_DRAIN_CLAIM_BUSY_BACKOFFS,
    PROJECTION_DRAIN_PRIVACY_BACKOFFS,
    PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS,
    PROJECTION_DRAIN_PRIVACY_ROW_CHANGED,
    record_privacy_stop,
)
from utils.batch_pipeline.scheduler import owner_key
from utils.executors import run_blocking, start_background_task, sync_executor

if TYPE_CHECKING:
    from utils.batch_pipeline.projection import Projector

logger = logging.getLogger(__name__)
# Owners draining at once in one process.
MAX_OWNER_DRAINS = max_owner_drains()
# One owner's turn; with more rows it re-queues behind every waiting owner.
DRAIN_TURN_SECONDS = 120.0
# A newly requested owner's first turn: about one step. An owner with a few fresh rows
# finishes inside it; one with a long chain continues as a backlog owner. 0: one FIFO queue.
FIRST_TURN_SECONDS = float(owner_drain_first_turn_seconds())
# Rounds of new owners (MAX_OWNER_DRAINS each) after which a waiting backlog owner goes first.
BACKLOG_OWED_TURNS = 4
# One blocking step: bounds a sync-pool slot and the owner-claim hold.
DRAIN_STEP_SECONDS = 15.0
MAX_DELAYED_OWNERS = 1024


def is_privacy_stop(stop: str | None) -> bool:
    """Zero-progress privacy stops the drain backs off: a ProjectionBlocked privacy
    disposition ('blocked_privacy_*') or a BatchPrivacyBlocked fence ('privacy_blocked',
    e.g. after the #24747 refusal fall-through re-fences assignment)."""
    return bool(stop) and (stop == 'privacy_blocked' or stop.startswith('blocked_privacy_'))


class OwnerDrains:
    def __init__(self, projector: Projector):
        self.projector = projector
        self.queue: deque[str] = deque()
        # Backlog owners (a productive turn ended with rows left) wait here, behind newly
        # requested owners, and give their slot back at a step boundary when one is waiting.
        self.backlog: deque[str] = deque()
        self.backlog_running: set[str] = set()
        self.yielding: set[str] = set()
        # New owners launched since a backlog owner last was; bounds how long the backlog can wait.
        self.new_since_backlog = 0
        self.tasks: dict[str, asyncio.Task] = {}
        # Owners requested again while draining: one more turn after this one.
        self.again: set[str] = set()
        self.delayed: dict[str, asyncio.TimerHandle] = {}
        # Retained across timer expiry; capped independently of active timers.
        self.live_target_attempts: dict[str, int] = {}
        self.continuations: set[str] = set()
        # Only active admissions/turns write this bounded stop state.
        self.stops: dict[str, str] = {}
        # Active-turn observations, then at most one per capped delayed owner.
        self.stopped_heads: dict[str, tuple[str, object] | None] = {}
        self.privacy_heads: dict[str, tuple[str, object] | None] = {}
        self.closed = False

    def request(self, owners) -> None:
        if self.closed:
            return
        for owner in owners:
            if owner in self.delayed and owner not in self.privacy_heads:
                continue
            if owner in self.tasks:
                self.again.add(owner)
            elif owner not in self.queue and owner not in self.backlog:
                self.queue.append(owner)
        self.launch()

    def classes(self) -> bool:
        return FIRST_TURN_SECONDS > 0

    def next_owner(self) -> str | None:
        """Newly requested owners first. With no backlog owner running, one goes ahead after
        BACKLOG_OWED_TURNS rounds of new owners, so the backlog advances however many arrive."""
        owed = not self.backlog_running and self.new_since_backlog >= BACKLOG_OWED_TURNS * MAX_OWNER_DRAINS
        if self.backlog and (not self.queue or owed):
            owner = self.backlog.popleft()
            self.backlog_running.add(owner)
            self.new_since_backlog = 0
            return owner
        if self.queue:
            self.new_since_backlog += 1
            return self.queue.popleft()
        return None

    def should_yield(self, owner: str) -> bool:
        """A backlog turn ends at this step when newly requested owners wait with no free
        slot: one backlog turn per waiting owner, and never the last one running."""
        if owner not in self.backlog_running or owner in self.yielding:
            return False
        waiting = len(self.queue) - (MAX_OWNER_DRAINS - len(self.tasks)) - len(self.yielding)
        if waiting <= 0 or len(self.backlog_running) - len(self.yielding) <= 1:
            return False
        self.yielding.add(owner)
        return True

    def launch(self) -> None:
        while len(self.tasks) < MAX_OWNER_DRAINS and not self.closed:
            owner = self.next_owner()
            if owner is None:
                break
            self.projector.draining.add(owner)
            continuation = owner in self.continuations
            self.continuations.discard(owner)
            task = start_background_task(
                self.admit_and_run(owner, continuation=continuation), name='batch_projection_owner_drain'
            )
            self.tasks[owner] = task
            task.add_done_callback(lambda done, owner=owner: self.finished(owner, done))

    async def admit_and_run(self, owner: str, *, continuation: bool = False) -> bool:
        if owner in self.privacy_heads:
            if projection_drain_privacy_backoff_enabled():
                unchanged, changed = await run_blocking(sync_executor, self.privacy_head_unchanged, owner)
                if unchanged and owner in self.privacy_heads:
                    self.stops[owner] = 'privacy_unchanged'
                    PROJECTION_DRAIN_PRIVACY_BACKOFFS.inc()
                    return False
                if changed and owner in self.privacy_heads:
                    PROJECTION_DRAIN_PRIVACY_ROW_CHANGED.inc()
            self.privacy_heads.pop(owner, None)
            handle = self.delayed.pop(owner, None)
            if handle is not None:
                handle.cancel()
        # Productive continuations retain FIFO progress without a new admission delay.
        if (
            not continuation
            and projection_drain_claim_aware_enabled()
            and await run_blocking(
                sync_executor, projection_claim_held, self.projector.store.store.namespace, owner_key(owner)
            )
        ):
            PROJECTION_DRAIN_CLAIM_HELD.inc()
            self.stops[owner] = 'claim_held'
            return False
        first = self.classes() and not continuation
        return await self.run(owner, turn_seconds=FIRST_TURN_SECONDS if first else DRAIN_TURN_SECONDS)

    def privacy_head_unchanged(self, owner: str) -> tuple[bool, bool]:
        """One cheap result read; missing version or read failure releases the wake."""
        head = self.privacy_heads.get(owner)
        if head is None or head[1] is None:
            return False, False
        try:
            snapshot = self.projector.store.ref('results', head[0]).get()
            version = snapshot.update_time
            if version is None and snapshot.exists:
                return False, False
            return version == head[1], version != head[1]
        except Exception as error:
            logger.info(
                'event=batch_projection action=privacy_head_check outcome=read_error exception_type=%s',
                type(error).__name__,
            )
            return False, False

    def defer(self, owner: str, *, delay: float | None = None, wake: bool = True) -> bool:
        """Hold ``owner`` out of admission for ``delay`` seconds.

        ``wake=True`` re-requests the owner when the hold expires. ``wake=False``
        only releases the hold: the owner waits for its next ordinary request
        (the sweep), so the hold can never make retries more frequent.
        """
        if owner in self.delayed or self.closed:
            return False
        if len(self.delayed) >= MAX_DELAYED_OWNERS:
            # Return overflow intent to the next serving pass; no extra timers,
            # immediate busy loop, or delay for productive FIFO continuations.
            if wake:
                self.projector.request_drain(owner)
            return False

        handle = None

        def retry():
            if self.delayed.get(owner) is not handle:
                return
            # Privacy can change outside the result row. TTL expiry always
            # releases the version hold for one ordinary drain turn.
            self.privacy_heads.pop(owner, None)
            self.delayed.pop(owner, None)
            if wake and owner not in self.tasks:
                self.request([owner])

        handle = asyncio.get_running_loop().call_later(random.uniform(5.0, 15.0) if delay is None else delay, retry)
        self.delayed[owner] = handle
        return True

    def close(self) -> None:
        self.closed = True
        self.queue.clear()
        self.backlog.clear()
        self.backlog_running.clear()
        self.yielding.clear()
        self.again.clear()
        self.stops.clear()
        self.stopped_heads.clear()
        self.privacy_heads.clear()
        self.live_target_attempts.clear()
        self.continuations.clear()
        for handle in self.delayed.values():
            handle.cancel()
        self.delayed.clear()
        for task in self.tasks.values():
            task.cancel()

    def finished(self, owner: str, task: asyncio.Task) -> None:
        self.tasks.pop(owner, None)
        self.backlog_running.discard(owner)
        self.yielding.discard(owner)
        self.projector.draining.discard(owner)
        if task.cancelled():
            # Global background-task shutdown: do not start another turn.
            self.close()
            return
        stop = self.stops.pop(owner, None)
        head = self.stopped_heads.pop(owner, None)
        if self.closed:
            return
        if stop != 'head_awaiting_live_target':
            self.live_target_attempts.pop(owner, None)
        more = task.exception() is None and task.result() is True
        if more:
            self.continuations.add(owner)
            # Productive turns always continue at a FIFO tail: the backlog's, when it has its own.
            (self.backlog if self.classes() else self.queue).append(owner)
        elif stop == 'privacy_unchanged':
            if owner not in self.privacy_heads:
                # The TTL fired after the check returned but before this callback.
                self.queue.append(owner)
        elif stop and is_privacy_stop(stop) and projection_drain_privacy_backoff_enabled():
            # run records privacy stops here only for zero-progress turns.
            if self.defer(owner, delay=projection_drain_privacy_backoff_seconds()):
                self.privacy_heads[owner] = head
                PROJECTION_DRAIN_PRIVACY_BACKOFFS.inc()
        elif projection_drain_claim_aware_enabled() and stop == 'claim_held':
            self.defer(owner)
        elif (
            stop == 'head_awaiting_live_target'
            and projection_drain_live_target_backoff_enabled()
            and self.defer_live_target(owner)
        ):
            pass
        elif owner in self.again and owner not in self.queue:
            if projection_drain_claim_aware_enabled() and stop == 'claim_busy':
                PROJECTION_DRAIN_CLAIM_BUSY_BACKOFFS.inc()
                self.defer(owner)
            else:
                self.queue.append(owner)
        self.again.discard(owner)
        self.launch()

    def defer_live_target(self, owner: str) -> bool:
        attempt = min(self.live_target_attempts.get(owner, 0) + 1, 5)
        # Passive hold (2026-11-09 readback): an expiry wake re-requested blocked
        # owners every 30-300 s, faster than the sweep that found them before,
        # and doubled owner-chain conflicts. Expiry only re-admits the owner
        # while a recurring sweep runs in this process to re-request it; without
        # one (serving off, sweep switch off, or a one-off reconcile request),
        # the hold keeps its wake so no owner is stranded.
        passive = recurring_sweep_active()
        if not self.defer(owner, delay=min(30 * 2 ** (attempt - 1), 300), wake=not passive):
            return False
        self.live_target_attempts.pop(owner, None)
        if len(self.live_target_attempts) >= MAX_DELAYED_OWNERS:
            self.live_target_attempts.pop(next(iter(self.live_target_attempts)))
        self.live_target_attempts[owner] = attempt
        PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS.inc()
        return True

    async def run(self, owner: str, *, turn_seconds: float = DRAIN_TURN_SECONDS) -> bool:
        """One turn; True when the chain had more rows when the turn ended."""
        started = time.monotonic()
        deadline = started + turn_seconds
        advanced = steps = 0
        more = False
        stop = 'end'
        walk = None
        # One read-ahead per turn, so a step boundary does not discard it.
        prefetch = None
        try:
            prefetch = self.projector.chain_prefetch(owner)
            while True:
                remaining = deadline - time.monotonic()
                if steps and remaining <= 0:
                    more = True
                    stop = 'turn_deadline'
                    break
                # Every turn takes at least one full step.
                budget = min(DRAIN_STEP_SECONDS, remaining) if remaining > 0 else DRAIN_STEP_SECONDS
                walk = await run_blocking(sync_executor, self.projector.drain_step, owner, budget, prefetch=prefetch)
                steps += 1
                advanced += len(walk.advanced)
                stop = walk.stop or 'end'
                if projection_drain_claim_aware_enabled() and stop == 'claim_busy':
                    self.stops[owner] = stop
                if walk.followups:
                    # Owed rows join behind the next follow-up discovery page.
                    self.projector.owe_followups(walk.followups)
                self.projector.schedule_index_flush()
                if not walk.more:
                    break
                if self.should_yield(owner):
                    more = True
                    stop = 'yield'
                    break
        except Exception as error:
            stop = 'error'
            logger.error(
                'event=batch_projection action=owner_drain outcome=error exception_type=%s', type(error).__name__
            )
        finally:
            if prefetch is not None:
                prefetch.close()
        if is_privacy_stop(stop):
            record_privacy_stop(stop)
            if advanced == 0:
                self.stops[owner] = stop
                self.stopped_heads[owner] = walk.blocked_head if walk is not None else None
        if advanced == 0 and stop == 'head_awaiting_live_target':
            self.stops[owner] = stop
        else:
            self.live_target_attempts.pop(owner, None)
        logger.info(
            'event=batch_projection action=owner_drain outcome=turn steps=%d advanced=%d more=%s stop=%s elapsed_ms=%d',
            steps,
            advanced,
            str(more).lower(),
            stop,
            int((time.monotonic() - started) * 1000),
        )
        return more

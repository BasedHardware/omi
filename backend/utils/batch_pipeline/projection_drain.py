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
    projection_drain_claim_aware_enabled,
    projection_drain_privacy_backoff_enabled,
    projection_drain_privacy_backoff_seconds,
)
from database.batch_pipeline_projection_claim import projection_claim_held
from utils.batch_pipeline.metrics import (
    PROJECTION_DRAIN_CLAIM_HELD,
    PROJECTION_DRAIN_CLAIM_BUSY_BACKOFFS,
    PROJECTION_DRAIN_PRIVACY_STOPS,
    PROJECTION_DRAIN_PRIVACY_BACKOFFS,
    PROJECTION_DRAIN_PRIVACY_ROW_CHANGED,
    privacy_stop_reason,
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
# One blocking step: bounds a sync-pool slot and the owner-claim hold.
DRAIN_STEP_SECONDS = 15.0
MAX_DELAYED_OWNERS = 1024


class OwnerDrains:
    def __init__(self, projector: Projector):
        self.projector = projector
        self.queue: deque[str] = deque()
        self.tasks: dict[str, asyncio.Task] = {}
        # Owners requested again while draining: one more turn after this one.
        self.again: set[str] = set()
        self.delayed: dict[str, asyncio.TimerHandle] = {}
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
            elif owner not in self.queue:
                self.queue.append(owner)
        self.launch()

    def launch(self) -> None:
        while self.queue and len(self.tasks) < MAX_OWNER_DRAINS and not self.closed:
            owner = self.queue.popleft()
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
                if unchanged:
                    self.stops[owner] = 'privacy_unchanged'
                    PROJECTION_DRAIN_PRIVACY_BACKOFFS.inc()
                    return False
                if changed:
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
        return await self.run(owner)

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

    def defer(self, owner: str, *, delay: float | None = None) -> bool:
        if owner in self.delayed or self.closed:
            return False
        if len(self.delayed) >= MAX_DELAYED_OWNERS:
            # Return overflow intent to the next serving pass; no extra timers,
            # immediate busy loop, or delay for productive FIFO continuations.
            self.projector.request_drain(owner)
            return False

        handle = None

        def retry():
            nonlocal handle
            if self.delayed.get(owner) is not handle:
                return
            if owner in self.privacy_heads:
                # Keep the slot reserved while queued/checking, so the same
                # cap bounds row-version state as well as timer handles.
                handle = asyncio.get_running_loop().call_later(projection_drain_privacy_backoff_seconds(), retry)
                self.delayed[owner] = handle
            else:
                self.delayed.pop(owner, None)
            self.request([owner])

        handle = asyncio.get_running_loop().call_later(random.uniform(5.0, 15.0) if delay is None else delay, retry)
        self.delayed[owner] = handle
        return True

    def close(self) -> None:
        self.closed = True
        self.queue.clear()
        self.again.clear()
        self.stops.clear()
        self.stopped_heads.clear()
        self.privacy_heads.clear()
        self.continuations.clear()
        for handle in self.delayed.values():
            handle.cancel()
        self.delayed.clear()
        for task in self.tasks.values():
            task.cancel()

    def finished(self, owner: str, task: asyncio.Task) -> None:
        self.tasks.pop(owner, None)
        self.projector.draining.discard(owner)
        if task.cancelled():
            # Global background-task shutdown: do not start another turn.
            self.close()
            return
        stop = self.stops.pop(owner, None)
        head = self.stopped_heads.pop(owner, None)
        if self.closed:
            return
        more = task.exception() is None and task.result() is True
        if more:
            self.continuations.add(owner)
            self.queue.append(owner)  # Productive turns always continue at the FIFO tail.
        elif stop == 'privacy_unchanged':
            pass  # Its timer still guarantees another bounded version check.
        elif stop and stop.startswith('blocked_privacy_') and projection_drain_privacy_backoff_enabled():
            # run records privacy stops here only for zero-progress turns.
            if self.defer(owner, delay=projection_drain_privacy_backoff_seconds()):
                self.privacy_heads[owner] = head
                PROJECTION_DRAIN_PRIVACY_BACKOFFS.inc()
        elif projection_drain_claim_aware_enabled() and stop == 'claim_held':
            self.defer(owner)
        elif owner in self.again and owner not in self.queue:
            if projection_drain_claim_aware_enabled() and stop == 'claim_busy':
                PROJECTION_DRAIN_CLAIM_BUSY_BACKOFFS.inc()
                self.defer(owner)
            else:
                self.queue.append(owner)
        self.again.discard(owner)
        self.launch()

    async def run(self, owner: str) -> bool:
        """One turn; True when the chain had more rows when the turn ended."""
        started = time.monotonic()
        deadline = started + DRAIN_TURN_SECONDS
        advanced = steps = 0
        more = False
        stop = 'end'
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
        except Exception as error:
            stop = 'error'
            logger.error(
                'event=batch_projection action=owner_drain outcome=error exception_type=%s', type(error).__name__
            )
        finally:
            if prefetch is not None:
                prefetch.close()
        if stop == 'privacy_blocked' or stop.startswith('blocked_privacy_'):
            PROJECTION_DRAIN_PRIVACY_STOPS.labels(reason=privacy_stop_reason(stop)).inc()
            if advanced == 0 and stop.startswith('blocked_privacy_'):
                self.stops[owner] = stop
                self.stopped_heads[owner] = walk.blocked_head
        logger.info(
            'event=batch_projection action=owner_drain outcome=turn steps=%d advanced=%d more=%s stop=%s elapsed_ms=%d',
            steps,
            advanced,
            str(more).lower(),
            stop,
            int((time.monotonic() - started) * 1000),
        )
        return more

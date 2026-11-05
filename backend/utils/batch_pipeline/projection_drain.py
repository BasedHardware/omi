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
from typing import TYPE_CHECKING, Callable

from config.batch_pipeline import max_owner_drains, projection_drain_claim_aware_enabled
from database.batch_pipeline_projection_claim import projection_claim_held
from utils.batch_pipeline.metrics import PROJECTION_DRAIN_CLAIM_HELD, PROJECTION_DRAIN_CLAIM_BUSY_BACKOFFS
from utils.batch_pipeline.scheduler import owner_key
from utils.executors import run_blocking, start_background_task, sync_executor

if TYPE_CHECKING:
    from utils.batch_pipeline.projection import Projector

logger = logging.getLogger(__name__)
# Owners draining at once in one process (BATCH_PIPELINE_MAX_OWNER_DRAINS, read at import).
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
        # The last turn's stop token per owner, for the idle hook.
        self.turn_stops: dict[str, str] = {}
        self.closed = False
        # Called as ``on_idle(owner, stop)`` once an owner leaves this drain
        # entirely (no task, queue entry, delay or continuation). Shard pumps
        # settle or cool their wakes here.
        self.on_idle: Callable[[str, str], None] | None = None

    @property
    def limit(self) -> int:
        return MAX_OWNER_DRAINS

    @property
    def free_slots(self) -> int:
        return max(0, self.limit - len(self.tasks) - len(self.queue))

    def busy(self, owner: str) -> bool:
        return owner in self.tasks or owner in self.queue or owner in self.delayed

    def request(self, owners) -> None:
        if self.closed:
            return
        for owner in owners:
            if owner in self.delayed:
                continue
            if owner in self.tasks:
                self.again.add(owner)
            elif owner not in self.queue:
                self.queue.append(owner)
        self.launch()

    def launch(self) -> None:
        while self.queue and len(self.tasks) < self.limit and not self.closed:
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

    def defer(self, owner: str) -> None:
        if owner in self.delayed or self.closed:
            return
        if len(self.delayed) >= MAX_DELAYED_OWNERS:
            # Return overflow intent to the next serving pass; no extra timers,
            # immediate busy loop, or delay for productive FIFO continuations.
            # Local on purpose: the shard router would push to Redis on the loop.
            getattr(self.projector, 'request_local_drain', self.projector.request_drain)(owner)
            return

        def retry():
            self.delayed.pop(owner, None)
            self.request([owner])

        self.delayed[owner] = asyncio.get_running_loop().call_later(random.uniform(5.0, 15.0), retry)

    def close(self) -> None:
        self.closed = True
        self.queue.clear()
        self.again.clear()
        self.stops.clear()
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
        if self.closed:
            return
        more = task.exception() is None and task.result() is True
        if more:
            self.continuations.add(owner)
            self.queue.append(owner)  # Productive turns always continue at the FIFO tail.
        elif projection_drain_claim_aware_enabled() and stop == 'claim_held':
            self.defer(owner)
        elif owner in self.again and owner not in self.queue:
            if projection_drain_claim_aware_enabled() and stop == 'claim_busy':
                PROJECTION_DRAIN_CLAIM_BUSY_BACKOFFS.inc()
                self.defer(owner)
            else:
                self.queue.append(owner)
        self.again.discard(owner)
        last = self.turn_stops.pop(owner, None)
        if task.exception() is not None:
            last = 'error'
        if self.on_idle is not None and not self.busy(owner):
            try:
                # Only a turn that walked to the chain end reports 'end'.
                self.on_idle(owner, stop or last or 'unknown')
            except Exception as error:
                logger.warning(
                    'event=batch_projection action=owner_drain_idle outcome=error exception_type=%s',
                    type(error).__name__,
                )
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
        self.turn_stops[owner] = stop
        logger.info(
            'event=batch_projection action=owner_drain outcome=turn steps=%d advanced=%d more=%s stop=%s elapsed_ms=%d',
            steps,
            advanced,
            str(more).lower(),
            stop,
            int((time.monotonic() - started) * 1000),
        )
        return more

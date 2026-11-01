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
import time
from typing import TYPE_CHECKING

from utils.executors import run_blocking, start_background_task, sync_executor

if TYPE_CHECKING:
    from utils.batch_pipeline.projection import Projector

logger = logging.getLogger(__name__)
# Owners draining at once in one process.
MAX_OWNER_DRAINS = 8
# One owner's turn; with more rows it re-queues behind every waiting owner.
DRAIN_TURN_SECONDS = 120.0
# One blocking step: bounds a sync-pool slot and the owner-claim hold.
DRAIN_STEP_SECONDS = 15.0


class OwnerDrains:
    def __init__(self, projector: Projector):
        self.projector = projector
        self.queue: deque[str] = deque()
        self.tasks: dict[str, asyncio.Task] = {}
        # Owners requested again while draining: one more turn after this one.
        self.again: set[str] = set()
        self.closed = False

    def request(self, owners) -> None:
        for owner in owners:
            if owner in self.tasks:
                self.again.add(owner)
            elif owner not in self.queue:
                self.queue.append(owner)
        self.launch()

    def launch(self) -> None:
        while self.queue and len(self.tasks) < MAX_OWNER_DRAINS and not self.closed:
            owner = self.queue.popleft()
            self.projector.draining.add(owner)
            task = start_background_task(self.run(owner), name='batch_projection_owner_drain')
            self.tasks[owner] = task
            task.add_done_callback(lambda done, owner=owner: self.finished(owner, done))

    def finished(self, owner: str, task: asyncio.Task) -> None:
        self.tasks.pop(owner, None)
        self.projector.draining.discard(owner)
        if task.cancelled():
            # Global background-task shutdown: do not start another turn.
            self.closed = True
            self.queue.clear()
            self.again.clear()
            return
        more = task.exception() is None and task.result() is True
        if (more or owner in self.again) and owner not in self.queue:
            self.queue.append(owner)  # FIFO: behind every owner already waiting
        self.again.discard(owner)
        self.launch()

    async def run(self, owner: str) -> bool:
        """One turn; True when the chain had more rows when the turn ended."""
        started = time.monotonic()
        deadline = started + DRAIN_TURN_SECONDS
        advanced = steps = 0
        more = False
        # One read-ahead per turn, so a step boundary does not discard it.
        prefetch = None
        try:
            prefetch = self.projector.chain_prefetch(owner)
            while True:
                remaining = deadline - time.monotonic()
                if steps and remaining <= 0:
                    more = True
                    break
                # Every turn takes at least one full step.
                budget = min(DRAIN_STEP_SECONDS, remaining) if remaining > 0 else DRAIN_STEP_SECONDS
                walk = await run_blocking(sync_executor, self.projector.drain_step, owner, budget, prefetch=prefetch)
                steps += 1
                advanced += len(walk.advanced)
                if walk.followups:
                    # Owed rows join behind the next follow-up discovery page.
                    self.projector.owe_followups(walk.followups)
                self.projector.schedule_index_flush()
                if not walk.more:
                    break
        except Exception as error:
            logger.error(
                'event=batch_projection action=owner_drain outcome=error exception_type=%s', type(error).__name__
            )
        finally:
            if prefetch is not None:
                prefetch.close()
        logger.info(
            'event=batch_projection action=owner_drain outcome=turn steps=%d advanced=%d more=%s elapsed_ms=%d',
            steps,
            advanced,
            str(more).lower(),
            int((time.monotonic() - started) * 1000),
        )
        return more

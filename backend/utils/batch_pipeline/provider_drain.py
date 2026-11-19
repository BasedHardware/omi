"""Coalesced owner merge wakes for settled provider-STT units.

A provider unit settles in its own delivery, outside the GPU pump, so nothing told the ordered
merge that the owner had a ready row: only the 100-row maintenance page found it, and two owners
could fill that page (2026-11-13). This is the provider route's equivalent of the pump's
drain-after-publication.

One task per owner per process. Every request that arrives while the task lives folds into it:
a burst of settles for one owner costs two drains, not one per unit. Each round drains once after
``delay`` (strict order, fresh-first) and once more after the merge's head wait, when rows that
were ready behind an unready head become committable. A request during a round schedules exactly
one further round.

Past ``max_owners`` live tasks a request is not dropped: the owner waits in arrival order and
starts when a task ends, so an owner's only settle still gets its drain.

The wake is a hint held in memory. A lost task (instance stop) delays that owner until its next
settle or the maintenance page, as before this module existed; the job rows stay the only state.
"""

import asyncio
import logging
from typing import Awaitable, Callable

from utils.executors import start_background_task

logger = logging.getLogger(__name__)

# Settles of one upload arrive together; wait this long so one drain serves them.
DRAIN_DELAY_SECONDS = 2.0
# Added to the head wait so the waited row is past it when the second drain runs.
HEAD_WAIT_MARGIN_SECONDS = 2.0
# Owners with a live wake task. Past this an owner waits its turn (owner ids only, in memory).
MAX_OWNERS = 4096
TASK_NAME = 'provider_owner_drain'
# Drains running at once in this process; each is an owner's bounded merge loop.
DRAIN_CONCURRENCY = 4


class OwnerDrainCoalescer:
    def __init__(
        self,
        drain: Callable[[str], Awaitable[None]],
        *,
        head_wait: Callable[[], float],
        delay: float = DRAIN_DELAY_SECONDS,
        max_owners: int = MAX_OWNERS,
        concurrency: int = DRAIN_CONCURRENCY,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._drain = drain
        self._head_wait = head_wait
        self._delay = delay
        self._max_owners = max_owners
        self._concurrency = concurrency
        self._sleep = sleep
        self._tasks: dict[str, asyncio.Task] = {}
        self._again: set[str] = set()
        # Owners past the task bound, in arrival order (a dict keeps order and dedupes).
        self._waiting: dict[str, None] = {}
        self._gate: asyncio.Semaphore | None = None

    def pending(self) -> int:
        return len(self._tasks) + len(self._waiting)

    def request(self, owner_id: str) -> bool:
        """Ask for one drain of ``owner_id``. Must be called on the event loop. Returns False
        when the owner had to queue behind the task bound (it still drains, later)."""
        if owner_id in self._tasks:
            self._again.add(owner_id)
            return True
        if len(self._tasks) >= self._max_owners:
            if owner_id not in self._waiting:
                self._waiting[owner_id] = None
                logger.warning('event=batch_provider_drain outcome=queued reason=owner_bound count=1')
            return False
        self._start(owner_id)
        return True

    def _start(self, owner_id: str) -> None:
        # Tracked: shutdown cancels it with the other background tasks, and a failure is logged.
        self._tasks[owner_id] = start_background_task(self._run(owner_id), name=TASK_NAME)

    async def _once(self, owner_id: str) -> None:
        if self._gate is None:
            self._gate = asyncio.Semaphore(self._concurrency)
        async with self._gate:
            try:
                await self._drain(owner_id)
            except Exception as error:
                # The rows stay result_ready; the next round, settle or maintenance pass retries.
                logger.warning('event=batch_provider_drain outcome=retry exception_type=%s', type(error).__name__)

    async def _run(self, owner_id: str) -> None:
        try:
            while True:
                self._again.discard(owner_id)
                await self._sleep(self._delay)
                await self._once(owner_id)
                wait = self._head_wait()
                if wait > 0:
                    await self._sleep(wait + HEAD_WAIT_MARGIN_SECONDS)
                    await self._once(owner_id)
                if owner_id not in self._again:
                    return
        finally:
            # No await between the check above and this removal: a request either saw the task
            # and set ``_again`` before the check, or finds no task and starts a new one.
            self._again.discard(owner_id)
            self._tasks.pop(owner_id, None)
            if self._waiting and len(self._tasks) < self._max_owners:
                waiter = next(iter(self._waiting))
                del self._waiting[waiter]
                self._start(waiter)

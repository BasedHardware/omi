"""Small, explicitly named models of runtime pieces the simulation cannot run for real.

Each model cites the production code it mirrors. Nothing here is imported by
product code.
"""

from __future__ import annotations

import asyncio
import collections
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from testing.pipeline_sim.stt import _Slots

# Revision-drain classification. Mirrors the vocabulary of the (unmerged)
# lane/opus-drain-harness fixture backend/tests/unit/fixtures/revision_drain.py,
# which is absent on this branch; this is a minimal equivalent for virtual time.
REQUEST_SCOPED = 'request_scoped'
FIRE_AND_FORGET = 'fire_and_forget'
COMPLETED = 'completed'
KILLED = 'killed'
RUNNING = 'running'
STOPPED_AT_HORIZON = 'stopped_at_horizon'


class ExecutorModel:
    """MODEL of a ``utils.executors`` ThreadPoolExecutor (e.g. ``sync_executor``, 16 workers).

    A call holds one worker for its whole service time, including time spent
    blocked on a provider (``run_blocking`` keeps the thread for the duration of
    the leaf call). Queueing is FIFO.
    """

    def __init__(self, name: str, workers: int, clock):
        self.name = name
        self.workers = workers
        self.clock = clock
        self.slots = _Slots(workers)
        self.max_queue = 0
        self.calls = collections.Counter()
        self.waits: dict[str, list[float]] = collections.defaultdict(list)

    async def run(self, label: str, work: Callable[[], Awaitable[Any]] | float) -> Any:
        self.max_queue = max(self.max_queue, len(self.slots.waiters) + (self.slots.in_use >= self.workers))
        queued_at = self.clock.now
        await self.slots.acquire(None)
        self.waits[label].append(self.clock.now - queued_at)
        self.calls[label] += 1
        try:
            if callable(work):
                return await work()
            await asyncio.sleep(work)
            return None
        finally:
            self.slots.release()


@dataclass
class WorkUnit:
    label: str
    scope: str
    revision: int
    task: asyncio.Task | None = None
    outcome: str = RUNNING


@dataclass
class DrainReport:
    replaced_at: float | None = None
    units: list[WorkUnit] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        result = collections.Counter(f'{unit.scope}:{unit.outcome}' for unit in self.units)
        return dict(sorted(result.items()))

    @property
    def lost(self) -> list[WorkUnit]:
        return [unit for unit in self.units if unit.scope == FIRE_AND_FORGET and unit.outcome == KILLED]


class RevisionModel:
    """MODEL of Cloud Run revision replacement for the CPU service.

    A request is protected while it is in flight: on replacement the old
    revision stops admitting new requests, in-flight requests drain (bounded by
    ``request_timeout``), then the instance gets SIGTERM, ``grace_seconds``,
    and SIGKILL. Work started with ``start_background_task`` / ``create_task``
    (``spawn``) is not protected and is killed if still running at SIGKILL.
    """

    def __init__(self, clock, *, request_timeout: float = 3600.0, grace_seconds: float = 10.0):
        self.clock = clock
        self.request_timeout = request_timeout
        self.grace_seconds = grace_seconds
        self.generation = 0
        self.report = DrainReport()

    def _track(self, label: str, scope: str, coro: Awaitable[Any]) -> WorkUnit:
        unit = WorkUnit(label, scope, self.generation)

        async def body():
            try:
                result = await coro
            except asyncio.CancelledError:
                if unit.outcome == RUNNING:
                    unit.outcome = STOPPED_AT_HORIZON  # cancelled when the simulation ended
                raise
            unit.outcome = COMPLETED
            return result

        unit.task = asyncio.get_running_loop().create_task(body(), name=label)
        self.report.units.append(unit)
        return unit

    async def request(self, label: str, coro: Awaitable[Any]) -> Any:
        """An awaited request handler (Cloud Tasks delivery or HTTP call)."""
        unit = self._track(label, REQUEST_SCOPED, coro)
        return await asyncio.shield(unit.task)

    def spawn(self, label: str, coro: Awaitable[Any]) -> WorkUnit:
        """``start_background_task``: outlives its request, unprotected by the drain."""
        return self._track(label, FIRE_AND_FORGET, coro)

    async def replace(self) -> None:
        old = self.generation
        self.generation += 1
        self.report.replaced_at = self.clock.now
        in_flight = [
            u for u in self.report.units if u.revision == old and u.scope == REQUEST_SCOPED and u.outcome == RUNNING
        ]
        if in_flight:
            await asyncio.wait([u.task for u in in_flight], timeout=self.request_timeout)
        await asyncio.sleep(self.grace_seconds)  # SIGTERM -> grace -> SIGKILL
        for unit in self.report.units:
            if unit.revision == old and unit.outcome == RUNNING and unit.task is not None:
                unit.outcome = KILLED
                unit.task.cancel()
        await asyncio.sleep(0)


@dataclass
class SequencerStats:
    dispatches: int = 0
    max_active_per_owner: int = 0
    max_pending_per_owner: int = 0


class SequencerModel:
    """MODEL of ``utils/sync/uid_sequencer.py`` + ``database/sync_backfill_sequencer.py``.

    Production keeps ONE active backfill job per UID: ``claim_next`` refuses
    while ``active_job_id`` is set, and the next job is only kicked after
    ``finish_job`` releases the owner at the end of the Cloud Tasks request
    (routers/sync.py). ``per_owner_concurrency`` > 1 is a hypothetical knob for
    comparison; 1 is production. A dispatch costs one Cloud Tasks hop. Jobs are
    claimed oldest capture first (``_first_pending``).
    """

    def __init__(
        self,
        clock,
        run_job: Callable[[Any], Awaitable[Any]],
        *,
        per_owner_concurrency: int = 1,
        dispatch_seconds: float = 1.5,
    ):
        if per_owner_concurrency < 1:
            raise ValueError('per-owner concurrency must be positive')
        self.clock = clock
        self.run_job = run_job
        self.k = per_owner_concurrency
        self.dispatch_seconds = dispatch_seconds
        self.pending: dict[str, list] = collections.defaultdict(list)
        self.active: collections.Counter = collections.Counter()
        self.stats = SequencerStats()
        self.tasks: list[asyncio.Task] = []

    def register(self, owner: str, job: Any, capture_at: float) -> None:
        self.pending[owner].append((capture_at, job))
        self.pending[owner].sort(key=lambda entry: entry[0])
        self.stats.max_pending_per_owner = max(self.stats.max_pending_per_owner, len(self.pending[owner]))
        self.kick(owner)

    def kick(self, owner: str) -> None:
        loop = asyncio.get_running_loop()
        while self.active[owner] < self.k and self.pending[owner]:
            _, job = self.pending[owner].pop(0)
            self.active[owner] += 1
            self.stats.dispatches += 1
            self.stats.max_active_per_owner = max(self.stats.max_active_per_owner, self.active[owner])
            self.tasks.append(loop.create_task(self._deliver(owner, job)))

    async def _deliver(self, owner: str, job: Any) -> None:
        try:
            await asyncio.sleep(self.dispatch_seconds)  # enqueue_sync_job -> Cloud Tasks -> /v2/sync-jobs/run
            await self.run_job(job)
        finally:
            self.active[owner] -= 1  # finish_job releases the UID, then kick() the next head
            self.kick(owner)

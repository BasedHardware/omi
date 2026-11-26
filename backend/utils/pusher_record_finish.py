"""Bounded process ownership of closed sockets' durable projection drains."""

import asyncio
import logging
import os
from collections import Counter, OrderedDict
from functools import lru_cache
from dataclasses import dataclass
from weakref import WeakSet
from typing import Any, Callable

from config.pusher_record import abandon_record_drain_cap
from utils.executors import start_background_task
from utils.other.audio_outbox import AudioProjection

logger = logging.getLogger(__name__)


def closed_record_drain_cap() -> int:
    try:
        value = int(os.getenv('PUSHER_MAX_CLOSED_RECORD_DRAINS', '32'))
    except ValueError:
        value = 32
    return max(8, min(128, value))


MAX_CLOSED_RECORD_DRAINS = closed_record_drain_cap()
_closed_record_drains: set[asyncio.Task] = set()
MAX_ABANDON_RECORD_DRAINS = abandon_record_drain_cap()
_abandon_record_drains: set[asyncio.Task] = set()


@lru_cache(maxsize=1)
def log_closed_record_drain_cap() -> None:
    logger.info('event=record_closed_finish_cap value=%s', MAX_CLOSED_RECORD_DRAINS)
    logger.info('event=record_abandon_cap value=%s', MAX_ABANDON_RECORD_DRAINS)


PREPARED_ABANDON_DEADLINE_SECONDS = 30.0


# A listen-pod scale-down can close many sockets on one pusher. Eight times
# the normal 32-drain budget absorbs a 256-socket burst without more I/O slots.
MAX_QUEUED_ABANDON_RECORD_DRAINS = 256
ABANDON_QUEUE_DEADLINE_SECONDS = 60.0
_abandon_by_worker: dict[asyncio.Task, "_AbandonEntry"] = {}
_abandon_queue: OrderedDict[asyncio.Task, "_AbandonEntry"] = OrderedDict()
_abandon_completed: WeakSet = WeakSet()


@dataclass
class _AbandonEntry:
    worker: asyncio.Task
    barrier: Any
    futures: Any
    prepared: set[str] | None
    expiry: asyncio.TimerHandle | None = None
    revision: int = 0


def _start_abandon(entry):
    if entry.expiry is not None:
        entry.expiry.cancel()
        entry.expiry = None

    async def abandon():
        try:
            async with asyncio.timeout(PREPARED_ABANDON_DEADLINE_SECONDS):
                await asyncio.wait([entry.worker])  # Never cancel the source.
                try:
                    entry.worker.exception()
                except asyncio.CancelledError:
                    pass
                await entry.futures.wait()
                while True:
                    revision = entry.revision
                    if entry.prepared is None:
                        await entry.barrier.abandon_recordings()
                    else:
                        await entry.barrier.abandon_recordings(set(entry.prepared))
                    if entry.revision == revision:
                        _abandon_completed.add(entry.worker)
                        break
        except TimeoutError:
            logger.warning('event=record_closed_finish outcome=prepared_unsettled')

    owner = start_background_task(abandon(), name='pusher:abandon_evicted_record_tokens')
    _abandon_record_drains.add(owner)

    def finished(done):
        _abandon_record_drains.discard(done)
        _abandon_by_worker.pop(entry.worker, None)
        if done.cancelled():
            # Process shutdown snapshots the tracked task set once. Starting
            # queued owners here would escape that cancellation snapshot.
            for worker, waiting in _abandon_queue.items():
                if waiting.expiry is not None:
                    waiting.expiry.cancel()
                _abandon_by_worker.pop(worker, None)
            _abandon_queue.clear()
            logger.info('event=record_closed_finish outcome=abandon_queue_cancelled')
            return  # Workers/futures and producer fences remain untouched.
        # FIFO admission is synchronous: no duplicate owner can take this slot.
        while _abandon_queue and len(_abandon_record_drains) < MAX_ABANDON_RECORD_DRAINS:
            _, waiting = _abandon_queue.popitem(last=False)
            _start_abandon(waiting)

    owner.add_done_callback(finished)


def abandon_evicted_record_drain(task, barrier, futures, *, prepared: set[str] | None = None) -> bool:
    """One owner per ended worker; bounded FIFO overflow keeps producer fences."""
    if prepared is None:
        barrier.forget_evicted_tokens()
    else:
        barrier.forget_evicted_tokens(prepared)
    if task in _abandon_completed:
        return True
    if task in _abandon_by_worker:
        entry = _abandon_by_worker[task]
        if prepared is None:
            entry.prepared = None  # Eviction's all-token scope dominates EOF.
        elif entry.prepared is not None:
            entry.prepared.update(prepared)
        entry.revision += 1
        return True
    if MAX_ABANDON_RECORD_DRAINS <= 0 or (
        len(_abandon_record_drains) >= MAX_ABANDON_RECORD_DRAINS
        and len(_abandon_queue) >= MAX_QUEUED_ABANDON_RECORD_DRAINS
    ):
        logger.warning('event=record_closed_finish outcome=abandon_overflow')
        return False
    entry = _AbandonEntry(task, barrier, futures, None if prepared is None else set(prepared))
    _abandon_by_worker[task] = entry
    if len(_abandon_record_drains) < MAX_ABANDON_RECORD_DRAINS:
        _start_abandon(entry)
    else:
        _abandon_queue[task] = entry

        def expired():
            _abandon_queue.pop(task, None)
            _abandon_by_worker.pop(task, None)
            logger.warning('event=record_closed_finish outcome=abandon_queue_expired')

        entry.expiry = asyncio.get_running_loop().call_later(ABANDON_QUEUE_DEADLINE_SECONDS, expired)
        logger.info('event=record_closed_finish outcome=abandon_queued')
    return True


class ProjectionQueueWaitTimeout(TimeoutError):
    """Capacity expired; the committed slot still belongs to the drain worker."""


class RecordProjectionQueue(asyncio.Queue[AudioProjection]):
    """Track queued work per conversation without inspecting Queue internals."""

    def __init__(self, maxsize: int):
        super().__init__(maxsize=maxsize)
        self.conversations: Counter[str] = Counter()
        # One producer, one committed reference. It never holds a PCM copy and
        # remains part of drain proof if its capacity waiter times out/cancels.
        self.pending_projection: AudioProjection | None = None
        self._pending_delivered = asyncio.Event()
        self.capacity_wait_active = False

    def stage_committed(self, item: AudioProjection) -> None:
        if self.pending_projection is not None:
            raise RuntimeError('committed projection slot already occupied')
        self.pending_projection = item
        self._pending_delivered.clear()

    def promote_pending(self) -> None:
        if self.pending_projection is not None and not self.full():
            self.put_nowait(self.pending_projection)
            self.pending_projection = None
            self._pending_delivered.set()

    async def deliver_pending(self, *, timeout: float | None) -> None:
        self.promote_pending()
        self.capacity_wait_active = True
        try:
            # This deadline covers capacity only. No storage call is cancelled,
            # and timeout/cancellation leaves the reference with the worker.
            async with asyncio.timeout(timeout):
                await self._pending_delivered.wait()
        except TimeoutError as exc:
            raise ProjectionQueueWaitTimeout from exc
        finally:
            self.capacity_wait_active = False

    def put_nowait(self, item: AudioProjection) -> None:
        super().put_nowait(item)
        if item.conversation_id is not None:
            self.conversations[item.conversation_id] += 1

    def get_nowait(self) -> AudioProjection:
        item = super().get_nowait()
        cid = item.conversation_id
        if cid is not None:
            self.conversations[cid] -= 1
            if not self.conversations[cid]:
                del self.conversations[cid]
        # The capacity release and slot transfer are atomic on this event loop.
        # Append at the tail, preserving capture order behind queued receipts.
        self.promote_pending()
        return item

    def has_conversation(self, cid: str) -> bool:
        return bool(self.conversations.get(cid)) or (
            self.pending_projection is not None and self.pending_projection.conversation_id == cid
        )


def retain_closed_record_drain(task: asyncio.Task, *, on_capacity: Callable[[], object] | None = None) -> bool:
    """Transfer an existing worker, never restart or certify its unfinished work.

    At capacity the caller retains ownership and cancels as before. The optional
    abandonment coordinator attests stoppage only after executor settlement;
    immutable receipts and the token remain for repair's tail proof. Shutdown cancels
    the tracked owner and its worker; process death is still the repair proof.
    Only a closed outcome enum is logged, never exception text or task names.
    """
    if task.done():
        return False
    if len(_closed_record_drains) >= MAX_CLOSED_RECORD_DRAINS:
        logger.warning('event=record_closed_finish outcome=capacity')
        if on_capacity is not None and os.getenv('PUSHER_ABANDON_EVICTED_TOKENS', 'on').strip().lower() != 'off':
            on_capacity()
        return False
    _closed_record_drains.add(task)

    async def finish() -> None:
        outcome = 'completed'
        try:
            await task
        except asyncio.CancelledError:
            outcome = 'cancelled'
            raise
        except Exception:
            outcome = 'failed'
        finally:
            _closed_record_drains.discard(task)
            logger.info('event=record_closed_finish outcome=%s', outcome)

    owner = start_background_task(finish(), name='pusher:closed_record_finish')

    def owner_done(done: asyncio.Task) -> None:
        # Cancellation before the coordinator's first instruction must still
        # reach the existing worker (its coroutine finally has not run yet).
        if done.cancelled() and not task.done():
            task.cancel()
        if task.done():
            _closed_record_drains.discard(task)

    owner.add_done_callback(owner_done)
    task.add_done_callback(_closed_record_drains.discard)
    logger.info('event=record_closed_finish outcome=retained')
    return True

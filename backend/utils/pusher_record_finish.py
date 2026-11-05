"""Bounded process ownership of closed sockets' durable projection drains."""

import asyncio
import logging
import os
from collections import Counter
from functools import lru_cache
from typing import Callable

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


def abandon_evicted_record_drain(task, barrier, futures) -> bool:
    """A small metadata coordinator; never restart the evicted projection."""
    # Even refusal must fence local reconnect recovery while late I/O settles.
    # This removes only a hint; the durable producer token remains unchanged.
    barrier.forget_evicted_tokens()
    if len(_abandon_record_drains) >= MAX_ABANDON_RECORD_DRAINS:
        logger.warning('event=record_closed_finish outcome=abandon_overflow')
        return False  # No coordinator or abandon write; retain the producer fence.

    async def abandon(worker):
        await asyncio.wait([worker])  # Settlement, not cancellation, is the proof.
        try:
            worker.exception()  # Release a cancellation traceback's upload locals.
        except asyncio.CancelledError:
            pass
        del worker  # Metadata retries must not retain a settled socket/PCM frame.
        await futures.wait()
        await barrier.abandon_recordings()

    owner = start_background_task(abandon(task), name='pusher:abandon_evicted_record_tokens')
    _abandon_record_drains.add(owner)
    owner.add_done_callback(_abandon_record_drains.discard)
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

"""Lightweight sink registry shared by listen and pusher shutdown paths."""

import asyncio
import logging
import weakref
from typing import Any

logger = logging.getLogger(__name__)
ACTIVE: weakref.WeakSet[Any] = weakref.WeakSet()
CLOSING: set[asyncio.Task[Any]] = set()
SHUTDOWN_DELIVERY_SECONDS = 28.0


async def flush_active(*, timeout: float = 30.0) -> None:
    """Both listen and pusher lifespans flush tails before shared IO teardown."""

    async def close(hold: Any) -> None:
        try:
            await hold.close()
            ACTIVE.discard(hold)
        except Exception as error:
            logger.error(
                'event=stt_cap_live_held outcome=shutdown_flush_failed exception_type=%s', type(error).__name__
            )

    tasks = [asyncio.create_task(close(hold), name='cap_hold_shutdown') for hold in list(ACTIVE)]
    for task in tasks:
        CLOSING.add(task)
        task.add_done_callback(CLOSING.discard)
        task.add_done_callback(observe_publication)
    if not tasks:
        return
    _, pending = await asyncio.wait(tasks, timeout=min(timeout, SHUTDOWN_DELIVERY_SECONDS))
    for task in pending:
        task.cancel()
    # Do not gather cancellation-resistant sinks here. Retained tasks observe
    # completion; shielded publication owns its lock/scratch until IO finishes.
    # Process termination can still lose the <=15s not yet durably staged.
    if pending:
        logger.error('event=stt_cap_live_held outcome=shutdown_flush_timeout sinks=%s', len(pending))


def observe_publication(task: asyncio.Task[Any]) -> None:
    """Observe a sink-owned publication even when its socket owner was cancelled."""
    if not task.cancelled() and (error := task.exception()) is not None:
        logger.error('event=stt_cap_live_held outcome=publication_failed exception_type=%s', type(error).__name__)

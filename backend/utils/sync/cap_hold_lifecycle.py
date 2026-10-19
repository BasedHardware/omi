"""Lightweight sink registry shared by listen and pusher shutdown paths."""

import asyncio
import logging
import weakref
from typing import Any

logger = logging.getLogger(__name__)
ACTIVE: weakref.WeakSet[Any] = weakref.WeakSet()


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
    if not tasks:
        return
    _, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in pending:
        task.cancel()
    # Observe every completion, including cancellation. Buffered PCM remains
    # bounded; durable staging rows are sealed by the scheduler after expiry.
    await asyncio.gather(*tasks, return_exceptions=True)
    if pending:
        logger.error('event=stt_cap_live_held outcome=shutdown_flush_timeout sinks=%s', len(pending))


def observe_publication(task: asyncio.Task[Any]) -> None:
    """Observe a sink-owned publication even when its socket owner was cancelled."""
    if not task.cancelled() and (error := task.exception()) is not None:
        logger.error('event=stt_cap_live_held outcome=publication_failed exception_type=%s', type(error).__name__)

import asyncio
import logging

logger = logging.getLogger(__name__)


def safe_create_task(t):
    task = asyncio.create_task(t)
    task.add_done_callback(
        lambda l: logger.error(f"Unhandled exception in background task: {l.exception()}") if l.exception() else None
    )
    return task

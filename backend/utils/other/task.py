import asyncio
import logging
from typing import Any, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def safe_create_task(t: Coroutine[Any, Any, T]) -> "asyncio.Task[T]":
    task = asyncio.create_task(t)
    task.add_done_callback(
        lambda l: logger.error(f"Unhandled exception in background task: {l.exception()}") if l.exception() else None
    )
    return task

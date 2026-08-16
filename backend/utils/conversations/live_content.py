"""Recover a fenced live-content write by moving once to a fresh generation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

ContentWrite = TypeVar('ContentWrite')


async def retry_fenced_live_content_once(
    *,
    write_current: Callable[[], ContentWrite | None],
    rollover: Callable[[], Awaitable[None]],
    write_fresh: Callable[[], ContentWrite | None],
) -> tuple[ContentWrite | None, bool]:
    """Write content once, rolling over only when cleanup fenced that write.

    A missing parent is a terminal durable outcome for its recording session;
    recreating that parent would violate the lifecycle fence.  The caller must
    instead open a fresh session/conversation generation and replay its still
    buffered content exactly once.
    """
    current_result = write_current()
    if current_result is not None:
        return current_result, False

    await rollover()
    return write_fresh(), True

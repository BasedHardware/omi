"""A request-scoped wall-clock deadline for the synchronous from-segments ingest.

The route must answer a retryable error inside the client's own 30 s HTTP pool
deadline instead of holding the request for the notes agent's full recovery
budget (agentic 120 s, then one-shot 180 s). The route sets the deadline; the
auth dependency checks it between steps and the notes step caps its own
deadlines to whatever remains. Unset — every other caller — changes nothing.

The deadline is a contextvar, so it reaches the synchronous auth dependency and
the handler through the threadpool context copy FastAPI makes for each, and the
``asyncio.run`` the notes step opens copies it again.
"""

from __future__ import annotations

import contextvars
import time
from typing import AsyncIterator

# The client's own HTTP pool gives up at 30 s per attempt; answering a retryable
# error before that is what makes the retry useful. Leave headroom for response
# serialization and the middleware.
FROM_SEGMENTS_REQUEST_BUDGET_SECONDS = 25.0
# A spent budget must still produce a deadline the notes loop accepts (> 0).
MINIMUM_DEADLINE_SECONDS = 0.05

_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar('omi_request_deadline_monotonic', default=None)


def set_request_deadline(seconds: float) -> contextvars.Token:
    return _deadline.set(time.monotonic() + max(0.0, seconds))


def reset_request_deadline(token: contextvars.Token) -> None:
    _deadline.reset(token)


def request_deadline_remaining_seconds() -> float | None:
    """Seconds left in the request budget, or ``None`` when no budget is set."""
    deadline = _deadline.get()
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


def request_deadline_exceeded() -> bool:
    remaining = request_deadline_remaining_seconds()
    return remaining is not None and remaining <= 0.0


def capped_deadline_seconds(deadline_seconds: float) -> float:
    """Cap *deadline_seconds* to the request budget; unchanged when unset."""
    remaining = request_deadline_remaining_seconds()
    if remaining is None:
        return deadline_seconds
    return max(MINIMUM_DEADLINE_SECONDS, min(deadline_seconds, remaining))


async def from_segments_request_deadline() -> AsyncIterator[None]:
    """Set the from-segments budget before the auth dependency resolves.

    Declared first in the route signature so FastAPI resolves it before
    ``with_rate_limit(get_current_user_uid, ...)``; the contextvar then reaches
    that dependency's threadpool copy.
    """
    token = set_request_deadline(FROM_SEGMENTS_REQUEST_BUDGET_SECONDS)
    try:
        yield
    finally:
        reset_request_deadline(token)

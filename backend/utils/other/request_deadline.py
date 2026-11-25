"""A request-scoped wall-clock deadline for the synchronous from-segments ingest.

The route bounds auth, intake and its processing wait with one deadline.
Enrichment uses the remaining budget in inline mode. Continued processing can
run with its own budget after the HTTP waiter returns a retryable error.
Other callers leave the deadline unset.

The deadline is a contextvar, so it reaches the synchronous auth dependency and
the handler through the threadpool context copy FastAPI makes for each, and the
``asyncio.run`` the notes step opens copies it again. It is stored as one
absolute monotonic instant, so every step derives its own relative timeout from
the same deadline instead of restarting a fresh budget.
"""

from __future__ import annotations

import asyncio
import contextvars
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, AsyncIterator, Callable, Coroutine, TypeVar

# The client's own HTTP pool gives up at 30 s per attempt; answering a retryable
# error before that is what makes the retry useful. Leave headroom for response
# serialization and the middleware.
FROM_SEGMENTS_REQUEST_BUDGET_SECONDS = 25.0
# A spent budget must still produce a deadline the notes loop accepts (> 0).
MINIMUM_DEADLINE_SECONDS = 0.05

T = TypeVar('T')

_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar('omi_request_deadline_monotonic', default=None)


class RequestDeadlineExceeded(TimeoutError):
    """The request's own budget expired before the work could finish.

    A ``TimeoutError`` so the existing processing boundary maps it to the
    retryable 503 contract instead of a generic 500.
    """


def set_request_deadline(seconds: float) -> contextvars.Token:
    return _deadline.set(time.monotonic() + max(0.0, seconds))


def reset_request_deadline(token: contextvars.Token) -> None:
    _deadline.reset(token)


def request_deadline_absolute() -> float | None:
    """The absolute monotonic deadline, or ``None`` when no budget is set."""
    return _deadline.get()


def request_deadline_remaining_seconds() -> float | None:
    """Seconds left in the request budget, or ``None`` when no budget is set."""
    deadline = _deadline.get()
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


def request_deadline_exceeded() -> bool:
    remaining = request_deadline_remaining_seconds()
    return remaining is not None and remaining <= 0.0


def require_request_budget() -> None:
    if request_deadline_exceeded():
        raise RequestDeadlineExceeded('request budget spent before the next step')


async def await_within_request_deadline(awaitable_factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Await an async dependency for at most the remaining request budget.

    A factory avoids creating an un-awaited coroutine when the budget is
    already spent. Cancellation stops the wait; any synchronous work already
    running in an executor remains subject to that operation's own timeout.
    """
    remaining = request_deadline_remaining_seconds()
    if remaining is None:
        return await awaitable_factory()
    if remaining <= 0.0:
        raise RequestDeadlineExceeded('request budget spent before the async call started')

    task = asyncio.create_task(awaitable_factory())
    try:
        done, _pending = await asyncio.wait((task,), timeout=remaining)
        if not done:
            raise RequestDeadlineExceeded('request budget spent while awaiting the async call')
    finally:
        if not task.done():
            task.cancel()

    result = task.result()
    if request_deadline_exceeded():
        raise RequestDeadlineExceeded('request budget spent before the async call returned')
    return result


def capped_deadline_seconds(deadline_seconds: float) -> float:
    """Cap *deadline_seconds* to the request budget; unchanged when unset."""
    remaining = request_deadline_remaining_seconds()
    if remaining is None:
        return deadline_seconds
    return max(MINIMUM_DEADLINE_SECONDS, min(deadline_seconds, remaining))


def call_within_request_deadline(fn: Callable[..., T], *args: object, **kwargs: object) -> T:
    """Run *fn* and wait at most the remaining request budget for it.

    Only the from-segments route sets a budget; every other caller runs *fn*
    inline, so this is a no-op for the rest of the app. A synchronous call
    cannot be interrupted, so a call that outlives the budget is abandoned in
    the dedicated pool and the caller answers the retryable 503; the call itself
    stays bounded by its provider's own deadline. The context is copied so the
    call still sees the request deadline and the request's read scope.
    """
    remaining = request_deadline_remaining_seconds()
    if remaining is None:
        return fn(*args, **kwargs)
    if remaining <= 0.0:
        raise RequestDeadlineExceeded('request budget spent before the call started')

    # Imported lazily: this module is imported by the notes policy, which must
    # not pull the executor/metrics graph in at import time.
    from utils.executors import ExecutorSaturatedError, auth_deadline_executor

    context = contextvars.copy_context()
    try:
        future = auth_deadline_executor.submit(context.run, fn, *args, **kwargs)
    except ExecutorSaturatedError as error:
        raise RequestDeadlineExceeded('auth deadline pool saturated') from error
    try:
        return future.result(timeout=remaining)
    except FuturesTimeoutError as error:
        # concurrent.futures re-raises a TimeoutError raised by the function
        # with the same type used for its own wait timeout.
        if future.done() and isinstance(future.exception(), FuturesTimeoutError):
            raise
        future.cancel()
        raise RequestDeadlineExceeded('request budget spent while the call was in flight') from error


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

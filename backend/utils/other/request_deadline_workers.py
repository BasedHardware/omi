"""Bound waits on synchronous workers using the current HTTP deadline."""

from __future__ import annotations

import contextvars
from concurrent.futures import TimeoutError as FuturesTimeoutError, wait
from typing import Callable, TypeVar

from utils.executors import (
    ExecutorSaturatedError,
    MonitoredThreadPoolExecutor,
    auth_deadline_executor,
    from_segments_executor,
)
from utils.other.request_deadline import (
    RequestDeadlineExceeded,
    clear_request_deadline,
    request_deadline_remaining_seconds,
)

T = TypeVar('T')


def call_within_request_deadline(
    fn: Callable[..., T],
    *args: object,
    executor: MonitoredThreadPoolExecutor = auth_deadline_executor,
    **kwargs: object,
) -> T:
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

    context = contextvars.copy_context()
    try:
        future = executor.submit(context.run, fn, *args, **kwargs)
    except ExecutorSaturatedError as error:
        raise RequestDeadlineExceeded('request deadline pool saturated') from error
    try:
        return future.result(timeout=remaining)
    except FuturesTimeoutError as error:
        # concurrent.futures re-raises a TimeoutError raised by the function
        # with the same type used for its own wait timeout.
        if future.done() and isinstance(future.exception(), FuturesTimeoutError):
            raise
        future.cancel()
        raise RequestDeadlineExceeded('request budget spent while the call was in flight') from error


def wait_for_from_segments_processing(fn: Callable[..., T], *args: object, **kwargs: object) -> T:
    """Bound the request's wait while the owner of the persisted claim finishes.

    The worker keeps the caller context except for the HTTP deadline. Its model
    calls retain their own processing budgets. Once running, the worker owns
    completion and cleanup even when the caller receives a retryable response.
    """
    remaining = request_deadline_remaining_seconds()
    if remaining is None:
        return fn(*args, **kwargs)
    if remaining <= 0.0:
        raise RequestDeadlineExceeded('request budget spent before transcript processing')

    context = contextvars.copy_context()
    context.run(clear_request_deadline)
    future = from_segments_executor.submit(context.run, fn, *args, **kwargs)
    done, _ = wait((future,), timeout=request_deadline_remaining_seconds())
    if done:
        return future.result()
    future.cancel()  # Only work that has yet to start can be cancelled.
    raise RequestDeadlineExceeded('request budget spent waiting for transcript processing')

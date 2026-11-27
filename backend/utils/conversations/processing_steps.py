"""Run the same conversation stages inline or with async provider waits."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass
from functools import partial, wraps
from typing import Any, Callable, Coroutine, Generator, Generic, ParamSpec, TypeVar

from utils.executors import run_blocking

P = ParamSpec('P')
T = TypeVar('T')


@dataclass(frozen=True)
class AsyncStep:
    invoke: Callable[[], Coroutine[Any, Any, Any]]
    run_sync: Callable[[], Any] | None = None


# A bare yield marks the boundary between two blocking stages. The async
# runner returns the worker to its pool at every boundary.
Steps = Generator[AsyncStep | None, Any, T]


def run_inline(steps: Steps[T]) -> T:
    advance: Callable[[], AsyncStep | None] = steps.__next__
    while True:
        try:
            step = advance()
        except StopIteration as done:
            return done.value
        if step is None:
            advance: Callable[[], AsyncStep | None] = steps.__next__
            continue
        try:
            value = step.run_sync() if step.run_sync is not None else asyncio.run(step.invoke())
        except BaseException as error:
            advance = partial(steps.throw, error)
        else:
            advance = partial(steps.send, value)


def inline_steps(function: Callable[P, Steps[T]]) -> Callable[P, T]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        return run_inline(function(*args, **kwargs))

    return wrapped


def blocking_step(function: Callable[P, T]) -> Callable[P, Steps[T]]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> Steps[T]:
        yield
        return function(*args, **kwargs)

    return wrapped


@dataclass(frozen=True)
class _Completed(Generic[T]):
    value: T


async def run_async(steps: Steps[T], executor: ThreadPoolExecutor) -> T:
    # Keep scope tokens (usage, spelling cache, Firestore attribution) in a
    # single context across worker handoffs. Like asyncio.run in the inline
    # path, each native async operation inherits a copy of those scopes.
    context = copy_context()

    def run_stage(advance: Callable[[], AsyncStep | None]) -> AsyncStep | None | _Completed[T]:
        try:
            return advance()
        except StopIteration as done:
            return _Completed(done.value)

    advance: Callable[[], AsyncStep | None] = steps.__next__
    try:
        while True:
            worker = asyncio.create_task(run_blocking(executor, context.run, run_stage, advance))
            try:
                step = await asyncio.shield(worker)
            except asyncio.CancelledError:
                # A running thread cannot be interrupted. Let it leave the
                # generator before unwinding the scopes and lease on close.
                try:
                    await worker
                finally:
                    raise
            if isinstance(step, _Completed):
                return step.value
            if step is None:
                advance = steps.__next__
                continue
            try:
                value = await asyncio.create_task(step.invoke(), context=context.copy())
            except Exception as error:
                advance = partial(steps.throw, error)
            else:
                advance = partial(steps.send, value)
    except BaseException:
        await run_blocking(executor, context.run, steps.close)
        raise

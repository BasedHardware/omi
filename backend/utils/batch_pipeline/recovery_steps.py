"""Resume fenced recovery around provider waits without retaining an executor slot."""

from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from utils.executors import run_blocking, sync_executor


@dataclass(frozen=True)
class ProviderReply:
    value: Any = None
    error: Exception | None = None

    def result(self):
        if self.error is not None:
            raise self.error
        return self.value


@dataclass(frozen=True)
class ProviderStep:
    operation: Callable[..., Any]
    arguments: tuple[Any, ...]
    asynchronous: Callable[..., Awaitable[Any]] | None = None


def advance(steps, reply):
    # StopIteration must not cross an asyncio Future boundary.
    try:
        return False, steps.send(reply)
    except StopIteration as finished:
        return True, finished.value


def run_sync(steps):
    reply = None
    while True:
        done, value = advance(steps, reply)
        if done:
            return value
        try:
            reply = ProviderReply(value=value.operation(*value.arguments))
        except Exception as error:
            reply = ProviderReply(error=error)


async def run_async(steps):
    reply = None
    while True:
        done, value = await run_blocking(sync_executor, advance, steps, reply)
        if done:
            return value
        try:
            # The continuation is suspended: no executor worker or DB
            # transaction stays borrowed during async HTTP/polling/sleep.
            result = (
                await value.asynchronous(*value.arguments)
                if value.asynchronous is not None
                else await run_blocking(sync_executor, value.operation, *value.arguments)
            )
            reply = ProviderReply(value=result)
        except Exception as error:
            reply = ProviderReply(error=error)

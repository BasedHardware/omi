"""Bounded provider queue with replay-only back-pressure; normal sends stay synchronous."""

import asyncio
from typing import TypeVar, Generic

T = TypeVar('T')
REPLAY_QUEUE_WAIT_SECONDS = 2.0


class AudioSendQueue(asyncio.Queue[T], Generic[T]):
    def __init__(self, maxsize: int) -> None:
        super().__init__(maxsize=maxsize)
        self._space = asyncio.Event()

    async def get(self) -> T:
        item = await super().get()
        self._space.set()
        return item

    async def wait_for_capacity(self) -> None:
        async with asyncio.timeout(REPLAY_QUEUE_WAIT_SECONDS):
            while self.full():
                self._space.clear()
                if self.full():
                    await self._space.wait()

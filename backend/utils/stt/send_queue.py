"""Bounded provider queue with replay-only back-pressure; normal sends stay synchronous."""

import asyncio
from typing import TypeVar, Generic

T = TypeVar('T')
REPLAY_QUEUE_WAIT_SECONDS = 2.0


class AudioSendQueue(asyncio.Queue[T], Generic[T]):
    def __init__(self, maxsize: int) -> None:
        super().__init__(maxsize=maxsize)
        self._space = asyncio.Event()
        self.high_water = 0

    def put_nowait(self, item: T) -> None:
        super().put_nowait(item)
        self.high_water = max(self.high_water, self.qsize())

    async def get(self) -> T:
        item = await super().get()
        self._space.set()
        return item

    async def wait_for_capacity(self) -> None:
        # Replay/live-tail pacing must not hide a stalled transport behind the
        # normal 2,000-item allowance. At most two paced packets may wait ahead.
        limit = min(2, self.maxsize) if self.maxsize else 2
        async with asyncio.timeout(REPLAY_QUEUE_WAIT_SECONDS):
            while self.qsize() >= limit:
                self._space.clear()
                if self.qsize() >= limit:
                    await self._space.wait()

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
        self.inflight = 0
        self.enqueued_audio = 0
        self.written_audio = 0

    def put_nowait(self, item: T) -> None:
        super().put_nowait(item)
        self.high_water = max(self.high_water, self.qsize() + self.inflight)
        if isinstance(item, (bytes, bytearray)) and len(item) > 0:
            self.enqueued_audio += 1

    async def get(self) -> T:
        item = await super().get()
        self.inflight += 1
        self._space.set()
        return item

    def note_written(self, item: T) -> None:
        self.inflight = max(0, self.inflight - 1)
        if isinstance(item, (bytes, bytearray)) and len(item) > 0:
            self.written_audio += 1
        self._space.set()

    def discard(self, item: T) -> None:
        """An item was dequeued but will not be written (dead/closed leg)."""
        self.inflight = max(0, self.inflight - 1)
        self._space.set()

    async def wait_for_capacity(self, limit: int | None = None, timeout: float | None = None) -> None:
        # Replay/live-tail pacing must not hide a stalled transport behind the
        bound = 2 if limit is None else limit
        bound = min(bound, self.maxsize) if self.maxsize else bound
        async with asyncio.timeout(REPLAY_QUEUE_WAIT_SECONDS if timeout is None else timeout):
            while self.qsize() + self.inflight >= bound:
                self._space.clear()
                if self.qsize() + self.inflight >= bound:
                    await self._space.wait()

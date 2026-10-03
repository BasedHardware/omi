"""Bounded provider queue with replay-only back-pressure; normal sends stay synchronous."""

import asyncio
from collections import deque
from contextvars import ContextVar
from typing import TypeVar, Generic

T = TypeVar('T')
REPLAY_QUEUE_WAIT_SECONDS = 2.0

# Absolute wire deadline for the next enqueued live audio frame; recovery tail
# sends stamp their capture-age bound, ordinary/PTT puts see the None default.
audio_send_deadline: ContextVar['float | None'] = ContextVar('audio_send_deadline', default=None)


class AudioSendQueue(asyncio.Queue[T], Generic[T]):
    def __init__(self, maxsize: int) -> None:
        super().__init__(maxsize=maxsize)
        self._space = asyncio.Event()
        self._deadlines: deque[float | None] = deque()
        self.inflight_deadline: float | None = None
        self.high_water = 0
        self.inflight = 0
        self.enqueued_audio = 0
        self.written_audio = 0

    def put_nowait(self, item: T) -> None:
        super().put_nowait(item)
        self._deadlines.append(
            audio_send_deadline.get() if isinstance(item, (bytes, bytearray)) and len(item) > 0 else None
        )
        self.high_water = max(self.high_water, self.qsize() + self.inflight)
        if isinstance(item, (bytes, bytearray)) and len(item) > 0:
            self.enqueued_audio += 1

    def _get(self) -> T:
        self.inflight_deadline = self._deadlines.popleft()
        return super()._get()

    async def get(self) -> T:
        item = await super().get()
        self.inflight += 1
        self._space.set()
        return item

    def note_written(self, item: T) -> None:
        self.inflight = max(0, self.inflight - 1)
        self.inflight_deadline = None
        if isinstance(item, (bytes, bytearray)) and len(item) > 0:
            self.written_audio += 1
        self._space.set()

    def discard(self, item: T) -> None:
        """An item was dequeued but will not be written (dead/closed leg)."""
        self.inflight = max(0, self.inflight - 1)
        self.inflight_deadline = None
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

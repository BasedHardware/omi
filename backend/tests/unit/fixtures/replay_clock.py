"""Event-driven fake clock for audio-time replay pacing tests."""

import asyncio
import heapq
import pytest


class VirtualClock:
    def __init__(self):
        self.now = 0.0
        self.waiters = []
        self.sequence = 0
        self.task = None

    async def sleep(self, seconds):
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        future = asyncio.get_running_loop().create_future()
        self.sequence += 1
        heapq.heappush(self.waiters, (self.now + seconds, self.sequence, future))
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.drive())
        await future

    async def drive(self):
        while self.waiters:
            # Let wait_for/get and the real adapter tasks finish their runnable
            # work before advancing to the next virtual timer (no real sleeps).
            for _ in range(6):
                await asyncio.sleep(0)
            due = self.waiters[0][0]
            self.now = due
            while self.waiters and self.waiters[0][0] <= due:
                _, _, future = heapq.heappop(self.waiters)
                if not future.done():
                    future.set_result(None)


@pytest.fixture(autouse=True)
def virtual_clock(monkeypatch):
    from utils.stt import recovery_state, replay_delivery, resilient_stream

    timer = VirtualClock()
    monkeypatch.setattr(replay_delivery, 'clock', lambda: timer.now)
    monkeypatch.setattr(replay_delivery, 'sleep', timer.sleep)
    monkeypatch.setattr(resilient_stream, 'clock', lambda: timer.now)
    monkeypatch.setattr(recovery_state, 'clock', lambda: timer.now)
    return timer

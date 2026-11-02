"""Virtual time for an in-process discrete-event simulation.

The event loop is asyncio's own: its scheduled-timer heap is the event queue
(``heapq`` ordered by virtual due time, ties broken by insertion order). The
selector never blocks; when no callback is ready it jumps the virtual clock to
the next timer. ``asyncio.sleep``/``wait_for`` and every Pump heartbeat or poll
therefore cost no wall time and are fully deterministic.

No sockets, threads or real IO are used by the simulation. A thread-safe wakeup
(``call_soon_threadsafe``) is not modelled: nothing in the simulation uses one.
"""

from __future__ import annotations

import asyncio
import selectors
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar('T')

# Arbitrary fixed epoch (2027-01-15T08:00:00Z) so scheduler timestamps look like production epochs.
SIM_EPOCH = 1_800_000_000.0


class SimulationStalled(RuntimeError):
    """Every coroutine is waiting and no timer is pending: a modelling deadlock."""


class VirtualClock:
    def __init__(self, start: float = SIM_EPOCH):
        self.start = float(start)
        self.now = float(start)

    def time(self) -> float:
        return self.now

    def elapsed(self) -> float:
        return self.now - self.start

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError('virtual time cannot move backwards')
        self.now += seconds

    def module(self) -> SimpleNamespace:
        """Stand-in for the ``time`` module attribute of a module under simulation."""
        return SimpleNamespace(time=self.time, monotonic=self.time, perf_counter=self.time)


class _VirtualSelector(selectors.SelectSelector):
    def __init__(self, clock: VirtualClock):
        super().__init__()
        self._clock = clock
        self.loop: asyncio.AbstractEventLoop | None = None

    def select(self, timeout: float | None = None):
        if timeout is None:
            raise SimulationStalled('no runnable callback and no pending timer')
        if timeout > 0:
            # Jump exactly to the head timer. Adding ``timeout`` to an epoch-sized
            # float can round below the timer's due time and spin forever.
            scheduled = getattr(self.loop, '_scheduled', None)
            target = self._clock.now + timeout
            if scheduled and scheduled[0].when() <= target + 1e-6:
                target = scheduled[0].when()
            self._clock.now = max(self._clock.now, target)
        return []


class VirtualTimeLoop(asyncio.SelectorEventLoop):
    def __init__(self, clock: VirtualClock):
        self._virtual_clock = clock
        selector = _VirtualSelector(clock)
        super().__init__(selector)
        selector.loop = self
        # asyncio runs timers due before ``time() + _clock_resolution``. At epoch
        # magnitude a float ulp is ~2e-7 s, so the default 1e-9 rounds away and a
        # timer due exactly ``now`` would never run. Timers within 1 ms are due.
        self._clock_resolution = 1e-3

    def time(self) -> float:
        return self._virtual_clock.now


def run_virtual(clock: VirtualClock, main: Callable[[], Awaitable[T]]) -> T:
    """Run ``main()`` to completion on a fresh virtual-time loop, then cancel stragglers."""
    loop = VirtualTimeLoop(clock)
    try:
        # Not installed as the thread's current loop: callers' loops stay untouched.
        result = loop.run_until_complete(main())
        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        return result
    finally:
        loop.close()


async def sleep_until(clock: VirtualClock, when: float) -> None:
    if when > clock.now:
        await asyncio.sleep(when - clock.now)


def call_at(clock: VirtualClock, when: float, callback: Callable[..., Any], *args: Any) -> asyncio.TimerHandle:
    loop = asyncio.get_running_loop()
    return loop.call_at(max(when, clock.now), callback, *args)

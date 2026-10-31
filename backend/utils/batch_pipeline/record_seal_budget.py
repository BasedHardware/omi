"""Cancellation for bounded sweep IO, without leaking provider error payloads."""

from contextlib import contextmanager
import signal
import time


class BudgetExhausted(BaseException):
    """Like cancellation, must escape dependency handlers that catch Exception."""


class SweepBudget:
    def __init__(self, seconds, *, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.deadline = self.started + seconds

    def check(self):
        if self.clock() >= self.deadline:
            raise BudgetExhausted()

    def timeout(self):
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise BudgetExhausted()
        return min(10.0, remaining)

    @contextmanager
    def interrupt_io(self):
        # Cron entrypoint is a dedicated Unix main thread. Cooperative checks
        # alone cannot bound next(iterator): it may read thousands of blobs
        # before yielding one retained unit, or sit in an SDK retry loop.
        def expired(*_):
            raise BudgetExhausted()

        previous = signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, max(0.001, self.deadline - self.clock()))
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)

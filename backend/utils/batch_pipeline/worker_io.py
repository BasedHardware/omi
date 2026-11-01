"""Attempt-local CPU preparation and a bounded, post-CUDA persistence receipt."""

from concurrent.futures import wait
import threading


class PendingResults:
    """No WorkResult escapes until all encrypted writes have settled."""

    def __init__(self, finish, futures):
        self._finish = finish
        self._futures = list(futures)

    def settle(self):
        try:
            return self._finish()
        finally:
            self.close()

    def close(self):
        wait(self._futures)
        self._futures.clear()


class FirstDecode:
    """One lane's first decode; never a cache indexed by segment identity."""

    def __init__(self, budget, item, future):
        self.budget, self.item, self.future = budget, item, future
        self._closed = False
        self.cancelled = False
        self._lock = threading.Lock()

    def cancel(self):
        self.cancelled = True
        future = self.future
        if future is not None:
            future.cancel()

    def take(self, item):
        if item is not self.item or self._closed or self.cancelled:
            raise ValueError('prepared decode belongs to another attempt')
        return self.future.result()

    def close(self):
        with self._lock:
            if self._closed:
                return
            if not self.future.cancel():
                wait([self.future])  # SDK IO has its own bounded request/retry deadline.
            # Release decoded buffers as well as the reservation on discard.
            self.future = None
            self._closed = True
            self.budget.release(self.item)


class DecodeBudget:
    """Shared across pump lanes; oversize items use ordinary locked decode."""

    def __init__(self, seconds=1800):
        self.limit = seconds
        self.seconds = 0.0
        self._segments = set()
        self._lock = threading.Lock()

    def submit(self, executor, decode, item):
        with self._lock:
            if item.segment_id in self._segments or self.seconds + item.duration_seconds > self.limit:
                return None
            self._segments.add(item.segment_id)
            self.seconds += item.duration_seconds
        try:
            return FirstDecode(self, item, executor.submit(decode, item))
        except BaseException:
            self.release(item)
            raise

    def release(self, item):
        with self._lock:
            self._segments.remove(item.segment_id)
            self.seconds -= item.duration_seconds

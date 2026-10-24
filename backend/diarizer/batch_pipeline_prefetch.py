"""CPU-only read-ahead across flights; never owns a CUDA context or a lease.

Reservations cover queued, running and completed-but-unconsumed decodes across
all pump lanes. They are released only after consumption or a drained discard.
"""

from concurrent.futures import wait
import threading

MAX_AHEAD_SECONDS = 1800


class DecodeAhead:
    def __init__(self, executor, decode, concurrency: int):
        if not 1 <= concurrency <= 4:
            raise ValueError('decode concurrency must be in [1, 4]')
        self.executor, self.decode = executor, decode
        self.limit = concurrency - 1
        self._lock = threading.Lock()
        self.items = 0
        self.seconds = 0.0

    def prepare(self, items):
        items = list(items)
        if len(items) > 32 or len({item.segment_id for item in items}) != len(items):
            raise ValueError('read-ahead requires at most 32 distinct items')
        prepared = PreparedDecode(self)
        if self.executor is None:
            return prepared
        for item in items:
            seconds = item.duration_seconds
            with self._lock:
                if self.items >= self.limit or self.seconds + seconds > MAX_AHEAD_SECONDS:
                    break  # Long units use the existing bounded in-flight decode.
                self.items += 1
                self.seconds += seconds
            try:
                future = self.executor.submit(self.decode, item)
            except Exception:
                self.release(seconds)
                # Keep earlier submissions in the handle for normal drain.
                # Never block the event loop by settling futures here. The
                # existing in-flight IO path still surfaces an unavailable pool.
                break
            prepared.pending[item.segment_id] = (future, seconds)
        return prepared

    def release(self, seconds):
        with self._lock:
            self.items -= 1
            self.seconds -= seconds


class PreparedDecode:
    def __init__(self, budget):
        self.budget = budget
        self.pending = {}

    def decode(self, item):
        entry = self.pending.pop(item.segment_id, None)
        if entry is None:
            return self.budget.decode(item)
        future, seconds = entry
        try:
            return future.result()
        finally:
            self.budget.release(seconds)

    def close(self):
        """Calling lane must have drained compute first; no IO outlives discard."""
        pending, self.pending = self.pending, {}
        for future, _ in pending.values():
            future.cancel()
        wait([future for future, _ in pending.values()])
        for _, seconds in pending.values():
            self.budget.release(seconds)

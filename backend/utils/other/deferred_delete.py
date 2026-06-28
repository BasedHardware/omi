"""Single-thread deferred-deletion scheduler.

Replaces the previous pattern of parking an executor thread in
time.sleep(480) per file: at sync volume that kept ~70% of
storage_executor's 128 threads asleep as ad-hoc timers, which is what
drove the pool's repeated saturation (#7531). One daemon thread and a
due-time heap handle any number of pending deletions.

Best-effort by design: pending deletions are lost on process death, same
as the sleeping threads were; the syncing bucket's lifecycle rule is the
backstop.
"""

import heapq
import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)


class DeferredDeleter:
    def __init__(self, delete_fn: Callable[[str], None], name: str = 'deferred-delete-janitor'):
        self._delete_fn = delete_fn
        self._name = name
        self._cond = threading.Condition()
        self._heap = []  # (due_monotonic, seq, path)
        self._seq = 0
        self._thread = None

    def schedule(self, path: str, delay_seconds: float) -> None:
        """Schedule path for deletion after delay_seconds. O(log n), never blocks."""
        with self._cond:
            self._seq += 1
            heapq.heappush(self._heap, (time.monotonic() + delay_seconds, self._seq, path))
            # is_alive() guard: restart the janitor if a BaseException
            # (MemoryError, SystemExit) ever killed it — otherwise schedules
            # would pile up silently for the rest of the process lifetime
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
                self._thread.start()
            self._cond.notify()

    def pending_count(self) -> int:
        with self._cond:
            return len(self._heap)

    def _run(self):
        while True:
            with self._cond:
                while not self._heap:
                    self._cond.wait()
                due, _, path = self._heap[0]
                delay = due - time.monotonic()
                if delay > 0:
                    # A schedule() for an earlier due-time re-notifies and we re-peek
                    self._cond.wait(timeout=delay)
                    continue
                heapq.heappop(self._heap)
            try:
                self._delete_fn(path)
            except Exception as e:
                logger.warning('deferred delete failed for %s: %s', path, e)

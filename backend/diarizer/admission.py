"""Bounded FIFO admission shared by upload and inference (one GPU worker)."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from queue import Full, Queue
import threading

GPU_LOCK = threading.Lock()


class CapacityExceeded(Exception):
    pass


class AdmissionQueue:
    def __init__(self, capacity=3):
        self.pending = Queue(maxsize=capacity)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='diarization')

    def reserve(self):
        try:
            self.pending.put_nowait(object())
        except Full:
            raise CapacityExceeded from None

    def release(self):
        self.pending.get_nowait()
        self.pending.task_done()

    @contextmanager
    def admit(self):
        self.reserve()
        try:
            yield
        finally:
            self.release()

    @property
    def depth(self):
        return self.pending.qsize()

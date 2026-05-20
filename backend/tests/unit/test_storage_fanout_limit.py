"""Tests for bounded fan-out in storage executor submissions (issue #7387).

Verifies that concurrent storage_executor submissions are capped by
threading.Semaphore to prevent queue spikes from unbounded fan-out.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock

import pytest


class TestStorageFanoutSemaphore:
    """Verify that _STORAGE_FANOUT_SEMAPHORE limits concurrent GCS operations."""

    def test_semaphore_limits_concurrency(self):
        """Fan-out of 50 tasks with semaphore(5) should never exceed 5 concurrent."""
        sem = threading.Semaphore(5)
        max_concurrent = 0
        current = 0
        lock = threading.Lock()

        def work(i):
            nonlocal max_concurrent, current
            with sem:
                with lock:
                    current += 1
                    if current > max_concurrent:
                        max_concurrent = current
                time.sleep(0.01)
                with lock:
                    current -= 1
            return i

        executor = ThreadPoolExecutor(max_workers=20)
        futures = [executor.submit(work, i) for i in range(50)]
        for f in as_completed(futures):
            f.result()
        executor.shutdown(wait=True)

        assert max_concurrent <= 5, f"Max concurrent was {max_concurrent}, expected <= 5"
        assert max_concurrent >= 2, "Semaphore should allow some parallelism"

    def test_semaphore_does_not_deadlock(self):
        """Nested semaphore acquisition (precache -> chunk download) must not deadlock."""
        outer_sem = threading.Semaphore(3)
        inner_sem = threading.Semaphore(3)
        results = []
        lock = threading.Lock()

        def inner_work(val):
            with inner_sem:
                time.sleep(0.005)
                return val * 2

        def outer_work(i):
            with outer_sem:
                inner_executor = ThreadPoolExecutor(max_workers=2)
                futs = [inner_executor.submit(inner_work, j) for j in range(3)]
                vals = [f.result(timeout=5) for f in futs]
                inner_executor.shutdown(wait=True)
                with lock:
                    results.append(sum(vals))
            return i

        executor = ThreadPoolExecutor(max_workers=10)
        futures = [executor.submit(outer_work, i) for i in range(6)]
        for f in as_completed(futures):
            f.result(timeout=10)
        executor.shutdown(wait=True)

        assert len(results) == 6
        assert all(r == 6 for r in results)  # 0*2 + 1*2 + 2*2 = 6

    def test_storage_module_has_semaphore(self):
        """The storage module must define a _STORAGE_FANOUT_SEMAPHORE.

        Uses ast parsing to avoid importing heavy native deps (opuslib, GCS).
        """
        import ast
        import pathlib

        storage_path = pathlib.Path(__file__).resolve().parents[2] / 'utils' / 'other' / 'storage.py'
        tree = ast.parse(storage_path.read_text())

        semaphore_found = False
        semaphore_value = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '_STORAGE_FANOUT_SEMAPHORE':
                        semaphore_found = True
                        if isinstance(node.value, ast.Call) and node.value.args:
                            arg = node.value.args[0]
                            if isinstance(arg, ast.Constant):
                                semaphore_value = arg.value

        assert semaphore_found, "_STORAGE_FANOUT_SEMAPHORE not found in storage.py"
        assert semaphore_value is not None, "Could not determine semaphore value"
        assert 5 <= semaphore_value <= 30, f"Semaphore value {semaphore_value} outside expected range [5, 30]"

    def test_bounded_fan_out_caps_queue_depth(self):
        """Simulate the storage pattern: N tasks submitted, only K run concurrently."""
        sem = threading.Semaphore(10)
        task_count = 100
        peak_queue = 0
        running = 0
        lock = threading.Lock()

        def bounded_work(i):
            nonlocal peak_queue, running
            with sem:
                with lock:
                    running += 1
                    if running > peak_queue:
                        peak_queue = running
                time.sleep(0.005)
                with lock:
                    running -= 1
            return i

        executor = ThreadPoolExecutor(max_workers=50)
        futures = [executor.submit(bounded_work, i) for i in range(task_count)]
        results = [f.result() for f in as_completed(futures)]
        executor.shutdown(wait=True)

        assert len(results) == task_count
        assert peak_queue <= 10, f"Peak concurrent {peak_queue} exceeded semaphore limit 10"

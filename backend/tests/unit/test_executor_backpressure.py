from __future__ import annotations

import threading

import pytest

from utils.executors import ExecutorSaturatedError, MonitoredThreadPoolExecutor


def test_bounded_executor_rejects_work_after_worker_and_queue_fill() -> None:
    release = threading.Event()
    started = threading.Event()

    def blocked() -> None:
        started.set()
        release.wait(timeout=5)

    executor = MonitoredThreadPoolExecutor(name='test', max_workers=1, max_queue_size=2)
    try:
        futures = [executor.submit(blocked) for _ in range(3)]
        assert started.wait(timeout=1)

        with pytest.raises(ExecutorSaturatedError, match='test executor is saturated'):
            executor.submit(lambda: None)

        release.set()
        for future in futures:
            future.result(timeout=2)
    finally:
        release.set()
        executor.shutdown(wait=True, cancel_futures=True)


def test_bounded_executor_reopens_capacity_after_completion() -> None:
    executor = MonitoredThreadPoolExecutor(name='test', max_workers=1, max_queue_size=0)
    try:
        assert executor.submit(lambda: 41).result(timeout=1) == 41
        assert executor.submit(lambda: 42).result(timeout=1) == 42
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

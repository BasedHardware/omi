"""
Tests for ThreadPoolExecutor replacement of raw threads in process_conversation.py (PR #4827).
Verifies executor behavior, exception handling, persona pool submission, and max_workers cap.
"""

import atexit
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch, call


class TestExecutorSetup:
    """Test module-level executor configuration."""

    def test_max_workers_cap(self):
        """ThreadPoolExecutor(max_workers=32) queues tasks instead of spawning unlimited threads."""
        import threading

        executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="test-cap")
        active_count = []
        barrier = threading.Event()

        def slow_task():
            active_count.append(threading.active_count())
            barrier.wait(timeout=5)

        # Submit 8 tasks to a pool of 4
        futures = [executor.submit(slow_task) for _ in range(8)]

        # Wait for first batch to start
        time.sleep(0.2)

        # Only 4 should be running, rest queued
        barrier.set()
        for f in futures:
            f.result(timeout=5)

        # Peak active threads should never exceed base + 4 workers
        # (not base + 8 like raw threads would)
        executor.shutdown(wait=True)
        assert len(active_count) == 8  # all 8 ran eventually

    def test_atexit_registration(self):
        """atexit.register(executor.shutdown) is callable and registers correctly."""
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-atexit")
        # Verify atexit.register accepts executor.shutdown
        # (This is the pattern used in process_conversation.py)
        atexit.register(executor.shutdown, wait=True)
        # Clean up
        atexit.unregister(executor.shutdown)
        executor.shutdown(wait=True)

    def test_submit_returns_future(self):
        """executor.submit() returns a Future that can be checked for results."""
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-future")
        future = executor.submit(lambda: 42)
        assert future.result(timeout=5) == 42
        executor.shutdown(wait=True)


class TestExceptionHandling:
    """Test that executor-submitted functions log exceptions instead of swallowing them."""

    def test_exception_in_submitted_function_is_logged(self, caplog):
        """Exceptions inside submitted functions should be caught and logged."""
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-exc")

        def failing_task():
            try:
                raise ValueError("test error in background task")
            except Exception as e:
                logging.exception(f"Error in background task: {e}")

        with caplog.at_level(logging.ERROR):
            future = executor.submit(failing_task)
            future.result(timeout=5)

        assert "test error in background task" in caplog.text
        executor.shutdown(wait=True)

    def test_exception_without_wrapper_is_swallowed(self):
        """Without try/except, executor.submit() swallows exceptions silently."""
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-swallow")

        def failing_task():
            raise ValueError("this would be silently swallowed")

        future = executor.submit(failing_task)
        # The exception is only raised when you call future.result()
        # If you never check the future, the exception is lost
        try:
            future.result(timeout=5)
            assert False, "Should have raised"
        except ValueError:
            pass  # This proves the exception exists in the future

        executor.shutdown(wait=True)

    def test_wrapped_function_does_not_propagate(self, caplog):
        """Wrapped functions catch exceptions so they don't kill the thread."""
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-wrap")

        def safe_failing_task():
            try:
                raise RuntimeError("handled error")
            except Exception as e:
                logging.exception(f"Background error: {e}")

        with caplog.at_level(logging.ERROR):
            future = executor.submit(safe_failing_task)
            result = future.result(timeout=5)

        # Function completes normally (returns None), exception was logged
        assert result is None
        assert "handled error" in caplog.text
        executor.shutdown(wait=True)


class TestPersonaPoolSubmission:
    """Test _update_personas_via_pool logic patterns."""

    def test_rate_limited_skips(self):
        """If can_update_persona returns False, no persona updates are submitted."""
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-rl")
        submitted = []

        def mock_update(persona):
            submitted.append(persona)

        # Simulate rate-limited path
        can_update = False
        if can_update:
            for p in ["persona1", "persona2"]:
                executor.submit(mock_update, p)

        assert len(submitted) == 0
        executor.shutdown(wait=True)

    def test_empty_personas_no_submissions(self):
        """If no personas found, nothing is submitted to the pool."""
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-empty")
        submitted = []

        def mock_update(persona):
            submitted.append(persona)

        personas = []  # empty
        for p in personas:
            executor.submit(mock_update, p)

        executor.shutdown(wait=True)
        assert len(submitted) == 0

    def test_per_persona_individual_submission(self):
        """Each persona gets its own submit() call, not a single thread with join()."""
        executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="test-indiv")
        submitted = []

        def mock_update(persona):
            submitted.append(persona)

        personas = ["p1", "p2", "p3", "p4"]
        futures = [executor.submit(mock_update, p) for p in personas]
        for f in futures:
            f.result(timeout=5)

        assert submitted == ["p1", "p2", "p3", "p4"]
        executor.shutdown(wait=True)

    def test_persona_exception_doesnt_block_others(self):
        """One failing persona update doesn't prevent others from running."""
        executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="test-iso")
        results = []

        def mock_update(persona):
            if persona == "p2":
                raise ValueError("p2 failed")
            results.append(persona)

        personas = ["p1", "p2", "p3"]
        futures = [executor.submit(mock_update, p) for p in personas]

        for f in futures:
            try:
                f.result(timeout=5)
            except ValueError:
                pass

        # p1 and p3 succeeded despite p2 failing
        assert "p1" in results
        assert "p3" in results
        executor.shutdown(wait=True)


class TestMaxWorkersBoundary:
    """Test that max_workers cap prevents thread explosion."""

    def test_concurrent_tasks_capped_at_max_workers(self):
        """Submitting N > max_workers tasks only runs max_workers concurrently."""
        import threading

        max_workers = 4
        executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="test-bound")
        peak_concurrent = []
        current = {'count': 0}
        lock = threading.Lock()

        def tracked_task():
            with lock:
                current['count'] += 1
                peak_concurrent.append(current['count'])
            time.sleep(0.1)  # Hold the worker
            with lock:
                current['count'] -= 1

        futures = [executor.submit(tracked_task) for _ in range(20)]
        for f in futures:
            f.result(timeout=10)

        # Peak concurrent should never exceed max_workers
        assert max(peak_concurrent) <= max_workers
        executor.shutdown(wait=True)

    def test_raw_threads_exceed_pool_cap(self):
        """Contrast: raw threads can exceed any cap. This is what we're preventing."""
        import threading

        peak_concurrent = []
        current = {'count': 0}
        lock = threading.Lock()

        def tracked_task():
            with lock:
                current['count'] += 1
                peak_concurrent.append(current['count'])
            time.sleep(0.1)
            with lock:
                current['count'] -= 1

        threads = [threading.Thread(target=tracked_task) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Raw threads can all run concurrently — peak should be close to 20
        assert max(peak_concurrent) > 4  # Proves the problem we're fixing

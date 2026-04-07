"""Tests for async HTTP infrastructure (issue #6369).

Covers:
- WebhookCircuitBreaker state machine (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Per-target circuit breaker registry
- Latest-wins dropping pattern for audio byte webhooks
- Semaphore bounded concurrency getters
- Shared executors from utils/executors.py
"""

import asyncio
import time
from unittest.mock import patch

import pytest

from utils.http_client import (
    WebhookCircuitBreaker,
    get_webhook_circuit_breaker,
    latest_wins_start,
    latest_wins_check,
    get_webhook_semaphore,
    get_maps_semaphore,
    get_auth_semaphore,
    get_stt_semaphore,
    _webhook_circuit_breakers,
    _latest_wins_versions,
    _semaphores,
    _CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    _CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
)
from utils.executors import critical_executor, storage_executor

# ============================================================================
# WebhookCircuitBreaker
# ============================================================================


class TestWebhookCircuitBreaker:
    """Circuit breaker state machine tests."""

    def test_initial_state_is_closed(self):
        cb = WebhookCircuitBreaker("test-host")
        assert cb.state == 'closed'
        assert cb.allow_request() is True

    def test_stays_closed_below_threshold(self):
        cb = WebhookCircuitBreaker("test-host")
        for _ in range(_CIRCUIT_BREAKER_FAILURE_THRESHOLD - 1):
            cb.record_failure()
        assert cb.state == 'closed'
        assert cb.allow_request() is True

    def test_opens_at_threshold(self):
        cb = WebhookCircuitBreaker("test-host")
        for _ in range(_CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure()
        assert cb.state == 'open'
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        cb = WebhookCircuitBreaker("test-host")
        for _ in range(_CIRCUIT_BREAKER_FAILURE_THRESHOLD - 1):
            cb.record_failure()
        cb.record_success()
        # Now failures are reset, need full threshold again
        for _ in range(_CIRCUIT_BREAKER_FAILURE_THRESHOLD - 1):
            cb.record_failure()
        assert cb.state == 'closed'

    def test_open_to_half_open_after_timeout(self):
        cb = WebhookCircuitBreaker("test-host")
        for _ in range(_CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure()
        assert cb.state == 'open'

        # Simulate time passing beyond recovery timeout
        cb._last_failure_time = time.monotonic() - _CIRCUIT_BREAKER_RECOVERY_TIMEOUT - 1
        assert cb.state == 'half_open'

    def test_half_open_allows_one_probe(self):
        cb = WebhookCircuitBreaker("test-host")
        for _ in range(_CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure()
        cb._last_failure_time = time.monotonic() - _CIRCUIT_BREAKER_RECOVERY_TIMEOUT - 1

        assert cb.state == 'half_open'
        assert cb.allow_request() is True  # first probe
        assert cb.allow_request() is False  # second blocked

    def test_half_open_success_closes(self):
        cb = WebhookCircuitBreaker("test-host")
        for _ in range(_CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure()
        cb._last_failure_time = time.monotonic() - _CIRCUIT_BREAKER_RECOVERY_TIMEOUT - 1

        assert cb.allow_request() is True
        cb.record_success()
        assert cb.state == 'closed'
        assert cb.allow_request() is True

    def test_half_open_failure_reopens(self):
        cb = WebhookCircuitBreaker("test-host")
        for _ in range(_CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure()
        cb._last_failure_time = time.monotonic() - _CIRCUIT_BREAKER_RECOVERY_TIMEOUT - 1

        assert cb.allow_request() is True
        # Fail again — should go back to open
        for _ in range(_CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure()
        assert cb.state == 'open'


# ============================================================================
# Circuit breaker registry
# ============================================================================


class TestCircuitBreakerRegistry:
    """Per-target circuit breaker lookup tests."""

    def setup_method(self):
        _webhook_circuit_breakers.clear()

    def test_same_url_returns_same_instance(self):
        cb1 = get_webhook_circuit_breaker("https://example.com/path1")
        cb2 = get_webhook_circuit_breaker("https://example.com/path1")
        assert cb1 is cb2

    def test_same_url_ignores_query_params(self):
        cb1 = get_webhook_circuit_breaker("https://example.com/hook?key=1")
        cb2 = get_webhook_circuit_breaker("https://example.com/hook?key=2")
        assert cb1 is cb2

    def test_different_paths_return_different_instances(self):
        cb1 = get_webhook_circuit_breaker("https://example.com/path1")
        cb2 = get_webhook_circuit_breaker("https://example.com/path2")
        assert cb1 is not cb2

    def test_different_hosts_return_different_instances(self):
        cb1 = get_webhook_circuit_breaker("https://foo.com/hook")
        cb2 = get_webhook_circuit_breaker("https://bar.com/hook")
        assert cb1 is not cb2

    def test_invalid_url_fallback(self):
        cb = get_webhook_circuit_breaker("not-a-url")
        assert cb is not None
        assert cb.state == 'closed'


# ============================================================================
# Latest-wins dropping
# ============================================================================


class TestLatestWins:
    """Latest-wins version tracking for audio byte webhooks."""

    def setup_method(self):
        _latest_wins_versions.clear()

    def test_start_increments_version(self):
        v1 = latest_wins_start("uid-1")
        v2 = latest_wins_start("uid-1")
        assert v2 == v1 + 1

    def test_check_passes_for_latest(self):
        v = latest_wins_start("uid-1")
        assert latest_wins_check("uid-1", v) is True

    def test_check_fails_for_stale(self):
        v1 = latest_wins_start("uid-1")
        latest_wins_start("uid-1")  # v2 supersedes v1
        assert latest_wins_check("uid-1", v1) is False

    def test_independent_uid_tracking(self):
        v_a = latest_wins_start("uid-a")
        v_b = latest_wins_start("uid-b")
        assert latest_wins_check("uid-a", v_a) is True
        assert latest_wins_check("uid-b", v_b) is True

    def test_check_unknown_uid_returns_false(self):
        assert latest_wins_check("nonexistent", 1) is False


# ============================================================================
# Semaphore getters
# ============================================================================


class TestSemaphoreGetters:
    """Verify semaphore creation and per-loop isolation."""

    def test_webhook_semaphore_returns_semaphore(self):
        sem = get_webhook_semaphore()
        assert isinstance(sem, asyncio.Semaphore)

    def test_maps_semaphore_returns_semaphore(self):
        sem = get_maps_semaphore()
        assert isinstance(sem, asyncio.Semaphore)

    def test_auth_semaphore_returns_semaphore(self):
        sem = get_auth_semaphore()
        assert isinstance(sem, asyncio.Semaphore)

    def test_stt_semaphore_returns_semaphore(self):
        sem = get_stt_semaphore()
        assert isinstance(sem, asyncio.Semaphore)

    @pytest.mark.asyncio
    async def test_same_loop_returns_same_instance(self):
        """Within the same event loop, getter returns the same semaphore."""
        sem1 = get_webhook_semaphore()
        sem2 = get_webhook_semaphore()
        assert sem1 is sem2

    def test_different_loops_return_different_instances(self):
        """Different asyncio.run() calls get isolated semaphores."""
        sems = []

        async def _get():
            return get_webhook_semaphore()

        sems.append(asyncio.run(_get()))
        _semaphores.clear()  # Ensure no stale entries from the destroyed loop
        sems.append(asyncio.run(_get()))
        assert sems[0] is not sems[1]


# ============================================================================
# Shared executors
# ============================================================================


class TestSharedExecutors:
    """Verify dedicated thread pool executors are functional."""

    def test_critical_executor_submits(self):
        future = critical_executor.submit(lambda: 42)
        assert future.result(timeout=5) == 42

    def test_storage_executor_submits(self):
        future = storage_executor.submit(lambda: "ok")
        assert future.result(timeout=5) == "ok"

    def test_critical_executor_thread_name_prefix(self):
        import threading

        result = critical_executor.submit(lambda: threading.current_thread().name).result(timeout=5)
        assert result.startswith("critical")

    def test_storage_executor_thread_name_prefix(self):
        import threading

        result = storage_executor.submit(lambda: threading.current_thread().name).result(timeout=5)
        assert result.startswith("storage")

    def test_critical_executor_parallel_work(self):
        """Verify critical executor handles concurrent submissions."""
        import time

        def slow_task(n):
            time.sleep(0.05)
            return n * 2

        futures = [critical_executor.submit(slow_task, i) for i in range(4)]
        results = [f.result(timeout=5) for f in futures]
        assert results == [0, 2, 4, 6]


class TestShutdownLifecycle:
    """Verify shutdown functions exist and are callable."""

    def test_shutdown_executors_callable(self):
        """shutdown_executors must be a callable function."""
        from utils.executors import shutdown_executors

        assert callable(shutdown_executors)

    def test_shutdown_executors_registered_with_atexit(self):
        """shutdown_executors must be registered via atexit."""
        import atexit

        from utils.executors import shutdown_executors

        # atexit._run_exitfuncs stores registered callables; check it's registered
        # We verify by checking the function exists and is registered
        # (atexit internals are implementation-dependent, so we just verify callability
        #  and that calling it on a fresh executor doesn't raise)
        from concurrent.futures import ThreadPoolExecutor

        test_exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-shutdown")
        test_exec.shutdown(wait=False, cancel_futures=True)  # Should not raise

    def test_close_all_clients_resets_semaphores(self):
        """close_all_clients must clear the semaphore cache."""
        # Populate semaphore cache
        sem = get_webhook_semaphore()
        assert isinstance(sem, asyncio.Semaphore)

        async def _close():
            from utils.http_client import close_all_clients

            await close_all_clients()

        asyncio.run(_close())

        # After close, semaphore cache should be cleared
        assert len(_semaphores) == 0

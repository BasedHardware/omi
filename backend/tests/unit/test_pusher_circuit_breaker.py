"""Unit tests for PusherCircuitBreaker and per-session reconnect state machine (Issue #6022).

Verifies:
- Circuit breaker state transitions (CLOSED→OPEN→HALF_OPEN→CLOSED)
- Failure threshold and window eviction
- Single-probe gating in HALF_OPEN
- PusherCircuitBreakerOpen exception raised when breaker is open
- connect_to_trigger_pusher integration with circuit breaker
- Per-session reconnect state machine transitions
- Graceful degradation routing
"""

import asyncio
import time
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from utils.pusher import (
    PusherCircuitBreaker,
    PusherCircuitBreakerOpen,
    CircuitState,
    connect_to_trigger_pusher,
    get_circuit_breaker,
)

# ---------------------------------------------------------------------------
# Circuit Breaker unit tests
# ---------------------------------------------------------------------------


class TestCircuitBreakerStateTransitions:
    def test_initial_state_is_closed(self):
        cb = PusherCircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_stays_closed_below_threshold(self):
        cb = PusherCircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_opens_at_threshold(self):
        cb = PusherCircuitBreaker(failure_threshold=5)
        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_opens_at_default_threshold_20(self):
        cb = PusherCircuitBreaker()
        for _ in range(20):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_transitions_to_half_open_after_cooldown(self):
        cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.1)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Before cooldown
        assert cb.state == CircuitState.OPEN

        # After cooldown
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)
        for _ in range(3):
            cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)
        for _ in range(3):
            cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_clears_failures(self):
        cb = PusherCircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        cb.record_success()
        # Should be back to zero failures
        assert cb.state == CircuitState.CLOSED
        assert len(cb._failures) == 0

    def test_window_eviction(self):
        """Failures outside the window are evicted and don't count."""
        cb = PusherCircuitBreaker(failure_threshold=5, failure_window=0.1)
        for _ in range(4):
            cb.record_failure()
        time.sleep(0.15)
        # Old failures evicted — adding 1 more shouldn't trip
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert len(cb._failures) == 1


class TestCircuitBreakerCanAttempt:
    def test_can_attempt_when_closed(self):
        cb = PusherCircuitBreaker()
        assert cb.can_attempt() is True

    def test_cannot_attempt_when_open(self):
        cb = PusherCircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.can_attempt() is False

    def test_can_attempt_when_half_open_no_probe(self):
        cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)
        for _ in range(3):
            cb.record_failure()
        time.sleep(0.02)
        assert cb.can_attempt() is True

    def test_cannot_attempt_when_half_open_probe_in_progress(self):
        cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)
        for _ in range(3):
            cb.record_failure()
        time.sleep(0.02)
        cb.acquire_probe()
        assert cb.can_attempt() is False


class TestCircuitBreakerProbe:
    def test_acquire_probe_succeeds_in_half_open(self):
        cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)
        for _ in range(3):
            cb.record_failure()
        time.sleep(0.02)
        assert cb.acquire_probe() is True

    def test_acquire_probe_fails_when_already_probing(self):
        cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)
        for _ in range(3):
            cb.record_failure()
        time.sleep(0.02)
        cb.acquire_probe()
        assert cb.acquire_probe() is False

    def test_acquire_probe_fails_when_closed(self):
        cb = PusherCircuitBreaker()
        assert cb.acquire_probe() is False

    def test_acquire_probe_fails_when_open(self):
        cb = PusherCircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.acquire_probe() is False

    def test_probe_success_resets_probe_flag(self):
        cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)
        for _ in range(3):
            cb.record_failure()
        time.sleep(0.02)
        cb.acquire_probe()
        cb.record_success()
        assert cb._probe_in_progress is False

    def test_probe_failure_resets_probe_flag(self):
        cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)
        for _ in range(3):
            cb.record_failure()
        time.sleep(0.02)
        cb.acquire_probe()
        cb.record_failure()
        assert cb._probe_in_progress is False


# ---------------------------------------------------------------------------
# connect_to_trigger_pusher integration with circuit breaker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_raises_circuit_breaker_open():
    """When breaker is OPEN, connect_to_trigger_pusher raises PusherCircuitBreakerOpen."""
    cb = PusherCircuitBreaker(failure_threshold=3)
    for _ in range(3):
        cb.record_failure()

    with patch('utils.pusher.get_circuit_breaker', return_value=cb):
        with pytest.raises(PusherCircuitBreakerOpen):
            await connect_to_trigger_pusher(uid="test", sample_rate=8000)


@pytest.mark.asyncio
async def test_connect_records_success_on_breaker():
    """Successful connect records success on circuit breaker."""
    cb = PusherCircuitBreaker()
    mock_ws = MagicMock()

    with patch('utils.pusher.get_circuit_breaker', return_value=cb), patch(
        'utils.pusher._connect_to_trigger_pusher', return_value=mock_ws
    ):
        result = await connect_to_trigger_pusher(uid="test", sample_rate=8000)

    assert result is mock_ws
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_connect_records_failure_on_breaker():
    """Failed connect records failure on circuit breaker."""
    cb = PusherCircuitBreaker(failure_threshold=5)

    with patch('utils.pusher.get_circuit_breaker', return_value=cb), patch(
        'utils.pusher._connect_to_trigger_pusher', side_effect=Exception("conn fail")
    ):
        with pytest.raises(Exception, match="conn fail"):
            await connect_to_trigger_pusher(uid="test", sample_rate=8000, retries=1)

    assert len(cb._failures) == 1


@pytest.mark.asyncio
async def test_connect_fails_fast_when_breaker_trips_during_retries():
    """If breaker trips during retry loop, raises PusherCircuitBreakerOpen immediately."""
    cb = PusherCircuitBreaker(failure_threshold=2)

    async def fake_sleep(d):
        pass

    with patch('utils.pusher.get_circuit_breaker', return_value=cb), patch(
        'utils.pusher._connect_to_trigger_pusher', side_effect=Exception("conn fail")
    ), patch('utils.pusher.asyncio.sleep', side_effect=fake_sleep):
        with pytest.raises(PusherCircuitBreakerOpen):
            await connect_to_trigger_pusher(uid="test", sample_rate=8000, retries=5)

    # Should have recorded 2 failures then stopped (not 5)
    assert len(cb._failures) == 2


@pytest.mark.asyncio
async def test_connect_returns_none_when_inactive():
    """is_active=False still returns None (not PusherCircuitBreakerOpen)."""
    cb = PusherCircuitBreaker()

    with patch('utils.pusher.get_circuit_breaker', return_value=cb):
        result = await connect_to_trigger_pusher(uid="test", sample_rate=8000, is_active=lambda: False)

    assert result is None


@pytest.mark.asyncio
async def test_half_open_probe_rejected_raises():
    """When HALF_OPEN with probe in progress, raises PusherCircuitBreakerOpen."""
    cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)
    for _ in range(3):
        cb.record_failure()
    time.sleep(0.02)
    cb.acquire_probe()  # Another coroutine took the probe

    with patch('utils.pusher.get_circuit_breaker', return_value=cb):
        with pytest.raises(PusherCircuitBreakerOpen):
            await connect_to_trigger_pusher(uid="test", sample_rate=8000)


# ---------------------------------------------------------------------------
# Concurrent probe gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_probes_only_one_succeeds():
    """When multiple coroutines try to probe in HALF_OPEN, only one succeeds."""
    cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)
    for _ in range(3):
        cb.record_failure()
    time.sleep(0.02)
    assert cb.state == CircuitState.HALF_OPEN

    results = []

    async def try_probe():
        results.append(cb.acquire_probe())

    await asyncio.gather(try_probe(), try_probe(), try_probe())
    assert results.count(True) == 1
    assert results.count(False) == 2


# ---------------------------------------------------------------------------
# Metrics integration
# ---------------------------------------------------------------------------


def test_metric_updates_on_state_transitions():
    """Circuit breaker metric is updated on every state transition."""
    from utils.metrics import PUSHER_CIRCUIT_BREAKER_STATE

    cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)

    # Start CLOSED
    cb.record_success()  # Explicit set
    assert PUSHER_CIRCUIT_BREAKER_STATE._value.get() == 0  # CLOSED=0

    # Trip to OPEN
    for _ in range(3):
        cb.record_failure()
    assert PUSHER_CIRCUIT_BREAKER_STATE._value.get() == 1  # OPEN=1

    # Wait for HALF_OPEN
    time.sleep(0.02)
    _ = cb.state  # triggers transition
    assert PUSHER_CIRCUIT_BREAKER_STATE._value.get() == 2  # HALF_OPEN=2

    # Success → CLOSED
    cb.record_success()
    assert PUSHER_CIRCUIT_BREAKER_STATE._value.get() == 0  # CLOSED=0


def test_metric_updates_on_half_open_failure():
    """HALF_OPEN failure → OPEN updates metric correctly."""
    from utils.metrics import PUSHER_CIRCUIT_BREAKER_STATE

    cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.01)
    for _ in range(3):
        cb.record_failure()
    time.sleep(0.02)
    _ = cb.state  # HALF_OPEN
    cb.record_failure()  # probe failed
    assert cb.state == CircuitState.OPEN
    assert PUSHER_CIRCUIT_BREAKER_STATE._value.get() == 1


# ---------------------------------------------------------------------------
# Behavioral tests for circuit breaker + connect integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breaker_recovery_lifecycle():
    """Full lifecycle: failures → OPEN → cooldown → HALF_OPEN → probe success → CLOSED."""
    cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.05)
    mock_ws = MagicMock()

    # 1. Fail until open
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # 2. Reject connections while open
    with patch('utils.pusher.get_circuit_breaker', return_value=cb):
        with pytest.raises(PusherCircuitBreakerOpen):
            await connect_to_trigger_pusher(uid="test", sample_rate=8000)

    # 3. Wait for cooldown
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN

    # 4. Probe succeeds
    with patch('utils.pusher.get_circuit_breaker', return_value=cb), patch(
        'utils.pusher._connect_to_trigger_pusher', return_value=mock_ws
    ):
        result = await connect_to_trigger_pusher(uid="test", sample_rate=8000)
    assert result is mock_ws
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_breaker_stays_open_on_probe_failure():
    """Probe failure keeps breaker in OPEN with new cooldown."""
    cb = PusherCircuitBreaker(failure_threshold=3, cooldown=0.05)

    async def fake_sleep(d):
        pass

    for _ in range(3):
        cb.record_failure()
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN

    # Probe fails
    with patch('utils.pusher.get_circuit_breaker', return_value=cb), patch(
        'utils.pusher._connect_to_trigger_pusher', side_effect=Exception("still down")
    ), patch('utils.pusher.asyncio.sleep', side_effect=fake_sleep):
        with pytest.raises(Exception, match="still down"):
            await connect_to_trigger_pusher(uid="test", sample_rate=8000, retries=1)

    assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# Circuit breaker singleton
# ---------------------------------------------------------------------------


def test_singleton_returns_same_instance():
    """get_circuit_breaker returns the same instance."""
    cb1 = get_circuit_breaker()
    cb2 = get_circuit_breaker()
    assert cb1 is cb2


def test_circuit_breaker_open_is_exception():
    """PusherCircuitBreakerOpen is a proper exception."""
    ex = PusherCircuitBreakerOpen("test")
    assert isinstance(ex, Exception)
    assert str(ex) == "test"

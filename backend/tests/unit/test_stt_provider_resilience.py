"""Tests for bounded live-STT provider circuit behavior."""

from __future__ import annotations

from utils.stt.provider_resilience import ProviderCircuitBreaker


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_circuit_opens_after_threshold_and_allows_one_recovery_probe():
    clock = Clock()
    circuit = ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=30, clock=clock)

    assert circuit.allow_request() is True
    circuit.record_failure()
    assert circuit.allow_request() is True
    circuit.record_failure()
    assert circuit.allow_request() is False

    clock.now = 30
    assert circuit.allow_request() is True
    assert circuit.allow_request() is False

    circuit.record_success()
    assert circuit.allow_request() is True


def test_capacity_rejection_does_not_poison_provider_health():
    circuit = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30)

    circuit.record_rejection('capacity_full')

    assert circuit.allow_request() is True


def test_expected_rejection_releases_a_half_open_probe():
    clock = Clock()
    circuit = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30, clock=clock)
    circuit.record_failure()
    clock.now = 30
    assert circuit.allow_request() is True

    circuit.record_rejection('capacity_full')

    assert circuit.state == 'closed'
    assert circuit.allow_request() is True

from __future__ import annotations

from unittest.mock import MagicMock

from utils.llm import gateway_resilience
from utils.llm.gateway_resilience import GatewayCircuitBreaker, gateway_transport_timeout


def test_gateway_transport_timeout_bounds_connect_and_first_byte(monkeypatch) -> None:
    monkeypatch.setenv('OMI_LLM_GATEWAY_CONNECT_TIMEOUT_SECONDS', '2.5')
    monkeypatch.setenv('OMI_LLM_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS', '11')

    timeout = gateway_transport_timeout()

    assert timeout.connect == 2.5
    assert timeout.pool == 2.5
    assert timeout.read == 11.0
    assert timeout.write == 11.0


def test_gateway_circuit_bypasses_until_bounded_cooldown_expires() -> None:
    now = [100.0]
    circuit = GatewayCircuitBreaker(failure_threshold=2, cooldown_seconds=30.0, monotonic=lambda: now[0])

    assert circuit.allow_request() is True
    circuit.record_transport_failure()
    assert circuit.allow_request() is True
    circuit.record_transport_failure()
    assert circuit.allow_request() is False

    now[0] += 30.0
    assert circuit.allow_request() is True


def test_gateway_first_byte_observation_has_bounded_feature_and_outcome_labels(monkeypatch) -> None:
    histogram = MagicMock()
    child = MagicMock()
    histogram.labels.return_value = child
    now = iter((103.25,))
    monkeypatch.setattr(gateway_resilience, 'LLM_GATEWAY_CLIENT_FIRST_BYTE_SECONDS', histogram)
    monkeypatch.setattr(gateway_resilience.time, 'monotonic', lambda: next(now))

    gateway_resilience.observe_gateway_first_byte(feature='chat_agent', started_at=100.0, outcome='transport_failure')

    histogram.labels.assert_called_once_with(feature='chat_agent', outcome='transport_failure')
    child.observe.assert_called_once_with(3.25)

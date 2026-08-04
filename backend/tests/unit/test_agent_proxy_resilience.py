import asyncio
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "agent_proxy_resilience",
    Path(__file__).resolve().parents[2] / "agent-proxy" / "resilience.py",
)
resilience = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(resilience)


class TestClassifyError:
    def test_cancellation_is_aborted(self):
        assert resilience.classify_error(asyncio.CancelledError()) == "aborted"

    def test_network_shapes_are_transient(self):
        assert resilience.classify_error(ConnectionResetError("peer reset")) == "transient"
        assert resilience.classify_error(TimeoutError()) == "transient"
        assert resilience.classify_error(RuntimeError("HTTP 529 overloaded")) == "transient"

    def test_auth_shapes(self):
        assert resilience.classify_error(RuntimeError("401 invalid_token")) == "auth"

    def test_unknown_is_internal(self):
        assert resilience.classify_error(ValueError("weird state")) == "internal"


class TestCircuitOpen:
    def test_closed_below_threshold(self):
        assert resilience.circuit_open({"restartFailures": 2, "lastRestartFailureAt": 1000.0}, now_ts=1001.0) is False

    def test_opens_at_threshold_within_cooldown(self):
        vm = {"restartFailures": 3, "lastRestartFailureAt": 1000.0}
        assert resilience.circuit_open(vm, now_ts=1000.0 + resilience.COOLDOWN_SECONDS - 1) is True

    def test_half_open_after_cooldown(self):
        vm = {"restartFailures": 3, "lastRestartFailureAt": 1000.0}
        assert resilience.circuit_open(vm, now_ts=1000.0 + resilience.COOLDOWN_SECONDS + 1) is False

    def test_malformed_state_fails_open(self):
        assert resilience.circuit_open({"restartFailures": 5}, now_ts=1000.0) is False

    def test_missing_fields_closed(self):
        assert resilience.circuit_open({}, now_ts=1000.0) is False

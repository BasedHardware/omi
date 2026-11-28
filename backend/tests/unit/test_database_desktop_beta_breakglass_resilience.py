"""Unit tests verifying defensive boundary guards in desktop_beta_breakglass."""

from datetime import datetime, timezone
from unittest.mock import patch
import pytest

from database.desktop_beta_breakglass import (
    _execute,
    _request,
    emergency_rollout_beta,
    rollback_beta,
)


def _valid_request(operation: str = "rollback") -> dict:
    return {
        "current_release_id": "v0.12.84+12084-macos",
        "target_release_id": "v0.12.73+12073-macos",
        "expected_generation": 4,
        "actor": "release-operator",
        "reason": "Beta crash loop on startup",
        "incident_url": "https://github.com/BasedHardware/omi/issues/12345",
        "request_id": "https://github.com/BasedHardware/omi/actions/runs/12345/attempts/1",
        "normal_path_unavailable": "runner offline" if operation == "rollout" else None,
    }


def test_request_rejects_non_dict_payload():
    """Verify _request raises ValueError when request payload is not a dictionary."""
    with pytest.raises(ValueError, match="request must be a dictionary"):
        _request(None, "rollback")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="request must be a dictionary"):
        _request("not-a-dict", "rollback")  # type: ignore[arg-type]


def test_request_rejects_unsupported_operation():
    """Verify _request raises ValueError when operation is not rollback or rollout."""
    req = _valid_request()
    with pytest.raises(ValueError, match="unsupported breakglass operation"):
        _request(req, "arbitrary_operation")


def test_request_rejects_boolean_and_negative_generation():
    """Verify _request strictly rejects booleans and negative values for expected_generation."""
    req = _valid_request()
    req["expected_generation"] = True
    with pytest.raises(ValueError, match="expected_generation is invalid"):
        _request(req, "rollback")

    req["expected_generation"] = -1
    with pytest.raises(ValueError, match="expected_generation is invalid"):
        _request(req, "rollback")


def test_request_rejects_invalid_normal_path_type():
    """Verify _request raises ValueError when normal_path_unavailable is non-string."""
    req = _valid_request("rollback")
    req["normal_path_unavailable"] = 12345
    with pytest.raises(ValueError, match="normal_path_unavailable must be a string or None"):
        _request(req, "rollback")


def test_execute_rejects_non_dict_early():
    """Verify rollback_beta and emergency_rollout_beta fail fast on non-dict request."""
    with pytest.raises(ValueError, match="request must be a dictionary"):
        rollback_beta(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="request must be a dictionary"):
        emergency_rollout_beta(None, {})  # type: ignore[arg-type]


def test_execute_rollout_requires_dict_manifest():
    """Verify emergency_rollout_beta requires a dictionary manifest."""
    req = _valid_request("rollout")
    with pytest.raises(ValueError, match="emergency manifest is required"):
        emergency_rollout_beta(req, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="emergency manifest is required"):
        emergency_rollout_beta(req, "not a manifest")  # type: ignore[arg-type]


def test_execute_coerces_naive_datetime():
    """Verify naive datetime passed as now is coerced with timezone.utc."""
    req = _valid_request("rollback")
    naive_dt = datetime(2026, 9, 30, 12, 0, 0)
    mock_client = type("MockClient", (), {
        "transaction": lambda self: None,
        "collection": lambda self, *_: type("MockColl", (), {
            "document": lambda self, *_: None
        })()
    })()
    # Test that _commit is called with timezone-aware datetime
    with patch("database.desktop_beta_breakglass._commit") as mock_commit:
        mock_commit.return_value = {"status": "ok"}
        _execute("rollback", req, firestore_client=mock_client, now=naive_dt)
        called_dt = mock_commit.call_args.kwargs.get("now") or mock_commit.call_args[0][8]
        assert called_dt.tzinfo == timezone.utc

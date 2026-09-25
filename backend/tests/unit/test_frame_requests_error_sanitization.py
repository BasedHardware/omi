import pytest

# Import the private helper directly for unit testing purposes.
# In production code the function is considered internal, but testing it
# ensures the sanitisation contract remains stable.
from backend.routers.frame_requests import _sanitize_frame_request_error


@pytest.mark.parametrize(
    "message,expected_key",
    [
        ("Invalid transition from PENDING to COMPLETED", "invalid_state_transition"),
        ("Validation failed: missing required field", "validation_error"),
        ("Resource already exists in the store", "conflict_error"),
        ("Some completely unrelated error", "bad_request"),
    ],
)
def test_sanitize_frame_request_error(message: str, expected_key: str):
    """
    Verify that various ValueError messages are mapped to the correct
    machine‑readable error keys and that no raw exception text leaks.
    """
    exc = ValueError(message)
    sanitized = _sanitize_frame_request_error(exc)

    # The result must be a dict with the expected structure.
    assert isinstance(sanitized, dict)
    assert sanitized["error"] == expected_key
    # The generic description should never expose the original message.
    assert sanitized["detail"] == "The request could not be processed due to invalid input."

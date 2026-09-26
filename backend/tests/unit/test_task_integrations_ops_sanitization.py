import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

try:
    import utils.task_integrations_ops as ops
except ImportError:
    import backend.utils.task_integrations_ops as ops  # noqa: F401

refresh_oauth_token = ops.refresh_oauth_token


@pytest.mark.asyncio
async def test_refresh_oauth_token_sanitizes_unexpected_exception():
    """Verify that an unexpected RuntimeError from the HTTP client is caught and
    re-raised as a generic HTTPException(500) that does NOT echo any raw internal
    detail back to the caller."""
    integration = {
        "refresh_token": "valid_refresh_token",
    }

    # Patch _build_refresh_request so we bypass env-var credential checks and
    # jump straight to the client.post() call where we inject a RuntimeError.
    fake_req = {
        "type": "form",
        "url": "https://example.com/token",
        "headers": {},
        "data": {},
    }

    client_instance = AsyncMock()
    client_instance.post.side_effect = RuntimeError("Sensitive socket exception with internal credentials")

    with patch.object(ops, "_build_refresh_request", return_value=fake_req):
        with pytest.raises(HTTPException) as exc_info:
            await refresh_oauth_token("uid_123", "google_tasks", integration, client=client_instance)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Error refreshing token"
    assert "Sensitive socket" not in exc_info.value.detail
    assert "credentials" not in exc_info.value.detail

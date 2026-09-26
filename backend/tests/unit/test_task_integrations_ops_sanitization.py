import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from backend.utils.task_integrations_ops import refresh_oauth_token


@pytest.mark.asyncio
async def test_refresh_oauth_token_sanitizes_unexpected_exception():
    integration = {
        "refresh_token": "valid_refresh_token",
        "app_key": "google_tasks",
    }
    with patch("backend.utils.task_integrations_ops.get_task_integration_oauth_credentials") as mock_creds, \
         patch("backend.utils.task_integrations_ops.httpx.AsyncClient") as mock_client:
        mock_creds.return_value = ("client_id", "client_secret")
        client_instance = AsyncMock()
        client_instance.post.side_effect = RuntimeError("Sensitive socket exception with internal credentials")
        mock_client.return_value.__aenter__.return_value = client_instance

        with pytest.raises(HTTPException) as exc_info:
            await refresh_oauth_token("uid_123", "google_tasks", integration, client=client_instance)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Error refreshing token"
        assert "Sensitive socket" not in exc_info.value.detail
        assert "credentials" not in exc_info.value.detail

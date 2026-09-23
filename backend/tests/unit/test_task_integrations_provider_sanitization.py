"""Unit tests for task_integrations router exception detail sanitization.

Verifies that raw provider exceptions (tokens, hostnames, error details) do not
leak through the HTTP 500 responses from task-integration workspace/project/team endpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

import routers.task_integrations as task_routes


@pytest.mark.asyncio
async def test_get_asana_workspaces_masks_provider_exception(monkeypatch):
    """RuntimeError carrying a bearer token must not appear in the 500 HTTP detail."""
    # Arrange: fake connected Asana integration
    fake_data = {
        "connected": True,
        "access_token": "asana_token_abc",
        "provider": "asana",
    }
    leak_text = "Bearer lin_api_sec_token_9999 invalid for workspace gid=12345"

    monkeypatch.setattr(task_routes, "run_blocking", AsyncMock(return_value=fake_data))
    monkeypatch.setattr(task_routes, "ensure_valid_oauth_token", AsyncMock(return_value=fake_data))

    # Make perform_request_with_token_retry raise RuntimeError with internal details
    async def _raise(*args, **kwargs):
        raise RuntimeError(leak_text)

    monkeypatch.setattr(task_routes, "perform_request_with_token_retry", _raise)

    # Act
    with pytest.raises(HTTPException) as exc_info:
        await task_routes.get_asana_workspaces(uid="uid-test-003")

    # Assert
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch workspaces from task integration provider."
    assert "lin_api_sec_token_9999" not in exc_info.value.detail
    assert "Bearer" not in exc_info.value.detail
    assert "12345" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_asana_projects_masks_provider_exception(monkeypatch):
    """RuntimeError from the Asana project fetch must be masked in the 500 detail."""
    fake_data = {"connected": True, "access_token": "asana_token_xyz"}
    leak_text = "host=asana-internal-api.corp:8443 SSL cert mismatch token=asana_api_secret_99"

    monkeypatch.setattr(task_routes, "run_blocking", AsyncMock(return_value=fake_data))
    monkeypatch.setattr(task_routes, "ensure_valid_oauth_token", AsyncMock(return_value=fake_data))

    async def _raise(*args, **kwargs):
        raise RuntimeError(leak_text)

    monkeypatch.setattr(task_routes, "perform_request_with_token_retry", _raise)

    with pytest.raises(HTTPException) as exc_info:
        await task_routes.get_asana_projects(workspace_gid="ws-999", uid="uid-test-004")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch projects from task integration provider."
    assert "asana-internal-api.corp" not in exc_info.value.detail
    assert "asana_api_secret_99" not in exc_info.value.detail

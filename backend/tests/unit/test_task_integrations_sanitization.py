import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Stub jinja2 in case it is absent in the test environment so task_integrations can import cleanly.
if "jinja2" not in sys.modules:
    sys.modules["jinja2"] = MagicMock()

from routers.task_integrations import (
    get_asana_projects,
    get_asana_workspaces,
    get_clickup_lists,
    get_clickup_spaces,
    get_clickup_teams,
)

SENSITIVE_TOKEN = "secret_abc123"
SENSITIVE_ERROR = (
    f"ConnectError: https://api.clickup.com/api/v2?token={SENSITIVE_TOKEN}&db=postgres://user:pass@internal:5432/db"
)


@pytest.fixture
def mock_valid_integration():
    valid_data = {"connected": True, "access_token": "valid_token"}
    with (
        patch("routers.task_integrations.run_blocking", new=AsyncMock(return_value=valid_data)),
        patch("routers.task_integrations.ensure_valid_oauth_token", new=AsyncMock(return_value=valid_data)),
    ):
        yield


@pytest.mark.asyncio
async def test_get_asana_workspaces_exception_sanitized(mock_valid_integration, caplog):
    with patch(
        "routers.task_integrations.perform_request_with_token_retry",
        new=AsyncMock(side_effect=RuntimeError(SENSITIVE_ERROR)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_asana_workspaces(uid="user_123")

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Failed to fetch Asana workspaces due to an internal error"
        assert SENSITIVE_TOKEN not in exc_info.value.detail
        assert "postgres://" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_asana_projects_exception_sanitized(mock_valid_integration, caplog):
    with patch(
        "routers.task_integrations.perform_request_with_token_retry",
        new=AsyncMock(side_effect=RuntimeError(SENSITIVE_ERROR)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_asana_projects(workspace_gid="workspace_456", uid="user_123")

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Failed to fetch Asana projects due to an internal error"
        assert SENSITIVE_TOKEN not in exc_info.value.detail
        assert "postgres://" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_clickup_teams_exception_sanitized(mock_valid_integration, caplog):
    with patch(
        "routers.task_integrations.perform_request_with_token_retry",
        new=AsyncMock(side_effect=RuntimeError(SENSITIVE_ERROR)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_clickup_teams(uid="user_123")

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Failed to fetch ClickUp teams due to an internal error"
        assert SENSITIVE_TOKEN not in exc_info.value.detail
        assert "postgres://" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_clickup_spaces_exception_sanitized(mock_valid_integration, caplog):
    with patch(
        "routers.task_integrations.perform_request_with_token_retry",
        new=AsyncMock(side_effect=RuntimeError(SENSITIVE_ERROR)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_clickup_spaces(team_id="team_789", uid="user_123")

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Failed to fetch ClickUp spaces due to an internal error"
        assert SENSITIVE_TOKEN not in exc_info.value.detail
        assert "postgres://" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_clickup_lists_exception_sanitized(mock_valid_integration, caplog):
    with patch(
        "routers.task_integrations.perform_request_with_token_retry",
        new=AsyncMock(side_effect=RuntimeError(SENSITIVE_ERROR)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_clickup_lists(space_id="space_101", uid="user_123")

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Failed to fetch ClickUp lists due to an internal error"
        assert SENSITIVE_TOKEN not in exc_info.value.detail
        assert "postgres://" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_http_exception_passthrough(mock_valid_integration):
    with patch(
        "routers.task_integrations.perform_request_with_token_retry",
        new=AsyncMock(side_effect=HTTPException(status_code=403, detail="Forbidden resource")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_asana_workspaces(uid="user_123")

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Forbidden resource"

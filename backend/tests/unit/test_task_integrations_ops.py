"""Characterization tests for external task creation in utils/task_integrations_ops.py.

Pins Todoist create success and main error paths before/after the ops extract from routers.
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils import task_integrations_ops as ops


def _mock_response(status_code: int, json_data=None, text: str = ""):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = text
    if json_data is not None:
        response.json.return_value = json_data
    return response


@pytest.mark.asyncio
async def test_create_task_todoist_success():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _mock_response(201, {"id": "todoist-task-42"})

    integration = {"connected": True, "access_token": "tok-todoist"}
    due = datetime(2026, 7, 15, tzinfo=timezone.utc)

    result = await ops.create_task_internal(
        uid="uid-1",
        app_key="todoist",
        integration=integration,
        title="Buy groceries",
        description="Milk and eggs",
        due_date=due,
        client=client,
    )

    assert result == {"success": True, "external_task_id": "todoist-task-42"}
    client.post.assert_awaited_once()
    call_kwargs = client.post.call_args.kwargs
    assert call_kwargs["json"]["content"] == "Buy groceries"
    assert call_kwargs["json"]["description"] == "Milk and eggs"
    assert call_kwargs["json"]["due_string"] == "2026-07-15"


@pytest.mark.asyncio
async def test_create_task_todoist_api_error_marks_disconnected():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _mock_response(401, text="Unauthorized")

    integration = {"connected": True, "access_token": "expired-token"}

    with patch.object(ops, "run_blocking", new=AsyncMock()) as mock_run_blocking:
        result = await ops.create_task_internal(
            uid="uid-2",
            app_key="todoist",
            integration=integration,
            title="Stale task",
            client=client,
        )

    assert result["success"] is False
    assert result["error_code"] == "api_error"
    mock_run_blocking.assert_awaited_once()
    saved = mock_run_blocking.call_args[0][4]
    assert saved["connected"] is False


@pytest.mark.asyncio
async def test_create_task_missing_access_token():
    result = await ops.create_task_internal(
        uid="uid-3",
        app_key="todoist",
        integration={"connected": True},
        title="No token task",
    )
    assert result == {
        "success": False,
        "error": "No access token for todoist",
        "error_code": "no_access_token",
    }

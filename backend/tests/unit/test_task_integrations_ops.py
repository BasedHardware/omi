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
    assert result["retryable"] is False
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
        "retryable": False,
        "ambiguous": False,
    }


@pytest.mark.asyncio
async def test_create_task_todoist_server_failure_is_ambiguous_not_retryable():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _mock_response(503, text="Unavailable")

    result = await ops.create_task_internal(
        uid="uid-4",
        app_key="todoist",
        integration={"connected": True, "access_token": "token"},
        title="Retry task",
        client=client,
    )

    assert result["success"] is False
    assert result["status_code"] == 503
    assert result["retryable"] is False
    assert result["ambiguous"] is True


@pytest.mark.asyncio
async def test_create_task_todoist_rate_limit_is_safe_to_retry():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _mock_response(429, text="Rate limited")

    result = await ops.create_task_internal(
        uid="uid-4",
        app_key="todoist",
        integration={"connected": True, "access_token": "token"},
        title="Retry task",
        client=client,
    )

    assert result["retryable"] is True
    assert result["ambiguous"] is False


@pytest.mark.asyncio
async def test_create_task_todoist_missing_identity_is_ambiguous_not_string_none():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _mock_response(201, {})

    result = await ops.create_task_internal(
        uid="uid-4",
        app_key="todoist",
        integration={"connected": True, "access_token": "token"},
        title="Ambiguous task",
        client=client,
    )

    assert result == {
        "success": False,
        "error": "Provider response omitted task identity",
        "error_code": "invalid_provider_response",
        "retryable": False,
        "ambiguous": True,
    }, "provider success without task identity must be reported as ambiguous"


@pytest.mark.asyncio
async def test_create_task_unexpected_success_status_is_ambiguous():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _mock_response(202, {"id": "possibly-created"})

    result = await ops.create_task_internal(
        uid="uid-4",
        app_key="todoist",
        integration={"connected": True, "access_token": "token"},
        title="Ambiguous task",
        client=client,
    )

    assert result == {
        "success": False,
        "error": "Todoist response did not contain a completed task",
        "error_code": "invalid_provider_response",
        "status_code": 202,
        "retryable": False,
        "ambiguous": True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("response timed out"),
        httpx.ReadError("response failed"),
        httpx.WriteTimeout("request write timed out"),
        httpx.WriteError("request write failed"),
    ],
)
async def test_create_task_transport_failure_is_ambiguous_not_blindly_retryable(error):
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = error

    result = await ops.create_task_internal(
        uid="uid-4",
        app_key="todoist",
        integration={"connected": True, "access_token": "token"},
        title="Ambiguous task",
        client=client,
    )

    assert result["error_code"] == "transport_error"
    assert result["retryable"] is False
    assert result["ambiguous"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        httpx.PoolTimeout("connection pool exhausted"),
        httpx.ConnectTimeout("connection timed out"),
        httpx.ConnectError("connection failed"),
    ],
)
async def test_create_task_pre_send_transport_failure_is_safe_to_retry(error):
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = error

    result = await ops.create_task_internal(
        uid="uid-4",
        app_key="todoist",
        integration={"connected": True, "access_token": "token"},
        title="Retry task",
        client=client,
    )

    assert result["error_code"] == "transport_error"
    assert result["retryable"] is True
    assert result["ambiguous"] is False


@pytest.mark.asyncio
async def test_asana_retry_reuses_injected_client_for_refresh_and_retry():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = [
        _mock_response(401, text="expired"),
        _mock_response(200, {"access_token": "fresh-token", "expires_in": 3600}),
        _mock_response(201, {"data": {"gid": "asana-task-42"}}),
    ]
    integration = {
        "connected": True,
        "access_token": "expired-token",
        "refresh_token": "refresh-token",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "workspace_gid": "workspace-1",
    }

    with (
        patch.dict(os.environ, {"ASANA_CLIENT_ID": "client-id", "ASANA_CLIENT_SECRET": "client-secret"}),
        patch.object(ops, "run_blocking", new=AsyncMock()) as mock_run_blocking,
        patch.object(ops, "get_http_client", side_effect=AssertionError("must reuse injected client")),
    ):
        result = await ops.create_task_internal(
            uid="uid-asana",
            app_key="asana",
            integration=integration,
            title="Retried task",
            client=client,
        )

    assert result == {"success": True, "external_task_id": "asana-task-42"}
    assert client.post.await_count == 3
    calls = client.post.await_args_list
    assert calls[0].args[0] == "https://app.asana.com/api/1.0/tasks"
    assert calls[0].kwargs["headers"]["Authorization"] == "Bearer expired-token"
    assert calls[1].args[0] == "https://app.asana.com/-/oauth_token"
    assert calls[2].args[0] == "https://app.asana.com/api/1.0/tasks"
    assert calls[2].kwargs["headers"]["Authorization"] == "Bearer fresh-token"
    mock_run_blocking.assert_awaited_once()

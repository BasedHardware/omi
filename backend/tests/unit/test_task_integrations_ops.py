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
async def test_create_task_todoist_success(monkeypatch):
    monkeypatch.setattr(ops.notifications_db, "resolve_user_timezone", lambda uid: "UTC")
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


def test_compute_expires_at_valid_and_numeric_strings():
    now_before = datetime.now(timezone.utc)
    for sample in [3600, "3600", 3600.0, "3600.5"]:
        iso = ops.compute_expires_at(sample)
        assert iso is not None
        parsed = datetime.fromisoformat(iso)
        assert parsed >= now_before
        diff = (parsed - now_before).total_seconds()
        assert 3590 <= diff <= 3615


def test_compute_expires_at_invalid_and_edge_values():
    invalid_cases = [
        None,
        True,
        False,
        "",
        "   ",
        "invalid_seconds",
        -10,
        "-10",
        0,
        "0",
        float("nan"),
        float("inf"),
        float("-inf"),
        "nan",
        "inf",
        "-inf",
        [],
        {},
        10**25,
    ]
    for case in invalid_cases:
        assert ops.compute_expires_at(case) is None, f"Expected None for {case!r}"


@pytest.mark.asyncio
async def test_refresh_oauth_token_with_string_expires_in():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _mock_response(
        200,
        {"access_token": "new-token-123", "refresh_token": "new-refresh-456", "expires_in": "7200"},
    )
    integration = {
        "connected": True,
        "access_token": "stale-access",
        "refresh_token": "stale-refresh",
    }

    with (
        patch.dict(os.environ, {"ASANA_CLIENT_ID": "client-id", "ASANA_CLIENT_SECRET": "client-secret"}),
        patch.object(ops, "run_blocking", new=AsyncMock()) as mock_run_blocking,
    ):
        result = await ops.refresh_oauth_token("uid-asana", "asana", integration, client=client)

    assert result["access_token"] == "new-token-123"
    assert result["refresh_token"] == "new-refresh-456"
    assert "expires_at" in result
    mock_run_blocking.assert_awaited_once()
    saved = mock_run_blocking.call_args[0][4]
    assert saved["access_token"] == "new-token-123"
    assert saved["refresh_token"] == "new-refresh-456"
    assert "expires_at" in saved


@pytest.mark.asyncio
async def test_refresh_oauth_token_sanitizes_unexpected_exception():
    client = AsyncMock(spec=httpx.AsyncClient)
    sensitive_detail = "ConnectionError: postgres://user:pass@10.0.0.5:5432/db?token=super_secret_token"
    client.post.side_effect = RuntimeError(sensitive_detail)

    integration = {"connected": True, "refresh_token": "stale-refresh"}

    with patch.dict(os.environ, {"ASANA_CLIENT_ID": "client-id", "ASANA_CLIENT_SECRET": "client-secret"}):
        with pytest.raises(ops.HTTPException) as exc_info:
            await ops.refresh_oauth_token("uid-asana", "asana", integration, client=client)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to refresh Asana token due to an internal error"
    assert "super_secret_token" not in exc_info.value.detail
    assert "10.0.0.5" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_refresh_oauth_token_invalid_expires_in_sets_none():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _mock_response(
        200,
        {"access_token": "new-token-123", "refresh_token": "new-refresh-456", "expires_in": "invalid"},
    )
    integration = {
        "connected": True,
        "access_token": "stale-access",
        "refresh_token": "stale-refresh",
        "expires_at": "2099-01-01T00:00:00Z",
    }

    with (
        patch.dict(os.environ, {"ASANA_CLIENT_ID": "client-id", "ASANA_CLIENT_SECRET": "client-secret"}),
        patch.object(ops, "run_blocking", new=AsyncMock()) as mock_run_blocking,
    ):
        result = await ops.refresh_oauth_token("uid-asana", "asana", integration, client=client)

    assert result["access_token"] == "new-token-123"
    assert result["expires_at"] is None
    mock_run_blocking.assert_awaited_once()
    saved = mock_run_blocking.call_args[0][4]
    assert saved["expires_at"] is None


@pytest.mark.asyncio
async def test_create_task_internal_sanitizes_exception_in_returned_dict():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = RuntimeError(
        "Failed connect to https://service:secr3t_tok3n_12345@example.com/api?key=tok_987654321"
    )
    integration = {"connected": True, "access_token": "valid-token"}

    result = await ops.create_task_internal(
        uid="uid-1",
        app_key="todoist",
        integration=integration,
        title="Test task",
        client=client,
    )

    assert result["success"] is False
    assert "secr3t_tok3n_12345" not in result["error"]
    assert "tok_987654321" not in result["error"]


@pytest.mark.asyncio
async def test_handle_oauth_callback_with_string_expires_in():
    import sys
    from fastapi import Request

    original_jinja2 = sys.modules.get("jinja2")
    try:
        try:
            import jinja2  # noqa: F401
        except ImportError:
            sys.modules["jinja2"] = MagicMock()
        from routers import task_integrations as ti

        class MockProviderConfig(ti.OAuthProviderConfig):
            async def fetch_additional_data(self, client, access_token):
                return {"user_gid": "user-gid-999"}

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _mock_response(
            200,
            {
                "access_token": "callback-access-tok",
                "refresh_token": "callback-refresh-tok",
                "expires_in": "3600",
            },
        )
        provider_config = MockProviderConfig(
            token_endpoint="https://example.com/oauth/token",
            token_request_type="form",
            token_request_data={"code": "auth-code"},
        )
        request = MagicMock(spec=Request)

        with (
            patch.object(ti, "get_http_client", return_value=client),
            patch.object(ti, "validate_and_consume_oauth_state", return_value={"uid": "user-42", "app_key": "asana"}),
            patch.object(ti, "run_blocking", new=AsyncMock()) as mock_run_blocking,
            patch.object(ti, "render_oauth_response", return_value="render_called") as mock_render,
        ):
            result = await ti.handle_oauth_callback(
                request=request,
                app_key="asana",
                code="auth-code",
                state="state-tok",
                provider_config=provider_config,
            )

        assert result == "render_called"
        mock_run_blocking.assert_awaited_once()
        saved = mock_run_blocking.call_args[0][4]
        assert saved["access_token"] == "callback-access-tok"
        assert saved["refresh_token"] == "callback-refresh-tok"
        assert saved["user_gid"] == "user-gid-999"
        assert "expires_at" in saved
        mock_render.assert_called_once()
        assert mock_render.call_args[1]["success"] is True

        # Now verify callback with invalid expires_in clears expires_at (sets it to None)
        client.post.return_value = _mock_response(
            200,
            {
                "access_token": "callback-access-tok-2",
                "refresh_token": "callback-refresh-tok-2",
                "expires_in": True,  # boolean should be rejected -> None
            },
        )
        mock_run_blocking.reset_mock()
        with (
            patch.object(ti, "get_http_client", return_value=client),
            patch.object(ti, "validate_and_consume_oauth_state", return_value={"uid": "user-42", "app_key": "asana"}),
            patch.object(ti, "run_blocking", new=AsyncMock()) as mock_run_blocking,
            patch.object(ti, "render_oauth_response", return_value="render_called"),
        ):
            await ti.handle_oauth_callback(
                request=request,
                app_key="asana",
                code="auth-code-2",
                state="state-tok-2",
                provider_config=provider_config,
            )

        mock_run_blocking.assert_awaited_once()
        saved_invalid = mock_run_blocking.call_args[0][4]
        assert saved_invalid["expires_at"] is None
    finally:
        if original_jinja2 is None:
            sys.modules.pop("jinja2", None)
        else:
            sys.modules["jinja2"] = original_jinja2

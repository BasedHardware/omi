import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "0123456789abcdef0123456789abcdef")

from models.app import ChatTool
from utils.retrieval.tools import app_tools

PARAMETERS = {
    "properties": {
        "query": {"type": "string", "description": "query string"},
    },
    "required": ["query"],
}
CONFIG = {"configurable": {"user_id": "test-uid-123"}}


def _allowing_breaker():
    breaker = MagicMock()
    breaker.allow_request.return_value = True
    return breaker


@pytest.fixture
def mock_dependencies():
    with (
        patch.object(app_tools, "is_app_webhook_disabled", return_value=False),
        patch.object(app_tools, "get_cached_user_geolocation", return_value=None),
        patch.object(app_tools, "get_webhook_circuit_breaker", return_value=_allowing_breaker()),
        patch.object(app_tools, "record_app_webhook_failure", return_value=0),
        patch.object(app_tools, "_handle_app_webhook_disable"),
    ):
        yield


@pytest.mark.asyncio
async def test_tool_endpoint_exception_leak_prevented(mock_dependencies, caplog):
    tool = ChatTool(
        name="test_tool", description="test description", endpoint="https://api.example.com/test", parameters=PARAMETERS
    )
    structured = app_tools.create_app_tool(tool, "app-1", "TestApp")

    sensitive_path = "/secrets/admin_token.key"
    client = AsyncMock()
    client.request = AsyncMock(side_effect=ConnectionRefusedError(sensitive_path))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client), caplog.at_level("ERROR"):
        token = app_tools.agent_config_context.set(CONFIG)
        try:
            result = await structured.ainvoke({"query": "search query"})
        finally:
            app_tools.agent_config_context.reset(token)

    assert result == "Error calling test_tool: Request failed."
    assert sensitive_path not in result
    assert "admin_token" not in result
    assert any(
        record.levelname == "ERROR"
        and "Error calling test_tool:" in record.message
        and "admin_token" not in record.message
        and "/sec***oken.key" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_tool_endpoint_runtime_error_sanitized_in_log(mock_dependencies, caplog):
    tool = ChatTool(
        name="secure_tool", description="secure tool", endpoint="https://api.example.com/secure", parameters=PARAMETERS
    )
    structured = app_tools.create_app_tool(tool, "app-2", "SecureApp")

    secret_token = "secret_token_123456789"
    client = AsyncMock()
    client.request = AsyncMock(side_effect=RuntimeError(f"Connection failed with token {secret_token}"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client), caplog.at_level("ERROR"):
        token = app_tools.agent_config_context.set(CONFIG)
        try:
            result = await structured.ainvoke({"query": "fetch"})
        finally:
            app_tools.agent_config_context.reset(token)

    assert result == "Error calling secure_tool: Request failed."
    assert secret_token not in result

    error_logs = [
        r.message for r in caplog.records if r.levelname == "ERROR" and "Error calling secure_tool:" in r.message
    ]
    assert len(error_logs) == 1
    assert secret_token not in error_logs[0]
    assert "secr***6789" in error_logs[0]


@pytest.mark.asyncio
async def test_remote_payload_error_sanitization_dict_error_field(mock_dependencies):
    tool = ChatTool(
        name="dict_tool", description="desc", endpoint="https://api.example.com/dict", parameters=PARAMETERS
    )
    structured = app_tools.create_app_tool(tool, "app-3", "DictApp")

    secret_key = "secret_api_key_987654321"
    response = MagicMock(status_code=500)
    response.json.return_value = {"error": f"Invalid token: {secret_key}"}
    client = AsyncMock()
    client.request = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        token = app_tools.agent_config_context.set(CONFIG)
        try:
            result = await structured.ainvoke({"query": "test"})
        finally:
            app_tools.agent_config_context.reset(token)

    assert secret_key not in result
    assert "secr***4321" in result
    assert result == "Error calling dict_tool: HTTP 500 - Invalid token: secr***4321"


@pytest.mark.asyncio
async def test_remote_payload_error_sanitization_dict_fallback(mock_dependencies):
    tool = ChatTool(
        name="fallback_tool", description="desc", endpoint="https://api.example.com/fallback", parameters=PARAMETERS
    )
    structured = app_tools.create_app_tool(tool, "app-4", "FallbackApp")

    email = "admin@supersecret.org"
    response = MagicMock(status_code=500)
    response.json.return_value = {"details": f"Failed for {email}"}
    client = AsyncMock()
    client.request = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        token = app_tools.agent_config_context.set(CONFIG)
        try:
            result = await structured.ainvoke({"query": "test"})
        finally:
            app_tools.agent_config_context.reset(token)

    assert email not in result
    assert "a***n@supersecret.org" in result
    assert "Error calling fallback_tool: HTTP 500 -" in result


@pytest.mark.asyncio
async def test_remote_payload_error_sanitization_raw_text(mock_dependencies):
    tool = ChatTool(
        name="text_tool", description="desc", endpoint="https://api.example.com/text", parameters=PARAMETERS
    )
    structured = app_tools.create_app_tool(tool, "app-5", "TextApp")

    secret_token = "token_123456789"
    response = MagicMock(status_code=502)
    response.json.side_effect = ValueError("Not JSON")
    response.text = f"Bad Gateway: upstream token {secret_token}"
    client = AsyncMock()
    client.request = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        token = app_tools.agent_config_context.set(CONFIG)
        try:
            result = await structured.ainvoke({"query": "test"})
        finally:
            app_tools.agent_config_context.reset(token)

    assert secret_token not in result
    assert "toke***6789" in result
    assert result == "Error calling text_tool: HTTP 502 - Bad Gateway: upstream token toke***6789"

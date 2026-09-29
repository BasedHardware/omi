"""Unit tests verifying exception sanitization in app retrieval tools and MCP dispatch.

Failure-Class: none
Ensures raw exception details from external HTTP or MCP tool calls are never returned directly in tool output strings.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import utils.retrieval.tools.app_tools as app_tools
from models.app import ChatTool

SENTINEL_ERROR = "SENTINEL_INTERNAL_LEAK_PG_CONN_127_0_0_1_PWD_SECRET"
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


class TestAppToolsSanitization:
    mod = app_tools

    @pytest.mark.asyncio
    async def test_mcp_tool_function_exception_sanitized(self):
        tool = ChatTool(name="search_mcp", description="d", endpoint="", is_mcp=True, parameters=PARAMETERS)
        structured = self.mod.create_app_tool(tool, "app-mcp", "Mcp", mcp_server_url="https://mcp.example")
        with (
            patch.object(self.mod, "is_app_webhook_disabled", return_value=False),
            patch.object(self.mod, "get_webhook_circuit_breaker", return_value=_allowing_breaker()),
            patch.object(self.mod, "call_mcp_tool", new_callable=AsyncMock, side_effect=RuntimeError(SENTINEL_ERROR)),
            patch.object(self.mod, "record_app_webhook_failure"),
            patch.object(self.mod, "_handle_app_webhook_disable"),
        ):
            result = await structured.ainvoke({"query": "test query"})
        assert SENTINEL_ERROR not in result
        assert result == "Error calling MCP tool search_mcp. Please try again later."

    @pytest.mark.asyncio
    async def test_tool_function_exception_sanitized(self):
        tool = ChatTool(name="fetch_http", description="d", endpoint="https://app.example/tool", parameters=PARAMETERS)
        structured = self.mod.create_app_tool(tool, "app-http", "Http")
        client = AsyncMock()
        client.request = AsyncMock(side_effect=RuntimeError(SENTINEL_ERROR))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with (
            patch.object(self.mod, "is_app_webhook_disabled", return_value=False),
            patch.object(self.mod, "get_cached_user_geolocation", return_value=None),
            patch.object(self.mod, "get_webhook_circuit_breaker", return_value=_allowing_breaker()),
            patch.object(self.mod, "record_app_webhook_failure"),
            patch.object(self.mod, "_handle_app_webhook_disable"),
            patch("httpx.AsyncClient", return_value=client),
        ):
            token = self.mod.agent_config_context.set(CONFIG)
            try:
                result = await structured.ainvoke({"query": "test query"})
            finally:
                self.mod.agent_config_context.reset(token)
        assert SENTINEL_ERROR not in result
        assert result == "Error calling fetch_http. Please try again later."

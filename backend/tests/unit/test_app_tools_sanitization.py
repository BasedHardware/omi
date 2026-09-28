"""Unit tests verifying exception sanitization in app retrieval tools and MCP dispatch.

Failure-Class: none
Ensures raw exception details from external HTTP or MCP tool calls are never returned directly in tool output strings.
"""

from unittest.mock import MagicMock, patch
from utils.retrieval.tools import app_tools

SENTINEL_ERROR = "SENTINEL_INTERNAL_LEAK_PG_CONN_127_0_0_1_PWD_SECRET"


def test_mcp_tool_function_exception_sanitized():
    fake_tool = MagicMock()
    fake_tool.client = MagicMock()
    fake_tool.client.call_tool_retrying.side_effect = RuntimeError(SENTINEL_ERROR)

    with (
        patch.object(app_tools, "resolve_config_uid", return_value=("test-uid-123", None)),
        patch.object(app_tools, "get_app_by_id_db", return_value={"id": "app-1", "name": "Test App"}),
        patch.object(app_tools, "get_mcp_tool_for_app", return_value=fake_tool),
    ):
        fn = app_tools.mcp_tool_function("app-1", "my_action")
        res = fn(config={"configurable": {"user_id": "test-uid-123"}})
    assert SENTINEL_ERROR not in res
    assert "Error executing MCP tool: Failed to execute tool." in res


def test_tool_function_exception_sanitized():
    fake_action = MagicMock()
    fake_action.action = "http_request"
    fake_action.url = "http://fake-url"

    with (
        patch.object(app_tools, "resolve_config_uid", return_value=("test-uid-123", None)),
        patch.object(app_tools, "get_app_by_id_db", return_value={"id": "app-2", "name": "Http App"}),
        patch.object(app_tools, "get_app_action", return_value=fake_action),
        patch.object(app_tools, "execute_app_action", side_effect=RuntimeError(SENTINEL_ERROR)),
    ):
        fn = app_tools.tool_function("app-2", "http_action")
        res = fn(config={"configurable": {"user_id": "test-uid-123"}})
    assert SENTINEL_ERROR not in res
    assert "Error executing tool: Failed to execute tool." in res

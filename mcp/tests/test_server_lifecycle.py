"""Tests for standalone MCP server startup, tool listing, and execution."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import anyio
import pytest
from mcp.client.session import ClientSession

from mcp_server_omi.server import OmiTools, _execute_tool, _get_tools, create_server


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_get_tools_contains_all_eight_tools() -> None:
    tools = _get_tools()
    assert len(tools) == 8
    names = {t.name for t in tools}
    expected = {
        OmiTools.GET_MEMORIES,
        OmiTools.SEARCH_MEMORIES,
        OmiTools.CREATE_MEMORY,
        OmiTools.DELETE_MEMORY,
        OmiTools.EDIT_MEMORY,
        OmiTools.GET_CONVERSATIONS,
        OmiTools.GET_CONVERSATION_BY_ID,
        OmiTools.SEARCH_CONVERSATIONS,
    }
    assert names == expected


def test_create_server_constructs_without_error() -> None:
    server = create_server()
    assert server is not None
    init_opts = server.create_initialization_options()
    assert init_opts.capabilities.tools is not None


@pytest.mark.anyio
async def test_server_session_list_tools() -> None:
    server = create_server()
    init_opts = server.create_initialization_options()

    client_send, server_receive = anyio.create_memory_object_stream(10)
    server_send, client_receive = anyio.create_memory_object_stream(10)

    async with anyio.create_task_group() as tg:
        tg.start_soon(server.run, server_receive, server_send, init_opts)
        async with ClientSession(client_receive, client_send) as session:
            await session.initialize()
            tool_res = await session.list_tools()
            tool_names = [t.name for t in tool_res.tools]
            assert len(tool_names) == 8
            assert OmiTools.GET_MEMORIES in tool_names
            assert OmiTools.SEARCH_MEMORIES in tool_names
            assert OmiTools.CREATE_MEMORY in tool_names
            assert OmiTools.DELETE_MEMORY in tool_names
            assert OmiTools.EDIT_MEMORY in tool_names
            assert OmiTools.GET_CONVERSATIONS in tool_names
            assert OmiTools.GET_CONVERSATION_BY_ID in tool_names
            assert OmiTools.SEARCH_CONVERSATIONS in tool_names
            tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_execute_tool_redacts_api_key_in_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_logger = MagicMock(spec=logging.Logger)
    monkeypatch.setattr("mcp_server_omi.server.get_memories", lambda *args, **kwargs: [])
    await _execute_tool(
        OmiTools.GET_MEMORIES,
        {"api_key": "secret_key_123", "offset": 0, "limit": 10},
        mock_logger,
    )
    mock_logger.info.assert_called_once()
    logged_msg = mock_logger.info.call_args[0][0]
    assert "secret_key_123" not in logged_msg
    assert "***" in logged_msg


@pytest.mark.anyio
async def test_create_server_legacy_mcp_1_compatibility(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test legacy MCP 1.x initialization path using list_tools and call_tool decorators."""
    class MockLegacyServer:
        def __init__(self, name: str):
            self.name = name
            self.list_tools_handler = None
            self.call_tool_handler = None

        def list_tools(self):
            def decorator(fn):
                self.list_tools_handler = fn
                return fn
            return decorator

        def call_tool(self):
            def decorator(fn):
                self.call_tool_handler = fn
                return fn
            return decorator

    monkeypatch.setattr("mcp_server_omi.server.Server", MockLegacyServer)
    server = create_server()
    assert isinstance(server, MockLegacyServer)
    assert server.name == "mcp-omi"
    assert server.list_tools_handler is not None
    assert server.call_tool_handler is not None

    tools = await server.list_tools_handler()
    assert len(tools) == 8
    assert {t.name for t in tools} == {
        OmiTools.GET_MEMORIES,
        OmiTools.SEARCH_MEMORIES,
        OmiTools.CREATE_MEMORY,
        OmiTools.DELETE_MEMORY,
        OmiTools.EDIT_MEMORY,
        OmiTools.GET_CONVERSATIONS,
        OmiTools.GET_CONVERSATION_BY_ID,
        OmiTools.SEARCH_CONVERSATIONS,
    }

    monkeypatch.setattr("mcp_server_omi.server.get_memories", lambda *args, **kwargs: [{"id": "mem_1"}])
    result = await server.call_tool_handler(
        OmiTools.GET_MEMORIES,
        {"api_key": "test_api_key_123", "offset": 0, "limit": 10},
    )
    assert len(result) == 1
    assert "mem_1" in result[0].text

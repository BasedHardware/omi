"""Tests for standalone MCP server startup, tool listing, and execution."""

from __future__ import annotations

import anyio
import pytest
from mcp.client.session import ClientSession

from mcp_server_omi.server import OmiTools, create_server, _get_tools


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

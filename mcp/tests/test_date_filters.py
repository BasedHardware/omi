"""Date-filter validation for the standalone MCP server's conversation tools.

``get_conversations`` used to log a warning and drop an unparseable ``start_date`` /
``end_date`` on the floor, then query the API with **no** date bound, so the model
received the unfiltered conversation list with no signal that its filter was ignored.
``search_conversations`` forwarded the raw strings and surfaced the backend's 400 as an
opaque ``HTTPError``. Both tools must reject a malformed date before any request.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.shared.exceptions import MCPError

from mcp_server_omi.server import (
    OmiTools,
    _execute_tool,
    create_server,
    get_conversations,
    search_conversations,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _ok_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.parametrize("field", ["start_date", "end_date"])
@pytest.mark.parametrize("bad", ["01/01/2026", "2026-1-1", "yesterday", "2026-13-40", ""])
def test_get_conversations_rejects_malformed_date_before_request(field, bad):
    logger = logging.getLogger("test")
    with patch("mcp_server_omi.server.requests.get") as mock_get:
        with pytest.raises(ValueError, match=f"{field}"):
            get_conversations(logger, "omi_mcp_key", **{field: bad})
        mock_get.assert_not_called()


def test_get_conversations_keeps_day_bounds_for_valid_dates():
    logger = logging.getLogger("test")
    with patch("mcp_server_omi.server.requests.get", return_value=_ok_response([])) as mock_get:
        get_conversations(logger, "omi_mcp_key", start_date="2026-01-01", end_date="2026-01-31")
    params = mock_get.call_args.kwargs["params"]
    assert params["start_date"] == "2026-01-01T00:00:00"
    assert params["end_date"] == "2026-01-31T23:59:59"


@pytest.mark.parametrize("field", ["start_date", "end_date"])
@pytest.mark.parametrize("bad", ["01/01/2026", "2026-1-1", ""])
def test_search_conversations_rejects_malformed_date_before_request(field, bad):
    logger = logging.getLogger("test")
    with patch("mcp_server_omi.server.requests.get") as mock_get:
        with pytest.raises(ValueError, match=f"{field}"):
            search_conversations(logger, "omi_mcp_key", query="meeting", **{field: bad})
        mock_get.assert_not_called()


@pytest.mark.anyio
async def test_get_conversations_tool_reports_malformed_date_to_the_client():
    # Drive the real server over an in-memory MCP session. The server's tool handler
    # surfaces exceptions as JSON-RPC errors (the same channel its existing
    # "query is required" and HTTP-failure errors use), so the client must receive an
    # error naming the bad field instead of a silently unfiltered conversation list.
    server = create_server()
    init_opts = server.create_initialization_options()
    client_send, server_receive = anyio.create_memory_object_stream(10)
    server_send, client_receive = anyio.create_memory_object_stream(10)

    with patch("mcp_server_omi.server.requests.get", return_value=_ok_response([{"id": "c1"}])) as mock_get:
        async with anyio.create_task_group() as tg:
            tg.start_soon(server.run, server_receive, server_send, init_opts)
            async with ClientSession(client_receive, client_send) as session:
                await session.initialize()
                with pytest.raises(MCPError, match=r"Invalid start_date '01/01/2026'\. Expected YYYY-MM-DD\."):
                    await session.call_tool(
                        OmiTools.GET_CONVERSATIONS,
                        {"api_key": "omi_mcp_key", "start_date": "01/01/2026"},
                    )
            tg.cancel_scope.cancel()

    mock_get.assert_not_called()

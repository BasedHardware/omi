"""Contract tests for standalone MCP memory listing."""

import asyncio
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import mcp_server_omi.server as server_module
from mcp_server_omi.server import GetMemories, get_memories


def test_get_memories_model_exposes_pending_processing_toggle():
    model = GetMemories()
    schema = GetMemories.model_json_schema()

    assert model.include_pending_processing is True
    assert schema["properties"]["include_pending_processing"]["default"] is True


def test_get_memories_forwards_pending_processing_toggle():
    response = MagicMock()
    response.json.return_value = []

    with patch("mcp_server_omi.server.requests.get", return_value=response) as request:
        get_memories(
            logging.getLogger("test"),
            "omi_mcp_testkey",
            include_pending_processing=False,
        )

    assert request.call_args.kwargs["params"]["include_pending_processing"] is False


def test_get_memories_defaults_to_pending_visibility():
    response = MagicMock()
    response.json.return_value = []

    with patch("mcp_server_omi.server.requests.get", return_value=response) as request:
        get_memories(logging.getLogger("test"), "omi_mcp_testkey")

    assert request.call_args.kwargs["params"]["include_pending_processing"] is True


def test_call_tool_forwards_pending_processing_toggle():
    servers = []

    class FakeServer:
        def __init__(self, _name):
            self.call_tool_handler: Any = None
            self.list_tools_handler: Any = None
            servers.append(self)

        def list_tools(self):
            def decorator(handler):
                self.list_tools_handler = handler
                return handler

            return decorator

        def call_tool(self):
            def decorator(handler):
                self.call_tool_handler = handler
                return handler

            return decorator

        def create_initialization_options(self):
            return None

        async def run(self, _read_stream, _write_stream, _options, **_kwargs):
            return None

    class FakeStdioContext:
        async def __aenter__(self):
            return object(), object()

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return False

    with (
        patch.object(server_module, "Server", FakeServer),
        patch.object(server_module, "stdio_server", return_value=FakeStdioContext()),
        patch.object(server_module, "get_memories", return_value=[]) as list_memories,
    ):
        asyncio.run(server_module.serve(None))
        result = asyncio.run(
            servers[0].call_tool_handler(
                "get_memories",
                {
                    "api_key": "omi_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "include_pending_processing": False,
                },
            )
        )

    assert result[0].text == "[]"
    assert list_memories.call_args.kwargs["include_pending_processing"] is False

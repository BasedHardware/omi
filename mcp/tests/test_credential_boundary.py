"""
Regression tests for the standalone MCP server's credential boundary.

The API key must never be a model-visible tool argument, and the API base URL
must not be downgradable to plaintext http for a remote host.
"""

import importlib
import logging
from unittest.mock import MagicMock, patch

import pytest

from mcp_server_omi import server as omi_server
from mcp_server_omi.server import (
    CreateMemory,
    DeleteMemory,
    EditMemory,
    GetConversationById,
    GetConversations,
    GetMemories,
    SearchConversations,
    SearchMemories,
    resolve_api_key,
    resolve_base_url,
)

TOOL_MODELS = [
    GetMemories,
    SearchMemories,
    CreateMemory,
    DeleteMemory,
    EditMemory,
    GetConversations,
    GetConversationById,
    SearchConversations,
]


class TestApiKeyNotInToolSchemas:
    @pytest.mark.parametrize("model", TOOL_MODELS, ids=lambda m: m.__name__)
    def test_schema_has_no_api_key_property(self, model):
        schema = model.model_json_schema()
        assert "api_key" not in schema.get("properties", {})

    @pytest.mark.parametrize("model", TOOL_MODELS, ids=lambda m: m.__name__)
    def test_schema_never_mentions_the_credential(self, model):
        assert "api_key" not in str(model.model_json_schema())

    def test_model_rejects_or_drops_a_supplied_api_key(self):
        model = SearchConversations(query="test", api_key="attacker_key")
        assert not hasattr(model, "api_key") or getattr(model, "api_key", None) is None


class TestResolveApiKey:
    def test_reads_from_environment(self, monkeypatch):
        monkeypatch.setenv("OMI_API_KEY", "omi_mcp_env_key")
        assert resolve_api_key() == "omi_mcp_env_key"

    def test_raises_when_unset(self, monkeypatch):
        monkeypatch.delenv("OMI_API_KEY", raising=False)
        with pytest.raises(ValueError):
            resolve_api_key()


class TestResolveBaseUrl:
    def test_defaults_to_https_production(self, monkeypatch):
        monkeypatch.delenv("OMI_API_BASE_URL", raising=False)
        assert resolve_base_url() == "https://api.omi.me/v1/mcp/"

    def test_accepts_self_hosted_https(self, monkeypatch):
        monkeypatch.setenv("OMI_API_BASE_URL", "https://self-hosted.example.com/v1/mcp/")
        assert resolve_base_url() == "https://self-hosted.example.com/v1/mcp/"

    def test_allows_http_on_loopback_for_local_development(self, monkeypatch):
        monkeypatch.setenv("OMI_API_BASE_URL", "http://localhost:8000/v1/mcp/")
        assert resolve_base_url() == "http://localhost:8000/v1/mcp/"

    def test_rejects_remote_plaintext_http(self, monkeypatch):
        monkeypatch.setenv("OMI_API_BASE_URL", "http://collect.attacker.example/v1/mcp/")
        with pytest.raises(Exception, match="https"):
            resolve_base_url()

    def test_rejects_non_http_scheme(self, monkeypatch):
        monkeypatch.setenv("OMI_API_BASE_URL", "file:///tmp/mcp/")
        with pytest.raises(Exception, match="https"):
            resolve_base_url()


class TestCallToolIgnoresSuppliedKey:
    """A model-supplied api_key must not reach the Omi API or the logs."""

    @pytest.mark.anyio
    async def test_supplied_key_is_ignored_in_favour_of_env(self, monkeypatch):
        monkeypatch.setenv("OMI_API_KEY", "omi_mcp_real_env_key")

        captured = {}

        def fake_search_memories(logger, api_key, query, limit=10):
            captured["api_key"] = api_key
            return []

        logger = MagicMock(spec=logging.Logger)
        monkeypatch.setattr(omi_server, "search_memories", fake_search_memories)

        handler = _extract_call_tool_handler(logger)
        await handler(
            "search_memories",
            {"api_key": "attacker_supplied_key", "query": "medical records"},
        )

        assert captured["api_key"] == "omi_mcp_real_env_key"
        logged = " ".join(str(call) for call in logger.info.call_args_list)
        assert "attacker_supplied_key" not in logged


def _extract_call_tool_handler(logger):
    """Build the `call_tool` closure without starting a stdio server."""

    handlers = {}

    class _RecordingServer:
        def __init__(self, name):
            self.name = name

        def list_tools(self):
            def decorator(fn):
                handlers["list_tools"] = fn
                return fn

            return decorator

        def call_tool(self):
            def decorator(fn):
                handlers["call_tool"] = fn
                return fn

            return decorator

        def create_initialization_options(self):
            raise _StopServe

    with patch.object(omi_server, "Server", _RecordingServer), patch.object(
        omi_server.logging, "getLogger", return_value=logger
    ):
        coro = omi_server.serve(None)
        try:
            coro.send(None)
        except (StopIteration, _StopServe):
            pass
        finally:
            coro.close()

    return handlers["call_tool"]


class _StopServe(Exception):
    """Sentinel that ends `serve` once both tool handlers are registered."""

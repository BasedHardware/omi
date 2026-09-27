"""Tests verifying exception sanitization across external retrieval and app tools.

Ensures that internal exception details (database strings, connection errors, tracebacks)
are not leaked to chat tool callers or LLM prompts.
"""

import importlib
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Ensure langchain_core is stubbed if not installed
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


_lc_tools.tool = _tool_decorator
_lc_tools.StructuredTool = MagicMock
_lc_tools.BaseTool = MagicMock

_lc_runnables = _mod("langchain_core.runnables")
_lc_runnables.RunnableConfig = dict

for _p in [
    "database",
    "models",
    "utils",
    "utils.llm",
    "utils.memory",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)

for _name, _attrs in {
    "utils.http_client": ["get_webhook_client", "get_web_fetch_client", "get_webhook_circuit_breaker"],
    "utils.llm.gateway_client": ["feature_auto_lane_id", "get_llm_gateway_base_url", "llm_gateway_headers"],
    "utils.log_sanitizer": ["sanitize"],
    "utils.memory.kg_graph_traversal": ["format_traversal_result", "traverse_knowledge_graph"],
    "utils.retrieval.agentic": ["agent_config_context"],
    "database.apps": ["get_app_by_id_db"],
    "database.redis_db": ["get_cached_user_geolocation", "delete_app_cache_by_id", "get_enabled_apps"],
    "database.webhook_health": [
        "ACTION_REDIRECT_NOT_FOLLOWED",
        "record_app_webhook_failure",
        "record_app_webhook_success",
        "is_app_webhook_disabled",
        "disable_app_in_firestore",
        "ENDPOINT_CHAT_TOOL",
        "ENDPOINT_MCP_TOOL",
    ],
    "models.app": ["App", "ChatTool"],
    "utils.mcp_client": ["call_mcp_tool"],
    "utils.executors": ["db_executor", "run_blocking"],
    "utils.notifications": ["send_notification"],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        if not hasattr(_m, _a):
            setattr(_m, _a, MagicMock())

_mod("utils.log_sanitizer").sanitize = lambda x: str(x)

# Load target modules directly
perplexity_mod = _load("utils.retrieval.tools._test_perplexity", "utils/retrieval/tools/perplexity_tools.py")
web_mod = _load("utils.retrieval.tools._test_web", "utils/retrieval/tools/web_tools.py")
graph_mod = _load("utils.retrieval.tools._test_graph", "utils/retrieval/tools/graph_tools.py")
app_mod = _load("utils.retrieval.tools._test_app", "utils/retrieval/tools/app_tools.py")


class TestExternalToolsSanitization(unittest.IsolatedAsyncioTestCase):
    """Hermetic unit tests verifying exception sanitization across external retrieval and app tools."""

    async def test_perplexity_unexpected_exception_sanitized(self):
        secret_leak = "internal_auth_token_leak_987654321"
        with patch.object(perplexity_mod, "_post_gateway_chat_completion", side_effect=RuntimeError(secret_leak)):
            result = await perplexity_mod._perplexity_gateway_search("test query")
            self.assertEqual(result, "Error: An unexpected error occurred while searching. Please try again later.")
            self.assertNotIn(secret_leak, result)

    async def test_fetch_url_unexpected_exception_sanitized(self):
        secret_leak = "socket_ssl_handshake_crash_to_db_host:5432"
        with patch.object(web_mod, "_fetch_page", side_effect=RuntimeError(secret_leak)):
            coro = getattr(web_mod.fetch_url_tool, "func", web_mod.fetch_url_tool)
            result = await coro("https://example.com")
            self.assertEqual(result, "Error: Failed to fetch the URL. Please verify the URL or try again later.")
            self.assertNotIn(secret_leak, result)

    def test_traverse_knowledge_graph_unexpected_exception_sanitized(self):
        secret_leak = "neo4j_bolt_connection_credentials_postgres_secret"
        with patch.object(graph_mod, "_resolve_uid", return_value="test_uid_123"), \
             patch.object(graph_mod, "traverse_knowledge_graph", side_effect=RuntimeError(secret_leak)):
            fn = getattr(graph_mod.traverse_knowledge_graph_tool, "func", graph_mod.traverse_knowledge_graph_tool)
            result = fn("Omi", 1)
            self.assertEqual(result, "Error traversing knowledge graph: Unable to complete traversal.")
            self.assertNotIn(secret_leak, result)

    async def test_call_tool_endpoint_unexpected_exception_sanitized(self):
        secret_leak = "aws_s3_bucket_leak_access_denied_key_xyz"
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.endpoint = "https://api.example.com/tool"
        mock_tool.method = "POST"

        with patch.object(app_mod, "get_webhook_circuit_breaker") as mock_cb, \
             patch.object(app_mod, "run_blocking", new_callable=AsyncMock) as mock_rb, \
             patch("httpx.AsyncClient") as mock_client:

            mock_cb.return_value.allow_request.return_value = True
            mock_rb.return_value = False
            mock_client.return_value.__aenter__.side_effect = RuntimeError(secret_leak)

            result = await app_mod._call_tool_endpoint({}, None, mock_tool, "app_123")
            self.assertEqual(result, "Error calling test_tool. Please try again later.")
            self.assertNotIn(secret_leak, result)

    async def test_mcp_tool_unexpected_exception_sanitized(self):
        secret_leak = "mcp_server_raw_internal_traceback_socket_error"
        mock_tool = MagicMock()
        mock_tool.name = "mcp_sample_tool"
        mock_tool.endpoint = "https://mcp.example.com/rpc"
        mock_tool.method = "POST"
        mock_tool.is_mcp = True
        mock_tool.transport = "sse"
        mock_tool.parameters = {"type": "object", "properties": {}}

        tool_fn = None

        def fake_structured_tool(*args, **kwargs):
            nonlocal tool_fn
            tool_fn = kwargs.get("coroutine")
            return MagicMock()

        with patch.object(app_mod, "get_webhook_circuit_breaker") as mock_cb, \
             patch.object(app_mod, "run_blocking", new_callable=AsyncMock) as mock_rb, \
             patch.object(app_mod, "call_mcp_tool", side_effect=RuntimeError(secret_leak)), \
             patch.object(app_mod, "StructuredTool", side_effect=fake_structured_tool):

            mock_cb.return_value.allow_request.return_value = True
            mock_rb.return_value = False
            app_mod.create_app_tool(mock_tool, "app_mcp_123", "Test MCP App", mcp_server_url="https://mcp.example.com")

            self.assertIsNotNone(tool_fn)
            result = await tool_fn()
            self.assertEqual(result, "Error calling MCP tool mcp_sample_tool. Please try again later.")
            self.assertNotIn(secret_leak, result)


if __name__ == "__main__":
    unittest.main()

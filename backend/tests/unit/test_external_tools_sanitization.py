"""External retrieval/app tools must not leak private exception details.

Import the real tools through the normal package path. Dependency patches are
scoped to each test rather than replacing package search paths at collection.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from utils.retrieval.tools import app_tools as app_mod
from utils.retrieval.tools import graph_tools as graph_mod
from utils.retrieval.tools import perplexity_tools as perplexity_mod
from utils.retrieval.tools import web_tools as web_mod


class TestExternalToolsSanitization(unittest.IsolatedAsyncioTestCase):
    """Hermetic unit tests verifying exception sanitization across external retrieval and app tools."""

    async def test_perplexity_unexpected_exception_sanitized(self):
        secret_leak = "internal_auth_token_leak_987654321"
        with patch.object(
            perplexity_mod, "_post_gateway_chat_completion", side_effect=RuntimeError(secret_leak)
        ) as request:
            result = await perplexity_mod._perplexity_gateway_search("test query")
            request.assert_awaited_once_with("test query")
            self.assertEqual(result, "Error: An unexpected error occurred while searching. Please try again later.")
            self.assertNotIn(secret_leak, result)

    async def test_fetch_url_unexpected_exception_sanitized(self):
        secret_leak = "socket_ssl_handshake_crash_to_db_host:5432"
        with patch.object(web_mod, "_fetch_page", side_effect=RuntimeError(secret_leak)) as fetch:
            coro = web_mod.fetch_url_tool.coroutine
            self.assertIsNotNone(coro)
            result = await coro("https://example.com")
            fetch.assert_awaited_once()
            self.assertEqual(result, "Error: Failed to fetch the URL. Please verify the URL or try again later.")
            self.assertNotIn(secret_leak, result)

    def test_traverse_knowledge_graph_unexpected_exception_sanitized(self):
        secret_leak = "neo4j_bolt_connection_credentials_postgres_secret"
        with patch.object(graph_mod, "_resolve_uid", return_value="test_uid_123"), patch.object(
            graph_mod, "traverse_knowledge_graph", side_effect=RuntimeError(secret_leak)
        ):
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

        with patch.object(app_mod, "get_webhook_circuit_breaker") as mock_cb, patch.object(
            app_mod, "run_blocking", new_callable=AsyncMock
        ) as mock_rb, patch("httpx.AsyncClient") as mock_client:

            mock_cb.return_value.allow_request.return_value = True
            mock_rb.return_value = False
            mock_client.return_value.__aenter__.side_effect = RuntimeError(secret_leak)

            result = await app_mod._call_tool_endpoint(
                {}, {"configurable": {"user_id": "test-user"}}, mock_tool, "app_123"
            )
            mock_client.return_value.__aenter__.assert_awaited_once()
            mock_cb.return_value.record_failure.assert_called_once()
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

        with patch.object(app_mod, "get_webhook_circuit_breaker") as mock_cb, patch.object(
            app_mod, "run_blocking", new_callable=AsyncMock
        ) as mock_rb, patch.object(app_mod, "call_mcp_tool", side_effect=RuntimeError(secret_leak)), patch.object(
            app_mod, "StructuredTool", side_effect=fake_structured_tool
        ):

            mock_cb.return_value.allow_request.return_value = True
            mock_rb.return_value = False
            app_mod.create_app_tool(mock_tool, "app_mcp_123", "Test MCP App", mcp_server_url="https://mcp.example.com")

            self.assertIsNotNone(tool_fn)
            result = await tool_fn()
            self.assertEqual(result, "Error calling MCP tool mcp_sample_tool. Please try again later.")
            self.assertNotIn(secret_leak, result)


if __name__ == "__main__":
    unittest.main()

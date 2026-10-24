"""Unit tests for MCP OAuth token refresh handling and persistence across tool calls."""

import os
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from models.app import ChatTool
from testing.import_isolation import load_module_fresh, stub_modules
import utils.mcp_client as mcp_client

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "..")


def _load_app_tools_module():
    retrieval_pkg = ModuleType("utils.retrieval")
    retrieval_pkg.__path__ = []
    tools_pkg = ModuleType("utils.retrieval.tools")
    tools_pkg.__path__ = []
    notif_mod = ModuleType("utils.notifications")
    notif_mod.send_notification = MagicMock()
    with stub_modules(
        {
            "utils.retrieval": retrieval_pkg,
            "utils.retrieval.tools": tools_pkg,
            "utils.notifications": notif_mod,
        }
    ):
        return load_module_fresh(
            "utils.retrieval.tools.app_tools",
            os.path.join(_BACKEND, "utils", "retrieval", "tools", "app_tools.py"),
        )


class TestMcpClientOAuthRefresh:
    @pytest.mark.asyncio
    async def test_http_refresh_propagates_token_to_next_candidate_and_parses_string_expires_in(self):
        tokens = {
            "access_token": "expired-token",
            "refresh_token": "refresh-1",
            "token_endpoint": "https://auth.example.com/token",
            "client_id": "client-1",
        }
        seen_tokens = []

        async def fake_init(url, token=None):
            seen_tokens.append((url, token))
            if token == "expired-token":
                raise PermissionError("401 Unauthorized")
            if url == "https://mcp.example.com":
                req = httpx.Request("POST", url)
                resp = httpx.Response(404, request=req)
                raise httpx.HTTPStatusError("404 Not Found", request=req, response=resp)
            return "sess-1"

        async def fake_post(url, payload, token=None, session_id=None):
            return {"result": {"content": [{"type": "text", "text": "ok-from-http"}]}}, session_id

        with (
            patch.object(mcp_client, "_initialize_session", side_effect=fake_init),
            patch.object(mcp_client, "_mcp_post", side_effect=fake_post),
            patch.object(
                mcp_client,
                "refresh_oauth_token",
                new_callable=AsyncMock,
                return_value={
                    "access_token": "fresh-token",
                    "refresh_token": "refresh-2",
                    "expires_in": "3600",
                },
            ) as mock_refresh,
        ):
            result = await mcp_client.call_mcp_tool(
                "https://mcp.example.com",
                "search",
                {"q": "omi"},
                access_token="expired-token",
                oauth_tokens=tokens,
                transport="streamable_http",
            )

        assert result == "ok-from-http"
        mock_refresh.assert_awaited_once_with("https://auth.example.com/token", "refresh-1", "client-1", None)
        assert tokens["access_token"] == "fresh-token"
        assert tokens["refresh_token"] == "refresh-2"
        assert isinstance(tokens.get("expires_at"), float)
        assert seen_tokens == [
            ("https://mcp.example.com", "expired-token"),
            ("https://mcp.example.com", "fresh-token"),
            ("https://mcp.example.com/http", "fresh-token"),
        ]

    @pytest.mark.asyncio
    async def test_http_refresh_failure_returns_error_without_retrying_candidates(self):
        tokens = {
            "access_token": "expired-token",
            "refresh_token": "revoked-refresh",
            "token_endpoint": "https://auth.example.com/token",
            "client_id": "client-1",
        }
        with (
            patch.object(
                mcp_client,
                "_initialize_session",
                new_callable=AsyncMock,
                side_effect=PermissionError("401 Unauthorized"),
            ) as mock_init,
            patch.object(
                mcp_client,
                "refresh_oauth_token",
                new_callable=AsyncMock,
                side_effect=RuntimeError("invalid_grant"),
            ) as mock_refresh,
        ):
            result = await mcp_client.call_mcp_tool(
                "https://mcp.example.com",
                "search",
                {},
                access_token="expired-token",
                oauth_tokens=tokens,
                transport="streamable_http",
            )

        assert result.startswith("Error refreshing MCP OAuth token:")
        assert "invalid_grant" in result
        assert mock_init.await_count == 1
        assert mock_refresh.await_count == 1

    @pytest.mark.asyncio
    async def test_sse_refresh_and_retry_failures_return_error_strings(self):
        tokens = {
            "access_token": "expired-token",
            "refresh_token": "refresh-1",
            "token_endpoint": "https://auth.example.com/token",
            "client_id": "client-1",
        }
        with (
            patch.object(
                mcp_client,
                "_call_tool_via_sse",
                new_callable=AsyncMock,
                side_effect=[PermissionError("401"), RuntimeError("stream closed")],
            ),
            patch.object(
                mcp_client,
                "refresh_oauth_token",
                new_callable=AsyncMock,
                return_value={"access_token": "fresh-token", "refresh_token": "refresh-2", "expires_in": 1800},
            ),
        ):
            result = await mcp_client.call_mcp_tool(
                "https://mcp.example.com/sse",
                "search",
                {},
                access_token="expired-token",
                oauth_tokens=tokens,
                transport="sse",
            )

        assert result == "Error calling MCP tool via SSE: stream closed"
        assert tokens["access_token"] == "fresh-token"
        assert tokens["refresh_token"] == "refresh-2"


class TestAppToolsMcpTokenPersistence:
    @pytest.fixture(autouse=True)
    def _setup_module(self):
        self.mod = _load_app_tools_module()

    @pytest.mark.asyncio
    async def test_refreshed_mcp_tokens_are_persisted_and_shared_across_sibling_tools(self):
        shared_tokens = {
            "access_token": "stale-token",
            "refresh_token": "refresh-old",
            "token_endpoint": "https://auth.example.com/token",
            "client_id": "client-1",
        }
        tool_a = ChatTool(name="search_notes", description="Search", endpoint="", is_mcp=True)
        tool_b = ChatTool(name="create_note", description="Create", endpoint="", is_mcp=True)

        structured_a = self.mod.create_app_tool(
            tool_a,
            "app-mcp-1",
            "NotesMCP",
            mcp_server_url="https://mcp.example.com",
            mcp_oauth_tokens=shared_tokens,
        )
        structured_b = self.mod.create_app_tool(
            tool_b,
            "app-mcp-1",
            "NotesMCP",
            mcp_server_url="https://mcp.example.com",
            mcp_oauth_tokens=shared_tokens,
        )

        observed_access_tokens = []

        async def fake_call_mcp_tool(server_url, tool_name, arguments, access_token, oauth_tokens, transport):
            observed_access_tokens.append((tool_name, access_token))
            if access_token == "stale-token":
                oauth_tokens["access_token"] = "fresh-token"
                oauth_tokens["refresh_token"] = "refresh-new"
                oauth_tokens["expires_at"] = 9999999999.0
            return "tool-ok"

        breaker = MagicMock()
        breaker.allow_request.return_value = True

        with (
            patch.object(self.mod, "is_app_webhook_disabled", return_value=False),
            patch.object(self.mod, "get_webhook_circuit_breaker", return_value=breaker),
            patch.object(self.mod, "call_mcp_tool", side_effect=fake_call_mcp_tool),
            patch.object(self.mod, "update_app_in_db") as mock_update_db,
            patch.object(self.mod, "delete_app_cache_by_id") as mock_delete_cache,
            patch.object(self.mod, "record_app_webhook_success"),
        ):
            await structured_a.coroutine()
            await structured_b.coroutine()

        assert observed_access_tokens == [
            ("search_notes", "stale-token"),
            ("create_note", "fresh-token"),
        ]
        mock_update_db.assert_called_once_with(
            {
                "id": "app-mcp-1",
                "external_integration.mcp_oauth_tokens": {
                    "access_token": "fresh-token",
                    "refresh_token": "refresh-new",
                    "token_endpoint": "https://auth.example.com/token",
                    "client_id": "client-1",
                    "expires_at": 9999999999.0,
                },
            }
        )
        mock_delete_cache.assert_called_once_with("app-mcp-1")

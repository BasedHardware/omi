"""Contract tests for the hosted MCP Streamable HTTP transport.

Covers the canonical ``/v1/mcp`` endpoint, the permanent ``/v1/mcp/sse`` alias,
protocol-version negotiation and stateless declarations, batch admission,
rate-limit charging, the tool result contract (``structuredContent`` /
``outputSchema`` / ``isError``), and the privacy-safe analytics seams.
"""

import importlib
import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

import utils.mcp_analytics as mcp_analytics
import utils.mcp_server.transport as mcp_transport
from database import mcp_oauth as mcp_oauth_db
from routers import mcp as rest_mcp
from routers import mcp_sse
from utils.mcp_scopes import MCP_FULL_ACCESS_SCOPES
from utils.mcp_server.auth import MCPAuthContext
from utils.mcp_server.errors import ToolExecutionError, authorization_denied_error
from utils.mcp_server.metadata import (
    MCP_LEGACY_PROTECTED_RESOURCE_METADATA_URL,
    MCP_PROTECTED_RESOURCE_METADATA_URL,
)
from utils.mcp_server.registry import MCP_TOOLS, TOOL_SPECS
from utils.mcp_server.versions import (
    DEFAULT_PROTOCOL_VERSION,
    HANDSHAKE_PROTOCOL_VERSIONS,
    META_CLIENT_CAPABILITIES,
    META_PROTOCOL_VERSION,
    META_SERVER_INFO,
    NEGOTIATED_FALLBACK_VERSION,
    PROTOCOL_VERSION_2026,
    SERVER_INFO,
    SUPPORTED_PROTOCOL_VERSIONS,
    TOOLS_LIST_CACHE_SCOPE,
    TOOLS_LIST_TTL_MS,
)

ALL_SCOPES = list(MCP_FULL_ACCESS_SCOPES)

EXPECTED_TOOL_ORDER = [
    "get_user_profile",
    "get_memories",
    "create_memory",
    "create_memories",
    "delete_memory",
    "edit_memory",
    "get_conversations",
    "get_conversation_by_id",
    "get_conversations_by_ids",
    "search_memories",
    "search_conversations",
    "search_x_posts",
    "get_x_posts",
    "get_action_items",
    "search_action_items",
    "create_action_item",
    "complete_action_item",
    "update_action_item",
    "delete_action_item",
    "get_goals",
    "get_chat_messages",
    "get_people",
    "get_screen_activity",
    "get_daily_summaries",
]

# Representative handler results exercising every success output schema.
FAKE_SUCCESS = {
    "get_user_profile": {
        "profile_text": "p",
        "generated_at": "2026-06-11T10:30:00+00:00",
        "data_sources_used": [],
    },
    "get_memories": {"memories": [{"id": "m1"}], "filters": {}},
    "create_memory": {"success": True, "memory": {"id": "m1", "content": "c"}},
    "create_memories": {"results": [{"index": 0, "status": "created", "memory_id": "m1"}]},
    "delete_memory": {"success": True},
    "edit_memory": {"success": True},
    "get_conversations": {"conversations": [{"id": "c1"}]},
    "get_conversation_by_id": {"conversation": {"id": "c1"}, "truncated": False},
    "get_conversations_by_ids": {
        "conversations": [{"id": "c1", "conversation": {"id": "c1"}, "truncated": False}],
        "not_found": [],
        "truncated": False,
    },
    "search_memories": {"memories": []},
    "search_conversations": {"conversations": []},
    "search_x_posts": {"posts": []},
    "get_x_posts": {"posts": []},
    "get_action_items": {"action_items": []},
    "search_action_items": {"action_items": []},
    "create_action_item": {"success": True, "action_item": {"id": "a1"}},
    "complete_action_item": {"success": True, "action_item": {"id": "a1"}},
    "update_action_item": {"success": True, "action_item": {"id": "a1"}},
    "delete_action_item": {"success": True},
    "get_goals": {"goals": []},
    "get_chat_messages": {"messages": []},
    "get_people": {"people": []},
    "get_screen_activity": {"screen_activity": []},
    "get_daily_summaries": {"daily_summaries": []},
}


def _full_auth(uid="uid-test", scopes=None, **kwargs):
    return MCPAuthContext(
        uid=uid,
        auth_type="oauth",
        scopes=list(scopes if scopes is not None else ALL_SCOPES),
        client_id="test-client",
        **kwargs,
    )


def _msg(method, msg_id=1, params=None):
    message = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def _tool_call(name, arguments=None, msg_id=7):
    return _msg("tools/call", msg_id=msg_id, params={"name": name, "arguments": arguments or {}})


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(mcp_sse.router)
    return TestClient(app)


@pytest.fixture
def authed():
    """Authenticated POST seams: auth context, admission limiter, telemetry sinks."""
    with (
        patch.object(mcp_transport, "authenticate_mcp_request", return_value=_full_auth()),
        patch.object(mcp_transport, "check_rate_limit_inline") as admission,
        patch.object(mcp_transport, "check_rate_limit_context") as context_limit,
        patch.object(mcp_transport, "log_mcp_request") as request_log,
        patch.object(mcp_transport, "schedule_mcp_active") as active_event,
        patch.object(mcp_transport, "schedule_mcp_tool_call") as tool_event,
    ):
        yield SimpleNamespace(
            admission=admission,
            context_limit=context_limit,
            request_log=request_log,
            active_event=active_event,
            tool_event=tool_event,
        )


def _post(client, path, body, **headers):
    return client.post(path, json=body, headers={"Authorization": "Bearer tok", **headers})


class TestRouteParity:
    def test_post_serves_both_paths(self, client, authed):
        for path in ("/v1/mcp", "/v1/mcp/sse"):
            response = _post(client, path, _msg("ping"))
            assert response.status_code == 200
            assert response.json() == {"jsonrpc": "2.0", "id": 1, "result": {}}

    def test_get_returns_405_on_both_paths(self, client):
        for path in ("/v1/mcp", "/v1/mcp/sse"):
            response = client.get(path)
            assert response.status_code == 405
            assert "POST" in response.headers.get("allow", "")
            assert "text/event-stream" not in response.headers.get("content-type", "")

    def test_head_requires_auth_then_200(self, client):
        for path in ("/v1/mcp", "/v1/mcp/sse"):
            assert client.head(path).status_code == 401
        with patch.object(mcp_transport, "authenticate_mcp_request", return_value=_full_auth()):
            for path in ("/v1/mcp", "/v1/mcp/sse"):
                assert client.head(path, headers={"Authorization": "Bearer tok"}).status_code == 200

    def test_delete_requires_auth_then_204(self, client):
        for path in ("/v1/mcp", "/v1/mcp/sse"):
            assert client.delete(path).status_code == 401
        with patch.object(mcp_transport, "authenticate_mcp_request", return_value=_full_auth()):
            for path in ("/v1/mcp", "/v1/mcp/sse"):
                assert client.delete(path, headers={"Authorization": "Bearer tok"}).status_code == 204

    def test_protected_resource_metadata_is_per_path(self, client):
        """Each well-known document describes the resource for its own path;
        the unqualified root keeps the legacy audience for now."""
        canonical = client.get("/.well-known/oauth-protected-resource/v1/mcp").json()
        legacy = client.get("/.well-known/oauth-protected-resource/v1/mcp/sse").json()
        root = client.get("/.well-known/oauth-protected-resource").json()
        assert canonical["resource"] == mcp_oauth_db.MCP_RESOURCE_URL
        assert legacy["resource"] == mcp_oauth_db.MCP_LEGACY_RESOURCE_URL
        assert root["resource"] == mcp_oauth_db.MCP_LEGACY_RESOURCE_URL
        assert canonical["authorization_servers"]
        assert legacy["authorization_servers"]
        for path in (
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/v1/mcp",
            "/.well-known/oauth-protected-resource/v1/mcp/sse",
        ):
            assert client.head(path).status_code == 200

    def test_authorization_server_metadata(self, client):
        doc = client.get("/.well-known/oauth-authorization-server").json()
        assert doc["issuer"]
        assert "client_registration_endpoint" not in doc  # no DCR/CIMD claimed
        assert doc["code_challenge_methods_supported"] == ["S256"]

    def test_sse_info_advertises_canonical_endpoint_on_legacy_path(self, client):
        """The info route lives on the legacy /sse path but must teach the
        canonical /v1/mcp URL and current protocol revision."""
        payload = client.get("/v1/mcp/sse/info").json()
        assert payload["endpoint"] == "/v1/mcp"
        assert payload["protocol_version"] == PROTOCOL_VERSION_2026
        assert payload["instructions"]["step2"].endswith("/v1/mcp")
        assert "/v1/mcp/sse" not in payload["instructions"]["step2"]


class TestVersionNegotiation:
    @pytest.mark.parametrize("version", HANDSHAKE_PROTOCOL_VERSIONS)
    def test_initialize_echoes_supported_handshake_versions(self, version):
        auth = _full_auth()
        response = mcp_transport.handle_mcp_message(auth, _msg("initialize", params={"protocolVersion": version}))
        result = response["result"]
        assert result["protocolVersion"] == version
        assert result["serverInfo"] == SERVER_INFO
        assert result["instructions"]
        assert result["capabilities"] == {"tools": {}}

    @pytest.mark.parametrize("requested", ["1999-01-01", PROTOCOL_VERSION_2026, None, 42])
    def test_initialize_falls_back_for_unsupported_or_stateless_requests(self, requested):
        auth = _full_auth()
        params = {} if requested is None else {"protocolVersion": requested}
        response = mcp_transport.handle_mcp_message(auth, _msg("initialize", params=params))
        assert response["result"]["protocolVersion"] == NEGOTIATED_FALLBACK_VERSION

    def test_undeclared_messages_default_to_legacy_revision(self):
        auth = _full_auth()
        response = mcp_transport.handle_mcp_message(auth, _msg("ping"))
        # 2025-03-26 default: ping still answers, no 2026 decorations.
        assert response == {"jsonrpc": "2.0", "id": 1, "result": {}}
        assert DEFAULT_PROTOCOL_VERSION == "2025-03-26"


class TestStateless2026:
    def test_tools_list_2026_via_header(self):
        auth = _full_auth()
        request = mcp_transport.McpRequestContext(auth_context=auth, header_version=PROTOCOL_VERSION_2026)
        response = mcp_transport.handle_mcp_message(auth, _msg("tools/list"), request)
        result = response["result"]
        assert result["resultType"] == "complete"
        assert result["_meta"][META_SERVER_INFO] == SERVER_INFO
        assert len(result["tools"]) == len(TOOL_SPECS)
        assert result["ttlMs"] == TOOLS_LIST_TTL_MS == 3_600_000
        assert result["cacheScope"] == TOOLS_LIST_CACHE_SCOPE == "private"

    def test_stateless_2026_via_meta_wins(self):
        auth = _full_auth()
        message = _msg("tools/list")
        message["params"] = {"_meta": {META_PROTOCOL_VERSION: PROTOCOL_VERSION_2026}}
        response = mcp_transport.handle_mcp_message(auth, message)
        assert response["result"]["resultType"] == "complete"

    def test_server_discover(self):
        auth = _full_auth()
        response = mcp_transport.handle_mcp_message(auth, _msg("server/discover"))
        result = response["result"]
        assert result["supportedVersions"] == list(SUPPORTED_PROTOCOL_VERSIONS)
        assert result["serverInfo"] == SERVER_INFO
        assert result["instructions"]
        assert "tools" in result["capabilities"]
        # DiscoverResult extends CacheableResult.
        assert result["ttlMs"] == TOOLS_LIST_TTL_MS
        assert result["cacheScope"] == TOOLS_LIST_CACHE_SCOPE

    def test_ping_removed_in_2026(self):
        auth = _full_auth()
        request = mcp_transport.McpRequestContext(auth_context=auth, header_version=PROTOCOL_VERSION_2026)
        response = mcp_transport.handle_mcp_message(auth, _msg("ping"), request)
        assert response["error"]["code"] == -32601

    def test_unsupported_header_version_rejected(self):
        auth = _full_auth()
        request = mcp_transport.McpRequestContext(auth_context=auth, header_version="1999-01-01")
        response = mcp_transport.handle_mcp_message(auth, _msg("tools/list"), request)
        assert response["error"]["code"] == -32022
        assert response["error"]["data"]["supported"] == list(SUPPORTED_PROTOCOL_VERSIONS)
        assert response["error"]["data"]["requested"] == "1999-01-01"

    def test_unsupported_meta_version_rejected(self):
        auth = _full_auth()
        message = _msg("tools/list")
        message["_meta"] = {META_PROTOCOL_VERSION: "1999-01-01"}
        response = mcp_transport.handle_mcp_message(auth, message)
        assert response["error"]["code"] == -32022

    def test_header_meta_version_mismatch_rejected(self):
        auth = _full_auth()
        message = _msg("tools/list")
        message["params"] = {"_meta": {META_PROTOCOL_VERSION: "2025-06-18"}}
        request = mcp_transport.McpRequestContext(auth_context=auth, header_version="2025-03-26")
        response = mcp_transport.handle_mcp_message(auth, message, request)
        assert response["error"]["code"] == -32020


class TestIntegrityHeaders:
    def test_mcp_method_header_mismatch(self):
        auth = _full_auth()
        request = mcp_transport.McpRequestContext(auth_context=auth, mcp_method="tools/list")
        response = mcp_transport.handle_mcp_message(auth, _msg("tools/call", params={"name": "x"}), request)
        assert response["error"]["code"] == -32020

    def test_mcp_method_header_match(self):
        auth = _full_auth()
        request = mcp_transport.McpRequestContext(auth_context=auth, mcp_method="ping")
        response = mcp_transport.handle_mcp_message(auth, _msg("ping"), request)
        assert response["result"] == {}

    def test_mcp_name_header_mismatch(self):
        auth = _full_auth()
        request = mcp_transport.McpRequestContext(auth_context=auth, mcp_name="get_memories")
        response = mcp_transport.handle_mcp_message(auth, _tool_call("get_conversations"), request)
        assert response["error"]["code"] == -32020

    def test_mcp_name_header_match(self):
        auth = _full_auth()
        request = mcp_transport.McpRequestContext(auth_context=auth, mcp_name="get_people")
        with patch.object(mcp_transport, "execute_tool", return_value=FAKE_SUCCESS["get_people"]):
            response = mcp_transport.handle_mcp_message(auth, _tool_call("get_people"), request)
        assert "result" in response


class TestBatchAdmission:
    def test_batch_accepted_for_batch_era_version(self):
        messages, error = mcp_transport.prepare_messages(
            [_msg("ping", 1), _msg("ping", 2)],
            header_version="2025-03-26",
            mcp_method=None,
            mcp_name=None,
        )
        assert error is None and len(messages) == 2

    def test_batch_accepted_when_no_version_declared(self):
        messages, error = mcp_transport.prepare_messages(
            [_msg("ping", 1)], header_version=None, mcp_method=None, mcp_name=None
        )
        assert error is None

    @pytest.mark.parametrize("version", ["2026-07-28", "2025-11-25", "2025-06-18"])
    def test_batch_rejected_for_post_batch_versions(self, version):
        _, error = mcp_transport.prepare_messages(
            [_msg("ping", 1)], header_version=version, mcp_method=None, mcp_name=None
        )
        assert error["error"]["code"] == -32600
        assert error["id"] is None

    def test_batch_rejected_via_meta_version(self):
        message = _msg("ping", 1)
        message["_meta"] = {META_PROTOCOL_VERSION: "2025-11-25"}
        _, error = mcp_transport.prepare_messages([message], header_version=None, mcp_method=None, mcp_name=None)
        assert error["error"]["code"] == -32600

    @pytest.mark.parametrize(
        "body",
        [[], [{"jsonrpc": "2.0", "id": 1, "method": "ping"}, 5], "nope", 7],
    )
    def test_invalid_batch_shapes_rejected(self, body):
        _, error = mcp_transport.prepare_messages(body, header_version=None, mcp_method=None, mcp_name=None)
        assert error["error"]["code"] == -32600

    def test_oversized_batch_rejected(self):
        _, error = mcp_transport.prepare_messages(
            [_msg("ping", i) for i in range(21)], header_version=None, mcp_method=None, mcp_name=None
        )
        assert error["error"]["code"] == -32600

    def test_conflicting_versions_in_batch_rejected(self):
        one = _msg("ping", 1)
        two = _msg("ping", 2)
        two["_meta"] = {META_PROTOCOL_VERSION: "2024-11-05"}
        _, error = mcp_transport.prepare_messages(
            [one, two], header_version="2025-03-26", mcp_method=None, mcp_name=None
        )
        assert error["error"]["code"] == -32020

    def test_integrity_headers_rejected_on_batch(self):
        _, error = mcp_transport.prepare_messages(
            [_msg("ping", 1)], header_version="2025-03-26", mcp_method="ping", mcp_name=None
        )
        assert error["error"]["code"] == -32020

    def test_batch_end_to_end_over_http(self, client, authed):
        response = _post(
            client,
            "/v1/mcp",
            [_msg("ping", 1), _msg("ping", 2)],
            **{"mcp-protocol-version": "2025-03-26"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert [item["id"] for item in payload] == [1, 2]

    def test_legacy_initialize_batch_accepted_when_others_undeclared(self):
        messages, error = mcp_transport.prepare_messages(
            [_msg("initialize", 1, params={"protocolVersion": "2025-03-26"}), _msg("ping", 2)],
            header_version=None,
            mcp_method=None,
            mcp_name=None,
        )
        assert error is None
        assert [message["id"] for message in messages] == [1, 2]

    def test_modern_initialize_in_batch_rejected(self):
        """An initialize's requested revision is a declaration for the whole
        batch: 2025-11-25 is handshake-era, not batch-era, so the array fails."""
        _, error = mcp_transport.prepare_messages(
            [_msg("initialize", 1, params={"protocolVersion": "2025-11-25"}), _msg("ping", 2)],
            header_version=None,
            mcp_method=None,
            mcp_name=None,
        )
        assert error["error"]["code"] == -32600

    def test_initialize_version_conflicting_with_header_rejected(self):
        _, error = mcp_transport.prepare_messages(
            [_msg("initialize", 1, params={"protocolVersion": "2025-03-26"}), _msg("ping", 2)],
            header_version="2025-11-25",
            mcp_method=None,
            mcp_name=None,
        )
        assert error["error"]["code"] == -32020

    def test_unsupported_initialize_version_rejects_batch(self):
        """An unrecognizable requested revision negotiates to the 2025-11-25
        fallback, which is not batch-era, so the array is rejected."""
        _, error = mcp_transport.prepare_messages(
            [_msg("initialize", 1, params={"protocolVersion": "1999-01-01"}), _msg("ping", 2)],
            header_version=None,
            mcp_method=None,
            mcp_name=None,
        )
        assert error["error"]["code"] == -32600

    def test_initialize_2026_request_rejects_batch(self):
        """Requesting the stateless revision negotiates the non-batch-era
        fallback, so the array is rejected."""
        _, error = mcp_transport.prepare_messages(
            [_msg("initialize", 1, params={"protocolVersion": "2026-07-28"}), _msg("ping", 2)],
            header_version=None,
            mcp_method=None,
            mcp_name=None,
        )
        assert error["error"]["code"] == -32600

    def test_initialize_without_version_rejects_batch(self):
        """An initialize with no requested revision still negotiates the
        non-batch-era fallback."""
        _, error = mcp_transport.prepare_messages(
            [_msg("initialize", 1, params={}), _msg("ping", 2)],
            header_version=None,
            mcp_method=None,
            mcp_name=None,
        )
        assert error["error"]["code"] == -32600

    def test_batch_response_stays_array_after_notification_trimmed(self, client, authed):
        response = _post(
            client,
            "/v1/mcp",
            [_msg("ping", 1), {"jsonrpc": "2.0", "method": "notifications/initialized"}],
            **{"mcp-protocol-version": "2025-03-26"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert payload[0] == {"jsonrpc": "2.0", "id": 1, "result": {}}


class TestRateLimitCharging:
    def test_admission_charged_per_message(self, client, authed):
        _post(client, "/v1/mcp", _msg("ping"))
        assert authed.admission.call_count == 1
        authed.admission.reset_mock()
        _post(
            client,
            "/v1/mcp",
            [_msg("ping", 1), _msg("ping", 2), _msg("ping", 3)],
            **{"mcp-protocol-version": "2025-03-26"},
        )
        assert authed.admission.call_count == 3

    def test_notifications_charged_and_return_202(self, client, authed):
        response = _post(client, "/v1/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert response.status_code == 202
        assert response.content == b""
        assert authed.admission.call_count == 1

    def test_malformed_write_never_burns_quota(self, client, authed):
        auth = _full_auth(memory_context=SimpleNamespace(kind="ctx"))
        bad_messages = [
            _tool_call("create_memory", ["not", "an", "object"]),  # non-dict arguments
            _msg("tools/call", params=["bad"]),  # non-dict params -> -32602
            {"jsonrpc": "1.0", "id": 1, "method": "tools/call", "params": {"name": "create_memory"}},
        ]
        with (
            patch.object(mcp_transport, "authenticate_mcp_request", return_value=auth),
            patch.object(mcp_transport, "execute_tool", return_value=FAKE_SUCCESS["create_memory"]),
            patch.object(mcp_transport, "check_rate_limit_context") as write_limiter,
        ):
            for message in bad_messages:
                response = _post(client, "/v1/mcp", message)
                assert response.status_code == 200
        write_limiter.assert_not_called()

    def test_write_bucket_uses_rest_policy_names(self, client, authed):
        auth = _full_auth(memory_context=SimpleNamespace(kind="ctx"))
        with (
            patch.object(mcp_transport, "authenticate_mcp_request", return_value=auth),
            patch.object(mcp_transport, "execute_tool", return_value=FAKE_SUCCESS["create_memory"]),
        ):
            _post(client, "/v1/mcp", _tool_call("create_memory", {"content": "x"}))
        authed.context_limit.assert_called_once_with(auth.memory_context, "memories:create")

    def test_write_bucket_429_returns_iserror_with_retry_hint(self, client, authed):
        auth = _full_auth(memory_context=SimpleNamespace(kind="ctx"))
        with (
            patch.object(mcp_transport, "authenticate_mcp_request", return_value=auth),
            patch.object(mcp_transport, "execute_tool") as execute,
            patch.object(
                mcp_transport,
                "check_rate_limit_context",
                side_effect=HTTPException(status_code=429, detail="Rate limit exceeded"),
            ),
        ):
            response = _post(client, "/v1/mcp", _tool_call("create_memory", {"content": "x"}))
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["error"]["code"] == "rate_limited"
        assert "Retry" in result["structuredContent"]["error"]["message"]
        execute.assert_not_called()  # charge precedes handler execution

    def test_write_bucket_503_returns_unavailable_without_leaking(self, client, authed, caplog):
        """Redis fail-closed in the context limiter (503) is a temporary outage,
        not an auth denial; its raw detail never reaches the model or logs."""
        auth = _full_auth(memory_context=SimpleNamespace(kind="ctx"))
        with (
            patch.object(mcp_transport, "authenticate_mcp_request", return_value=auth),
            patch.object(mcp_transport, "execute_tool") as execute,
            patch.object(
                mcp_transport,
                "check_rate_limit_context",
                side_effect=HTTPException(status_code=503, detail="private redis client addr or key"),
            ),
            caplog.at_level(logging.WARNING),
        ):
            response = _post(client, "/v1/mcp", _tool_call("create_memory", {"content": "x"}))
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["isError"] is True
        error = result["structuredContent"]["error"]
        assert error["code"] == "unavailable"
        assert "Retry" in error["message"]
        assert "private redis" not in json.dumps(result)
        assert "private redis" not in caplog.text
        execute.assert_not_called()  # charge precedes handler execution
        event = authed.tool_event.call_args.kwargs
        assert event["error_category"] == "internal"
        assert event["error_code"] == "unavailable"
        assert event["authorization_outcome"] == "not_applicable"

    def test_action_item_writes_share_write_bucket(self):
        auth = _full_auth()
        request = mcp_transport.McpRequestContext(auth_context=auth)
        for name in ("create_action_item", "complete_action_item", "update_action_item", "delete_action_item"):
            message = _tool_call(name, {"description": "x"})
            assert mcp_transport._write_rate_policy(auth, message, request) == "action_items:write"

    def test_action_item_write_charges_shared_uid_bucket(self, client, authed):
        """action_items:write shares REST's per-UID inline bucket, not the
        per-app/key memory context bucket."""
        auth = _full_auth(memory_context=SimpleNamespace(kind="ctx"))
        with (
            patch.object(mcp_transport, "authenticate_mcp_request", return_value=auth),
            patch.object(mcp_transport, "execute_tool", return_value={"success": True}),
        ):
            response = _post(client, "/v1/mcp", _tool_call("complete_action_item", {"action_item_id": "ai-1"}))
        assert response.status_code == 200
        inline_calls = [c.args for c in authed.admission.call_args_list]
        assert ("uid-test", "mcp:sse") in inline_calls
        assert ("uid-test", "action_items:write") in inline_calls
        authed.context_limit.assert_not_called()

    def test_memory_write_without_context_falls_back_to_uid_bucket(self, client, authed):
        auth = _full_auth()  # no memory_context (e.g. legacy API key)
        with (
            patch.object(mcp_transport, "authenticate_mcp_request", return_value=auth),
            patch.object(mcp_transport, "execute_tool", return_value={"success": True}),
        ):
            response = _post(client, "/v1/mcp", _tool_call("create_memory", {"content": "x"}))
        assert response.status_code == 200
        inline_calls = [c.args for c in authed.admission.call_args_list]
        assert ("uid-test", "mcp:sse") in inline_calls
        assert ("uid-test", "memories:create") in inline_calls
        authed.context_limit.assert_not_called()


class TestMalformedJsonRpc:
    @pytest.mark.parametrize(
        ("message", "expected_code", "expected_id"),
        [
            ({"id": 1, "method": "ping"}, -32600, None),  # missing jsonrpc
            ({"jsonrpc": "1.0", "id": 1, "method": "ping"}, -32600, None),
            ({"jsonrpc": "2.0", "id": 1}, -32600, None),  # missing method
            ({"jsonrpc": "2.0", "id": 1, "method": ""}, -32600, None),
            ({"jsonrpc": "2.0", "id": 1, "method": 42}, -32600, None),
            ({"jsonrpc": "2.0", "id": True, "method": "ping"}, -32600, None),  # bool id
            ({"jsonrpc": "2.0", "id": 1.5, "method": "ping"}, -32600, None),  # float id
            ({"jsonrpc": "2.0", "method": "ping"}, -32600, None),  # request missing id
            ({"jsonrpc": "2.0", "id": None, "method": "ping"}, -32600, None),
            ({"jsonrpc": "2.0", "id": 9, "method": "notifications/initialized"}, -32600, None),
            ({"jsonrpc": "2.0", "id": None, "method": "notifications/initialized"}, -32600, None),
            ({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": ["x"]}, -32602, 3),
        ],
    )
    def test_malformed_envelopes(self, message, expected_code, expected_id):
        auth = _full_auth()
        response = mcp_transport.handle_mcp_message(auth, message)
        assert response["error"]["code"] == expected_code
        assert response["id"] == expected_id

    def test_notification_without_id_produces_no_response(self):
        auth = _full_auth()
        assert mcp_transport.handle_mcp_message(auth, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

    def test_unknown_notification_still_no_response(self):
        auth = _full_auth()
        assert mcp_transport.handle_mcp_message(auth, {"jsonrpc": "2.0", "method": "notifications/bogus"}) is None

    def test_malformed_over_http(self, client, authed):
        response = _post(client, "/v1/mcp", {"jsonrpc": "1.0", "id": 1, "method": "ping"})
        assert response.status_code == 200
        assert response.json()["error"]["code"] == -32600

    def test_nonobject_body_over_http(self, client, authed):
        response = client.post("/v1/mcp", content='"nope"', headers={"Authorization": "Bearer tok"})
        assert response.status_code == 200
        assert response.json()["error"]["code"] == -32600

    def test_tools_call_nonobject_arguments_is_model_visible_error(self):
        auth = _full_auth()
        response = mcp_transport.handle_mcp_message(
            auth, _msg("tools/call", params={"name": "get_memories", "arguments": [1, 2]})
        )
        result = response["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["error"]["code"] == "invalid_arguments"

    def test_tools_call_nonobject_params_is_jsonrpc_error(self):
        auth = _full_auth()
        response = mcp_transport.handle_mcp_message(auth, _msg("tools/call", params=["get_memories"]))
        assert response["error"]["code"] == -32602
        assert response["id"] == 1

    @pytest.mark.parametrize(
        ("tool_name", "arguments"),
        [
            ("create_memory", {"content": 123}),
            ("edit_memory", {"memory_id": "m1", "content": 123}),
            ("edit_memory", {"memory_id": 7, "content": "new"}),
            ("delete_memory", {"memory_id": 7}),
            ("complete_action_item", {"action_item_id": 7}),
            ("update_action_item", {"action_item_id": 7, "description": "x"}),
            ("delete_action_item", {"action_item_id": 7}),
            ("create_action_item", {"description": 123}),
        ],
    )
    def test_required_field_type_errors_are_model_visible(self, tool_name, arguments):
        """Required text/id fields of the wrong type must surface as
        invalid_arguments (isError), never as an internal failure."""
        auth = _full_auth(memory_context=SimpleNamespace(kind="ctx"))
        response = mcp_transport.handle_mcp_message(auth, _tool_call(tool_name, arguments))
        result = response["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["error"]["code"] == "invalid_arguments"


class TestUnknownsAndScope:
    def test_unknown_method(self):
        auth = _full_auth()
        response = mcp_transport.handle_mcp_message(auth, _msg("resources/list"))
        assert response["error"]["code"] == -32601

    def test_unknown_tool(self):
        auth = _full_auth()
        response = mcp_transport.handle_mcp_message(auth, _tool_call("nonexistent_tool"))
        assert response["error"]["code"] == -32601

    def test_missing_tool_name(self):
        auth = _full_auth()
        response = mcp_transport.handle_mcp_message(auth, _msg("tools/call", params={"arguments": {}}))
        assert response["error"]["code"] == -32602

    def test_insufficient_scope_challenge(self):
        auth = _full_auth(scopes=["conversations.read"])
        response = mcp_transport.handle_mcp_message(auth, _tool_call("get_memories"))
        error = response["error"]
        assert error["code"] == -32003
        challenge = error["data"]["_meta"]["mcp/www_authenticate"]
        assert f'resource_metadata="{MCP_PROTECTED_RESOURCE_METADATA_URL}"' in challenge
        assert 'error="insufficient_scope"' in challenge
        assert 'scope="memories.read"' in challenge
        assert "/v1/mcp/sse" not in challenge  # canonical resource metadata URL

    def test_insufficient_scope_challenge_on_legacy_path(self):
        auth = _full_auth(scopes=["conversations.read"])
        request = mcp_transport.McpRequestContext(auth_context=auth, path_kind="legacy_sse")
        response = mcp_transport.handle_mcp_message(auth, _tool_call("get_memories"), request)
        challenge = response["error"]["data"]["_meta"]["mcp/www_authenticate"]
        assert f'resource_metadata="{MCP_LEGACY_PROTECTED_RESOURCE_METADATA_URL}"' in challenge

    @pytest.mark.parametrize(
        ("path", "metadata_url"),
        [
            ("/v1/mcp", MCP_PROTECTED_RESOURCE_METADATA_URL),
            ("/v1/mcp/sse", MCP_LEGACY_PROTECTED_RESOURCE_METADATA_URL),
        ],
    )
    def test_401_challenge_advertises_per_path_metadata(self, client, path, metadata_url):
        response = client.post(path, json=_msg("ping"))
        assert response.status_code == 401
        challenge = response.headers["www-authenticate"]
        assert f'resource_metadata="{metadata_url}"' in challenge

    def test_tools_list_filtered_by_scopes(self):
        auth = _full_auth(scopes=["conversations.read"])
        response = mcp_transport.handle_mcp_message(auth, _msg("tools/list"))
        names = {tool["name"] for tool in response["result"]["tools"]}
        assert names == {
            "get_conversations",
            "get_conversation_by_id",
            "get_conversations_by_ids",
            "search_conversations",
            "get_daily_summaries",
        }


class TestToolResultContract:
    def _call(self, name, **context_kwargs):
        auth = _full_auth()
        request = mcp_transport.McpRequestContext(auth_context=auth, **context_kwargs)
        return mcp_transport.handle_mcp_message(auth, _tool_call(name), request)

    @pytest.mark.parametrize("spec", TOOL_SPECS, ids=lambda spec: spec.name)
    def test_success_result_validates_against_output_schema(self, spec):
        with patch.object(mcp_transport, "execute_tool", return_value=FAKE_SUCCESS[spec.name]):
            response = self._call(spec.name)
        result = response["result"]
        assert result.get("isError") is not True
        Draft202012Validator(spec.output_schema).validate(result["structuredContent"])
        # The text channel carries the same payload, compact-encoded.
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == json.dumps(
            result["structuredContent"], ensure_ascii=False, separators=(",", ":")
        )

    @pytest.mark.parametrize("spec", TOOL_SPECS, ids=lambda spec: spec.name)
    def test_error_result_validates_against_output_schema(self, spec):
        error_payload = {"error": {"code": "unavailable", "message": "try again"}}
        Draft202012Validator(spec.output_schema).validate(error_payload)
        with patch.object(mcp_transport, "execute_tool", side_effect=ToolExecutionError("try again", code=-32009)):
            response = self._call(spec.name)
        result = response["result"]
        assert result["isError"] is True
        Draft202012Validator(spec.output_schema).validate(result["structuredContent"])

    @pytest.mark.parametrize(
        ("raised", "expected_code"),
        [
            (ToolExecutionError("gone", code=-32001), "not_found"),
            (ToolExecutionError("pay", code=-32002), "paid_plan_required"),
            (ToolExecutionError("bad", code=-32602), "invalid_arguments"),
            (ToolExecutionError("bad", code=-32000), "invalid_arguments"),
            (HTTPException(status_code=403, detail="denied"), "authorization_denied"),
            (HTTPException(status_code=404, detail="nope"), "not_found"),
            (HTTPException(status_code=402, detail="pay"), "paid_plan_required"),
            (HTTPException(status_code=429, detail="slow"), "rate_limited"),
            (authorization_denied_error("scope"), "authorization_denied"),
            (RuntimeError("boom"), "internal"),
        ],
    )
    def test_error_code_mapping(self, raised, expected_code):
        with patch.object(mcp_transport, "execute_tool", side_effect=raised):
            response = self._call("get_memories")
        result = response["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["error"]["code"] == expected_code
        if expected_code == "rate_limited":
            assert "Retry" in result["structuredContent"]["error"]["message"]

    def test_tools_list_order_deterministic(self):
        assert [tool["name"] for tool in MCP_TOOLS] == EXPECTED_TOOL_ORDER
        for tool in MCP_TOOLS:
            assert tool["title"]
            assert tool["inputSchema"]["type"] == "object"
            assert "anyOf" in tool["outputSchema"]
            for hint in ("title", "readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
                assert hint in tool["annotations"]

    @pytest.mark.parametrize("spec", TOOL_SPECS, ids=lambda spec: spec.name)
    def test_pagination_properties_advertise_enforced_bounds(self, spec):
        """Every advertised limit/offset declares the bounds the handler clamps to.

        ``parse_mcp_int`` clamps silently instead of erroring, so the advertised
        schema is the only place a client can learn the effective ceiling — a
        bound-less property invites arguments the server will quietly shrink.
        """
        for name in ("limit", "offset"):
            prop = spec.input_schema.get("properties", {}).get(name)
            if prop is None:
                continue
            assert "minimum" in prop, f"{spec.name}.{name} must advertise minimum"
            assert "maximum" in prop, f"{spec.name}.{name} must advertise maximum"

    def test_annotation_hints_match_operation_kind(self):
        by_name = {tool["name"]: tool for tool in MCP_TOOLS}
        assert by_name["get_memories"]["annotations"]["readOnlyHint"] is True
        assert by_name["create_memory"]["annotations"]["readOnlyHint"] is False
        assert by_name["create_memory"]["annotations"]["idempotentHint"] is False
        assert by_name["delete_memory"]["annotations"]["destructiveHint"] is True
        assert by_name["edit_memory"]["annotations"]["destructiveHint"] is False

    def test_non_serializable_results_are_json_safe(self):
        class Opaque:
            def __str__(self):
                return "opaque"

        with patch.object(mcp_transport, "execute_tool", return_value={"memories": [Opaque()]}):
            response = self._call("get_memories")
        assert response["result"]["structuredContent"] == {"memories": ["opaque"]}


class TestSseAcceptAndAudiences:
    def test_accept_event_stream_returns_sse_body(self, client, authed):
        response = _post(client, "/v1/mcp", _msg("ping"), accept="text/event-stream")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert "event: message" in response.text
        assert "data: " in response.text

    def test_json_default_when_no_sse_accept(self, client, authed):
        response = _post(client, "/v1/mcp", _msg("ping"))
        assert "application/json" in response.headers["content-type"]

    def test_resource_audience_canonical_equivalence(self):
        canonical = "https://api.omi.me/v1/mcp"
        legacy = "https://api.omi.me/v1/mcp/sse"
        assert mcp_oauth_db.mcp_resource_urls_match(canonical, legacy)
        assert mcp_oauth_db.mcp_resource_urls_match(legacy, canonical)
        assert not mcp_oauth_db.mcp_resource_urls_match(canonical, "https://api.omiapi.com/v1/mcp")
        client_doc = {"allowed_resources": [legacy]}
        assert mcp_oauth_db.validate_resource(client_doc, canonical)
        client_doc = {"allowed_resources": [canonical]}
        assert mcp_oauth_db.validate_resource(client_doc, legacy)
        assert not mcp_oauth_db.validate_resource({"allowed_resources": []}, canonical)

    @pytest.mark.parametrize("path", ["/v1/mcp", "/v1/mcp/sse"])
    def test_oauth_validation_uses_canonical_resource_on_both_paths(self, client, path):
        ctx = {
            "uid": "u1",
            "scopes": ALL_SCOPES,
            "client_id": "c",
            "resource": mcp_oauth_db.MCP_LEGACY_RESOURCE_URL,
            "grant_id": "g",
        }
        with (
            patch.object(mcp_oauth_db, "validate_access_token", return_value=ctx) as validate,
            patch("utils.mcp_server.auth.enforce_account_deletion_http_access"),
            patch("utils.mcp_server.auth._enforce_mcp_cutover_access"),
            patch("utils.mcp_server.auth._mcp_memory_context_from_auth_data", return_value=None),
            patch.object(mcp_transport, "check_rate_limit_inline"),
            patch.object(mcp_transport, "log_mcp_request"),
            patch.object(mcp_transport, "schedule_mcp_active"),
            patch.object(mcp_transport, "schedule_mcp_tool_call"),
        ):
            response = _post(client, path, _msg("ping"))
        assert response.status_code == 200
        # Whatever path served the request, token validation binds the canonical
        # audience; legacy-audience tokens still match via canonicalization.
        validate.assert_called_once_with("tok", mcp_oauth_db.MCP_RESOURCE_URL)


class TestMemoryToolBehavior:
    def test_create_memory_honors_explicit_category(self):
        from models.memories import MemoryCategory
        from utils.mcp_server.handlers import memories as memory_handlers

        created = {}
        service = MagicMock()
        service.create_external_memory.side_effect = (
            lambda uid, memory_db, **kw: created.setdefault("memory", memory_db) or memory_db
        )
        with (
            patch.object(
                memory_handlers,
                "authorize_memory_external_default_memory_write",
                return_value=SimpleNamespace(allowed=True, observability="ok"),
            ),
            patch.object(memory_handlers, "MemoryService", return_value=service),
            patch.object(memory_handlers, "capture_memory_write"),
            patch.object(memory_handlers, "identify_category_for_memory") as classify,
            patch.object(memory_handlers, "memory_api_payload", return_value={"id": "m1"}),
        ):
            result = memory_handlers.create_memory(
                "u1", {"content": "hello", "category": "work"}, auth_context=SimpleNamespace()
            )
        assert result["success"] is True
        assert created["memory"].category == MemoryCategory.work
        classify.assert_not_called()

    def test_create_memory_falls_back_to_classifier(self):
        from models.memories import MemoryCategory
        from utils.mcp_server.handlers import memories as memory_handlers

        service = MagicMock()
        service.create_external_memory.side_effect = lambda uid, memory_db, **kw: memory_db
        with (
            patch.object(
                memory_handlers,
                "authorize_memory_external_default_memory_write",
                return_value=SimpleNamespace(allowed=True, observability="ok"),
            ),
            patch.object(memory_handlers, "MemoryService", return_value=service),
            patch.object(memory_handlers, "capture_memory_write"),
            patch.object(
                memory_handlers, "identify_category_for_memory", return_value=MemoryCategory.interesting
            ) as classify,
            patch.object(memory_handlers, "memory_api_payload", return_value={"id": "m1"}),
        ):
            memory_handlers.create_memory(
                "u1", {"content": "hello", "category": "bogus"}, auth_context=SimpleNamespace()
            )
        classify.assert_called_once_with("hello")

    def test_update_external_memory_content_routes_through_ledger_path(self):
        from utils.memory.memory_service import MemoryService

        service = MemoryService(db_client=MagicMock())
        sentinel = object()
        with patch.object(MemoryService, "update_content", return_value=sentinel) as update:
            result = service.update_external_memory_content(
                "u1",
                "m1",
                "new content",
                memory_system=MagicMock(),
                consumer="mcp",
                operation="mcp_tool_memory_update",
                upsert_vector=False,
            )
        update.assert_called_once_with("u1", "m1", "new content")
        assert result is sentinel


class TestObservabilityNormalization:
    """Client-controlled tool names and protocol versions must never reach
    logs or event properties raw (they could carry PII-shaped payloads)."""

    PII_VERSION = "attacker@example.com|uid-12345|session-secret"
    PII_TOOL = "get_memories_for_alice@corp.io_ssn_123-45-6789"

    def test_request_log_normalizes_hostile_values(self, client, authed, capsys, caplog):
        import logging

        with caplog.at_level(logging.INFO, logger="utils.mcp_server.transport"):
            response = _post(
                client,
                "/v1/mcp",
                _tool_call(self.PII_TOOL, {"x": 1}),
                **{"mcp-protocol-version": self.PII_VERSION},
            )
        # Unsupported header version is rejected at HTTP 400, and nothing
        # client-supplied leaks into logs.
        assert response.status_code == 400
        assert response.json()["error"]["code"] == -32022
        joined = "\n".join(record.getMessage() for record in caplog.records)
        assert self.PII_VERSION not in joined
        assert self.PII_TOOL not in joined
        authed.request_log.assert_called_once()
        # The transport forwards the raw declared version to the log seam...
        assert authed.request_log.call_args.kwargs["protocol_version"] == self.PII_VERSION
        # ...and the emitted log line normalizes it away.
        mcp_analytics.log_mcp_request(
            jsonrpc_methods=["tools/call"],
            message_count=1,
            is_handshake=False,
            protocol_version=self.PII_VERSION,
            client_name="unknown",
            auth_type="oauth",
            http_status=400,
            path="canonical",
            duration_ms=1.0,
            tool_name=self.PII_TOOL,
        )
        record = json.loads(capsys.readouterr().out.strip())
        assert record["protocol_version"] == "unknown"
        assert record["tool"] == "unknown"
        assert self.PII_VERSION not in json.dumps(record)
        assert self.PII_TOOL not in json.dumps(record)

    def test_tool_call_event_normalizes_error_code_and_version(self):
        with patch.object(mcp_analytics, "emit_mcp_posthog_event") as emit:
            mcp_analytics.emit_mcp_tool_call(
                uid="u",
                tool_name=self.PII_TOOL,
                auth_type="oauth",
                client_id="raw-client-id-must-not-leak",
                outcome="error",
                authorization_outcome="not_applicable",
                error_category="internal",
                error_code=self.PII_VERSION,
                duration_ms=1.0,
                result_count=0,
                protocol_version=self.PII_VERSION,
                client_name="not-in-enum",
                user_sample_rate=1.0,
            )
        properties = emit.call_args.args[2]
        assert properties["tool"] == "unknown"
        assert properties["error_code"] == "internal"
        assert properties["protocol_version"] == "unknown"
        assert properties["client_name"] == "unknown"
        assert properties["$process_person_profile"] is False
        assert self.PII_VERSION not in json.dumps(properties)
        assert "raw-client-id-must-not-leak" not in json.dumps(properties)

    def test_tool_exception_logs_stack_with_tool_name_only(self, caplog):
        """A tool exception logs via ``logger.exception`` — the trace is
        useful server-side, but the log *message* carries only the normalized
        tool name, never arguments or user content."""
        import logging

        marker = "user-secret-memory-content-9f8e7d"
        auth = _full_auth()
        with caplog.at_level(logging.DEBUG, logger="utils.mcp_server.transport"):
            with patch.object(mcp_transport, "execute_tool", side_effect=RuntimeError(marker)):
                response = mcp_transport.handle_mcp_message(auth, _tool_call("get_memories", {"query": marker}))
        assert response["result"]["structuredContent"]["error"]["code"] == "internal"
        errors = [r for r in caplog.records if r.name == "utils.mcp_server.transport" and r.levelno >= logging.ERROR]
        assert errors, "expected the tool-failure logger.exception record"
        record = errors[0]
        assert record.exc_info is not None  # stack trace is intentional
        assert record.getMessage() == "hosted MCP tool call failed tool=get_memories"
        assert marker not in record.getMessage()

    def test_known_error_codes_pass_through(self):
        for code in (
            "none",
            "not_found",
            "paid_plan_required",
            "invalid_arguments",
            "authorization_denied",
            "rate_limited",
            "unavailable",
            "internal",
            "unknown_tool",
        ):
            assert mcp_analytics.mcp_error_code_enum(code) == code
        assert mcp_analytics.mcp_error_code_enum("anything_else") == "internal"


class TestAuthDenialPrivacy:
    def test_denied_memory_write_never_serializes_observability(self):
        from utils.mcp_server.handlers import memories as memory_handlers

        marker = "internal-grant-doc-id-9f8e7d6c_secret"
        grant = SimpleNamespace(allowed=False, observability={"grant_doc": marker, "reason": "no_grant"})
        with (
            patch.object(
                memory_handlers,
                "authorize_memory_external_default_memory_write",
                return_value=grant,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            memory_handlers.create_memory("u1", {"content": "x"}, auth_context=SimpleNamespace())
        assert marker not in str(exc_info.value)
        assert marker not in repr(exc_info.value)

        # The same denial through the transport yields the generic advice.
        auth = _full_auth(memory_context=SimpleNamespace(kind="ctx"))
        with patch.object(
            memory_handlers,
            "authorize_memory_external_default_memory_write",
            return_value=grant,
        ):
            response = mcp_transport.handle_mcp_message(auth, _tool_call("create_memory", {"content": "x"}))
        result = response["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["error"]["code"] == "authorization_denied"
        assert marker not in json.dumps(result)
        assert "permission" in result["structuredContent"]["error"]["message"]

    def test_denied_memory_grant_logs_reason_at_warning(self, caplog):
        """Grant denials log the server-side observability reason at WARNING —
        the reason only, never the rest of the observability payload."""
        import logging

        from utils.mcp_server.handlers import memories as memory_handlers

        marker = "internal-grant-doc-id-9f8e7d6c_secret"
        grant = SimpleNamespace(allowed=False, observability={"grant_doc": marker, "reason": "no_grant"})
        with (
            patch.object(
                memory_handlers,
                "authorize_memory_external_default_memory_write",
                return_value=grant,
            ),
            caplog.at_level(logging.WARNING, logger="utils.mcp_server.handlers.memories"),
            pytest.raises(Exception),
        ):
            memory_handlers.create_memory("u1", {"content": "x"}, auth_context=SimpleNamespace())
        warnings = [r for r in caplog.records if r.name == "utils.mcp_server.handlers.memories"]
        assert warnings, "expected the grant-denial warning"
        message = warnings[0].getMessage()
        assert "reason=no_grant" in message
        assert "tool=create_memory" in message
        assert marker not in message


class TestOAuthResourceCanonicalization:
    def test_scope_list_is_single_source(self):
        import config.mcp_scopes as config_scopes
        import utils.mcp_scopes as util_scopes

        assert mcp_oauth_db.SUPPORTED_SCOPES is config_scopes.MCP_FULL_ACCESS_SCOPES
        assert util_scopes.MCP_FULL_ACCESS_SCOPES is config_scopes.MCP_FULL_ACCESS_SCOPES
        assert util_scopes.MCP_FULL_ACCESS_SCOPES == [
            "memories.read",
            "memories.write",
            "conversations.read",
            "action_items.read",
            "action_items.write",
            "goals.read",
            "chat.read",
            "screen_activity.read",
            "people.read",
        ]

    def test_sse_suffixed_env_resource_is_canonicalized(self, monkeypatch):
        """A stale ``/v1/mcp/sse`` MCP_RESOURCE_URL must still advertise the
        canonical audience and accept both forms."""
        monkeypatch.setenv("MCP_RESOURCE_URL", "https://api.omi.me/v1/mcp/sse")
        module = importlib.reload(sys.modules["database.mcp_oauth"])
        try:
            assert module.MCP_RESOURCE_URL == "https://api.omi.me/v1/mcp"
            assert module.MCP_LEGACY_RESOURCE_URL == "https://api.omi.me/v1/mcp/sse"
            assert module.mcp_resource_urls_match(module.MCP_LEGACY_RESOURCE_URL, module.MCP_RESOURCE_URL)
            assert not module.mcp_resource_urls_match(module.MCP_RESOURCE_URL, "https://evil.example/v1/mcp")
        finally:
            monkeypatch.delenv("MCP_RESOURCE_URL", raising=False)
            importlib.reload(sys.modules["database.mcp_oauth"])

    def test_token_exchange_and_refresh_accept_legacy_resource(self):
        """Explicit-resource comparisons treat canonical and legacy as the same
        audience; foreign origins stay rejected."""
        canonical = "https://api.omi.me/v1/mcp"
        legacy = "https://api.omi.me/v1/mcp/sse"
        for stored, supplied in (
            (canonical, legacy),
            (legacy, canonical),
            (canonical, canonical),
        ):
            assert mcp_oauth_db.mcp_resource_urls_match(stored, supplied), (stored, supplied)
        # Omitted resource keeps the stored audience by design; foreign
        # origins and sibling paths are still rejected.
        assert not mcp_oauth_db.mcp_resource_urls_match(legacy, "https://evil.example/v1/mcp")
        assert not mcp_oauth_db.mcp_resource_urls_match(legacy, "https://api.omi.me/v1/mcp/other")


class TestRestRegistrySharing:
    """REST routes with genuinely identical semantics dispatch through the
    shared registry handlers rather than duplicating business logic."""

    def test_rest_get_goals_dispatches_through_registry(self):
        from utils.mcp_server.handlers import other as other_handlers

        with patch.object(other_handlers.goals_db, "get_all_goals", return_value=[{"id": "g1"}]) as goals:
            result = rest_mcp.get_goals(include_inactive=True, uid="u1")
        goals.assert_called_once_with("u1", include_inactive=True)
        assert result == [{"id": "g1"}]

    def test_rest_get_people_dispatches_through_registry(self):
        from utils.mcp_server.handlers import other as other_handlers

        person = {"id": "p1", "name": "Bob", "speech_samples": ["gs://secret"], "speaker_embedding": [0.1]}
        with patch.object(other_handlers.users_db, "get_people", return_value=[person]):
            result = rest_mcp.get_people(uid="u1")
        assert result == [{"id": "p1", "name": "Bob", "created_at": None, "speech_sample_transcripts": []}]
        assert "speech_samples" not in result[0]
        assert "speaker_embedding" not in result[0]


class TestProfileAndScreenOutputVariants:
    def test_profile_success_variants_validate(self):
        spec = next(s for s in TOOL_SPECS if s.name == "get_user_profile")
        validator = Draft202012Validator(spec.output_schema)
        validator.validate(
            {"profile_text": "p", "generated_at": "2026-06-11T10:30:00+00:00", "data_sources_used": ["x"]}
        )
        validator.validate({"profile_text": "p", "generated_at": None, "data_sources_used": 3})
        validator.validate({"profile_text": "p", "data_sources_used": None})
        validator.validate({"profile": None, "message": "No profile has been generated for this user yet."})
        with pytest.raises(Exception):
            validator.validate({"arbitrary": "object"})
        with pytest.raises(Exception):
            validator.validate({"profile_text": "p", "data_sources_used": "not-a-union-member"})
        with pytest.raises(Exception):
            validator.validate({"profile_text": "p", "data_sources_used": -1})

    def test_screen_activity_variants_validate(self):
        spec = next(s for s in TOOL_SPECS if s.name == "get_screen_activity")
        validator = Draft202012Validator(spec.output_schema)
        validator.validate({"screen_activity": [{"id": "r1"}]})
        validator.validate({"apps": {"Cursor": {"count": 2}}, "total_screenshots": 2, "coverage": {}})
        with pytest.raises(Exception):
            validator.validate({"arbitrary": "object"})

    def test_screen_activity_summary_with_group_by_is_invalid_arguments(self, client, authed):
        """summary=true cannot combine with a grouped projection — a
        model-visible invalid_arguments error, answered before any DB read."""
        from utils.mcp_server.handlers import other as other_handlers

        with (
            patch.object(other_handlers.screen_activity_db, "get_screen_activity_page") as page_fn,
            patch.object(other_handlers.screen_activity_db, "get_screen_activity_summary") as summary_fn,
        ):
            response = _post(client, "/v1/mcp", _tool_call("get_screen_activity", {"summary": True, "group_by": "app"}))
        result = response.json()["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["error"]["code"] == "invalid_arguments"
        page_fn.assert_not_called()
        summary_fn.assert_not_called()


def _iter_schema_properties(node):
    """Yield ``(name, property_schema)`` pairs from anywhere in a schema tree."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                yield from value.items()
                for sub in value.values():
                    yield from _iter_schema_properties(sub)
            else:
                yield from _iter_schema_properties(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_schema_properties(item)


class TestOutputSchemaTimestampFormats:
    _TIMESTAMP_FIELDS = {
        "created_at",
        "started_at",
        "finished_at",
        "due_at",
        "completed_at",
        "updated_at",
        "generated_at",
    }

    @pytest.mark.parametrize("spec", TOOL_SPECS, ids=lambda spec: spec.name)
    def test_timestamp_properties_advertise_datetime(self, spec):
        found = [name for name, prop in _iter_schema_properties(spec.output_schema) if name in self._TIMESTAMP_FIELDS]
        for name, prop in _iter_schema_properties(spec.output_schema):
            if name in self._TIMESTAMP_FIELDS:
                assert prop.get("format") == "date-time", f"{spec.name}.{name} missing date-time format"
                assert prop.get("type") in (["string", "null"], "string"), f"{spec.name}.{name}"
        if spec.name in {
            "get_user_profile",
            "get_conversations",
            "get_conversation_by_id",
            "get_conversations_by_ids",
            "search_conversations",
            "get_action_items",
            "search_action_items",
            "create_action_item",
            "complete_action_item",
            "update_action_item",
            "get_chat_messages",
            "get_x_posts",
            "search_x_posts",
            "get_people",
        }:
            assert found, f"{spec.name} should advertise timestamp properties"

    def test_datetime_results_serialize_iso8601_on_json_and_sse(self, client, authed):
        moment = datetime(2026, 6, 11, 10, 30, 0, tzinfo=timezone.utc)
        fake = {"conversations": [{"id": "c1", "meta": {"created_at": moment}}]}
        with patch.object(mcp_transport, "execute_tool", return_value=fake):
            json_response = _post(client, "/v1/mcp", _tool_call("get_conversations"))
        result = json_response.json()["result"]
        assert result["structuredContent"]["conversations"][0]["meta"]["created_at"] == "2026-06-11T10:30:00+00:00"
        assert result["content"][0]["text"] == json.dumps(
            result["structuredContent"], ensure_ascii=False, separators=(",", ":")
        )

        with patch.object(mcp_transport, "execute_tool", return_value=fake):
            sse_response = _post(client, "/v1/mcp", _tool_call("get_conversations"), accept="text/event-stream")
        frame = next(line for line in sse_response.text.splitlines() if line.startswith("data: "))
        sse_result = json.loads(frame[len("data: ") :])["result"]
        assert sse_result["structuredContent"] == result["structuredContent"]
        assert sse_result["content"][0]["text"] == result["content"][0]["text"]


class TestClientCapabilities2026:
    """Explicit 2026-07-28 declarations must carry the clientCapabilities
    ``_meta`` object — both official SDKs stamp it on every modern call."""

    @pytest.mark.parametrize("path", ["/v1/mcp", "/v1/mcp/sse"])
    def test_2026_header_without_capabilities_rejected(self, client, authed, path):
        response = _post(client, path, _msg("tools/list"), **{"mcp-protocol-version": PROTOCOL_VERSION_2026})
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == -32602
        assert META_CLIENT_CAPABILITIES in error["message"]

    @pytest.mark.parametrize("path", ["/v1/mcp", "/v1/mcp/sse"])
    def test_2026_meta_without_capabilities_rejected(self, client, authed, path):
        message = _msg("tools/list")
        message["params"] = {"_meta": {META_PROTOCOL_VERSION: PROTOCOL_VERSION_2026}}
        response = _post(client, path, message)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == -32602

    @pytest.mark.parametrize("caps", ["read-only", ["tools"], 7])
    def test_2026_non_object_capabilities_rejected(self, client, authed, caps):
        message = _msg("tools/list")
        message["params"] = {"_meta": {META_PROTOCOL_VERSION: PROTOCOL_VERSION_2026, META_CLIENT_CAPABILITIES: caps}}
        response = _post(client, "/v1/mcp", message)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == -32602

    @pytest.mark.parametrize("meta_location", ["params", "message"])
    def test_2026_empty_capabilities_accepted(self, client, authed, meta_location):
        message = _msg("tools/list")
        meta = {META_PROTOCOL_VERSION: PROTOCOL_VERSION_2026, META_CLIENT_CAPABILITIES: {}}
        if meta_location == "params":
            message["params"] = {"_meta": meta}
        else:
            message["_meta"] = meta
        response = _post(client, "/v1/mcp", message)
        assert response.status_code == 200
        assert response.json()["result"]["resultType"] == "complete"

    def test_2026_header_accepts_capabilities_in_meta(self, client, authed):
        message = _msg("tools/list")
        message["params"] = {"_meta": {META_CLIENT_CAPABILITIES: {}}}
        response = _post(client, "/v1/mcp", message, **{"mcp-protocol-version": PROTOCOL_VERSION_2026})
        assert response.status_code == 200
        assert response.json()["result"]["resultType"] == "complete"

    @pytest.mark.parametrize("path", ["/v1/mcp", "/v1/mcp/sse"])
    @pytest.mark.parametrize("header", [PROTOCOL_VERSION_2026, "2099-01-01"])
    def test_initialize_ignores_protocol_version_header(self, client, authed, path, header):
        # Prod regression 2026-09-25: a client sent ``MCP-Protocol-Version: 2026-07-28``
        # on a handshake ``initialize`` and every retry got HTTP 400.
        message = _msg("initialize")
        message["params"] = {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "probe", "version": "1"},
        }
        response = _post(client, path, message, **{"mcp-protocol-version": header})
        assert response.status_code == 200
        assert response.json()["result"]["protocolVersion"] == "2025-11-25"

    @pytest.mark.parametrize("version", ["2025-11-25", "2025-03-26"])
    def test_handshake_requests_need_no_capabilities(self, client, authed, version):
        response = _post(client, "/v1/mcp", _msg("tools/list"), **{"mcp-protocol-version": version})
        assert response.status_code == 200
        assert "tools" in response.json()["result"]

    def test_undeclared_request_needs_no_capabilities(self, client, authed):
        response = _post(client, "/v1/mcp", _msg("tools/list"))
        assert response.status_code == 200
        assert "tools" in response.json()["result"]


class TestCutoverRequestEnforcement:
    """With cutover enforcement on, POST/HEAD/DELETE hand the real Request to
    ``enforce_account_cutover_http_access``; Request-free callers keep the
    mutating-path default, and enforcement-off changes nothing."""

    def _oauth_ctx(self):
        return {
            "uid": "u1",
            "scopes": ALL_SCOPES,
            "client_id": "c",
            "resource": mcp_oauth_db.MCP_RESOURCE_URL,
            "grant_id": "g",
        }

    @contextmanager
    def _seams(self, enforce_on=True):
        with (
            patch.object(mcp_oauth_db, "validate_access_token", return_value=self._oauth_ctx()),
            patch("utils.mcp_server.auth.enforce_account_deletion_http_access"),
            patch("utils.mcp_server.auth.cutover_enforcement_enabled", return_value=enforce_on),
            patch("utils.mcp_server.auth._mcp_memory_context_from_auth_data", return_value=None),
            patch.object(mcp_transport, "check_rate_limit_inline"),
            patch.object(mcp_transport, "log_mcp_request"),
            patch.object(mcp_transport, "schedule_mcp_active"),
            patch.object(mcp_transport, "schedule_mcp_tool_call"),
        ):
            yield

    def test_post_passes_real_request_to_cutover_hook(self, client):
        with (
            self._seams(),
            patch("utils.mcp_server.auth.enforce_account_cutover_http_access") as enforce,
        ):
            response = _post(client, "/v1/mcp", _msg("ping"), **{"x-account-generation": "4"})
        assert response.status_code == 200
        enforce.assert_called_once()
        assert enforce.call_args.kwargs["method"] == "POST"
        assert enforce.call_args.kwargs["path"] == "/v1/mcp"
        assert enforce.call_args.kwargs["headers"]["authorization"] == "Bearer tok"
        assert enforce.call_args.kwargs["headers"]["x-account-generation"] == "4"

    def test_head_passes_real_request_to_cutover_hook(self, client):
        with (
            self._seams(),
            patch("utils.mcp_server.auth.enforce_account_cutover_http_access") as enforce,
        ):
            response = client.head("/v1/mcp/sse", headers={"Authorization": "Bearer tok", "X-Account-Generation": "4"})
        assert response.status_code == 200
        enforce.assert_called_once()
        assert enforce.call_args.kwargs["method"] == "HEAD"
        assert enforce.call_args.kwargs["path"] == "/v1/mcp/sse"
        assert enforce.call_args.kwargs["headers"]["authorization"] == "Bearer tok"
        assert enforce.call_args.kwargs["headers"]["x-account-generation"] == "4"

    def test_delete_passes_real_request_to_cutover_hook(self, client):
        with (
            self._seams(),
            patch("utils.mcp_server.auth.enforce_account_cutover_http_access") as enforce,
        ):
            response = client.delete("/v1/mcp", headers={"Authorization": "Bearer tok", "X-Account-Generation": "4"})
        assert response.status_code == 204
        enforce.assert_called_once()
        assert enforce.call_args.kwargs["method"] == "DELETE"
        assert enforce.call_args.kwargs["path"] == "/v1/mcp"
        assert enforce.call_args.kwargs["headers"]["x-account-generation"] == "4"

    def test_generation_header_reaches_the_real_evaluator(self, client, monkeypatch):
        """The forwarded header feeds real evaluation: a positive-generation
        account permits a matching X-Account-Generation and 403s a mismatch."""
        from database import account_cutover as account_cutover_db
        from models.account_cutover import AccountCutoverRecord, AccountCutoverState

        monkeypatch.setenv("ACCOUNT_CUTOVER_ENFORCEMENT", "on")
        record = AccountCutoverRecord(uid="u1", state=AccountCutoverState.legacy, account_generation=4)
        with (
            self._seams(),
            patch.object(account_cutover_db, "get_account_cutover_record", return_value=record),
        ):
            permitted = _post(client, "/v1/mcp", _msg("ping"), **{"x-account-generation": "4"})
            mismatched = _post(client, "/v1/mcp", _msg("ping"), **{"x-account-generation": "3"})
            missing = _post(client, "/v1/mcp", _msg("ping"))
        assert permitted.status_code == 200
        assert mismatched.status_code == 403
        assert mismatched.json()["detail"]["code"] == "account_generation_mismatch"
        assert missing.status_code == 403

    def test_no_enforcement_when_disabled(self, client):
        with (
            self._seams(enforce_on=False),
            patch("utils.mcp_server.auth.enforce_account_cutover_http_access") as enforce,
        ):
            response = _post(client, "/v1/mcp", _msg("ping"))
        assert response.status_code == 200
        enforce.assert_not_called()

    def test_request_free_caller_keeps_mutating_default(self):
        """Direct (Request-free) callers keep the documented POST /v1/mcp/sse
        default so migrating/new rules still apply fail-closed."""
        with (
            patch("utils.mcp_server.auth.cutover_enforcement_enabled", return_value=True),
            patch("utils.mcp_server.auth.enforce_account_cutover_http_access") as enforce,
        ):
            from utils.mcp_server import auth as mcp_auth

            mcp_auth._enforce_mcp_cutover_access("u1")
        enforce.assert_called_once_with("u1", method="POST", path="/v1/mcp/sse", headers={})

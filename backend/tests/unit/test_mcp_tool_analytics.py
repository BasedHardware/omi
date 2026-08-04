"""Behavioral contract for privacy-safe hosted MCP tool telemetry."""

from unittest.mock import patch

from routers import mcp_sse
from utils import mcp_analytics


def _auth(*, scopes=None, client_id="omi-chatgpt-prod"):
    return mcp_sse.MCPAuthContext(
        uid="uid-test-123",
        auth_type="oauth",
        scopes=scopes or ["memories.read", "conversations.read"],
        client_id=client_id,
    )


def test_memory_retrieval_event_has_only_bounded_allowlisted_properties(monkeypatch):
    captured = []
    monkeypatch.setattr(
        mcp_analytics,
        "emit_posthog_event",
        lambda distinct_id, event, properties: captured.append((distinct_id, event, properties)),
    )

    mcp_analytics.emit_mcp_tool_call(
        uid="uid-test-123",
        tool_name="search_memories",
        auth_type="oauth",
        client_id="omi-chatgpt-prod",
        outcome="success",
        authorization_outcome="allowed",
        error_category="none",
        duration_ms=88.9,
        result_count=2,
    )

    assert captured == [
        (
            "uid-test-123",
            "MCP Tool Call",
            {
                "tool": "search_memories",
                "operation": "memory_search",
                "client": "chatgpt",
                "transport": "hosted_oauth",
                "outcome": "success",
                "authorization_outcome": "allowed",
                "error_category": "none",
                "duration_ms": 88,
                "result_count": 2,
            },
        )
    ]
    properties = captured[0][2]
    forbidden = {"query", "content", "memory", "conversation", "token", "uid", "email", "ip", "client_id"}
    assert forbidden.isdisjoint(properties)


def test_conversation_retrieval_records_only_cardinality_at_tool_boundary(monkeypatch):
    events = []
    monkeypatch.setattr(mcp_sse, "schedule_mcp_tool_call", lambda **event: events.append(event))

    with patch.object(mcp_sse, "execute_tool", return_value={"conversations": [{"transcript": "private"}]}):
        response, _ = mcp_sse.handle_mcp_message(
            _auth(),
            {
                "id": 7,
                "method": "tools/call",
                "params": {"name": "get_conversations", "arguments": {"query": "secret query"}},
            },
        )

    assert response["result"]["content"]
    assert events == [
        {
            "uid": "uid-test-123",
            "tool_name": "get_conversations",
            "auth_type": "oauth",
            "client_id": "omi-chatgpt-prod",
            "outcome": "success",
            "authorization_outcome": "allowed",
            "error_category": "none",
            "duration_ms": events[0]["duration_ms"],
            "result_count": 1,
        }
    ]
    assert 0 <= events[0]["duration_ms"] <= 60_000
    assert "secret query" not in str(events[0])
    assert "private" not in str(events[0])


def test_authorization_and_validation_errors_emit_bounded_categories(monkeypatch):
    events = []
    monkeypatch.setattr(mcp_sse, "schedule_mcp_tool_call", lambda **event: events.append(event))

    denied, _ = mcp_sse.handle_mcp_message(
        _auth(scopes=["memories.read"]),
        {"id": 1, "method": "tools/call", "params": {"name": "get_conversations", "arguments": {}}},
    )
    invalid, _ = mcp_sse.handle_mcp_message(
        _auth(),
        {"id": 2, "method": "tools/call", "params": {"arguments": {"query": "do not capture"}}},
    )

    assert denied["error"]["code"] == -32003
    assert invalid["error"]["code"] == -32602
    assert events[0]["authorization_outcome"] == "denied"
    assert events[0]["error_category"] == "authorization_denied"
    assert events[0]["result_count"] == 0
    assert events[1]["authorization_outcome"] == "not_applicable"
    assert events[1]["error_category"] == "validation"
    assert "do not capture" not in str(events)


def test_analytics_submission_failure_does_not_change_tool_response(monkeypatch):
    def _raising_submit(*_args, **_kwargs):
        raise RuntimeError("PostHog unavailable")

    monkeypatch.setattr(mcp_analytics, "submit_with_context", _raising_submit)

    with patch.object(mcp_sse, "execute_tool", return_value={"memories": []}):
        response, _ = mcp_sse.handle_mcp_message(
            _auth(),
            {"id": 3, "method": "tools/call", "params": {"name": "get_memories", "arguments": {}}},
        )

    assert response["result"]["content"]


def test_connector_tool_names_share_the_stable_event_contract(monkeypatch):
    captured = []
    monkeypatch.setattr(
        mcp_analytics,
        "emit_posthog_event",
        lambda distinct_id, event, properties: captured.append((distinct_id, event, properties)),
    )

    for tool_name, operation in (("search", "memory_conversation_search"), ("fetch", "memory_conversation_fetch")):
        mcp_analytics.emit_mcp_tool_call(
            uid="uid-test-123",
            tool_name=tool_name,
            auth_type="oauth",
            client_id="omi-claude-prod",
            outcome="success",
            authorization_outcome="allowed",
            error_category="none",
            duration_ms=1,
            result_count=1,
        )
        assert captured[-1][1] == "MCP Tool Call"
        assert captured[-1][2]["operation"] == operation
        assert captured[-1][2]["client"] == "claude"

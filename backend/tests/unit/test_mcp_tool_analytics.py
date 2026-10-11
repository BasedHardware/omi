"""Behavioral contract for privacy-safe hosted MCP tool telemetry."""

from unittest.mock import patch

import pytest

from routers import mcp_sse
from utils import mcp_analytics
from utils.mcp_server import transport as mcp_transport


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
        "emit_mcp_posthog_event",
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
                "error_code": "none",
                "duration_ms": 88,
                "result_count": 2,
                "protocol_version": "unknown",
                "client_name": "unknown",
                "in_batch": False,
                "write_operation": "none",
                "user_sample_rate": 0.25,
                "$process_person_profile": False,
            },
        )
    ]
    properties = captured[0][2]
    forbidden = {"query", "content", "memory", "conversation", "token", "uid", "email", "ip", "client_id"}
    assert forbidden.isdisjoint(properties)


def test_conversation_retrieval_records_only_cardinality_at_tool_boundary(monkeypatch):
    events = []
    monkeypatch.setattr(mcp_transport, "schedule_mcp_tool_call", lambda **event: events.append(event))

    with patch.object(mcp_transport, "execute_tool", return_value={"conversations": [{"transcript": "private"}]}):
        response = mcp_sse.handle_mcp_message(
            _auth(),
            {
                "jsonrpc": "2.0",
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
            "error_code": "none",
            "duration_ms": events[0]["duration_ms"],
            "result_count": 1,
            "protocol_version": "2025-03-26",
            "client_name": "unknown",
            "in_batch": False,
            "write_operation": "none",
        }
    ]
    assert 0 <= events[0]["duration_ms"] <= 60_000
    assert "secret query" not in str(events[0])
    assert "private" not in str(events[0])


def test_authorization_and_validation_errors_emit_bounded_categories(monkeypatch):
    events = []
    monkeypatch.setattr(mcp_transport, "schedule_mcp_tool_call", lambda **event: events.append(event))

    denied = mcp_sse.handle_mcp_message(
        _auth(scopes=["memories.read"]),
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_conversations", "arguments": {}}},
    )
    invalid = mcp_sse.handle_mcp_message(
        _auth(),
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"arguments": {"query": "do not capture"}}},
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

    with patch.object(mcp_transport, "execute_tool", return_value={"memories": []}):
        response = mcp_sse.handle_mcp_message(
            _auth(),
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_memories", "arguments": {}}},
        )

    assert response["result"]["content"]


def test_tool_names_share_the_stable_event_contract(monkeypatch):
    captured = []
    monkeypatch.setattr(
        mcp_analytics,
        "emit_mcp_posthog_event",
        lambda distinct_id, event, properties: captured.append((distinct_id, event, properties)),
    )

    for tool_name, operation in (
        ("search_conversations", "conversation_search"),
        ("get_conversation_by_id", "conversation_get"),
    ):
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


def test_nonexistent_tool_names_never_emit_named_operations(monkeypatch):
    captured = []
    monkeypatch.setattr(
        mcp_analytics,
        "emit_mcp_posthog_event",
        lambda distinct_id, event, properties: captured.append((distinct_id, event, properties)),
    )

    for tool_name in ("search", "fetch"):
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
        assert captured[-1][2]["tool"] == "unknown"
        assert captured[-1][2]["operation"] == "other"


def test_profile_result_count_ignores_data_source_metadata_and_empty_profiles():
    assert (
        mcp_analytics.result_count_for_tool_result(
            "get_user_profile", {"profile_text": "private", "data_sources_used": ["a", "b"]}
        )
        == 1
    )
    assert (
        mcp_analytics.result_count_for_tool_result(
            "get_user_profile", {"profile": None, "message": "No profile has been generated"}
        )
        == 0
    )
    assert (
        mcp_analytics.result_count_for_tool_result(
            "get_memories", {"metadata": ["not a result"], "memories": [{"id": "one"}, {"id": "two"}]}
        )
        == 2
    )


def test_tool_execution_error_analytics_preserves_error_semantics(monkeypatch):
    events = []
    monkeypatch.setattr(mcp_transport, "schedule_mcp_tool_call", lambda **event: events.append(event))

    with patch.object(mcp_transport, "execute_tool", side_effect=mcp_sse.ToolExecutionError("query is required")):
        invalid = mcp_sse.handle_mcp_message(
            _auth(),
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search_memories", "arguments": {}}},
        )
    with patch.object(
        mcp_transport, "execute_tool", side_effect=mcp_sse.ToolExecutionError("index unavailable", code=-32009)
    ):
        unavailable = mcp_sse.handle_mcp_message(
            _auth(),
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "search_memories", "arguments": {}}},
        )
    with patch.object(mcp_transport, "execute_tool", side_effect=mcp_sse._authorization_denied_error("access denied")):
        denied = mcp_sse.handle_mcp_message(
            _auth(),
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "search_memories", "arguments": {}}},
        )

    assert invalid["result"]["structuredContent"]["error"]["code"] == "invalid_arguments"
    assert unavailable["result"]["structuredContent"]["error"]["code"] == "unavailable"
    assert denied["result"]["structuredContent"]["error"]["code"] == "authorization_denied"
    assert [(event["authorization_outcome"], event["error_category"]) for event in events] == [
        ("not_applicable", "validation"),
        ("not_applicable", "internal"),
        ("denied", "authorization_denied"),
    ]


def test_unexpected_tool_errors_are_recorded_and_return_retryable_json_rpc_error(monkeypatch):
    events = []
    monkeypatch.setattr(mcp_transport, "schedule_mcp_tool_call", lambda **event: events.append(event))

    with patch.object(mcp_transport, "execute_tool", side_effect=RuntimeError("private failure")):
        response = mcp_sse.handle_mcp_message(
            _auth(),
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "get_memories", "arguments": {}}},
        )

    assert response['result']['isError'] is True
    assert response['result']['structuredContent']['error'] == {
        'code': 'internal',
        'message': 'Tool temporarily unavailable. Retry shortly.',
    }
    assert events[0]["outcome"] == "error"
    assert events[0]["authorization_outcome"] == "not_applicable"
    assert events[0]["error_category"] == "internal"
    assert "private failure" not in str(events)


def test_not_found_and_paid_plan_errors_are_validation_not_internal(monkeypatch):
    events = []
    monkeypatch.setattr(mcp_transport, "schedule_mcp_tool_call", lambda **event: events.append(event))

    for i, code in enumerate((-32001, -32002)):
        with patch.object(mcp_transport, "execute_tool", side_effect=mcp_sse.ToolExecutionError("expected", code=code)):
            mcp_sse.handle_mcp_message(
                _auth(),
                {
                    "jsonrpc": "2.0",
                    "id": 10 + i,
                    "method": "tools/call",
                    "params": {"name": "get_conversation_by_id", "arguments": {}},
                },
            )

    assert [event["error_category"] for event in events] == ["validation", "validation"]
    assert [event["authorization_outcome"] for event in events] == ["not_applicable", "not_applicable"]


def test_read_tools_have_named_operations(monkeypatch):
    captured = []
    monkeypatch.setattr(
        mcp_analytics,
        "emit_mcp_posthog_event",
        lambda distinct_id, event, properties: captured.append(properties),
    )

    for tool_name in (
        "get_screen_activity",
        "get_daily_summaries",
        "get_action_items",
        "search_action_items",
        "get_goals",
        "get_chat_messages",
        "get_people",
        "search_x_posts",
        "get_x_posts",
    ):
        mcp_analytics.emit_mcp_tool_call(
            uid="uid-test-123",
            tool_name=tool_name,
            auth_type="oauth",
            client_id="omi-chatgpt-prod",
            outcome="success",
            authorization_outcome="allowed",
            error_category="none",
            duration_ms=1,
            result_count=0,
        )
        assert captured[-1]["operation"] != "other", tool_name


def test_screen_activity_summary_result_count_uses_screenshot_total():
    assert (
        mcp_analytics.result_count_for_tool_result(
            "get_screen_activity", {"apps": {"Safari": {"count": 3}}, "total_screenshots": 7}
        )
        == 7
    )
    # Non-summary (row list) path still counts the screen_activity list.
    assert (
        mcp_analytics.result_count_for_tool_result("get_screen_activity", {"screen_activity": [{"id": 1}, {"id": 2}]})
        == 2
    )

"""Privacy-safe product telemetry for hosted MCP tool calls.

``MCP Tool Call`` is the stable PostHog event contract for the hosted
Streamable HTTP MCP tool boundary. Its properties deliberately contain only
closed enums and bounded numeric values. In particular, they never contain
tool arguments, result content, OAuth/API-key credentials, user identifiers,
client IDs, IP addresses, or exception text.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Mapping, Optional

from utils.executors import postprocess_executor, submit_with_context
from utils.integration_telemetry import emit_posthog_event

logger = logging.getLogger(__name__)

MCP_TOOL_CALL = "MCP Tool Call"

_CHATGPT_CLIENT_IDS = frozenset(
    client_id
    for client_id in {
        "omi-chatgpt-prod",
        "omi-chatgpt-dev",
        os.getenv("MCP_OAUTH_CHATGPT_CLIENT_ID", ""),
    }
    if client_id
)
_CLAUDE_CLIENT_IDS = frozenset(
    client_id
    for client_id in {
        "omi-claude-prod",
        os.getenv("MCP_OAUTH_CLAUDE_CLIENT_ID", ""),
    }
    if client_id
)

_TOOL_OPERATIONS = {
    "get_user_profile": "memory_get",
    "get_memories": "memory_list",
    "search_memories": "memory_search",
    "get_conversations": "conversation_list",
    "get_conversation_by_id": "conversation_get",
    "search_conversations": "conversation_search",
    "get_daily_summaries": "daily_summary_list",
    "search_x_posts": "x_post_search",
    "get_x_posts": "x_post_list",
    "get_action_items": "action_item_list",
    "search_action_items": "action_item_search",
    "get_goals": "goal_list",
    "get_chat_messages": "chat_message_list",
    "get_people": "people_list",
    "get_screen_activity": "screen_activity_get",
    # Kept here for the connector branch: once search/fetch reaches this
    # boundary it automatically uses the same event contract.
    "search": "memory_conversation_search",
    "fetch": "memory_conversation_fetch",
}
_RESULT_LIST_KEY_BY_TOOL = {
    "get_memories": "memories",
    "search_memories": "memories",
    "get_conversations": "conversations",
    "search_conversations": "conversations",
    "search_x_posts": "posts",
    "get_x_posts": "posts",
    "get_action_items": "action_items",
    "search_action_items": "action_items",
    "get_goals": "goals",
    "get_chat_messages": "messages",
    "get_people": "people",
    "get_screen_activity": "screen_activity",
    "get_daily_summaries": "daily_summaries",
}
_KNOWN_TOOLS = frozenset(
    {
        "get_user_profile",
        "get_memories",
        "search_memories",
        "create_memory",
        "edit_memory",
        "delete_memory",
        "get_conversations",
        "search_conversations",
        "get_conversation_by_id",
        "get_daily_summaries",
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
        "search",
        "fetch",
    }
)


def schedule_mcp_tool_call(
    *,
    uid: str,
    tool_name: object,
    auth_type: object,
    client_id: Optional[str],
    outcome: str,
    authorization_outcome: str,
    error_category: str,
    duration_ms: float,
    result_count: int,
) -> None:
    """Queue optional analytics without delaying or changing the MCP response."""
    try:
        submit_with_context(
            postprocess_executor,
            emit_mcp_tool_call,
            uid=uid,
            tool_name=tool_name,
            auth_type=auth_type,
            client_id=client_id,
            outcome=outcome,
            authorization_outcome=authorization_outcome,
            error_category=error_category,
            duration_ms=duration_ms,
            result_count=result_count,
        )
    except Exception as exc:  # noqa: BLE001 - optional telemetry must fail open
        logger.warning("mcp analytics scheduling failed error=%s", type(exc).__name__)


def emit_mcp_tool_call(
    *,
    uid: str,
    tool_name: object,
    auth_type: object,
    client_id: Optional[str],
    outcome: str,
    authorization_outcome: str,
    error_category: str,
    duration_ms: float,
    result_count: int,
) -> None:
    """Emit the shared PostHog event using only bounded, allowlisted values."""
    properties = {
        "tool": _normalize_tool(tool_name),
        "operation": _normalize_operation(tool_name),
        "client": _normalize_client(auth_type, client_id),
        "transport": _normalize_transport(auth_type),
        "outcome": outcome if outcome in {"success", "error"} else "error",
        "authorization_outcome": (
            authorization_outcome
            if authorization_outcome in {"allowed", "denied", "not_applicable"}
            else "not_applicable"
        ),
        "error_category": (
            error_category
            if error_category in {"none", "authorization_denied", "validation", "unknown_tool", "internal"}
            else "internal"
        ),
        "duration_ms": _bounded_int(duration_ms, maximum=60_000),
        "result_count": _bounded_int(result_count, maximum=1_000),
    }
    # The shared helper owns the PostHog client and catches capture failures.
    emit_posthog_event(uid, MCP_TOOL_CALL, properties)


def result_count_for_tool_result(tool_name: object, result: Mapping[str, Any]) -> int:
    """Return only a capped top-level result cardinality, never result contents."""
    if tool_name == "get_user_profile":
        # ``data_sources_used`` is metadata, not a collection of profiles. A
        # missing profile is represented by ``{"profile": None, ...}``.
        return 1 if result.get("profile_text") else 0
    if tool_name == "get_screen_activity":
        # Summary mode returns ``{"apps": {...}, "total_screenshots": N}`` instead
        # of the ``screen_activity`` row list; count its bounded screenshot total.
        if "total_screenshots" in result:
            return _bounded_int(result.get("total_screenshots"), maximum=1_000)
    list_key = _RESULT_LIST_KEY_BY_TOOL.get(_normalize_tool(tool_name))
    if list_key is not None:
        value = result.get(list_key)
        return _bounded_int(len(value), maximum=1_000) if isinstance(value, list) else 0
    operation = _normalize_operation(tool_name)
    if operation.endswith("_get") or operation.endswith("_fetch"):
        return 1 if result else 0
    return 0


def error_category_for_code(code: int, *, authorization_denied: bool = False) -> str:
    if authorization_denied or code == -32003:
        return "authorization_denied"
    if code in {-32602, -32000, -32001, -32002}:
        # -32001 (not found) and -32002 (paid-plan/locked) are expected
        # client/product-gating outcomes, not backend failures; classifying
        # them as validation keeps the internal-error bucket meaningful.
        return "validation"
    if code == -32601:
        return "unknown_tool"
    return "internal"


def authorization_outcome_for_code(code: int, *, authorization_denied: bool = False) -> str:
    return "denied" if authorization_denied or code == -32003 else "not_applicable"


def _normalize_tool(tool_name: object) -> str:
    return tool_name if isinstance(tool_name, str) and tool_name in _KNOWN_TOOLS else "unknown"


def _normalize_operation(tool_name: object) -> str:
    normalized_tool = _normalize_tool(tool_name)
    return _TOOL_OPERATIONS.get(normalized_tool, "other")


def _normalize_client(auth_type: object, client_id: Optional[str]) -> str:
    if auth_type == "legacy_mcp_key":
        return "api_key"
    if auth_type != "oauth":
        return "unknown"
    if client_id in _CHATGPT_CLIENT_IDS:
        return "chatgpt"
    if client_id in _CLAUDE_CLIENT_IDS:
        return "claude"
    # OAuth token validation means this is a registered client. Do not publish
    # its raw client ID as an analytics dimension.
    return "other_registered"


def _normalize_transport(auth_type: object) -> str:
    if auth_type == "oauth":
        return "hosted_oauth"
    if auth_type == "legacy_mcp_key":
        return "api_key"
    return "unknown"


def _bounded_int(value: object, *, maximum: int) -> int:
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        return max(0, min(int(value), maximum))
    except (TypeError, ValueError, OverflowError):
        return 0

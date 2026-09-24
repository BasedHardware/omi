"""Privacy-safe product telemetry for hosted MCP tool calls and requests.

``MCP Tool Call`` is the stable PostHog event contract for the hosted
Streamable HTTP MCP tool boundary, and ``MCP Request`` is the sampled
per-POST envelope event. Their properties deliberately contain only
closed enums and bounded numeric values. In particular, they never contain
tool arguments, result content, OAuth/API-key credentials, user identifiers,
client IDs, IP addresses, user agents, or exception text.
"""

from __future__ import annotations

import logging
import math
import os
import random
from typing import Any, List, Mapping, Optional

from utils.executors import postprocess_executor, submit_with_context
from utils.integration_telemetry import emit_posthog_event
from utils.mcp_server.constants import MCP_MAX_BATCH_MESSAGES
from utils.mcp_server.registry import TOOL_SPECS
from utils.mcp_server.versions import SUPPORTED_PROTOCOL_VERSIONS

logger = logging.getLogger(__name__)

MCP_TOOL_CALL = "MCP Tool Call"
MCP_REQUEST = "MCP Request"
MCP_ANONYMOUS_DISTINCT_ID = "mcp-anonymous"

MCP_REQUEST_EVENT_SAMPLE_RATE_ENV = "MCP_REQUEST_EVENT_SAMPLE_RATE"
MCP_TOOL_CALL_EVENT_SAMPLE_RATE_ENV = "MCP_TOOL_CALL_EVENT_SAMPLE_RATE"
MCP_REQUEST_SAMPLE_RATE_DEFAULT = 0.05
MCP_TOOL_CALL_SAMPLE_RATE_DEFAULT = 1.0

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

# Registry is the single source of truth for tool names, operations, and write
# operations; analytics never allowlists a tool the server cannot dispatch.
_TOOL_OPERATIONS = {spec.name: spec.operation for spec in TOOL_SPECS}
_KNOWN_TOOLS = frozenset(spec.name for spec in TOOL_SPECS)
_WRITE_OPERATIONS = frozenset({spec.write_operation for spec in TOOL_SPECS} | {"other"})
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

_MCP_CLIENT_NAMES = frozenset(
    {
        "claude_code",
        "claude_ai",
        "claude_desktop",
        "cursor",
        "codex",
        "chatgpt",
        "grok_cli",
        "python_sdk",
        "node_sdk",
        "other",
        "unknown",
    }
)

_MCP_METHODS = frozenset(
    {
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
        "ping",
        "server/discover",
        "subscriptions/listen",
        "unknown",
    }
)


def normalize_client_name(client_name: Any, user_agent: Any) -> str:
    """Normalize clientInfo.name/User-Agent into the closed client enum."""
    text = client_name if isinstance(client_name, str) and client_name else ""
    if not text:
        text = user_agent if isinstance(user_agent, str) else ""
    text = text.lower()
    if not text:
        return "unknown"
    if "claude-code" in text or "claude_code" in text:
        return "claude_code"
    if "claude-user" in text or "claude.ai" in text or "claude_ai" in text:
        return "claude_ai"
    if "claude" in text:
        return "claude_desktop"
    if "cursor" in text:
        return "cursor"
    if "codex" in text or "openai-mcp" in text:
        return "codex"
    if "chatgpt" in text or "openai" in text:
        return "chatgpt"
    if "grok" in text:
        return "grok_cli"
    if "python" in text or "httpx" in text or "urllib" in text or "aiohttp" in text:
        return "python_sdk"
    if "undici" in text or "node" in text or "bun" in text:
        return "node_sdk"
    return "other"


def mcp_method_enum(method: Any) -> str:
    return method if isinstance(method, str) and method in _MCP_METHODS else "unknown"


def mcp_tool_enum(tool_name: Any) -> str:
    """Tool names are allowlisted to the registry; anything else is ``unknown``."""
    return _normalize_tool(tool_name)


def mcp_protocol_version_enum(version: Any) -> str:
    return version if isinstance(version, str) and version in SUPPORTED_PROTOCOL_VERSIONS else "unknown"


_MCP_ERROR_CODES = frozenset(
    {
        "none",
        "not_found",
        "paid_plan_required",
        "invalid_arguments",
        "authorization_denied",
        "rate_limited",
        "unavailable",
        "internal",
        "unknown_tool",
    }
)


def mcp_error_code_enum(error_code: Any) -> str:
    return error_code if isinstance(error_code, str) and error_code in _MCP_ERROR_CODES else "internal"


def _sample_rate(env_name: str, default: float) -> float:
    raw = os.getenv(env_name)
    if raw is None:
        return default
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(rate):
        return default
    return max(0.0, min(rate, 1.0))


def _bounded_sample_rate(value: Any, default: float) -> float:
    """Event property: sample rates are finite and bounded to [0, 1]."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return default
    if not math.isfinite(value):
        return default
    return max(0.0, min(value, 1.0))


def request_sample_rate() -> float:
    return _sample_rate(MCP_REQUEST_EVENT_SAMPLE_RATE_ENV, MCP_REQUEST_SAMPLE_RATE_DEFAULT)


def tool_call_sample_rate() -> float:
    return _sample_rate(MCP_TOOL_CALL_EVENT_SAMPLE_RATE_ENV, MCP_TOOL_CALL_SAMPLE_RATE_DEFAULT)


def _sampled(rate: float) -> bool:
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    return random.random() < rate


def schedule_mcp_request(
    *,
    uid: Optional[str],
    jsonrpc_methods: List[str],
    message_count: int,
    is_handshake: bool,
    protocol_version: Any,
    client_name: Any,
    transport: Any,
    http_status: Any,
    path: Any,
    duration_ms: float,
    tool_name: Any = None,
) -> None:
    """Queue the sampled per-POST ``MCP Request`` event without delaying the response."""
    rate = request_sample_rate()
    if not _sampled(rate):
        return
    try:
        submit_with_context(
            postprocess_executor,
            emit_mcp_request,
            uid=uid,
            jsonrpc_methods=jsonrpc_methods,
            message_count=message_count,
            is_handshake=is_handshake,
            protocol_version=protocol_version,
            client_name=client_name,
            transport=transport,
            http_status=http_status,
            path=path,
            duration_ms=duration_ms,
            tool_name=tool_name,
            sample_rate=rate,
        )
    except Exception as exc:  # noqa: BLE001 - optional telemetry must fail open
        logger.warning("mcp request analytics scheduling failed error=%s", type(exc).__name__)


def emit_mcp_request(
    *,
    uid: Optional[str],
    jsonrpc_methods: List[str],
    message_count: int,
    is_handshake: bool,
    protocol_version: Any,
    client_name: Any,
    transport: Any,
    http_status: Any,
    path: Any,
    duration_ms: float,
    tool_name: Any = None,
    sample_rate: float = MCP_REQUEST_SAMPLE_RATE_DEFAULT,
) -> None:
    """Emit the per-POST envelope event using only bounded, allowlisted values."""
    properties = {
        "jsonrpc_methods": [mcp_method_enum(method) for method in (jsonrpc_methods or [])][:MCP_MAX_BATCH_MESSAGES],
        "message_count": _bounded_int(message_count, maximum=100),
        "is_handshake": bool(is_handshake),
        "protocol_version": mcp_protocol_version_enum(protocol_version),
        "client_name": client_name if client_name in _MCP_CLIENT_NAMES else "unknown",
        "transport": _normalize_transport(transport),
        "http_status": _bounded_int(http_status, maximum=599),
        "path": path if path in {"canonical", "legacy_sse"} else "other",
        "duration_ms": _bounded_int(duration_ms, maximum=60_000),
        "tool": mcp_tool_enum(tool_name),
        "sample_rate": _bounded_sample_rate(sample_rate, MCP_REQUEST_SAMPLE_RATE_DEFAULT),
    }
    emit_posthog_event(uid or MCP_ANONYMOUS_DISTINCT_ID, MCP_REQUEST, properties)


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
    error_code: str = "none",
    protocol_version: Any = "unknown",
    client_name: Any = "unknown",
    in_batch: bool = False,
    write_operation: Any = "none",
) -> None:
    """Queue optional analytics without delaying or changing the MCP response."""
    rate = tool_call_sample_rate()
    if not _sampled(rate):
        return
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
            error_code=error_code,
            duration_ms=duration_ms,
            result_count=result_count,
            protocol_version=protocol_version,
            client_name=client_name,
            in_batch=in_batch,
            write_operation=write_operation,
            sample_rate=rate,
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
    error_code: str = "none",
    protocol_version: Any = "unknown",
    client_name: Any = "unknown",
    in_batch: bool = False,
    write_operation: Any = "none",
    sample_rate: float = MCP_TOOL_CALL_SAMPLE_RATE_DEFAULT,
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
        "error_code": mcp_error_code_enum(error_code),
        "duration_ms": _bounded_int(duration_ms, maximum=60_000),
        "result_count": _bounded_int(result_count, maximum=1_000),
        "protocol_version": mcp_protocol_version_enum(protocol_version),
        "client_name": client_name if client_name in _MCP_CLIENT_NAMES else "unknown",
        "in_batch": bool(in_batch),
        "write_operation": write_operation if write_operation in _WRITE_OPERATIONS else "other",
        "sample_rate": _bounded_sample_rate(sample_rate, MCP_TOOL_CALL_SAMPLE_RATE_DEFAULT),
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

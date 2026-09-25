"""Privacy-safe product telemetry for hosted MCP tool calls and requests.

``MCP Tool Call`` is the stable PostHog event contract for the hosted
Streamable HTTP MCP tool boundary, and ``MCP Active`` is the once-per-uid-
per-day marker that keeps DAU/WAU exact. The per-POST envelope is NOT a
PostHog event: it is a structured ``mcp_request`` log line emitted for 100%
of requests so log-based metrics carry the volume PostHog pricing cannot.

PostHog properties deliberately contain only closed enums and bounded
numeric values. In particular, they never contain tool arguments, result
content, OAuth/API-key credentials, user identifiers, client IDs, IP
addresses, user agents, or exception text.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import math
import os
import sys
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, List, Mapping, Optional

import database.redis_db as redis_db
from utils.executors import postprocess_executor, submit_with_context
from utils.integration_telemetry import emit_posthog_event
from utils.mcp_server.constants import MCP_MAX_BATCH_MESSAGES
from utils.mcp_server.registry import TOOL_SPECS
from utils.mcp_server.versions import SUPPORTED_PROTOCOL_VERSIONS

logger = logging.getLogger(__name__)

MCP_TOOL_CALL = "MCP Tool Call"
MCP_ACTIVE = "MCP Active"
MCP_ANONYMOUS_DISTINCT_ID = "mcp-anonymous"

MCP_REQUEST_LOG_MESSAGE = "mcp_request"

MCP_TOOL_CALL_USER_SAMPLE_RATE_ENV = "MCP_TOOL_CALL_USER_SAMPLE_RATE"
MCP_TOOL_CALL_USER_SAMPLE_RATE_DEFAULT = 0.25
# Fixed salt: the sampling decision for a uid must stay stable across deploys
# and instances, so it is keyed by an in-code constant, never an env secret.
MCP_TOOL_CALL_USER_SAMPLE_SALT = "omi:mcp-tool-call:user-sample:v1:"

# One ``MCP Active`` marker per uid per UTC day, deduped by a Redis NX claim
# with a 48-hour TTL so exact-day boundaries never emit twice.
MCP_ACTIVE_REDIS_PREFIX = "mcp:active"
MCP_ACTIVE_TTL_SECONDS = 172800

MCP_ACTIVE_LOCAL_SEEN_MAX = 100_000
_mcp_active_seen_uids: "OrderedDict[str, None]" = OrderedDict()
_mcp_active_seen_day: Optional[str] = None
_mcp_active_seen_lock = threading.Lock()


def _utc_day(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%d")


def _mcp_active_seen_reset_day(now: Optional[datetime] = None) -> str:
    """Return the current UTC day, clearing the local cache on rollover."""
    global _mcp_active_seen_day
    day = _utc_day(now)
    if _mcp_active_seen_day != day:
        _mcp_active_seen_uids.clear()
        _mcp_active_seen_day = day
    return day


def _mcp_active_locally_seen(uid: str, *, now: Optional[datetime] = None) -> bool:
    with _mcp_active_seen_lock:
        _mcp_active_seen_reset_day(now)
        return uid in _mcp_active_seen_uids


def _mcp_active_mark_local(uid: str, *, now: Optional[datetime] = None) -> None:
    with _mcp_active_seen_lock:
        _mcp_active_seen_reset_day(now)
        _mcp_active_seen_uids[uid] = None
        while len(_mcp_active_seen_uids) > MCP_ACTIVE_LOCAL_SEEN_MAX:
            _mcp_active_seen_uids.popitem(last=False)


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
    "create_memories": "results",
    "get_conversations": "conversations",
    "get_conversations_by_ids": "conversations",
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


def tool_call_user_sample_rate() -> float:
    return _sample_rate(MCP_TOOL_CALL_USER_SAMPLE_RATE_ENV, MCP_TOOL_CALL_USER_SAMPLE_RATE_DEFAULT)


def user_in_tool_call_sample(uid: Any, rate: float) -> bool:
    """Deterministic per-uid sampling: a uid is either fully in or fully out.

    The decision is a salted SHA256 bucket of the uid — identical on every
    instance and deploy, with no per-event randomness — so a sampled user's
    calls are ALL sent, keeping per-user journeys intact.
    """
    if not isinstance(uid, str) or not uid or rate <= 0:
        return False
    if rate >= 1:
        return True
    bucket = int(hashlib.sha256((MCP_TOOL_CALL_USER_SAMPLE_SALT + uid).encode("utf-8")).hexdigest()[:8], 16)
    return bucket / 0xFFFFFFFF < rate


_mcp_events_client: Optional[Any] = None
_mcp_events_client_disabled = False


def _build_mcp_events_client(api_key: str) -> Any:
    host = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
    posthog_module = importlib.import_module("posthog")
    posthog_client_cls = getattr(posthog_module, "Posthog")
    return posthog_client_cls(project_api_key=api_key, host=host)


def _get_mcp_events_client() -> Optional[Any]:
    """Dedicated capture client for MCP events, built from the events key only.

    The events key is never mixed into generic capture, and this client never
    falls back to the project key — when POSTHOG_EVENTS_API_KEY is unset the
    caller falls back to the generic emit path instead.
    """
    global _mcp_events_client, _mcp_events_client_disabled
    if _mcp_events_client_disabled:
        return None
    if _mcp_events_client is not None:
        return _mcp_events_client

    api_key = os.getenv("POSTHOG_EVENTS_API_KEY")
    if not api_key:
        return None

    try:
        _mcp_events_client = _build_mcp_events_client(api_key)
    except Exception as exc:
        logger.warning("mcp analytics posthog_import_failed error=%s", type(exc).__name__)
        _mcp_events_client_disabled = True
        return None
    return _mcp_events_client


def emit_mcp_posthog_event(distinct_id: Optional[str], event: str, properties: dict) -> None:
    """Capture one MCP event through the dedicated events-key client.

    Falls back to the generic emit path when POSTHOG_EVENTS_API_KEY is unset
    (or the dedicated client cannot be built) so dev keeps working as today.
    """
    if not distinct_id:
        return
    client = _get_mcp_events_client()
    if client is None:
        emit_posthog_event(distinct_id, event, properties)
        return
    try:
        client.capture(distinct_id=distinct_id, event=event, properties=properties)
    except Exception as exc:
        logger.warning("mcp analytics posthog_emit_failed event=%s error=%s", event, type(exc).__name__)


def set_mcp_events_client_for_tests(client: Optional[Any]) -> None:
    global _mcp_events_client, _mcp_events_client_disabled
    _mcp_events_client = client
    _mcp_events_client_disabled = client is None


def log_mcp_request(
    *,
    jsonrpc_methods: List[str],
    message_count: int,
    is_handshake: bool,
    protocol_version: Any,
    client_name: Any,
    auth_type: Any,
    http_status: Any,
    path: Any,
    duration_ms: float,
    tool_name: Any = None,
) -> None:
    """Write the per-POST ``mcp_request`` envelope as one exact JSON object.

    Emitted for 100% of POSTs — including auth and rate-limit failures — so
    Cloud Logging ingests it as ``jsonPayload`` and log-based metrics can be
    built on it. This is the only place these fields are emitted; there is no
    ``MCP Request`` PostHog event.
    """
    event = {
        "message": MCP_REQUEST_LOG_MESSAGE,
        "jsonrpc_methods": [mcp_method_enum(method) for method in (jsonrpc_methods or [])][:MCP_MAX_BATCH_MESSAGES],
        "message_count": _bounded_int(message_count, maximum=100),
        "is_handshake": bool(is_handshake),
        "protocol_version": mcp_protocol_version_enum(protocol_version),
        "client_name": client_name if client_name in _MCP_CLIENT_NAMES else "unknown",
        "auth_type": _normalize_transport(auth_type),
        "http_status": _bounded_int(http_status, maximum=599),
        "path": path if path in {"canonical", "legacy_sse"} else "other",
        "duration_ms": _bounded_int(duration_ms, maximum=60_000),
        "tool": mcp_tool_enum(tool_name),
    }
    try:
        sys.stdout.write(json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n")
        sys.stdout.flush()
    except Exception as exc:  # noqa: BLE001 - request logging must fail open
        logger.warning("mcp_request log write failed error=%s", type(exc).__name__)


def schedule_mcp_active(
    *,
    uid: Optional[str],
    client_name: Any,
    transport: Any,
    protocol_version: Any,
    first_tool: Any = None,
) -> None:
    """Queue the once-per-uid-per-day ``MCP Active`` marker without delaying the response."""
    if not uid or uid == MCP_ANONYMOUS_DISTINCT_ID:
        return
    if _mcp_active_locally_seen(uid):
        return
    try:
        submit_with_context(
            postprocess_executor,
            emit_mcp_active,
            uid=uid,
            client_name=client_name,
            transport=transport,
            protocol_version=protocol_version,
            first_tool=first_tool,
        )
    except Exception as exc:  # noqa: BLE001 - optional telemetry must fail open
        logger.warning("mcp active analytics scheduling failed error=%s", type(exc).__name__)


def _claim_daily_active_marker(uid: str, *, now: Optional[datetime] = None) -> Optional[bool]:
    """Redis ``SET NX EX`` dedupe: True only for the first claim of the UTC day.

    Returns ``None`` when Redis errored, so callers skip local caching and
    keep retrying. Fail-open: a Redis error skips the marker event but never
    blocks or fails the request it rode in on.
    """
    day = _utc_day(now)
    try:
        claimed = redis_db.r.set(f"{MCP_ACTIVE_REDIS_PREFIX}:{day}:{uid}", "1", nx=True, ex=MCP_ACTIVE_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 - dedupe failures skip the event
        logger.warning("mcp active marker dedupe failed error=%s", type(exc).__name__)
        return None
    return bool(claimed)


def emit_mcp_active(
    *,
    uid: str,
    client_name: Any,
    transport: Any,
    protocol_version: Any,
    first_tool: Any = None,
) -> None:
    """Emit the daily active marker; the NX claim caps it at one per uid per UTC day."""
    now = datetime.now(timezone.utc)
    if _mcp_active_locally_seen(uid, now=now):
        return
    claimed = _claim_daily_active_marker(uid, now=now)
    if claimed is None:
        return
    _mcp_active_mark_local(uid, now=now)
    if not claimed:
        return
    properties = {
        "client_name": client_name if client_name in _MCP_CLIENT_NAMES else "unknown",
        "transport": _normalize_transport(transport),
        "protocol_version": mcp_protocol_version_enum(protocol_version),
        "first_tool": mcp_tool_enum(first_tool) if first_tool else "none",
        "$process_person_profile": False,
    }
    emit_mcp_posthog_event(uid, MCP_ACTIVE, properties)


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
    rate = tool_call_user_sample_rate()
    if not user_in_tool_call_sample(uid, rate):
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
            user_sample_rate=rate,
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
    user_sample_rate: float = MCP_TOOL_CALL_USER_SAMPLE_RATE_DEFAULT,
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
        "user_sample_rate": _bounded_sample_rate(user_sample_rate, MCP_TOOL_CALL_USER_SAMPLE_RATE_DEFAULT),
        "$process_person_profile": False,
    }
    # The dedicated MCP capture client owns PostHog and catches capture failures.
    emit_mcp_posthog_event(uid, MCP_TOOL_CALL, properties)


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
        buckets = result.get("buckets")
        if isinstance(buckets, list):
            return _bounded_int(len(buckets), maximum=1_000)
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

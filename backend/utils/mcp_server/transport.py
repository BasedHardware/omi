"""Streamable HTTP transport and JSON-RPC dispatch for the hosted MCP server.

Both the canonical ``/v1/mcp`` and legacy ``/v1/mcp/sse`` routes delegate here.
The transport is stateless: bearer-token auth scopes every request, POST-level
rate limiting charges once per JSON-RPC message, and tool execution failures
surface as model-visible ``isError`` results rather than JSON-RPC errors.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, cast

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from utils.executors import critical_executor, db_executor, run_blocking
from utils.mcp_analytics import (
    authorization_outcome_for_code,
    error_category_for_code,
    log_mcp_request,
    mcp_method_enum,
    mcp_tool_enum,
    normalize_client_name,
    result_count_for_tool_result,
    schedule_mcp_active,
    schedule_mcp_tool_call,
)
from utils.mcp_context import MCP_SERVER_INSTRUCTIONS
from utils.mcp_server.auth import MCPAuthContext, authenticate_mcp_request, invalid_mcp_auth_exception
from utils.mcp_server.constants import MCP_MAX_BATCH_MESSAGES
from utils.mcp_server.errors import ToolExecutionError, stable_error_code, tool_error_from_http
from utils.mcp_server.metadata import protected_resource_metadata_url
from utils.mcp_server.payloads import (
    complete_result as _complete_result,
    tool_error_payload as _tool_error_payload,
    tool_result_payload as _tool_result_payload,
)
from utils.mcp_server.registry import (
    MCP_TOOLS,
    TOOL_REQUIRED_SCOPE,
    execute_tool,
    spec_for_tool,
)
from utils.mcp_server.versions import (
    DEFAULT_PROTOCOL_VERSION,
    JSONRPC_VERSION,
    MCP_CAPABILITIES,
    MCP_METHOD_HEADER,
    MCP_NAME_HEADER,
    MCP_PROTOCOL_VERSION_HEADER,
    META_CLIENT_CAPABILITIES,
    PROTOCOL_VERSION_2026,
    SERVER_INFO,
    SUPPORTED_PROTOCOL_VERSIONS,
    TOOLS_LIST_CACHE_SCOPE,
    TOOLS_LIST_TTL_MS,
    JsonRpcProtocolError,
    client_info_name,
    declared_client_capabilities,
    declared_protocol_version,
    is_batch_era_version,
    is_supported_version,
    negotiate_protocol_version,
    resolve_effective_version,
    unsupported_version_error,
)
from utils.other.endpoints import check_rate_limit_context, check_rate_limit_inline

logger = logging.getLogger(__name__)


@dataclass
class McpRequestContext:
    """Per-POST context shared by every message in the request."""

    auth_context: MCPAuthContext
    header_version: Optional[str] = None
    mcp_method: Optional[str] = None
    mcp_name: Optional[str] = None
    in_batch: bool = False
    client_name: str = "unknown"
    user_agent: Optional[str] = None
    path_kind: str = "canonical"
    extra: Dict[str, Any] = field(default_factory=dict)


def create_mcp_response(id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    """Create a JSON-RPC 2.0 response."""
    return {"jsonrpc": JSONRPC_VERSION, "id": id, "result": result}


def create_mcp_error(id: Any, code: int, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create a JSON-RPC 2.0 error response."""
    error: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": id, "error": error}


def _protocol_error_response(msg_id: Any, exc: JsonRpcProtocolError) -> Dict[str, Any]:
    return create_mcp_error(msg_id, exc.code, exc.message, data=exc.data)


def _tools_for_scopes(scopes: List[str]) -> List[Dict[str, Any]]:
    scope_set = set(scopes)
    return [tool for tool in MCP_TOOLS if TOOL_REQUIRED_SCOPE.get(tool["name"]) in scope_set]


def require_tool_scope(auth_context: MCPAuthContext, tool_name: str) -> None:
    required_scope = TOOL_REQUIRED_SCOPE.get(tool_name)
    if required_scope and required_scope not in set(auth_context.scopes):
        raise ToolExecutionError(f"Insufficient scope: {required_scope}", code=-32003)


_require_tool_scope = require_tool_scope


def _tool_call_analytics(
    auth_context: MCPAuthContext,
    request: McpRequestContext,
    tool_name: Any,
    *,
    outcome: str,
    authorization_outcome: str,
    error_category: str,
    error_code: str,
    duration_ms: float,
    result_count: int,
    effective_version: str,
) -> None:
    spec = spec_for_tool(tool_name)
    schedule_mcp_tool_call(
        uid=auth_context.uid,
        tool_name=tool_name,
        auth_type=auth_context.auth_type,
        client_id=auth_context.client_id,
        outcome=outcome,
        authorization_outcome=authorization_outcome,
        error_category=error_category,
        error_code=error_code,
        duration_ms=duration_ms,
        result_count=result_count,
        protocol_version=effective_version,
        client_name=request.client_name,
        in_batch=request.in_batch,
        write_operation=spec.write_operation if spec is not None else "none",
    )


def _handle_tool_call(
    auth_context: MCPAuthContext,
    request: McpRequestContext,
    msg_id: Any,
    params: Dict[str, Any],
    effective_version: str,
) -> Optional[Dict[str, Any]]:
    tool_name = params.get("name")
    if "arguments" in params and not isinstance(params["arguments"], dict):
        _tool_call_analytics(
            auth_context,
            request,
            tool_name,
            outcome="error",
            authorization_outcome="not_applicable",
            error_category="validation",
            error_code="invalid_arguments",
            duration_ms=0,
            result_count=0,
            effective_version=effective_version,
        )
        return create_mcp_response(
            msg_id,
            _complete_result(
                _tool_error_payload("invalid_arguments", "tools/call arguments must be an object."),
                effective_version,
            ),
        )
    arguments: Dict[str, Any] = cast(Dict[str, Any], params.get("arguments") or {})

    if not isinstance(tool_name, str) or not tool_name:
        _tool_call_analytics(
            auth_context,
            request,
            tool_name,
            outcome="error",
            authorization_outcome="not_applicable",
            error_category="validation",
            error_code="invalid_arguments",
            duration_ms=0,
            result_count=0,
            effective_version=effective_version,
        )
        return create_mcp_error(msg_id, -32602, "Tool name is required")

    started_at = time.monotonic()
    tool_error: Optional[ToolExecutionError] = None
    result: Optional[Dict[str, Any]] = None
    try:
        require_tool_scope(auth_context, tool_name)
        result = execute_tool(auth_context.uid, tool_name, arguments, auth_context=auth_context.memory_context)
    except ToolExecutionError as e:
        tool_error = e
    except HTTPException as exc:
        tool_error = tool_error_from_http(exc)
    except Exception:
        logger.exception("hosted MCP tool call failed tool=%s", mcp_tool_enum(tool_name))
        _tool_call_analytics(
            auth_context,
            request,
            tool_name,
            outcome="error",
            authorization_outcome="not_applicable",
            error_category="internal",
            error_code="internal",
            duration_ms=(time.monotonic() - started_at) * 1_000,
            result_count=0,
            effective_version=effective_version,
        )
        return create_mcp_response(
            msg_id,
            _complete_result(
                _tool_error_payload("internal", "Tool temporarily unavailable. Retry shortly."),
                effective_version,
            ),
        )

    if tool_error is not None:
        # Scope and dispatch failures stay JSON-RPC errors; the insufficient_scope
        # challenge advertises the canonical protected-resource metadata.
        if tool_error.code == -32003:
            _tool_call_analytics(
                auth_context,
                request,
                tool_name,
                outcome="error",
                authorization_outcome=authorization_outcome_for_code(
                    tool_error.code, authorization_denied=tool_error.analytics_authorization_denied
                ),
                error_category=error_category_for_code(
                    tool_error.code, authorization_denied=tool_error.analytics_authorization_denied
                ),
                error_code=stable_error_code(tool_error),
                duration_ms=(time.monotonic() - started_at) * 1_000,
                result_count=0,
                effective_version=effective_version,
            )
            required_scope = TOOL_REQUIRED_SCOPE.get(tool_name)
            return create_mcp_error(
                msg_id,
                tool_error.code,
                tool_error.message,
                data={
                    "_meta": {
                        "mcp/www_authenticate": (
                            f'Bearer resource_metadata="{protected_resource_metadata_url(request.path_kind)}", '
                            f'error="insufficient_scope", scope="{required_scope}"'
                        )
                    }
                },
            )
        if tool_error.code == -32601:
            _tool_call_analytics(
                auth_context,
                request,
                tool_name,
                outcome="error",
                authorization_outcome="not_applicable",
                error_category="unknown_tool",
                error_code="unknown_tool",
                duration_ms=(time.monotonic() - started_at) * 1_000,
                result_count=0,
                effective_version=effective_version,
            )
            return create_mcp_error(msg_id, tool_error.code, tool_error.message)

        # Everything else is a model-visible tool failure: a successful JSON-RPC
        # result with isError and a stable error code the client can act on.
        error_code = stable_error_code(tool_error)
        if tool_error.analytics_rate_limited and "Retry" not in tool_error.message:
            tool_error = ToolExecutionError(
                f"{tool_error.message} Retry after the current rate-limit window.",
                code=tool_error.code,
                analytics_rate_limited=True,
            )
        _tool_call_analytics(
            auth_context,
            request,
            tool_name,
            outcome="error",
            authorization_outcome=authorization_outcome_for_code(
                tool_error.code, authorization_denied=tool_error.analytics_authorization_denied
            ),
            error_category=error_category_for_code(
                tool_error.code, authorization_denied=tool_error.analytics_authorization_denied
            ),
            error_code=error_code,
            duration_ms=(time.monotonic() - started_at) * 1_000,
            result_count=0,
            effective_version=effective_version,
        )
        return create_mcp_response(
            msg_id,
            _complete_result(_tool_error_payload(error_code, tool_error.message), effective_version),
        )

    _tool_call_analytics(
        auth_context,
        request,
        tool_name,
        outcome="success",
        authorization_outcome="allowed",
        error_category="none",
        error_code="none",
        duration_ms=(time.monotonic() - started_at) * 1_000,
        result_count=result_count_for_tool_result(tool_name, result or {}),
        effective_version=effective_version,
    )
    return create_mcp_response(msg_id, _complete_result(_tool_result_payload(result or {}), effective_version))


def _envelope_error(message: Dict[str, Any]) -> Optional[Tuple[int, str, Any]]:
    """Validate the JSON-RPC envelope of one message.

    Returns ``(code, message, response_id)`` for malformed requests or ``None``
    when the envelope is well-formed. Envelope failures answer ``-32600`` with
    a null id; a present ``params`` that is not an object answers ``-32602``
    bound to the request id.
    """
    if message.get("jsonrpc") != JSONRPC_VERSION:
        return -32600, "Invalid Request: jsonrpc must be '2.0'.", None
    method = message.get("method")
    if not isinstance(method, str) or not method:
        return -32600, "Invalid Request: method must be a non-empty string.", None
    msg_id = message.get("id")
    if msg_id is not None and (isinstance(msg_id, bool) or not isinstance(msg_id, (str, int))):
        return -32600, "Invalid Request: id must be a string or integer.", None
    if method.startswith("notifications/"):
        if "id" in message:
            return -32600, "Invalid Request: notifications must not carry a request id.", None
    elif msg_id is None:
        return -32600, "Invalid Request: request methods require an id.", None
    if "params" in message and not isinstance(message["params"], dict):
        return -32602, "Invalid params: params must be an object.", msg_id
    return None


def handle_mcp_message(
    auth_context: MCPAuthContext,
    message: Dict[str, Any],
    request: Optional[McpRequestContext] = None,
) -> Optional[Dict[str, Any]]:
    """Process one MCP JSON-RPC message and return its response, or None."""
    method = message.get("method")
    request = request or McpRequestContext(auth_context=auth_context)

    envelope_error = _envelope_error(message)
    if envelope_error is not None:
        code, text, response_id = envelope_error
        return create_mcp_error(response_id, code, text)

    if isinstance(method, str) and method.startswith("notifications/"):
        # Notifications never produce a response.
        return None

    msg_id = message.get("id")
    params: Dict[str, Any] = cast(Dict[str, Any], message.get("params") or {})

    try:
        effective_version = resolve_effective_version(message, request.header_version)
    except JsonRpcProtocolError as exc:
        return _protocol_error_response(msg_id, exc)

    # Mcp-* integrity headers, when sent, must describe this exact message.
    if request.mcp_method is not None and request.mcp_method != method:
        return create_mcp_error(
            msg_id,
            -32020,
            f"Mcp-Method header '{request.mcp_method}' does not match message method '{method}'.",
        )
    if request.mcp_name is not None:
        expected_name = params.get("name") if method == "tools/call" else None
        if expected_name != request.mcp_name:
            return create_mcp_error(
                msg_id,
                -32020,
                "Mcp-Name header does not match the tools/call params.name for this message.",
            )

    if method == "initialize":
        return create_mcp_response(
            msg_id,
            _complete_result(
                {
                    "protocolVersion": negotiate_protocol_version(params.get("protocolVersion")),
                    "capabilities": dict(MCP_CAPABILITIES),
                    "serverInfo": dict(SERVER_INFO),
                    "instructions": MCP_SERVER_INSTRUCTIONS,
                },
                effective_version,
            ),
        )

    if method == "tools/list":
        return create_mcp_response(
            msg_id,
            _complete_result(
                {
                    "tools": _tools_for_scopes(auth_context.scopes),
                    "ttlMs": TOOLS_LIST_TTL_MS,
                    "cacheScope": TOOLS_LIST_CACHE_SCOPE,
                },
                effective_version,
            ),
        )

    if method == "server/discover":
        # DiscoverResult extends CacheableResult: supportedVersions,
        # capabilities, optional instructions, plus the required ttlMs and
        # cacheScope pair (private — capabilities may vary by token scopes).
        return create_mcp_response(
            msg_id,
            _complete_result(
                {
                    "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
                    "capabilities": dict(MCP_CAPABILITIES),
                    "serverInfo": dict(SERVER_INFO),
                    "instructions": MCP_SERVER_INSTRUCTIONS,
                    "ttlMs": TOOLS_LIST_TTL_MS,
                    "cacheScope": TOOLS_LIST_CACHE_SCOPE,
                },
                effective_version,
            ),
        )

    if method == "tools/call":
        return _handle_tool_call(auth_context, request, msg_id, params, effective_version)

    if method == "ping":
        # ping was removed in the 2026 stateless revision.
        if effective_version == PROTOCOL_VERSION_2026:
            return create_mcp_error(msg_id, -32601, "Method not found: ping")
        return create_mcp_response(msg_id, {})

    # subscriptions/listen and other unimplemented methods stay method-not-found;
    # no subscription channel exists on this transport (GET also returns 405).
    return create_mcp_error(msg_id, -32601, f"Method not found: {method}")


def _charge_write_bucket(auth_context: MCPAuthContext, policy_name: str) -> None:
    if policy_name == "action_items:write":
        # REST action-item writes use with_rate_limit(get_uid_from_mcp_api_key):
        # charge the same per-UID bucket so hosted and REST share one counter.
        check_rate_limit_inline(auth_context.uid, policy_name)
    elif auth_context.memory_context is not None:
        # Memory writes use with_rate_limit_context on REST: charge the same
        # per-app/key bucket (OAuth grants carry grant_id/client_id through
        # memory_context, so per-grant identity is preserved).
        check_rate_limit_context(auth_context.memory_context, policy_name)
    else:
        check_rate_limit_inline(auth_context.uid, policy_name)


def _write_bucket_failure(exc: HTTPException) -> Tuple[str, str, str, str]:
    """Map a write-bucket limiter failure to (stable code, model-visible
    message, authorization_outcome, error_category).

    Only the 429 detail is forwarded — it is the limiter's own message. Other
    details can carry internal identifiers (limiter backend addresses, bucket
    keys), so model-visible text stays generic.
    """
    if exc.status_code == 429:
        return (
            "rate_limited",
            f"{exc.detail} Retry after the current rate-limit window.",
            "not_applicable",
            "validation",
        )
    if exc.status_code == 403:
        return (
            "authorization_denied",
            "This credential is not permitted to perform this write. Reconnect the account and retry.",
            "denied",
            "authorization_denied",
        )
    return (
        "unavailable",
        "Tool temporarily unavailable. Retry shortly.",
        "not_applicable",
        "internal",
    )


def _write_rate_policy(
    auth_context: MCPAuthContext, message: Dict[str, Any], request: McpRequestContext
) -> Optional[str]:
    """Return the write-bucket policy a tools/call would consume, or None.

    Quota is only burned for messages that would actually reach the handler:
    malformed envelopes, integrity-header mismatches, unresolvable versions,
    unknown tools, and scope failures all answer before execution.
    """
    if _envelope_error(message) is not None:
        return None
    if message.get("method") != "tools/call":
        return None
    if request.mcp_method is not None and request.mcp_method != message.get("method"):
        return None
    params = cast(Dict[str, Any], message.get("params") or {})
    if request.mcp_name is not None and params.get("name") != request.mcp_name:
        return None
    try:
        resolve_effective_version(message, request.header_version)
    except JsonRpcProtocolError:
        return None
    spec = spec_for_tool(params.get("name"))
    if spec is None or spec.rate_bucket is None:
        return None
    arguments = params.get("arguments")
    if arguments is not None and not isinstance(arguments, dict):
        # Dispatch answers invalid_arguments; this is not a dispatchable
        # write and must not consume write quota.
        return None
    # A scope failure never reaches the handler; let the -32003 path answer
    # without burning write quota.
    if spec.scope and spec.scope not in set(auth_context.scopes):
        return None
    return spec.rate_bucket


async def dispatch_message(
    auth_context: MCPAuthContext,
    message: Dict[str, Any],
    request: McpRequestContext,
) -> Optional[Dict[str, Any]]:
    """Dispatch one message: write-bucket charge on critical_executor, then the
    sync handler on db_executor."""
    policy = _write_rate_policy(auth_context, message, request)
    if policy is not None:
        try:
            await run_blocking(critical_executor, _charge_write_bucket, auth_context, policy)
        except HTTPException as exc:
            if message.get("id") is None:
                return None
            msg_id = message.get("id")
            try:
                effective_version = resolve_effective_version(message, request.header_version)
            except JsonRpcProtocolError:
                return await run_blocking(db_executor, handle_mcp_message, auth_context, message, request)
            code, detail, authorization_outcome, error_category = _write_bucket_failure(exc)
            _tool_call_analytics(
                auth_context,
                request,
                (message.get("params") or {}).get("name"),
                outcome="error",
                authorization_outcome=authorization_outcome,
                error_category=error_category,
                error_code=code,
                duration_ms=0,
                result_count=0,
                effective_version=effective_version,
            )
            return create_mcp_response(
                msg_id,
                _complete_result(_tool_error_payload(code, detail), effective_version),
            )
    return await run_blocking(db_executor, handle_mcp_message, auth_context, message, request)


def prepare_messages(
    body: Any,
    *,
    header_version: Optional[str],
    mcp_method: Optional[str],
    mcp_name: Optional[str],
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    """Validate the POST body shape and batch-era rules.

    Returns ``(messages, None)`` on success or ``(None, error_response)``; batch
    failures are single JSON-RPC errors with a null id, never HTTP 500s.
    """
    if isinstance(body, dict):
        return [body], None
    if not isinstance(body, list):
        return None, create_mcp_error(None, -32600, "Invalid Request: expected a JSON-RPC object.")
    if not body:
        return None, create_mcp_error(None, -32600, "Invalid Request: empty JSON-RPC batch.")
    if len(body) > MCP_MAX_BATCH_MESSAGES:
        return None, create_mcp_error(
            None, -32600, f"Invalid Request: batch exceeds {MCP_MAX_BATCH_MESSAGES} messages."
        )
    if any(not isinstance(message, dict) for message in body):
        return None, create_mcp_error(None, -32600, "Invalid Request: every batch element must be a JSON-RPC object.")

    declared = set()
    for message in body:
        version = declared_protocol_version(message)
        if version:
            declared.add(version)
        if message.get("method") == "initialize":
            params = message.get("params")
            requested = params.get("protocolVersion") if isinstance(params, dict) else None
            declared.add(negotiate_protocol_version(requested))
    if header_version:
        declared.add(header_version)
    if len(declared) > 1:
        return None, create_mcp_error(
            None,
            -32020,
            "Conflicting MCP protocol versions across the request header and batch messages.",
        )
    if declared:
        version = next(iter(declared))
        if not is_supported_version(version):
            return None, _protocol_error_response(None, unsupported_version_error(version))
        if not is_batch_era_version(version):
            return None, create_mcp_error(
                None,
                -32600,
                f"JSON-RPC batch requests are not supported for protocol version {version}.",
            )
    if mcp_method or mcp_name:
        return None, create_mcp_error(
            None,
            -32020,
            "Mcp-Method and Mcp-Name headers cannot annotate a JSON-RPC batch request.",
        )
    return body, None


def header_violation_error(
    body: Any,
    *,
    header_version: Optional[str],
    mcp_method: Optional[str],
    mcp_name: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Return a JSON-RPC error body when the request HEADERS are at fault.

    ``HeaderMismatchError`` (-32020) and ``UnsupportedProtocolVersionError``
    (-32022) caused by HTTP headers answer HTTP 400 per the 2026-07-28 schema.
    Body-level ``_meta`` version problems are NOT checked here — they stay
    per-message errors on a 200 response.
    """
    # ``initialize`` negotiates from ``params.protocolVersion``; a stale or
    # future MCP-Protocol-Version header on the handshake must not block it.
    if isinstance(body, dict) and body.get("method") == "initialize":
        header_version = None
    if header_version is not None and not is_supported_version(header_version):
        return _protocol_error_response(None, unsupported_version_error(header_version))
    if mcp_method or mcp_name:
        if isinstance(body, list):
            return create_mcp_error(
                None,
                -32020,
                "Mcp-Method and Mcp-Name headers cannot annotate a JSON-RPC batch request.",
            )
        if isinstance(body, dict):
            if mcp_method is not None and body.get("method") != mcp_method:
                return create_mcp_error(
                    body.get("id"),
                    -32020,
                    f"Mcp-Method header '{mcp_method}' does not match message method '{body.get('method')}'.",
                )
            if mcp_name is not None:
                raw_params = body.get("params")
                params: Dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
                expected_name = params.get("name") if body.get("method") == "tools/call" else None
                if expected_name != mcp_name:
                    return create_mcp_error(
                        body.get("id"),
                        -32020,
                        "Mcp-Name header does not match the tools/call params.name for this message.",
                    )
    if header_version:
        declared_versions = (
            {declared_protocol_version(message) for message in body if isinstance(message, dict)}
            if isinstance(body, list)
            else {declared_protocol_version(body)} if isinstance(body, dict) else set()
        )
        declared_versions.discard(None)
        if declared_versions and header_version not in declared_versions:
            return create_mcp_error(
                None,
                -32020,
                f"MCP-Protocol-Version header '{header_version}' does not match the declared "
                "protocol version in the request body.",
            )
    return None


def _client_capabilities_error(message: Dict[str, Any], header_version: Optional[str]) -> Optional[Dict[str, Any]]:
    """2026-07-28 requires every request to carry ``clientCapabilities`` ``_meta``.

    Both official SDKs (``mcp`` Python 2.0.0, ``@modelcontextprotocol/client``
    2.0.0) stamp it on every modern call, so a 2026-declared message without a
    capabilities OBJECT is a malformed request: ``-32602`` on HTTP 400.
    Older revisions and undeclared messages are untouched.
    """
    if message.get("method") == "initialize":
        return None
    declared = declared_protocol_version(message) or header_version
    if declared != PROTOCOL_VERSION_2026:
        return None
    if isinstance(declared_client_capabilities(message), dict):
        return None
    return create_mcp_error(
        message.get("id"),
        -32602,
        f"Invalid params: _meta['{META_CLIENT_CAPABILITIES}'] must be an object "
        f"for protocol version {PROTOCOL_VERSION_2026}.",
    )


def _request_client_name(messages: List[Any], user_agent: Optional[str]) -> str:
    for message in messages:
        if isinstance(message, dict):
            name = client_info_name(message)
            if name:
                return normalize_client_name(name, user_agent)
    return normalize_client_name(None, user_agent)


def _request_protocol_version(messages: List[Any], header_version: Optional[str]) -> str:
    """Analytics-facing version for the whole POST.

    An explicit ``_meta`` declaration wins. When no message declares one but
    the POST carries an ``initialize``, the version the server actually
    negotiated for it — not a disagreeing header — is what the client observes.
    """
    for message in messages:
        if isinstance(message, dict):
            version = declared_protocol_version(message)
            if version:
                return version
    for message in messages:
        if isinstance(message, dict) and message.get("method") == "initialize":
            params = message.get("params")
            requested = params.get("protocolVersion") if isinstance(params, dict) else None
            return negotiate_protocol_version(requested)
    return header_version or DEFAULT_PROTOCOL_VERSION


def _emit_request_observability(
    *,
    uid: str,
    auth_type: str,
    path_kind: str,
    http_status: int,
    method_enums: List[str],
    message_count: int,
    is_handshake: bool,
    protocol_version: str,
    client_name: str,
    tool_name: Optional[str],
    duration_ms: float,
) -> None:
    """The 100% ``mcp_request`` structured log plus the daily ``MCP Active`` marker."""
    log_mcp_request(
        jsonrpc_methods=method_enums,
        message_count=message_count,
        is_handshake=is_handshake,
        protocol_version=protocol_version,
        client_name=client_name,
        auth_type=auth_type,
        http_status=http_status,
        path=path_kind,
        duration_ms=duration_ms,
        tool_name=tool_name,
    )
    schedule_mcp_active(
        uid=uid,
        client_name=client_name,
        transport=auth_type,
        protocol_version=protocol_version,
        first_tool=tool_name,
    )


async def handle_post_request(
    request: Request,
    authorization: Optional[str],
    *,
    path_kind: str,
) -> Response:
    """Serve one Streamable HTTP POST on either the canonical or legacy path."""
    started_at = time.monotonic()
    http_status = 500
    uid = "mcp-anonymous"
    auth_type = "unknown"
    client_name = "unknown"
    protocol_version = DEFAULT_PROTOCOL_VERSION
    method_enums: List[str] = []
    message_count = 0
    tool_name: Optional[str] = None
    try:
        auth_context = await run_blocking(db_executor, authenticate_mcp_request, authorization, request)
        if not auth_context:
            raise invalid_mcp_auth_exception(path_kind=path_kind)
        uid = auth_context.uid
        auth_type = auth_context.auth_type

        header_version = request.headers.get(MCP_PROTOCOL_VERSION_HEADER)
        try:
            body: object = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        is_batch = isinstance(body, list)
        raw_messages = cast(List[Any], body) if is_batch else [body]
        method_enums = [mcp_method_enum(message.get("method")) for message in raw_messages if isinstance(message, dict)]
        message_count = len(raw_messages)
        protocol_version = _request_protocol_version(raw_messages, header_version)
        client_name = _request_client_name(raw_messages, request.headers.get("user-agent"))

        request_context = McpRequestContext(
            auth_context=auth_context,
            header_version=header_version,
            mcp_method=request.headers.get(MCP_METHOD_HEADER),
            mcp_name=request.headers.get(MCP_NAME_HEADER),
            in_batch=is_batch,
            client_name=client_name,
            user_agent=request.headers.get("user-agent"),
            path_kind=path_kind,
        )

        # Header-level protocol failures (-32020/-32022) answer HTTP 400 per
        # the 2026-07-28 schema; body-level version problems stay on a 200.
        header_error = header_violation_error(
            body,
            header_version=header_version,
            mcp_method=request_context.mcp_method,
            mcp_name=request_context.mcp_name,
        )
        if header_error is not None:
            http_status = 400
            return JSONResponse(status_code=400, content=header_error)

        messages, error_response = prepare_messages(
            body,
            header_version=header_version,
            mcp_method=request_context.mcp_method,
            mcp_name=request_context.mcp_name,
        )
        if error_response is not None:
            http_status = 200
            accept = request.headers.get("accept") or ""
            if "text/event-stream" in accept:
                return _sse_response([error_response])
            return JSONResponse(content=error_response)
        messages = cast(List[Dict[str, Any]], messages)

        for message in messages:
            capabilities_error = _client_capabilities_error(message, header_version)
            if capabilities_error is not None:
                http_status = 400
                return JSONResponse(status_code=400, content=capabilities_error)

        all_notifications = all(message.get("id") is None for message in messages)

        # Admission-level rate limiting: one mcp:sse charge per JSON-RPC message,
        # including notifications, before any message executes.
        for _ in messages:
            await run_blocking(critical_executor, check_rate_limit_inline, uid, "mcp:sse")

        tool_calls = [message for message in messages if message.get("method") == "tools/call"]
        tool_name = None
        if len(tool_calls) == 1:
            params = tool_calls[0].get("params")
            name = params.get("name") if isinstance(params, dict) else None
            tool_name = name if isinstance(name, str) and name else None

        responses: List[Dict[str, Any]] = []
        for message in messages:
            response = await dispatch_message(auth_context, message, request_context)
            if response:
                responses.append(response)

        if all_notifications:
            http_status = 202
            return Response(status_code=202)

        http_status = 200
        accept = request.headers.get("accept") or ""
        if "text/event-stream" in accept:
            return _sse_response(responses)
        return JSONResponse(content=responses if is_batch else responses[0])
    except HTTPException as exc:
        http_status = exc.status_code
        raise
    finally:
        _emit_request_observability(
            uid=uid,
            auth_type=auth_type,
            path_kind=path_kind,
            http_status=http_status,
            method_enums=method_enums,
            message_count=message_count,
            is_handshake=any(method in {"initialize", "notifications/initialized"} for method in method_enums),
            protocol_version=protocol_version,
            client_name=client_name,
            tool_name=tool_name,
            duration_ms=(time.monotonic() - started_at) * 1_000,
        )


def _sse_response(responses: List[Dict[str, Any]]) -> StreamingResponse:
    """Wrap JSON-RPC payloads as ``event: message`` SSE frames."""

    async def event_generator():
        for resp in responses:
            yield f"event: message\ndata: {json.dumps(resp, default=str)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def no_stream_get_response() -> Response:
    """GET: this server offers no server-initiated stream, so 405 per spec."""
    return Response(status_code=405, headers={"Allow": "POST, HEAD, DELETE"})


def handle_head(
    authorization: Optional[str], path_kind: str = "canonical", request: Optional[Request] = None
) -> Response:
    if not authenticate_mcp_request(authorization, request):
        raise invalid_mcp_auth_exception(path_kind=path_kind)
    return Response(status_code=200)


def handle_delete(
    authorization: Optional[str], path_kind: str = "canonical", request: Optional[Request] = None
) -> Response:
    auth_context = authenticate_mcp_request(authorization, request)
    if not auth_context:
        raise invalid_mcp_auth_exception("Invalid or missing API key", path_kind=path_kind)

    # Hosted MCP is stateless; terminate requests are best-effort so stale
    # or load-balanced session ids do not create client-visible errors.
    return Response(status_code=204)

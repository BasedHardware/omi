"""Authentication for the hosted MCP transport (OAuth bearer + legacy MCP keys)."""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request
from google.api_core import exceptions as google_api_exceptions

import database.mcp_api_key as mcp_api_key_db
import database.mcp_oauth as mcp_oauth_db
import database.mcp_token_cache as mcp_token_cache_db
from utils.mcp_memories import McpVerifiedAuth, build_mcp_default_memory_read_context
from utils.mcp_scopes import MCP_FULL_ACCESS_SCOPES
from utils.mcp_server.metadata import protected_resource_metadata_url
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.observability.api_keys import record_api_key_repairs
from utils.other.endpoints import (
    cutover_enforcement_enabled,
    enforce_account_cutover_http_access,
    enforce_account_deletion_http_access,
)

logger = logging.getLogger(__name__)

MCP_RESOURCE_URL = mcp_oauth_db.MCP_RESOURCE_URL
# How long a client should wait before retrying once the token store is down.
# Kept short: the outages this covers (quota, transient Firestore unavailability)
# clear on their own, and MCP clients hold no session state to rebuild.
MCP_AUTH_UNAVAILABLE_RETRY_AFTER_SECONDS = int(os.getenv("MCP_AUTH_UNAVAILABLE_RETRY_AFTER_SECONDS", "30"))
MCP_LEGACY_API_KEY_SCOPES = list(MCP_FULL_ACCESS_SCOPES)
# The 401 challenge advertises every read scope so a client told
# ``invalid_token`` knows which read-only grant to re-request.
READ_SCOPE_HINT = " ".join(sorted(scope for scope in MCP_FULL_ACCESS_SCOPES if scope.endswith(".read")))


@dataclass
class MCPAuthContext:
    uid: str
    auth_type: str
    scopes: List[str]
    app_id: Optional[str] = None
    key_id: Optional[str] = None
    client_id: Optional[str] = None
    resource: Optional[str] = None
    grant_id: Optional[str] = None
    memory_context: Optional[ProductAuthorizationContext] = None


def _enforce_mcp_cutover_access(uid: str, request: Optional[Request] = None) -> None:
    """Fence MCP product principals when cutover enforcement is enabled.

    HTTP callers pass the live Request so generation rules see the real
    method/path/headers; Request-free callers evaluate as a mutating product
    path so positive-generation and migrating/new rules apply fail-closed.
    """
    if not cutover_enforcement_enabled():
        return
    if request is not None:
        enforce_account_cutover_http_access(
            uid,
            method=request.method,
            path=request.url.path,
            headers=request.headers,
        )
        return
    enforce_account_cutover_http_access(
        uid,
        method='POST',
        path='/v1/mcp/sse',
        headers={},
    )


def _mcp_memory_context_from_auth_data(user_data: Dict[str, Any]) -> ProductAuthorizationContext:
    verified_auth = McpVerifiedAuth(
        uid=user_data.get("user_id") or user_data["uid"],
        app_id=user_data.get("app_id") or user_data.get("client_id"),
        key_id=user_data.get("key_id") or user_data.get("grant_id"),
        scopes=tuple(user_data.get("scopes") or ()),
    )
    return build_mcp_default_memory_read_context(verified_auth)


def authenticate_api_key_auth_context(authorization: Optional[str]) -> Optional[ProductAuthorizationContext]:
    if not authorization:
        return None

    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    if not token.startswith("omi_mcp_"):
        return None

    auth_result = mcp_api_key_db.get_api_key_auth_result(token)
    record_api_key_repairs(key_kind="mcp", operation="auth", repairs=auth_result.repairs, log=logger)
    user_data = auth_result.context
    if not user_data or not user_data.get("user_id"):
        return None
    enforce_account_deletion_http_access(user_data["user_id"])
    _enforce_mcp_cutover_access(user_data["user_id"])
    return _mcp_memory_context_from_auth_data(user_data)


def authenticate_mcp_request(
    authorization: Optional[str], request: Optional[Request] = None
) -> Optional[MCPAuthContext]:
    """Validate Authorization and return an MCP auth context.

    Raises 503 (never 401) when the token store itself is unreachable: a client
    told "unauthorized" discards its token and restarts the whole OAuth dance,
    which is the wrong answer to a transient backend outage.
    """
    if not authorization:
        return None

    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    try:
        return _authenticate_mcp_token(token, request)
    except google_api_exceptions.GoogleAPIError as exc:
        logger.warning("MCP auth lookup failed against the token store: %s", exc)
        raise mcp_auth_store_unavailable_exception() from exc
    except mcp_token_cache_db.McpTokenStoreUnavailable as exc:
        logger.warning("MCP auth token cache is unavailable: %s", type(exc).__name__)
        raise mcp_auth_store_unavailable_exception() from exc


def mcp_auth_store_unavailable_exception() -> HTTPException:
    """Return a retryable failure for an unreachable MCP token store."""
    return HTTPException(
        status_code=503,
        detail="MCP authentication is temporarily unavailable. Please retry shortly.",
        headers={"Retry-After": str(MCP_AUTH_UNAVAILABLE_RETRY_AFTER_SECONDS)},
    )


def _authenticate_mcp_token(token: str, request: Optional[Request] = None) -> Optional[MCPAuthContext]:
    if token.startswith("omi_mcp_"):
        auth_result = mcp_api_key_db.get_api_key_auth_result(token)
        record_api_key_repairs(key_kind="mcp", operation="auth", repairs=auth_result.repairs, log=logger)
        user_data = auth_result.context
        if not user_data or not user_data.get("user_id"):
            return None
        enforce_account_deletion_http_access(user_data["user_id"])
        _enforce_mcp_cutover_access(user_data["user_id"], request)
        return MCPAuthContext(
            uid=user_data["user_id"],
            auth_type="legacy_mcp_key",
            scopes=list(user_data.get("scopes") or MCP_LEGACY_API_KEY_SCOPES),
            app_id=user_data.get("app_id"),
            key_id=user_data.get("key_id"),
            memory_context=_mcp_memory_context_from_auth_data(user_data),
        )

    oauth_context = mcp_oauth_db.validate_access_token(token, MCP_RESOURCE_URL)
    if not oauth_context:
        return None
    enforce_account_deletion_http_access(oauth_context["uid"])
    _enforce_mcp_cutover_access(oauth_context["uid"], request)
    return MCPAuthContext(
        uid=oauth_context["uid"],
        auth_type="oauth",
        scopes=oauth_context.get("scopes") or [],
        client_id=oauth_context.get("client_id"),
        resource=oauth_context.get("resource"),
        grant_id=oauth_context.get("grant_id"),
        memory_context=_mcp_memory_context_from_auth_data(oauth_context),
    )


def authenticate_api_key(authorization: Optional[str]) -> Optional[str]:
    """Validate API key from Authorization header and return user_id if valid."""
    auth_context = authenticate_mcp_request(authorization)
    if not auth_context or auth_context.auth_type != "legacy_mcp_key":
        return None
    return auth_context.uid


def invalid_mcp_auth_exception(
    detail: str = "Invalid or missing API key. Provide via Authorization header.",
    path_kind: str = "canonical",
) -> HTTPException:
    """Return an MCP OAuth discovery hint for clients that need authorization.

    The challenge advertises the protected-resource document for the path that
    was actually requested, so a legacy-path client discovers the legacy
    ``/v1/mcp/sse`` audience rather than the canonical one.
    """
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={
            "WWW-Authenticate": (
                f'Bearer resource_metadata="{protected_resource_metadata_url(path_kind)}", '
                'error="invalid_token", '
                'error_description="Valid Omi MCP OAuth bearer token required", '
                f'scope="{READ_SCOPE_HINT}"'
            )
        },
    )

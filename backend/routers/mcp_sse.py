"""
Hosted MCP Server via Streamable HTTP Transport

Thin FastAPI surface for the hosted MCP server. The canonical endpoint is
``/v1/mcp``; ``/v1/mcp/sse`` remains a permanent alias for released clients.
Protocol dispatch, tools, auth, OAuth, and discovery documents live under
``utils/mcp_server/`` — this module only binds routes and re-exports the
public seams existing tests and integrations rely on.
"""

import logging
from typing import Optional

import firebase_admin.auth
from fastapi import APIRouter, Form, Header, Request, Response
from fastapi.responses import HTMLResponse

import database.action_items as action_items_db
import database.chat as chat_db
import database.conversations as conversations_db
import database.daily_summaries as daily_summaries_db
import database.goals as goals_db
import database.mcp_api_key as mcp_api_key_db
import database.mcp_oauth as mcp_oauth_db
import database.screen_activity as screen_activity_db
import database.users as users_db
import database.vector_db as vector_db
import database.x_posts as x_posts_db
from database._client import db
from utils.mcp_analytics import schedule_mcp_tool_call  # noqa: F401 — compat re-export
from utils.mcp_server import metadata as _metadata
from utils.mcp_server import oauth as _oauth
from utils.mcp_server import transport as _transport
from utils.mcp_server.versions import PROTOCOL_VERSION_2026
from utils.mcp_server.auth import (  # noqa: F401 — compat re-exports
    MCP_AUTH_UNAVAILABLE_RETRY_AFTER_SECONDS,
    MCP_LEGACY_API_KEY_SCOPES,
    MCP_RESOURCE_URL,
    MCPAuthContext,
    authenticate_api_key,
    authenticate_api_key_auth_context,
    authenticate_mcp_request,
    invalid_mcp_auth_exception,
    mcp_auth_store_unavailable_exception,
)
from utils.mcp_server.errors import (  # noqa: F401 — compat re-exports
    ToolExecutionError,
    authorization_denied_error,
)
from utils.mcp_server.errors import _authorization_denied_error  # noqa: F401
from utils.mcp_server.metadata import (  # noqa: F401 — compat re-exports
    MCP_AUTHORIZATION_ENDPOINT,
    MCP_AUTHORIZATION_SERVER_URL,
    MCP_PROTECTED_RESOURCE_METADATA_URL,
    MCP_SCOPES_SUPPORTED,
    MCP_TOKEN_ENDPOINT,
    OPENAI_APPS_CHALLENGE_TOKEN,
    SCOPE_PERMISSION_TEXT,
)
from utils.mcp_server.oauth import (
    McpAuthorizeConsentResponse,
    McpSseInfoResponse,
    McpTokenResponse,
)
from utils.mcp_server.oauth import (  # noqa: F401 — compat re-exports
    _effective_resource,
    _get_token_request_data,
    _oauth_error,
    _redirect_with_code,
    _validate_authorize_request,
    templates,
)
from utils.mcp_server.auth import _enforce_mcp_cutover_access  # noqa: F401
from utils.mcp_server.auth import _mcp_memory_context_from_auth_data  # noqa: F401
from utils.mcp_server.registry import (  # noqa: F401 — compat re-exports
    ACTION_ITEMS_READ_SECURITY,
    ACTION_ITEMS_WRITE_SECURITY,
    CHAT_READ_SECURITY,
    CONVERSATIONS_READ_SECURITY,
    GOALS_READ_SECURITY,
    MCP_TOOLS,
    MEMORIES_READ_SECURITY,
    MEMORIES_WRITE_SECURITY,
    PEOPLE_READ_SECURITY,
    SCREEN_ACTIVITY_READ_SECURITY,
    TOOL_REQUIRED_SCOPE,
    execute_tool,
)
from utils.mcp_server.transport import (  # noqa: F401 — compat re-exports
    create_mcp_error,
    create_mcp_response,
    handle_mcp_message,
)
from utils.mcp_server.versions import SUPPORTED_PROTOCOL_VERSIONS  # noqa: F401
from utils.jit_qa_admission import JITQAAdmissionError, enforce_jit_qa_uid  # noqa: F401

router = APIRouter()
logger = logging.getLogger(__name__)


def _path_kind(request: Request) -> str:
    return "canonical" if request.url.path.rstrip("/") == "/v1/mcp" else "legacy_sse"


@router.post("/v1/mcp", tags=["mcp"], response_class=Response)
@router.post("/v1/mcp/sse", tags=["mcp"], response_class=Response)
async def mcp_streamable_http(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
    accept: Optional[str] = Header(None, alias="Accept"),
):
    """
    Streamable HTTP Transport endpoint for MCP clients.

    Canonical path ``/v1/mcp`` and permanent alias ``/v1/mcp/sse`` share one
    stateless implementation in ``utils.mcp_server.transport``.
    """
    return await _transport.handle_post_request(request, authorization, path_kind=_path_kind(request))


@router.get("/v1/mcp", tags=["mcp"], response_class=Response)
@router.get("/v1/mcp/sse", tags=["mcp"], response_class=Response)
def mcp_sse_get(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
):
    """
    GET on the Streamable HTTP endpoint: this server offers no server-initiated
    stream, so it answers 405 (``Allow: POST, HEAD, DELETE``) on both paths.
    """
    return _transport.no_stream_get_response()


@router.head("/v1/mcp", tags=["mcp"], response_class=Response)
@router.head("/v1/mcp/sse", tags=["mcp"], response_class=Response)
def mcp_sse_head(request: Request, authorization: Optional[str] = Header(None, alias="Authorization")):
    return _transport.handle_head(authorization, path_kind=_path_kind(request), request=request)


@router.delete("/v1/mcp", tags=["mcp"], response_class=Response)
@router.delete("/v1/mcp/sse", tags=["mcp"], response_class=Response)
def mcp_delete_session(
    request: Request,
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Delete/terminate an MCP session (stateless: always 204 when authed)."""
    return _transport.handle_delete(authorization, path_kind=_path_kind(request), request=request)


@router.get("/.well-known/oauth-protected-resource", tags=["mcp"])
@router.get("/.well-known/oauth-protected-resource/v1/mcp", tags=["mcp"])
@router.get("/.well-known/oauth-protected-resource/v1/mcp/sse", tags=["mcp"])
def oauth_protected_resource_metadata(request: Request):
    """Per-path RFC 9728 document: the unqualified root keeps describing the
    legacy ``/v1/mcp/sse`` resource until canonical OAuth clients roll out."""
    if request.url.path.rstrip("/").endswith("/v1/mcp"):
        resource = mcp_oauth_db.MCP_RESOURCE_URL
    else:
        resource = mcp_oauth_db.MCP_LEGACY_RESOURCE_URL
    return _metadata.protected_resource_document(resource)


@router.head("/.well-known/oauth-protected-resource", tags=["mcp"])
@router.head("/.well-known/oauth-protected-resource/v1/mcp", tags=["mcp"])
@router.head("/.well-known/oauth-protected-resource/v1/mcp/sse", tags=["mcp"])
def oauth_protected_resource_metadata_head():
    return Response(status_code=200)


@router.get("/.well-known/oauth-authorization-server", tags=["mcp"])
def oauth_authorization_server_metadata():
    return _metadata.authorization_server_document()


@router.head("/.well-known/oauth-authorization-server", tags=["mcp"])
def oauth_authorization_server_metadata_head():
    return Response(status_code=200)


@router.get("/.well-known/openai-apps-challenge", tags=["mcp"])
def openai_apps_challenge():
    return Response(content=OPENAI_APPS_CHALLENGE_TOKEN, media_type="text/plain")


@router.get("/authorize", response_class=HTMLResponse, tags=["mcp"])
async def mcp_authorize(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    resource: Optional[str] = None,
    state: Optional[str] = None,
    scope: Optional[str] = None,
    code_challenge: Optional[str] = None,
    code_challenge_method: Optional[str] = None,
):
    """OAuth authorize endpoint."""
    return await _oauth.mcp_authorize(
        request,
        response_type,
        client_id,
        redirect_uri,
        resource=resource,
        state=state,
        scope=scope,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )


@router.post("/authorize", tags=["mcp"], response_model=McpAuthorizeConsentResponse)
async def mcp_authorize_consent(
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    resource: Optional[str] = Form(None),
    firebase_id_token: str = Form(...),
    state: Optional[str] = Form(None),
    scope: Optional[str] = Form(None),
    code_challenge: Optional[str] = Form(None),
    code_challenge_method: Optional[str] = Form(None),
):
    return await _oauth.mcp_authorize_consent(
        response_type,
        client_id,
        redirect_uri,
        resource,
        firebase_id_token,
        state,
        scope,
        code_challenge,
        code_challenge_method,
    )


@router.post("/token", tags=["mcp"], response_model=McpTokenResponse)
async def mcp_token(request: Request):
    """OAuth token endpoint."""
    return await _oauth.mcp_token(request)


@router.get("/v1/mcp/sse/info", tags=["mcp"], response_model=McpSseInfoResponse)
def mcp_sse_info(request: Request):
    """
    Get information about the hosted MCP server.
    """
    base_url = str(request.base_url).rstrip("/")
    return {
        # Instructional payload advertises the canonical endpoint; the /sse
        # path hosting this route stays a permanent alias for released clients.
        "endpoint": "/v1/mcp",
        "transport": "streamable-http",
        "protocol_version": PROTOCOL_VERSION_2026,
        "authentication": {
            "methods": ["oauth2", "api_key"],
            "api_key": {"header": "Authorization", "format": "Bearer <api_key>"},
            "oauth2": {
                "authorization_endpoint": MCP_AUTHORIZATION_ENDPOINT,
                "token_endpoint": MCP_TOKEN_ENDPOINT,
                "resource": MCP_RESOURCE_URL,
                "scopes": MCP_SCOPES_SUPPORTED,
            },
        },
        "instructions": {
            "step1": "Create an MCP API key in the Omi app (Settings > Developer > MCP)",
            "step2": f"Set Server URL to: {base_url}/v1/mcp",
            "step3": "Set Authorization header to your key",
        },
    }

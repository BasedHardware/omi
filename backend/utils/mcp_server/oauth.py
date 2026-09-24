"""OAuth authorize/token endpoint logic for the hosted MCP server.

Route functions in ``routers/mcp_sse.py`` delegate here so the OAuth surface
stays identical on the canonical and legacy endpoints.
"""

import os
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import firebase_admin.auth
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import database.mcp_oauth as mcp_oauth_db
from utils.executors import critical_executor, db_executor, run_blocking
from utils.jit_qa_admission import JITQAAdmissionError, enforce_jit_qa_uid
from utils.mcp_server.metadata import SCOPE_PERMISSION_TEXT

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


class McpSseAuthMethodResponse(BaseModel):
    header: Optional[str] = None
    format: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    resource: Optional[str] = None
    scopes: List[str] = []


class McpSseAuthenticationResponse(BaseModel):
    methods: List[str]
    api_key: McpSseAuthMethodResponse
    oauth2: McpSseAuthMethodResponse


class McpSseInstructionsResponse(BaseModel):
    step1: str
    step2: str
    step3: str


class McpSseInfoResponse(BaseModel):
    endpoint: str
    transport: str
    protocol_version: str
    authentication: McpSseAuthenticationResponse
    instructions: McpSseInstructionsResponse


class McpAuthorizeConsentResponse(BaseModel):
    redirect_uri: str


class McpTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    scope: str


def _oauth_error(error: str, description: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error, "error_description": description})


def _effective_resource(resource: Optional[str]) -> str:
    # RFC 8707 resource indicators are optional; connector clients such as claude.ai
    # omit the parameter entirely. An omitted indicator at the authorization step binds
    # the grant to this deployment's canonical resource — the audience advertised in
    # the protected-resource metadata. Cross-plane clients with a second allowed
    # resource must keep sending it explicitly, and a present-but-invalid value
    # (an empty string included) still fails validate_resource exactly as before.
    return mcp_oauth_db.MCP_RESOURCE_URL if resource is None else resource


def _validate_authorize_request(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    resource: str,
    scope: Optional[str],
    code_challenge: Optional[str],
    code_challenge_method: Optional[str],
) -> Tuple[Dict[str, Any], List[str]]:
    client = mcp_oauth_db.get_client(client_id)
    if response_type != "code":
        raise ValueError("response_type must be code")
    if not client or client.get("disabled_at"):
        raise ValueError("Unknown OAuth client")
    if not mcp_oauth_db.validate_redirect_uri(client, redirect_uri):
        raise ValueError("redirect_uri is not registered for this client")
    if not mcp_oauth_db.validate_resource(client, resource):
        raise ValueError("Invalid resource")
    if not mcp_oauth_db.validate_pkce_challenge(code_challenge, code_challenge_method):
        raise ValueError("PKCE S256 is required")
    scopes = mcp_oauth_db.normalize_scopes(scope, client)
    return client, scopes


def _redirect_with_code(redirect_uri: str, code: str, state: Optional[str]) -> str:
    parts = urlsplit(redirect_uri)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["code"] = code
    if state:
        params["state"] = state
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))


async def get_token_request_data(request: Request) -> Dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if content_type == "application/json":
        body: object = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Invalid request body")
        return cast(Dict[str, Any], body)

    form_data = await request.form()
    return dict(form_data)


_get_token_request_data = get_token_request_data


def mcp_authorize(
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
    """OAuth authorize endpoint: render the consent page after request validation."""
    resource = _effective_resource(resource)
    try:
        client, scopes = _validate_authorize_request(
            response_type, client_id, redirect_uri, resource, scope, code_challenge, code_challenge_method
        )
    except ValueError as e:
        return _oauth_error("invalid_request", str(e))

    client_name = str(client.get("name") or client_id)
    permissions = [SCOPE_PERMISSION_TEXT[item] for item in scopes]
    return templates.TemplateResponse(
        request,
        "mcp_oauth_authorize.html",
        {
            "client_name": client_name,
            "oauth_params": {
                "response_type": response_type,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "resource": resource,
                "scope": " ".join(scopes),
                "state": state or "",
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
            },
            "permissions": permissions,
            "firebase_config": {
                "apiKey": os.getenv("FIREBASE_API_KEY"),
                "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
                "projectId": os.getenv("FIREBASE_PROJECT_ID"),
            },
        },
    )


async def mcp_authorize_consent(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    resource: Optional[str],
    firebase_id_token: str,
    state: Optional[str],
    scope: Optional[str],
    code_challenge: Optional[str],
    code_challenge_method: Optional[str],
):
    resource = _effective_resource(resource)
    try:
        _, scopes = await run_blocking(
            db_executor,
            _validate_authorize_request,
            response_type,
            client_id,
            redirect_uri,
            resource,
            scope,
            code_challenge,
            code_challenge_method,
        )
        decoded_token: Dict[str, Any] = await run_blocking(
            critical_executor, firebase_admin.auth.verify_id_token, firebase_id_token
        )  # type: ignore[reportUnknownMemberType]  # firebase_admin auth untyped
        uid = cast(str, decoded_token["uid"])
    except firebase_admin.auth.InvalidIdTokenError:
        return _oauth_error("access_denied", "Invalid Omi sign-in token", status_code=401)
    except Exception as e:
        if isinstance(e, ValueError):
            return _oauth_error("invalid_request", str(e))
        return _oauth_error("access_denied", "Could not verify Omi sign-in token", status_code=401)

    try:
        enforce_jit_qa_uid(uid)
    except JITQAAdmissionError as error:
        raise HTTPException(status_code=403, detail="account is not admitted to the isolated JIT QA plane") from error

    try:
        _, code = await run_blocking(
            db_executor,
            mcp_oauth_db.create_grant_and_authorization_code_if_allowed,
            uid,
            client_id,
            redirect_uri,
            resource,
            scopes,
            cast(str, code_challenge),
        )
    except mcp_oauth_db.AccountDeletionAccessBlocked as exc:
        detail = {"code": "account_deletion_in_progress", "status": str(exc), "retryable": False}
        raise HTTPException(status_code=403, detail=detail) from exc
    return {"redirect_uri": _redirect_with_code(redirect_uri, code, state)}


async def mcp_token(request: Request):
    """OAuth token endpoint."""
    try:
        request_data = await get_token_request_data(request)
    except Exception:
        return _oauth_error("invalid_request", "Invalid request body")

    client_secret = request_data.get("client_secret")
    client_id = request_data.get("client_id")
    grant_type = request_data.get("grant_type")
    code = request_data.get("code")
    redirect_uri = request_data.get("redirect_uri")
    # RFC 8707: at the token endpoint an omitted resource indicator keeps the audience
    # stored on the code / refresh-token document, so no server-side default here —
    # None flows through and only an explicit value is validated and matched.
    resource = request_data.get("resource")
    code_verifier = request_data.get("code_verifier")
    refresh_token = request_data.get("refresh_token")
    scope = request_data.get("scope")

    client = await run_blocking(db_executor, mcp_oauth_db.get_client, client_id or "")
    if (
        not client
        or client.get("disabled_at")
        or not await run_blocking(db_executor, mcp_oauth_db.verify_client_auth, client, client_secret)
    ):
        return _oauth_error("invalid_client", "Invalid client", status_code=401)

    if grant_type == "authorization_code":
        if not code or not redirect_uri or not code_verifier:
            return _oauth_error("invalid_request", "code, redirect_uri, and code_verifier are required")
        if resource is not None and not await run_blocking(
            db_executor, mcp_oauth_db.validate_resource, client, resource
        ):
            return _oauth_error("invalid_target", "Invalid resource")
        token_pair = await run_blocking(
            db_executor,
            mcp_oauth_db.exchange_authorization_code_for_tokens,
            code,
            cast(str, client_id),
            redirect_uri,
            resource,
            code_verifier,
        )
        if not token_pair:
            return _oauth_error("invalid_grant", "Invalid authorization code")
        return token_pair

    if grant_type == "refresh_token":
        if not refresh_token:
            return _oauth_error("invalid_request", "refresh_token is required")
        if resource is not None and not await run_blocking(
            db_executor, mcp_oauth_db.validate_resource, client, resource
        ):
            return _oauth_error("invalid_target", "Invalid resource")
        token_pair = await run_blocking(
            db_executor, mcp_oauth_db.rotate_refresh_token, refresh_token, cast(str, client_id), resource, scope
        )
        if not token_pair:
            return _oauth_error("invalid_grant", "Invalid refresh token")
        return token_pair

    return _oauth_error("unsupported_grant_type", "grant_type must be authorization_code or refresh_token")

"""OAuth authorize/token endpoint logic for the hosted MCP server.

Route functions in ``routers/mcp_sse.py`` delegate here so the OAuth surface
stays identical on the canonical and legacy endpoints.
"""

import os
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import firebase_admin.auth
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config.mcp_client_ids import is_url_form_client_id
import database.mcp_client_metadata as mcp_client_metadata
import database.mcp_oauth as mcp_oauth_db
import database.mcp_token_cache as mcp_token_cache_db
from utils.executors import ExecutorSaturatedError, cimd_executor, critical_executor, db_executor, run_blocking
from utils.jit_qa_admission import JITQAAdmissionError, enforce_jit_qa_uid
from utils.mcp_server.metadata import MCP_AUTHORIZATION_SERVER_URL, SCOPE_PERMISSION_TEXT
from utils.other.endpoints import check_rate_limit_inline

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


def _oauth_temporarily_unavailable() -> JSONResponse:
    # RFC 6749 §5.2 temporarily_unavailable: the Redis revocation store is
    # fail-closed, so a refresh whose replay-revoke cannot be written is a
    # retryable 503 — never a silent skip and never a 401.
    return JSONResponse(
        status_code=503,
        content={"error": "temporarily_unavailable", "error_description": "Token store is unavailable"},
        headers={"Retry-After": "30"},
    )


def _oauth_cimd_saturated() -> JSONResponse:
    # The bounded CIMD pool is full: fail fast so unauthenticated URL-form
    # client_id floods can never park shared workers on outbound fetches.
    return JSONResponse(
        status_code=503,
        content={"error": "temporarily_unavailable", "error_description": "Client metadata lookups are busy"},
        headers={"Retry-After": "30"},
    )


def _client_lookup_executor(client_id: Any):
    """URL-form (CIMD) client ids fetch remote metadata: their lookups run on
    the dedicated bounded ``cimd_executor`` — never the db or anyio pools."""
    return cimd_executor if is_url_form_client_id(client_id) else db_executor


def _url_form_rate_limit_key(client_id: Any) -> str:
    """Bucket URL-form client_ids by the normalized CIMD host the metadata
    document would be fetched from: ``parse_metadata_url`` lowercases and
    IDNA-encodes it, so one host shares a bucket across paths and case. The
    connection peer is the load balancer and forwarding headers are untrusted
    by design, so neither can key this limiter. A malformed URL-form id maps
    to one shared ``invalid`` bucket so garbage ids cannot mint unbounded
    distinct limiter keys."""
    parsed = mcp_client_metadata.parse_metadata_url(client_id) if isinstance(client_id, str) else None
    host = parsed[0] if parsed is not None else "invalid"
    return f"host:{host}"


async def _enforce_url_form_rate_limit(client_id: Any) -> None:
    """Per-CIMD-host limiter for unauthenticated URL-form client_id lookups —
    each one can cost a bounded outbound fetch, so the budget sits before it.
    A generous global bucket is checked first as a fleet-wide backstop."""
    if not is_url_form_client_id(client_id):
        return
    await run_blocking(
        critical_executor,
        check_rate_limit_inline,
        "global",
        "mcp:oauth_url_client_global",
    )
    host_key = await run_blocking(critical_executor, _url_form_rate_limit_key, client_id)
    await run_blocking(
        critical_executor,
        check_rate_limit_inline,
        host_key,
        "mcp:oauth_url_client",
    )


class _AuthorizeRequestError(ValueError):
    """Authorize-request failure that knows whether an RFC 9207 error redirect
    is safe: only once the client AND its redirect URI are both validated may
    the error be sent to the client's redirect URI. Unknown clients and
    redirect mismatches always get a JSON error — never a redirect."""

    def __init__(self, description: str, *, error: str = "invalid_request", redirect_allowed: bool = False):
        super().__init__(description)
        self.error = error
        self.redirect_allowed = redirect_allowed


def _effective_resource(resource: Optional[str]) -> str:
    # RFC 8707 resource indicators are optional; connector clients such as claude.ai
    # omit the parameter entirely. An omitted indicator binds the grant to the
    # LEGACY ``/v1/mcp/sse`` audience — the same audience old backend code
    # exact-matches — so a rollback keeps every token minted after this deploy
    # valid. The canonical audience is stored only when a client explicitly
    # requests it, and a present-but-invalid value (an empty string included)
    # still fails validate_resource exactly as before.
    return mcp_oauth_db.MCP_LEGACY_RESOURCE_URL if resource is None else resource


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
    client_ok = client is not None and not client.get("disabled_at")
    redirect_ok = client_ok and mcp_oauth_db.validate_redirect_uri(client or {}, redirect_uri)
    if response_type != "code":
        raise _AuthorizeRequestError(
            "response_type must be code", error="unsupported_response_type", redirect_allowed=redirect_ok
        )
    if client is None or client.get("disabled_at"):
        raise _AuthorizeRequestError("Unknown OAuth client")
    if not redirect_ok:
        raise _AuthorizeRequestError("redirect_uri is not registered for this client")
    if not mcp_oauth_db.validate_resource(client, resource):
        raise _AuthorizeRequestError("Invalid resource", error="invalid_target", redirect_allowed=True)
    if not mcp_oauth_db.validate_pkce_challenge(code_challenge, code_challenge_method):
        raise _AuthorizeRequestError("PKCE S256 is required", redirect_allowed=True)
    try:
        scopes = mcp_oauth_db.normalize_scopes(scope, client)
    except ValueError as exc:
        raise _AuthorizeRequestError(
            "Unsupported scope requested", error="invalid_scope", redirect_allowed=True
        ) from exc
    return client, scopes


# Query parameters an authorization redirect always rebuilds itself; anything
# already on the registered redirect URI under these names is replaced.
_REDIRECT_OWNED_PARAMS = {"code", "error", "error_description", "error_uri", "iss", "state"}


def _redirect_with_params(redirect_uri: str, params: Dict[str, str]) -> str:
    parts = urlsplit(redirect_uri)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for owned in _REDIRECT_OWNED_PARAMS:
        query.pop(owned, None)
    query.update({key: value for key, value in params.items() if value})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _redirect_with_code(redirect_uri: str, code: str, state: Optional[str]) -> str:
    return _redirect_with_params(
        redirect_uri, {"code": code, "state": state or "", "iss": MCP_AUTHORIZATION_SERVER_URL}
    )


def _redirect_with_error(redirect_uri: str, error: str, description: str, state: Optional[str]) -> str:
    return _redirect_with_params(
        redirect_uri,
        {"error": error, "error_description": description, "state": state or "", "iss": MCP_AUTHORIZATION_SERVER_URL},
    )


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
    """OAuth authorize endpoint: render the consent page after request validation."""
    resource = _effective_resource(resource)
    await _enforce_url_form_rate_limit(client_id)
    try:
        client, scopes = await run_blocking(
            _client_lookup_executor(client_id),
            _validate_authorize_request,
            response_type,
            client_id,
            redirect_uri,
            resource,
            scope,
            code_challenge,
            code_challenge_method,
        )
    except (ExecutorSaturatedError, mcp_client_metadata.McpCimdUnavailable):
        return _oauth_cimd_saturated()
    except _AuthorizeRequestError as e:
        if e.redirect_allowed:
            return RedirectResponse(_redirect_with_error(redirect_uri, e.error, str(e), state), status_code=302)
        return _oauth_error(e.error, "Invalid authorization request")
    except ValueError:
        return _oauth_error("invalid_request", "Invalid authorization request")

    client_name = str(client.get("name") or client_id)
    # URL-form (CIMD) clients are unverified third parties: the consent page
    # shows the metadata document's ASCII host next to a fixed marker so a
    # spoofed client_name cannot impersonate a registered connector.
    unverified_client = client.get("registration_mode") == "client_id_metadata_document"
    client_host = str(client.get("metadata_host") or "") if unverified_client else ""
    permissions = [SCOPE_PERMISSION_TEXT[item] for item in scopes]
    return templates.TemplateResponse(
        request,
        "mcp_oauth_authorize.html",
        {
            "client_name": client_name,
            "client_host": client_host,
            "unverified_client": unverified_client,
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
    await _enforce_url_form_rate_limit(client_id)
    try:
        _, scopes = await run_blocking(
            _client_lookup_executor(client_id),
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
    except (ExecutorSaturatedError, mcp_client_metadata.McpCimdUnavailable):
        return _oauth_cimd_saturated()
    except Exception as e:
        if isinstance(e, _AuthorizeRequestError):
            if e.redirect_allowed:
                return {"redirect_uri": _redirect_with_error(redirect_uri, e.error, str(e), state)}
            return _oauth_error(e.error, "Invalid authorization request")
        if isinstance(e, ValueError):
            return _oauth_error("invalid_request", "Invalid authorization request")
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

    await _enforce_url_form_rate_limit(client_id)
    try:
        client = await run_blocking(_client_lookup_executor(client_id), mcp_oauth_db.get_client, client_id or "")
    except (ExecutorSaturatedError, mcp_client_metadata.McpCimdUnavailable):
        return _oauth_cimd_saturated()
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
        try:
            token_pair = await run_blocking(
                db_executor, mcp_oauth_db.rotate_refresh_token, refresh_token, cast(str, client_id), resource, scope
            )
        except mcp_token_cache_db.McpTokenStoreUnavailable:
            return _oauth_temporarily_unavailable()
        if not token_pair:
            return _oauth_error("invalid_grant", "Invalid refresh token")
        return token_pair

    return _oauth_error("unsupported_grant_type", "grant_type must be authorization_code or refresh_token")

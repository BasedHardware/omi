import hmac
import os

from fastapi import HTTPException, Request

_SHIPBOB_TOOLS_SECRET_ENV = "SHIPBOB_TOOLS_SECRET"
_QUERY_TOKEN_PARAM = "shipbob_tools_token"


def _configured_secret() -> str | None:
    secret = os.getenv(_SHIPBOB_TOOLS_SECRET_ENV)
    if secret is None:
        return None
    secret = secret.strip()
    return secret or None


def _presented_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth:
        scheme, _, credentials = auth.partition(" ")
        if scheme.lower() == "bearer" and credentials.strip():
            return credentials.strip()
    query_token = request.query_params.get(_QUERY_TOKEN_PARAM)
    if query_token and query_token.strip():
        return query_token.strip()
    return None


def require_shipbob_tools_auth(request: Request) -> str:
    """Bind the chat-tool routes to an authenticated caller.

    The uid these routes act on is supplied in the request body, so callers
    must present the shared secret that only Omi's backend holds. Without it,
    anyone who knows a uid could read or write that user's ShipBob account.
    """
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail="shipbob tools auth is not configured")

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="unauthorized")

    return token

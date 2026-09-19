"""Shared-secret guard for the MS365 chat-tool routes.

The /tools/* endpoints take uid from the JSON body and act with that
user's stored MS365 credentials — no caller authentication. This guard
requires callers to present the app-level shared secret via
Authorization: Bearer <secret> or the ms365_tools_token query param.

Fails closed (503) when MS365_TOOLS_SECRET is unset so the tool surface is never
silently unauthenticated in production.
"""

import hmac
import os

from fastapi import HTTPException, Request

_SECRET_ENV = "MS365_TOOLS_SECRET"
_QUERY_PARAM = "ms365_tools_token"


def require_ms365_tools_auth(request: Request) -> None:
    secret = os.environ.get(_SECRET_ENV, "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="MS365 tools auth is not configured (MS365_TOOLS_SECRET unset)",
        )

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
    elif _QUERY_PARAM in request.query_params:
        token = request.query_params[_QUERY_PARAM]

    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")

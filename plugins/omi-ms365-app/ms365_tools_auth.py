"""Shared-secret guard for the ms365 chat-tool dispatch route.

The uid these tools act on is supplied in the request body, so callers must
present the shared secret that only Omi's backend holds. `_auth_guard` in
main.py checks that the target uid is connected to Microsoft; it does not
authenticate the caller. Without this guard, anyone who knows a uid could run
Graph tools (read mail, send mail, post in Teams, write files) as that user.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request

_MS365_TOOLS_SECRET_ENV = "MS365_TOOLS_SECRET"
_QUERY_TOKEN_PARAM = "ms365_tools_token"


def _configured_secret() -> str | None:
    secret = os.getenv(_MS365_TOOLS_SECRET_ENV)
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


def require_ms365_tools_auth(request: Request) -> str:
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail="ms365 tools auth is not configured")

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="unauthorized")

    return token

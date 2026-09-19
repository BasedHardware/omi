"""
Shared-secret authentication guard for Whoop chat-tool endpoints (#14453).
"""

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request

_WHOOP_TOOLS_SECRET_ENV = "WHOOP_TOOLS_SECRET"
_QUERY_TOKEN_PARAM = "whoop_tools_token"


def _configured_secret() -> Optional[str]:
    secret = os.getenv(_WHOOP_TOOLS_SECRET_ENV)
    if secret is None:
        return None
    secret = secret.strip()
    return secret or None


def _presented_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization")
    if auth:
        scheme, _, credentials = auth.partition(" ")
        if scheme.lower() == "bearer" and credentials.strip():
            return credentials.strip()
    query_token = request.query_params.get(_QUERY_TOKEN_PARAM)
    if query_token and query_token.strip():
        return query_token.strip()
    return None


def require_whoop_tools_auth(request: Request) -> None:
    """Guard Whoop tool routes with shared-secret authentication."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail="whoop tools auth is not configured")

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="unauthorized")

"""
Shared-secret guard for hume-ai routes acting on uid-keyed state.

The /save-emotion-memory and /force-send-notification routes take uid from
the query string and write a memory into that user's Omi account (via the
app's integration key) or push a notification to that user — with no caller
authentication. /audio?uid=... attributes the posted audio to that uid's
emotion stats and can trigger that user's notifications. This guard requires
callers to present the app-level shared secret via
Authorization: Bearer <secret> or the hume_tools_token query param.

Fails closed (503) when HUME_TOOLS_SECRET is unset so the route surface is
never silently unauthenticated in production.
"""

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request

_SECRET_ENV = "HUME_TOOLS_SECRET"
_QUERY_PARAM = "hume_tools_token"


def _configured_secret() -> Optional[str]:
    secret = os.getenv(_SECRET_ENV)
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
    query_token = request.query_params.get(_QUERY_PARAM)
    if query_token and query_token.strip():
        return query_token.strip()
    return None


def require_hume_tools_auth(request: Request) -> None:
    """Guard hume-ai uid-keyed routes with shared-secret authentication."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(
            status_code=503,
            detail="hume tools auth is not configured",
        )

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="unauthorized")

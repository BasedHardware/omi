"""
Shared-secret guard for the hume-ai service routes.

The `/audio`, `/save-emotion-memory` and `/force-send-notification` routes
read `uid` from the query string with no caller authentication: they write
emotion memories into any user's Omi account with the app's integration key
and push notifications to any user. This guard requires callers to present
the app-level shared secret either as an `Authorization: Bearer *** header
or a `hume_tools_token` query parameter.

Fails closed (503) when HUME_TOOLS_SECRET is unset so the service surface
is never silently unauthenticated in production. Mirrors
`plugins/basic/mentor_webhook_auth.py`.
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
    """Guard the hume-ai uid-keyed routes with shared-secret authentication."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(
            status_code=503,
            detail="hume tools auth is not configured",
        )

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="unauthorized")

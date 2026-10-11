"""
Shared-secret guard for Composio backend routes acting on uid-keyed credentials.

The /api/omi/facts, /api/omi/facts/batch and /api/notion/{blocks,page} routes
take uid from the request and create memories in Omi with the app's integration
key or read the user's Notion workspace with that user's stored OAuth token —
with no caller authentication. This guard requires callers to present the
app-level shared secret via Authorization: Bearer <secret> or the
composio_tools_token query param.

Fails closed (503) when COMPOSIO_TOOLS_SECRET is unset so the tool surface
is never silently unauthenticated in production.
"""

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request

_SECRET_ENV = "COMPOSIO_TOOLS_SECRET"
_QUERY_PARAM = "composio_tools_token"


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


def require_composio_tools_auth(request: Request) -> None:
    """Guard Composio backend routes with shared-secret authentication."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(
            status_code=503,
            detail="composio tools auth is not configured",
        )

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="unauthorized")

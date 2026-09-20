"""Shared-secret guard for the uid-keyed hume-ai routes.

`POST /audio`, `POST /save-emotion-memory` and `POST /force-send-notification`
take `uid` straight from the query string and act on that user's Omi account:
the first two feed (and then persist) emotion memories through the app's
`OMI_API_KEY`, the third pushes a notification to the victim bypassing the
cooldown. None of them authenticated the caller, so anyone who knows a uid
could write memories into any Omi account and notify any user.

The caller must present the app-level shared secret either as an
`Authorization: Bearer *** header or a `hume_tools_token` query parameter,
compared in constant time against the `HUME_TOOLS_SECRET` environment
variable.

Fails closed: 503 when the secret is not configured, 401 when it is missing or
wrong. Mirrors `plugins/omi-shipbob-app/shipbob_tools_auth.py` and
`plugins/composio/src/tools_auth.py`.
"""

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request

_HUME_TOOLS_SECRET_ENV = "HUME_TOOLS_SECRET"
_QUERY_TOKEN_PARAM = "hume_tools_token"


def _configured_secret() -> Optional[str]:
    secret = os.getenv(_HUME_TOOLS_SECRET_ENV)
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


def require_hume_tools_auth(request: Request) -> None:
    """Reject unauthenticated callers of the uid-keyed hume-ai routes."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail="hume tools auth is not configured")

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="unauthorized")

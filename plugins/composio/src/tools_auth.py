"""
Shared-secret and signed-session guard for Composio routes acting on uid-keyed credentials.

Guards Composio backend and browser routes:
- Backend tool routes (/api/omi/facts, /api/notion/blocks, etc.) accept the shared secret
  via Authorization: Bearer <secret> or composio_tools_token query param.
- Browser-facing routes (/api/notion/search, /api/notion/extract-memories,
  /api/omi/process-pending-memories, /api/omi/memories) accept either the shared secret
  OR an HMAC-signed session token (X-Composio-Session or composio_session query param)
  scoped to the target uid and issued by /api/notion/import.

Fails closed (503) when COMPOSIO_TOOLS_SECRET is unset so the tool surface
is never silently unauthenticated in production.
"""

import hashlib
import hmac
import os
import time
from typing import Optional

from fastapi import HTTPException, Request

_SECRET_ENV = "COMPOSIO_TOOLS_SECRET"
_QUERY_PARAM = "composio_tools_token"
_SESSION_HEADER = "X-Composio-Session"
_SESSION_PARAM = "composio_session"
_SESSION_MAX_AGE_SECONDS = 86400  # 24 hours


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


def create_composio_session_token(uid: str, timestamp: Optional[int] = None) -> str:
    """Create an HMAC-signed session token for browser-facing routes for a specific uid."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(
            status_code=503,
            detail="composio tools auth is not configured",
        )
    ts = timestamp if timestamp is not None else int(time.time())
    msg = f"{uid}:{ts}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"{ts}:{sig}"


def verify_composio_session_token(uid: str, token: str, max_age_seconds: int = _SESSION_MAX_AGE_SECONDS) -> bool:
    """Verify an HMAC-signed session token matches the uid and is not expired."""
    secret = _configured_secret()
    if secret is None or not token or not uid:
        return False
    parts = token.strip().split(":", 1)
    if len(parts) != 2:
        return False
    try:
        ts = int(parts[0])
    except ValueError:
        return False

    now = int(time.time())
    # Reject timestamps too far in the future (skew tolerance 300s) or older than max_age
    if ts > now + 300 or (now - ts) > max_age_seconds:
        return False

    expected_token = create_composio_session_token(uid, timestamp=ts)
    return hmac.compare_digest(token, expected_token)


def require_composio_tools_auth(request: Request) -> Optional[str]:
    """Guard Composio routes with shared-secret or signed-session authentication.

    Returns:
        The verified uid (str) when authenticated via a signed session token, or
        None when authenticated via the server-to-server shared secret (which has
        unrestricted authority to act on any caller-supplied uid).
    """
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(
            status_code=503,
            detail="composio tools auth is not configured",
        )

    # 1. Server-to-server shared secret (trusted backend caller)
    token = _presented_token(request)
    if token and hmac.compare_digest(token, secret):
        return None

    # 2. Browser signed session token
    session_token = (
        request.headers.get(_SESSION_HEADER)
        or request.headers.get("x-composio-session")
        or request.query_params.get(_SESSION_PARAM)
    )
    if session_token:
        # Extract uid from request: query params or path params.
        # Browser session auth binds to query/path uid; route handlers then verify
        # that any body-supplied uid matches this verified identity.
        uid = request.query_params.get("uid") or request.path_params.get("uid")
        if uid and verify_composio_session_token(uid, session_token):
            return uid

    raise HTTPException(status_code=401, detail="unauthorized")

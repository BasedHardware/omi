"""Caller-authentication guard for the Whoop app's /tools/* routes.

The chat-tool routes act with a user's stored Whoop OAuth token based solely
on the `uid` supplied in the request body, with no caller authentication.
That let anyone who knows a uid read that user's sensitive health data.

This module adds a shared-secret guard: callers must present the secret via
`Authorization: Bearer <secret>` or the `whoop_tools_token` query parameter.
The secret is read from the `WHOOP_TOOLS_SECRET` environment variable.

Behaviour:
  - Unconfigured (no WHOOP_TOOLS_SECRET) -> fail closed with HTTP 503.
  - Missing / wrong token                -> HTTP 401.
  - Correct token                        -> request proceeds.

Comparisons use hmac.compare_digest to avoid timing side-channels. This is
caller authentication only; uid remains a body-level value.
"""

from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Query, Request


def _configured_secret() -> str:
    return os.environ.get("WHOOP_TOOLS_SECRET", "")


def _extract_presented_token(request: Request, query_token: str | None) -> str:
    """Pull the caller-supplied secret from the Authorization header or query."""
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        parts = auth.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        # Allow a bare token in the header too.
        return auth.strip()
    return query_token or ""


async def require_whoop_tools_auth(
    request: Request,
    whoop_tools_token: str | None = Query(default=None),
) -> None:
    """FastAPI dependency enforcing the shared-secret guard. Fail-closed."""
    secret = _configured_secret()
    if not secret:
        # Never operate on user tokens without a configured guard.
        raise HTTPException(status_code=503, detail="Tool authentication not configured")

    presented = _extract_presented_token(request, whoop_tools_token)
    # Compare on UTF-8 bytes: hmac.compare_digest raises TypeError on
    # non-ASCII str, so a hostile Authorization header would otherwise
    # surface as a 500 instead of a clean 401.
    if not presented or not hmac.compare_digest(
        presented.encode("utf-8"), secret.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")

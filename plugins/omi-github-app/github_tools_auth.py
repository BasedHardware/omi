"""Shared-secret guard for GitHub App chat-tool routes.

The chat-tool routes under `/tools/*` read `uid` from the request body and act
on that user's stored GitHub OAuth access token. They must only be reachable by
the trusted Omi backend, so every route is gated behind this dependency: the
caller presents a shared secret either as an `Authorization: Bearer <secret>`
header or a `github_tools_token` query parameter, compared in constant time
against the `GITHUB_TOOLS_SECRET` environment variable.

Fails closed: 503 when the secret is not configured, 401 when it is missing or
wrong. Mirrors `plugins/omi-shipbob-app/shipbob_tools_auth.py` and
`plugins/basic/mentor_webhook_auth.py`.
"""

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request

_GITHUB_TOOLS_SECRET_ENV = "GITHUB_TOOLS_SECRET"
_QUERY_TOKEN_PARAM = "github_tools_token"


def _configured_secret() -> Optional[str]:
    secret = os.getenv(_GITHUB_TOOLS_SECRET_ENV)
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


def require_github_tools_auth(request: Request) -> None:
    """Reject unauthenticated callers of the GitHub chat-tool routes."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(
            status_code=503,
            detail="github tools auth is not configured",
        )

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="unauthorized")

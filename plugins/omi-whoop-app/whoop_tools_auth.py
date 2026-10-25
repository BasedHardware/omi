"""Shared-secret guard for Whoop chat-tool routes (#14453).

The guard accepts the app-level secret via Authorization: Bearer or
the whoop_tools_token query parameter. It fails closed with 503 when the
secret is not configured, so a missing deployment variable can never
silently leave the health-data surface open.
"""

import hmac
import os

from fastapi import HTTPException, Request

SECRET_ENV = "WHOOP_TOOLS_SECRET"
TOKEN_QUERY_PARAM = "whoop_tools_token"


def _presented_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        return credentials.strip()
    return (request.query_params.get(TOKEN_QUERY_PARAM) or "").strip()


def require_whoop_tools_auth(request: Request) -> None:
    secret = os.environ.get(SECRET_ENV, "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Whoop tools authentication is not configured",
        )

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token.encode("utf-8"), secret.encode("utf-8")):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing Whoop tools credentials",
        )

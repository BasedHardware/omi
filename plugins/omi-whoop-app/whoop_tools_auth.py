"""Shared-secret guard for the whoop chat-tool routes.

All /tools/* endpoints take uid from the JSON body and read that user's
stored Whoop OAuth token (recovery, strain, sleep, workouts, body
measurements, profile — health data) with no caller authentication.
This guard requires callers to present the app-level shared secret via
Authorization: Bearer <secret> or the whoop_tools_token query param.

Fails closed (503) when WHOOP_TOOLS_SECRET is unset so the tool surface
is never silently unauthenticated in production.
"""

import hmac
import os

from fastapi import HTTPException, Request

_SECRET_ENV = "WHOOP_TOOLS_SECRET"
_QUERY_PARAM = "whoop_tools_token"


def require_whoop_tools_auth(request: Request) -> None:
    secret = os.environ.get(_SECRET_ENV, "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Whoop tools auth is not configured (WHOOP_TOOLS_SECRET unset)",
        )

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
    elif _QUERY_PARAM in request.query_params:
        token = request.query_params[_QUERY_PARAM]

    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")

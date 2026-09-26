"""Shared-secret guard for the multion mutating endpoints.

`POST /multion` (webhook) triggers MultiOn browse sessions — real-world
purchases ("add these books to my Amazon cart") — keyed by a raw uid
query param. `POST /multion/submit_uid` writes the uid -> multion
user_id binding with no verification, so anyone can rebind or corrupt
any user's integration state.

This guard requires callers to present the app-level shared secret via
Authorization: Bearer <secret> or the multion_token query param. It
fails closed (503) when MULTION_WEBHOOK_SECRET is unset so the
mutating surface is never silently unauthenticated in production.
"""

import hmac
import os

from fastapi import HTTPException, Request

_SECRET_ENV = "MULTION_WEBHOOK_SECRET"
_QUERY_PARAM = "multion_token"


def require_multion_auth(request: Request) -> None:
    secret = os.environ.get(_SECRET_ENV, "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Multion auth is not configured (MULTION_WEBHOOK_SECRET unset)",
        )

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
    elif _QUERY_PARAM in request.query_params:
        token = request.query_params[_QUERY_PARAM]

    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")

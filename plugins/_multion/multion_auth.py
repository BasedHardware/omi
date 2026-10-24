"""Shared-secret guard for the MultiOn mutating endpoints.

``POST /multion`` triggers a real MultiOn browse session ("add these books
to my Amazon cart") for the MultiOn user bound to a raw ``uid`` query
parameter. ``POST /multion/submit_uid`` writes that ``uid -> user_id``
binding. Neither endpoint verified the caller, so anyone who knew an Omi
uid could rebind the integration or fire purchases inside that user's
MultiOn session.

The guard accepts the app-level secret via ``Authorization: Bearer`` or
the ``multion_token`` query parameter. It fails closed with 503 when the
secret is not configured, so a missing deployment variable can never
silently leave the mutating surface open. Deployments must set
``MULTION_WEBHOOK_SECRET`` before this ships; rotating it invalidates
tokens already handed to callers.
"""

import hmac
import os

from fastapi import HTTPException, Request

SECRET_ENV = "MULTION_WEBHOOK_SECRET"
TOKEN_QUERY_PARAM = "multion_token"


def _presented_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        return credentials.strip()
    return (request.query_params.get(TOKEN_QUERY_PARAM) or "").strip()


def require_multion_auth(request: Request) -> None:
    secret = os.environ.get(SECRET_ENV, "")
    if not secret:
        raise HTTPException(status_code=503, detail="MultiOn webhook auth is not configured")

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token.encode("utf-8"), secret.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Unauthorized")

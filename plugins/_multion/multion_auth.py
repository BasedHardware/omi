"""
Shared-secret authentication guard for MultiOn endpoints (#14463).
"""

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request

_MULTION_WEBHOOK_SECRET_ENV = "MULTION_WEBHOOK_SECRET"
_QUERY_TOKEN_PARAM = "multion_token"


def _configured_secret() -> Optional[str]:
    secret = os.getenv(_MULTION_WEBHOOK_SECRET_ENV)
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


def require_multion_auth(request: Request) -> None:
    """Guard MultiOn mutating endpoints with shared-secret authentication."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail="multion auth is not configured")

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="unauthorized")

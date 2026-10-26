"""Shared-secret authentication guard for Twitter chat tools.

Validates that incoming /tools/* requests present the shared secret
configured via TWITTER_TOOLS_SECRET, preventing unauthorized callers
from executing actions with a victim's Twitter credentials.
"""

from __future__ import annotations

import hmac
import os
from typing import Optional

try:
    from fastapi import Header, HTTPException, Query, status
except ImportError:  # pragma: no cover - defensive for minimal CI stub environments
    def Header(default=None, **kwargs):
        return default

    def Query(default=None, **kwargs):
        return default

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None, headers=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
            self.headers = headers or {}

    class status:
        HTTP_401_UNAUTHORIZED = 401
        HTTP_503_SERVICE_UNAVAILABLE = 503

_TWITTER_TOOLS_SECRET_ENV = "TWITTER_TOOLS_SECRET"


def _configured_secret() -> str | None:
    secret = os.getenv(_TWITTER_TOOLS_SECRET_ENV)
    if secret is None:
        return None
    secret = secret.strip()
    return secret or None


def require_twitter_tools_auth(
    authorization: Optional[str] = Header(None),
    twitter_tools_token: Optional[str] = Query(None),
) -> None:
    """Validate incoming chat tool request against TWITTER_TOOLS_SECRET.

    Fails closed with 503 when TWITTER_TOOLS_SECRET is unset or empty.
    Returns 401 on missing or incorrect credentials.
    Accepts credentials via:
      - Authorization: Bearer <token>
      - ?twitter_tools_token=<token>
    """
    secret = _configured_secret()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Twitter tools authentication is not configured",
        )

    token = None
    if isinstance(authorization, str) and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing Twitter tools credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    elif isinstance(twitter_tools_token, str) and twitter_tools_token:
        token = twitter_tools_token

    if not token or not hmac.compare_digest(token.encode("utf-8"), secret.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Twitter tools credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

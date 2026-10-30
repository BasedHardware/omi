"""Shared-secret authentication for Whoop chat tools called by the trusted backend."""

import hmac
import os

from fastapi import HTTPException, Request


def require_whoop_tools_auth(request: Request) -> None:
    """Fail closed before any body uid can be used to access Whoop data."""
    secret = os.getenv("WHOOP_TOOLS_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="whoop tools auth is not configured")

    token = None
    authorization = request.headers.get("Authorization", "")
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        token = credentials.strip()
    else:
        token = request.query_params.get("whoop_tools_token", "").strip()

    if not token or not hmac.compare_digest(token.encode("utf-8"), secret.encode("utf-8")):
        raise HTTPException(status_code=401, detail="unauthorized")

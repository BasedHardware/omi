import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException, Query, status


def require_whoop_tools_auth(
    authorization: Optional[str] = Header(default=None),
    whoop_tools_token: Optional[str] = Query(default=None),
) -> None:
    """Protect Whoop chat-tool routes with a deployment-provided shared secret."""
    configured_secret = os.getenv("WHOOP_TOOLS_SECRET")

    if not configured_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Whoop tools authentication is not configured",
        )

    bearer_token: Optional[str] = None
    if authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer" and credentials:
            bearer_token = credentials

    supplied_token = bearer_token or whoop_tools_token

    if not supplied_token or not hmac.compare_digest(
        supplied_token.encode("utf-8"),
        configured_secret.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Whoop tools credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

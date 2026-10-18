"""Authentication dependency for IQ Rating plugin routes."""
import hmac
import os
from typing import Optional
from fastapi import Header, HTTPException, Query, status

IQ_RATING_SECRET = os.getenv("IQ_RATING_SECRET")


def verify_iq_auth(
    authorization: Optional[str] = Header(None),
    iq_rating_token: Optional[str] = Query(None, description="Auth token for webview actions"),
) -> bool:
    """Verify incoming request against IQ_RATING_SECRET.

    Fails closed with HTTP 503 if IQ_RATING_SECRET is not configured.
    Returns True if valid token presented in Authorization header or query param.
    Raises HTTP 401 if token is missing or invalid.
    """
    secret = os.getenv("IQ_RATING_SECRET", IQ_RATING_SECRET)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IQ Rating authentication is unconfigured (IQ_RATING_SECRET missing).",
        )
    if authorization is not None and not isinstance(authorization, str):
        authorization = None
    if iq_rating_token is not None and not isinstance(iq_rating_token, str):
        iq_rating_token = None

    token = None
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1:
            token = parts[0]

    if not token and iq_rating_token:
        token = iq_rating_token.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(token.encode("utf-8"), secret.encode("utf-8"))
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True

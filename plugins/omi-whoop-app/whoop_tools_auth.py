import hmac
import os
from typing import Optional

try:
    from fastapi import Header, HTTPException, Query, status
except ImportError:  # pragma: no cover - defensive for minimal CI stub runners
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


def require_whoop_tools_auth(
    authorization: Optional[str] = Header(None),
    whoop_tools_token: Optional[str] = Query(None),
) -> None:
    expected = os.getenv("WHOOP_TOOLS_SECRET")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Whoop tools authentication is not configured",
        )

    token = None
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing Whoop tools credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    elif whoop_tools_token:
        token = whoop_tools_token

    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Whoop tools credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

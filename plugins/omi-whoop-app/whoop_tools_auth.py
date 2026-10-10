"""
Shared-secret authentication guard for Whoop tool routes.

Validates either an Authorization: Bearer header or a whoop_tools_token
query parameter against the WHOOP_TOOLS_SECRET environment variable
using constant-time comparison to prevent timing attacks.

Returns 503 when WHOOP_TOOLS_SECRET is not configured (fail-closed),
and 401 on missing or incorrect token.
"""

import os
import hmac
from fastapi import Header, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)

WHOOP_TOOLS_SECRET = os.environ.get("WHOOP_TOOLS_SECRET")


async def require_whoop_tools_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = None,
    token_query: str = Query(None, alias="whoop_tools_token"),
) -> dict:
    """
    Dependency that enforces shared-secret authentication on Whoop tool routes.

    Accepts authentication via:
      - Authorization: Bearer <token> header
      - ?whoop_tools_token=<token> query parameter

    Raises HTTPException:
      - 503 if WHOOP_TOOLS_SECRET is not set (fail-closed)
      - 401 if token is missing or incorrect
    """
    if not WHOOP_TOOLS_SECRET:
        raise HTTPException(
            status_code=503,
            detail="WHOOP_TOOLS_SECRET environment variable is not configured",
        )

    provided_token = None

    if credentials is not None:
        provided_token = credentials.credentials
    elif token_query is not None:
        provided_token = token_query

    if provided_token is None:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token. Provide Authorization: Bearer or ?whoop_tools_token query parameter.",
        )

    if not hmac.compare_digest(provided_token, WHOOP_TOOLS_SECRET):
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token.",
        )

    return {"authenticated": True}

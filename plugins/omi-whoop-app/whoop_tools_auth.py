<content>
import os
import hmac
from fastapi import Header, HTTPException, status

WHOOP_TOOLS_SECRET = os.environ.get("WHOOP_TOOLS_SECRET")

async def require_whoop_tools_auth(authorization: str = Header(None), whoop_tools_token: str = None):
    """
    Validates the shared-secret for whoop-app /tools/* routes.
    Can be passed via 'Authorization: Bearer <secret>' or 'whoop_tools_token' query param.
    """
    if not WHOOP_TOOLS_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Whoop tools authentication is not configured."
        )

    provided_token = None
    if authorization and authorization.startswith("Bearer "):
        provided_token = authorization.split(" ", 1)[1]
    elif whoop_tools_token:
        provided_token = whoop_tools_token

    if not provided_token or not hmac.compare_digest(provided_token, WHOOP_TOOLS_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Whoop tools token."
        )

    return True
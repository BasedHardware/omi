```python
import os
import hmac
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import APIKeyHeader

MULTION_WEBHOOK_SECRET = os.environ.get("MULTION_WEBHOOK_SECRET")

async def verify_multion_auth(request: Request):
    if not MULTION_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MultiOn authentication not configured"
        )

    # Try Authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        if hmac.compare_digest(token, MULTION_WEBHOOK_SECRET):
            return

    # Fall back to query param
    token = request.query_params.get("multion_token")
    if token and hmac.compare_digest(token, MULTION_WEBHOOK_SECRET):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid MultiOn authentication token"
    )

def get_multion_auth_dependency():
    return Depends(verify_multion_auth)
```
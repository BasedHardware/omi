# backend/auth/dependencies.py
#
# FIX: The CurrentUser Annotated alias must NOT be used alongside
# = Depends(...) in function signatures. The Annotated type already
# carries the Depends — just use it as the type annotation alone.
#
# CORRECT usage in routes:
#   async def my_route(user: CurrentUser):         ✅
#
# WRONG (causes the AssertionError):
#   async def my_route(user: CurrentUser = Depends(get_current_user)):  ❌

from typing import Annotated, Dict
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from auth.supabase_client import get_anon_client

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Dict:
    """
    Validates the Bearer JWT issued by Supabase Auth.
    Returns { id, email, user_id, access_token }
    Raises 401 if token is missing, expired, or invalid.
    """
    token = credentials.credentials
    client = get_anon_client()

    try:
        response = client.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = response.user
        return {
            "id": user.id,
            "email": user.email,
            "user_id": user.id,       # alias for compatibility with knowledge.py
            "access_token": token,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ✅ This is the ONLY way to define this alias.
# Use it in route signatures as just:  user: CurrentUser
# Do NOT add = Depends(...) alongside it — the Depends is already inside Annotated.
CurrentUser = Annotated[Dict, Depends(get_current_user)]

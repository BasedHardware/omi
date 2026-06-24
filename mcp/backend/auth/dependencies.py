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

import jwt
import uuid
import hashlib

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Dict:
    """
    Decodes the Bearer JWT issued by Firebase (from the desktop app).
    Returns { id, email, user_id, access_token }
    """
    token = credentials.credentials

    try:
        # Decode Firebase JWT without signature verification for local backend use
        payload = jwt.decode(token, options={"verify_signature": False})
        
        firebase_uid = payload.get("sub")
        email = payload.get("email", "")
        
        if not firebase_uid:
            raise ValueError("Token missing 'sub' claim")
            
        # Hash the Firebase UID into a valid UUID format for Supabase database compatibility
        m = hashlib.md5()
        m.update(firebase_uid.encode('utf-8'))
        stable_uuid = str(uuid.UUID(m.hexdigest()))
        
        return {
            "id": stable_uuid,
            "email": email,
            "user_id": stable_uuid,
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

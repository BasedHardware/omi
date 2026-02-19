from typing import List, Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

import database.mcp_api_key as mcp_api_key_db
import database.dev_api_key as dev_api_key_db
from utils.firebase_auth import verify_firebase_token
from utils.scopes import Scopes, has_scope

bearer_scheme = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        id_token = credentials.credentials
        decoded_token = verify_firebase_token(id_token)
        return decoded_token["uid"]
    except Exception as e:
        print(f"Error verifying Firebase ID token: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")


api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def get_uid_from_mcp_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or not api_key.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'",
        )

    token = api_key.replace("Bearer ", "")
    user_id = mcp_api_key_db.get_user_id_by_api_key(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return user_id


# Data structure to return from auth
class ApiKeyAuth:
    def __init__(self, uid: str, scopes: Optional[List[str]]):
        self.uid = uid
        self.scopes = scopes


async def get_api_key_auth(api_key: str = Security(api_key_header)) -> ApiKeyAuth:
    """Extract user ID and scopes from API key"""
    if not api_key or not api_key.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'",
        )

    token = api_key.replace("Bearer ", "")
    user_data = dev_api_key_db.get_user_and_scopes_by_api_key(token)

    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    return ApiKeyAuth(uid=user_data["user_id"], scopes=user_data.get("scopes"))


async def get_uid_from_dev_api_key(api_key: str = Security(api_key_header)) -> str:
    """Legacy function for backward compatibility. Use scope-specific dependencies instead."""
    auth_data = await get_api_key_auth(api_key)
    return auth_data.uid


# Scope-specific dependencies
async def get_uid_with_conversations_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.CONVERSATIONS_READ):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.CONVERSATIONS_READ}"
        )
    return auth.uid


async def get_uid_with_conversations_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.CONVERSATIONS_WRITE):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.CONVERSATIONS_WRITE}"
        )
    return auth.uid


async def get_uid_with_memories_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.MEMORIES_READ):
        raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.MEMORIES_READ}")
    return auth.uid


async def get_uid_with_memories_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.MEMORIES_WRITE):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.MEMORIES_WRITE}"
        )
    return auth.uid


async def get_uid_with_action_items_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.ACTION_ITEMS_READ):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.ACTION_ITEMS_READ}"
        )
    return auth.uid


async def get_uid_with_action_items_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.ACTION_ITEMS_WRITE):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.ACTION_ITEMS_WRITE}"
        )
    return auth.uid


async def get_uid_with_goals_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.GOALS_READ):
        raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.GOALS_READ}")
    return auth.uid


async def get_uid_with_goals_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.GOALS_WRITE):
        raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.GOALS_WRITE}")
    return auth.uid

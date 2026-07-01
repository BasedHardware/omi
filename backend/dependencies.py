from typing import List, Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth

import database.mcp_api_key as mcp_api_key_db
import database.dev_api_key as dev_api_key_db
from utils.scopes import Scopes, has_scope
from utils.other.endpoints import check_api_key_rate_limit
import logging

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        id_token = credentials.credentials
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token["uid"]
    except Exception as e:
        logger.error(f"Error verifying Firebase ID token: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")


api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def get_uid_from_mcp_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or not api_key.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'",
        )

    token = api_key.replace("Bearer ", "")
    user_data = mcp_api_key_db.get_user_and_scopes_by_api_key(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    user_id = user_data["user_id"]
    check_api_key_rate_limit(
        prefix="mcp",
        uid=user_id,
        app_id=user_data.get("app_id"),
        key_id=user_data.get("key_id"),
        policy_name="mcp:read",
    )
    return user_id


# Data structure to return from auth
class ApiKeyAuth:
    def __init__(
        self,
        uid: str,
        scopes: Optional[List[str]],
        app_id: Optional[str] = None,
        key_id: Optional[str] = None,
    ):
        self.uid = uid
        self.scopes = scopes
        self.app_id = app_id
        self.key_id = key_id


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

    return ApiKeyAuth(
        uid=user_data["user_id"],
        scopes=user_data.get("scopes"),
        app_id=user_data.get("app_id"),
        key_id=user_data.get("key_id"),
    )


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
    check_api_key_rate_limit(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:conversations_read",
    )
    return auth.uid


async def get_uid_with_conversations_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.CONVERSATIONS_WRITE):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.CONVERSATIONS_WRITE}"
        )
    check_api_key_rate_limit(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:conversations",
    )
    return auth.uid


async def get_uid_with_memories_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.MEMORIES_READ):
        raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.MEMORIES_READ}")
    check_api_key_rate_limit(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:memories_read",
    )
    return auth.uid


async def get_uid_with_memories_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.MEMORIES_WRITE):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.MEMORIES_WRITE}"
        )
    check_api_key_rate_limit(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:memories",
    )
    return auth.uid


async def get_uid_with_action_items_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.ACTION_ITEMS_READ):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.ACTION_ITEMS_READ}"
        )
    check_api_key_rate_limit(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:action_items_read",
    )
    return auth.uid


async def get_uid_with_action_items_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.ACTION_ITEMS_WRITE):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.ACTION_ITEMS_WRITE}"
        )
    check_api_key_rate_limit(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:action_items_write",
    )
    return auth.uid


async def get_uid_with_goals_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.GOALS_READ):
        raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.GOALS_READ}")
    check_api_key_rate_limit(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:goals_read",
    )
    return auth.uid


async def get_uid_with_goals_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    if not has_scope(auth.scopes, Scopes.GOALS_WRITE):
        raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.GOALS_WRITE}")
    check_api_key_rate_limit(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:goals_write",
    )
    return auth.uid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging

from ..core.auth import (
    Scope, AuthContext, APIKeyInfo,
    get_auth_context, register_api_key, revoke_api_key, list_api_keys,
    require_scopes
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class CreateAPIKeyRequest(BaseModel):
    name: str
    scopes: List[str]
    expires_in_days: Optional[int] = None


class CreateAPIKeyResponse(BaseModel):
    api_key: str
    key_info: APIKeyInfo
    message: str


class APIKeyListResponse(BaseModel):
    keys: List[APIKeyInfo]


class RevokeKeyResponse(BaseModel):
    success: bool
    message: str


SCOPE_DESCRIPTIONS = {
    Scope.MEMORIES_READ: "Read memories and stored facts",
    Scope.MEMORIES_WRITE: "Create and update memories",
    Scope.MEMORIES_DELETE: "Delete memories",
    Scope.TASKS_READ: "Read tasks and reminders",
    Scope.TASKS_WRITE: "Create and update tasks",
    Scope.TASKS_DELETE: "Delete tasks",
    Scope.CONVERSATIONS_READ: "Read conversation history",
    Scope.CONVERSATIONS_WRITE: "Create conversations",
    Scope.GRAPH_READ: "Read knowledge graph entities",
    Scope.GRAPH_WRITE: "Modify knowledge graph",
    Scope.NOTIFICATIONS_SEND: "Send notifications",
    Scope.LOCATION_READ: "Read location data",
    Scope.LOCATION_WRITE: "Update location data",
    Scope.CHAT: "Use the chat interface",
    Scope.ADMIN: "Full administrative access",
}


@router.get("/scopes")
async def list_available_scopes():
    return {
        "scopes": [
            {
                "id": scope.value,
                "name": scope.name,
                "description": SCOPE_DESCRIPTIONS.get(scope, "")
            }
            for scope in Scope
        ]
    }


@router.post("/keys", response_model=CreateAPIKeyResponse)
async def create_api_key(
    request: CreateAPIKeyRequest,
    auth: AuthContext = Depends(require_scopes(Scope.ADMIN))
):
    scopes = []
    for scope_str in request.scopes:
        try:
            scopes.append(Scope(scope_str))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scope: {scope_str}"
            )
    
    api_key, key_info = register_api_key(
        name=request.name,
        user_id=auth.user_id,
        scopes=scopes,
        expires_in_days=request.expires_in_days
    )
    
    return CreateAPIKeyResponse(
        api_key=api_key,
        key_info=key_info,
        message="API key created successfully. Store this key securely - it cannot be retrieved again."
    )


@router.get("/keys", response_model=APIKeyListResponse)
async def list_keys(
    auth: AuthContext = Depends(require_scopes(Scope.ADMIN))
):
    keys = list_api_keys(auth.user_id)
    return APIKeyListResponse(keys=keys)


@router.delete("/keys/{key_id}", response_model=RevokeKeyResponse)
async def revoke_key(
    key_id: str,
    auth: AuthContext = Depends(require_scopes(Scope.ADMIN))
):
    success = revoke_api_key(key_id)
    
    if success:
        return RevokeKeyResponse(
            success=True,
            message=f"API key {key_id} revoked successfully"
        )
    else:
        raise HTTPException(
            status_code=404,
            detail=f"API key {key_id} not found"
        )


@router.get("/me")
async def get_current_auth_context(
    auth: AuthContext = Depends(get_auth_context)
):
    return {
        "user_id": auth.user_id,
        "scopes": [s.value for s in auth.scopes],
        "key_id": auth.key_id,
        "key_name": auth.key_name,
        "is_internal": auth.is_internal
    }

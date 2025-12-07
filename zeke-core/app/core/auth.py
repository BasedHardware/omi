from typing import Optional, List, Set, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from fastapi import HTTPException, Header, Depends, Request
from pydantic import BaseModel
import hashlib
import secrets
import logging

from .config import get_settings
from .database import get_db_context

logger = logging.getLogger(__name__)
settings = get_settings()


class Scope(str, Enum):
    MEMORIES_READ = "memories:read"
    MEMORIES_WRITE = "memories:write"
    MEMORIES_DELETE = "memories:delete"
    
    TASKS_READ = "tasks:read"
    TASKS_WRITE = "tasks:write"
    TASKS_DELETE = "tasks:delete"
    
    CONVERSATIONS_READ = "conversations:read"
    CONVERSATIONS_WRITE = "conversations:write"
    
    GRAPH_READ = "graph:read"
    GRAPH_WRITE = "graph:write"
    
    NOTIFICATIONS_SEND = "notifications:send"
    
    LOCATION_READ = "location:read"
    LOCATION_WRITE = "location:write"
    
    CHAT = "chat"
    
    ADMIN = "admin"


SCOPE_HIERARCHY = {
    Scope.ADMIN: {
        Scope.MEMORIES_READ, Scope.MEMORIES_WRITE, Scope.MEMORIES_DELETE,
        Scope.TASKS_READ, Scope.TASKS_WRITE, Scope.TASKS_DELETE,
        Scope.CONVERSATIONS_READ, Scope.CONVERSATIONS_WRITE,
        Scope.GRAPH_READ, Scope.GRAPH_WRITE,
        Scope.NOTIFICATIONS_SEND,
        Scope.LOCATION_READ, Scope.LOCATION_WRITE,
        Scope.CHAT
    },
    Scope.MEMORIES_WRITE: {Scope.MEMORIES_READ},
    Scope.MEMORIES_DELETE: {Scope.MEMORIES_READ, Scope.MEMORIES_WRITE},
    Scope.TASKS_WRITE: {Scope.TASKS_READ},
    Scope.TASKS_DELETE: {Scope.TASKS_READ, Scope.TASKS_WRITE},
    Scope.CONVERSATIONS_WRITE: {Scope.CONVERSATIONS_READ},
    Scope.GRAPH_WRITE: {Scope.GRAPH_READ},
    Scope.LOCATION_WRITE: {Scope.LOCATION_READ},
}


class APIKeyInfo(BaseModel):
    key_id: str
    name: str
    user_id: str
    scopes: List[str]
    created_at: datetime
    last_used: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True


@dataclass
class AuthContext:
    user_id: str
    scopes: Set[Scope]
    key_id: Optional[str] = None
    key_name: Optional[str] = None
    is_internal: bool = False
    
    def has_scope(self, scope: Scope) -> bool:
        if scope in self.scopes:
            return True
        
        for granted_scope in self.scopes:
            if granted_scope in SCOPE_HIERARCHY:
                if scope in SCOPE_HIERARCHY[granted_scope]:
                    return True
        
        return False
    
    def require_scope(self, scope: Scope) -> None:
        if not self.has_scope(scope):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required scope: {scope.value}"
            )
    
    def require_any_scope(self, scopes: List[Scope]) -> None:
        for scope in scopes:
            if self.has_scope(scope):
                return
        
        scope_names = [s.value for s in scopes]
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions. Required one of: {', '.join(scope_names)}"
        )


_api_keys: Dict[str, APIKeyInfo] = {}


def generate_api_key() -> tuple[str, str]:
    key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, key_hash


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def register_api_key(
    name: str,
    user_id: str,
    scopes: List[Scope],
    expires_in_days: Optional[int] = None
) -> tuple[str, APIKeyInfo]:
    key, key_hash = generate_api_key()
    
    expires_at = None
    if expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
    
    key_info = APIKeyInfo(
        key_id=key_hash[:12],
        name=name,
        user_id=user_id,
        scopes=[s.value for s in scopes],
        created_at=datetime.utcnow(),
        expires_at=expires_at
    )
    
    _api_keys[key_hash] = key_info
    
    return key, key_info


def validate_api_key(key: str) -> Optional[APIKeyInfo]:
    key_hash = hash_api_key(key)
    
    key_info = _api_keys.get(key_hash)
    
    if not key_info:
        return None
    
    if not key_info.is_active:
        return None
    
    if key_info.expires_at and key_info.expires_at < datetime.utcnow():
        return None
    
    key_info.last_used = datetime.utcnow()
    
    return key_info


def revoke_api_key(key_id: str) -> bool:
    for key_hash, key_info in _api_keys.items():
        if key_info.key_id == key_id:
            key_info.is_active = False
            return True
    return False


def list_api_keys(user_id: str) -> List[APIKeyInfo]:
    return [
        key_info for key_info in _api_keys.values()
        if key_info.user_id == user_id and key_info.is_active
    ]


def get_internal_auth_context(user_id: str = "default_user") -> AuthContext:
    return AuthContext(
        user_id=user_id,
        scopes=set(Scope),
        is_internal=True
    )


async def get_auth_context(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> AuthContext:
    api_key = None
    
    if authorization and authorization.startswith("Bearer "):
        api_key = authorization[7:]
    elif x_api_key:
        api_key = x_api_key
    
    if not api_key:
        return AuthContext(
            user_id="default_user",
            scopes=set(Scope),
            is_internal=True
        )
    
    key_info = validate_api_key(api_key)
    
    if not key_info:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired API key"
        )
    
    scopes = set()
    for scope_str in key_info.scopes:
        try:
            scopes.add(Scope(scope_str))
        except ValueError:
            logger.warning(f"Unknown scope in API key: {scope_str}")
    
    return AuthContext(
        user_id=key_info.user_id,
        scopes=scopes,
        key_id=key_info.key_id,
        key_name=key_info.name,
        is_internal=False
    )


def require_scopes(*required_scopes: Scope):
    async def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        for scope in required_scopes:
            auth.require_scope(scope)
        return auth
    return dependency


def require_any_scope(*required_scopes: Scope):
    async def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        auth.require_any_scope(list(required_scopes))
        return auth
    return dependency


class ScopeChecker:
    def __init__(self, *scopes: Scope, require_all: bool = True):
        self.scopes = scopes
        self.require_all = require_all
    
    async def __call__(
        self, 
        auth: AuthContext = Depends(get_auth_context)
    ) -> AuthContext:
        if self.require_all:
            for scope in self.scopes:
                auth.require_scope(scope)
        else:
            auth.require_any_scope(list(self.scopes))
        
        return auth

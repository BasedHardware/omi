import logging
from typing import List, Optional

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth

import database.mcp_api_key as mcp_api_key_db
import database.dev_api_key as dev_api_key_db
from utils.executors import critical_executor, run_blocking
from utils.log_sanitizer import sanitize
from utils.observability.api_keys import record_api_key_repairs
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.mcp_memories import (
    McpVerifiedAuth,
    build_mcp_default_memory_read_context,
    build_mcp_default_memory_write_context,
)
from utils.other.endpoints import check_api_key_rate_limit
from utils.scopes import Scopes, has_scope

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        id_token = credentials.credentials
        decoded_token = await run_blocking(critical_executor, auth.verify_id_token, id_token)
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
    auth_result = await run_blocking(critical_executor, mcp_api_key_db.get_api_key_auth_result, token)
    record_api_key_repairs(key_kind="mcp", operation="auth", repairs=auth_result.repairs, log=logger)
    user_data = auth_result.context
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    user_id = user_data["user_id"]
    await _check_api_key_rate_limit_async(
        prefix="mcp",
        uid=user_id,
        app_id=user_data.get("app_id"),
        key_id=user_data.get("key_id"),
        policy_name="mcp:read",
    )
    return user_id


async def get_mcp_api_key_auth(api_key: str = Security(api_key_header)) -> "ApiKeyAuth":
    """Extract uid plus persisted MCP app/key/scope context from an MCP API key.

    Existing uid-only MCP auth remains available through get_uid_from_mcp_api_key.
    Missing scopes/app_id/key_id are preserved as missing values so memory memory
    authorization fails closed instead of inferring advertised MCP tool scopes.
    """
    if not api_key or not api_key.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'",
        )

    token = api_key.replace("Bearer ", "")
    auth_result = await run_blocking(critical_executor, mcp_api_key_db.get_api_key_auth_result, token)
    record_api_key_repairs(key_kind="mcp", operation="auth", repairs=auth_result.repairs, log=logger)
    user_data = auth_result.context
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    return ApiKeyAuth(
        uid=user_data["user_id"],
        scopes=user_data.get("scopes"),
        app_id=user_data.get("app_id"),
        key_id=user_data.get("key_id"),
    )


async def get_mcp_memory_default_memory_read_context(
    auth: "ApiKeyAuth" = Depends(get_mcp_api_key_auth),
) -> ProductAuthorizationContext:
    if not has_scope(auth.scopes, 'memories.read'):
        raise HTTPException(status_code=403, detail="Insufficient permissions. Required scope: memories.read")
    if not auth.app_id or not auth.key_id:
        raise HTTPException(status_code=403, detail="Missing MCP API app/key identity for memory memory authorization")
    await _check_api_key_rate_limit_async(
        prefix="mcp",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="mcp:memories_read",
    )
    return build_mcp_default_memory_read_context(
        McpVerifiedAuth(
            uid=auth.uid,
            app_id=auth.app_id,
            key_id=auth.key_id,
            scopes=tuple(auth.scopes or ()),
        )
    )


async def get_mcp_memory_default_memory_write_context(
    auth: "ApiKeyAuth" = Depends(get_mcp_api_key_auth),
) -> ProductAuthorizationContext:
    """Authenticate an MCP key and build the memory write authorization context.

    Requires a persisted ``memories.write`` scope so legacy/read-only MCP keys
    cannot mutate canonical memories. Missing app/key identity fails closed; the
    shared grant seam enforces the persisted ``write`` capability separately.
    """
    if not has_scope(auth.scopes, 'memories.write'):
        raise HTTPException(status_code=403, detail="Insufficient permissions. Required scope: memories.write")
    if not auth.app_id or not auth.key_id:
        raise HTTPException(status_code=403, detail="Missing MCP API app/key identity for memory memory authorization")
    await _check_api_key_rate_limit_async(
        prefix="mcp",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="mcp:memories_write",
    )
    return build_mcp_default_memory_write_context(
        McpVerifiedAuth(
            uid=auth.uid,
            app_id=auth.app_id,
            key_id=auth.key_id,
            scopes=tuple(auth.scopes or ()),
        )
    )


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
    auth_result = await run_blocking(critical_executor, dev_api_key_db.get_api_key_auth_result, token)
    record_api_key_repairs(key_kind="dev", operation="auth", repairs=auth_result.repairs, log=logger)
    user_data = auth_result.context

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
def _log_dev_api_rate_limit_failure(
    *,
    request: Optional[Request],
    auth: ApiKeyAuth,
    policy_name: str,
    status_code: int,
):
    path = request.url.path if request else 'unknown_path'
    remote_ip = request.client.host if request and request.client else None
    user_agent = sanitize(request.headers.get('user-agent')) if request else None
    logger.warning(
        "developer_api_rate_limit_failure policy=%s status=%s path=%s uid=%s app_id=%s key_id=%s remote_ip=%s user_agent=%s",
        policy_name,
        status_code,
        path,
        auth.uid,
        auth.app_id or 'unknown_app',
        auth.key_id or 'unknown_key',
        remote_ip,
        user_agent,
    )


def _check_dev_api_key_rate_limit(
    *,
    request: Optional[Request],
    auth: ApiKeyAuth,
    policy_name: str,
):
    try:
        check_api_key_rate_limit(
            prefix="dev",
            uid=auth.uid,
            app_id=auth.app_id,
            key_id=auth.key_id,
            policy_name=policy_name,
        )
    except HTTPException as exc:
        _log_dev_api_rate_limit_failure(
            request=request,
            auth=auth,
            policy_name=policy_name,
            status_code=exc.status_code,
        )
        raise


async def _check_api_key_rate_limit_async(
    *,
    prefix: str,
    uid: str,
    app_id: Optional[str],
    key_id: Optional[str],
    policy_name: str,
) -> None:
    await run_blocking(
        critical_executor,
        check_api_key_rate_limit,
        prefix=prefix,
        uid=uid,
        app_id=app_id,
        key_id=key_id,
        policy_name=policy_name,
    )


async def _check_dev_api_key_rate_limit_async(
    *,
    request: Optional[Request],
    auth: ApiKeyAuth,
    policy_name: str,
) -> None:
    await run_blocking(
        critical_executor,
        _check_dev_api_key_rate_limit,
        request=request,
        auth=auth,
        policy_name=policy_name,
    )


def _require_conversations_read_scope(auth: ApiKeyAuth):
    if not has_scope(auth.scopes, Scopes.CONVERSATIONS_READ):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.CONVERSATIONS_READ}"
        )


async def get_auth_with_conversations_read(
    auth: ApiKeyAuth = Depends(get_api_key_auth),
    request: Request = None,
) -> ApiKeyAuth:
    _require_conversations_read_scope(auth)
    await _check_dev_api_key_rate_limit_async(request=request, auth=auth, policy_name="dev:conversations_read")
    return auth


async def get_auth_with_conversation_detail_read(
    auth: ApiKeyAuth = Depends(get_api_key_auth),
    request: Request = None,
) -> ApiKeyAuth:
    _require_conversations_read_scope(auth)
    await _check_dev_api_key_rate_limit_async(request=request, auth=auth, policy_name="dev:conversation_detail_read")
    return auth


async def get_uid_with_conversations_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    await get_auth_with_conversations_read(auth)
    return auth.uid


def check_conversation_transcript_read_limit(
    auth: ApiKeyAuth,
    request: Optional[Request] = None,
):
    _require_conversations_read_scope(auth)
    _check_dev_api_key_rate_limit(request=request, auth=auth, policy_name="dev:conversation_transcript_read")


async def get_auth_with_conversations_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> ApiKeyAuth:
    if not has_scope(auth.scopes, Scopes.CONVERSATIONS_WRITE):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.CONVERSATIONS_WRITE}"
        )
    await _check_api_key_rate_limit_async(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:conversations",
    )
    return auth


async def get_uid_with_conversations_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    await get_auth_with_conversations_write(auth)
    return auth.uid


async def get_auth_with_memories_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> ApiKeyAuth:
    if not has_scope(auth.scopes, Scopes.MEMORIES_READ):
        raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.MEMORIES_READ}")
    await _check_api_key_rate_limit_async(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:memories_read",
    )
    return auth


async def get_uid_with_memories_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    await get_auth_with_memories_read(auth)
    return auth.uid


async def get_auth_with_memories_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> ApiKeyAuth:
    if not has_scope(auth.scopes, Scopes.MEMORIES_WRITE):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.MEMORIES_WRITE}"
        )
    await _check_api_key_rate_limit_async(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:memories",
    )
    return auth


async def get_uid_with_memories_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    await get_auth_with_memories_write(auth)
    return auth.uid


async def get_auth_with_action_items_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> ApiKeyAuth:
    if not has_scope(auth.scopes, Scopes.ACTION_ITEMS_READ):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.ACTION_ITEMS_READ}"
        )
    await _check_api_key_rate_limit_async(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:action_items_read",
    )
    return auth


async def get_uid_with_action_items_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    await get_auth_with_action_items_read(auth)
    return auth.uid


async def get_auth_with_action_items_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> ApiKeyAuth:
    if not has_scope(auth.scopes, Scopes.ACTION_ITEMS_WRITE):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.ACTION_ITEMS_WRITE}"
        )
    await _check_api_key_rate_limit_async(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:action_items_write",
    )
    return auth


async def get_uid_with_action_items_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    await get_auth_with_action_items_write(auth)
    return auth.uid


async def get_auth_with_goals_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> ApiKeyAuth:
    if not has_scope(auth.scopes, Scopes.GOALS_READ):
        raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.GOALS_READ}")
    await _check_api_key_rate_limit_async(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:goals_read",
    )
    return auth


async def get_uid_with_goals_read(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    await get_auth_with_goals_read(auth)
    return auth.uid


async def get_auth_with_goals_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> ApiKeyAuth:
    if not has_scope(auth.scopes, Scopes.GOALS_WRITE):
        raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.GOALS_WRITE}")
    await _check_api_key_rate_limit_async(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:goals_write",
    )
    return auth


async def get_uid_with_goals_write(auth: ApiKeyAuth = Depends(get_api_key_auth)) -> str:
    await get_auth_with_goals_write(auth)
    return auth.uid


DEVELOPER_TO_MEMORY_SCOPES = {
    Scopes.MEMORIES_READ: 'memories.read',
    Scopes.MEMORIES_WRITE: 'memories.write',
}


def _memory_memory_scopes_from_developer_scopes(scopes: Optional[List[str]]) -> tuple[str, ...]:
    return tuple(
        memory_scope
        for developer_scope, memory_scope in DEVELOPER_TO_MEMORY_SCOPES.items()
        if has_scope(scopes, developer_scope)
    )


async def get_developer_memory_default_memory_read_context(
    auth: ApiKeyAuth = Depends(get_api_key_auth),
) -> ProductAuthorizationContext:
    if not has_scope(auth.scopes, Scopes.MEMORIES_READ):
        raise HTTPException(status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.MEMORIES_READ}")
    if not auth.app_id or not auth.key_id:
        raise HTTPException(
            status_code=403, detail="Missing Developer API app/key identity for memory memory authorization"
        )
    await _check_api_key_rate_limit_async(
        prefix="dev",
        uid=auth.uid,
        app_id=auth.app_id,
        key_id=auth.key_id,
        policy_name="dev:memories_read",
    )
    return ProductAuthorizationContext(
        uid=auth.uid,
        consumer='developer_api',
        surface='developer_default_memory_read',
        app_id=auth.app_id,
        key_id=auth.key_id,
        scopes=_memory_memory_scopes_from_developer_scopes(auth.scopes),
    )


def get_developer_memory_default_memory_write_auth_context(
    auth: ApiKeyAuth = Depends(get_api_key_auth),
) -> ProductAuthorizationContext:
    if not has_scope(auth.scopes, Scopes.MEMORIES_WRITE):
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions. Required scope: {Scopes.MEMORIES_WRITE}"
        )
    if not auth.app_id or not auth.key_id:
        raise HTTPException(
            status_code=403, detail="Missing Developer API app/key identity for memory memory authorization"
        )
    return ProductAuthorizationContext(
        uid=auth.uid,
        consumer='developer_api',
        surface='developer_default_memory_write',
        app_id=auth.app_id,
        key_id=auth.key_id,
        scopes=_memory_memory_scopes_from_developer_scopes(auth.scopes),
    )


async def get_developer_memory_default_memory_write_context(
    auth_context: ProductAuthorizationContext = Depends(get_developer_memory_default_memory_write_auth_context),
) -> ProductAuthorizationContext:
    await _check_api_key_rate_limit_async(
        prefix="dev",
        uid=auth_context.uid,
        app_id=auth_context.app_id,
        key_id=auth_context.key_id,
        policy_name="dev:memories",
    )
    return auth_context


async def get_developer_memory_default_memory_batch_write_context(
    auth_context: ProductAuthorizationContext = Depends(get_developer_memory_default_memory_write_auth_context),
) -> ProductAuthorizationContext:
    await _check_api_key_rate_limit_async(
        prefix="dev",
        uid=auth_context.uid,
        app_id=auth_context.app_id,
        key_id=auth_context.key_id,
        policy_name="dev:memories_batch",
    )
    return auth_context

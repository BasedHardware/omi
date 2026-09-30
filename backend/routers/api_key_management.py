"""Dependency-light HTTP boundary for MCP and Developer API-key lifecycle."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException

import database.dev_api_key as dev_api_key_db
import database.mcp_api_key as mcp_api_key_db
from database.api_key_metadata import ApiKeyRevocationUnavailableError, ApiKeyValidationError
from dependencies import get_current_user_id
from models.dev_api_key import DevApiKey, DevApiKeyCreate, DevApiKeyCreated
from models.mcp_api_key import McpApiKey, McpApiKeyCreate, McpApiKeyCreated
from utils.dev_cache import invalidate_developer_cache
from utils.observability.api_keys import record_api_key_repairs, record_api_key_revocation_exhausted
from utils.scopes import AVAILABLE_SCOPES, validate_scopes

logger = logging.getLogger(__name__)

mcp_router = APIRouter()
developer_router = APIRouter()


def _sanitize_api_key_error(exc: Exception, fallback: str) -> str:
    """Sanitize internal API key management exception details while preserving debug logging."""
    logger.warning("API key operation failed: %s: %s", type(exc).__name__, exc)
    return fallback


@mcp_router.get(
    "/v1/mcp/keys",
    response_model=List[McpApiKey],
    tags=["mcp"],
    summary="Get Keys",
    operation_id="get_keys_v1_mcp_keys_get",
)
def get_mcp_keys(uid: str = Depends(get_current_user_id)):
    keys, repairs = mcp_api_key_db.get_mcp_keys_for_user_with_repair_info(uid)
    record_api_key_repairs(key_kind="mcp", operation="list", repairs=repairs, log=logger)
    return keys


@mcp_router.post(
    "/v1/mcp/keys",
    response_model=McpApiKeyCreated,
    tags=["mcp"],
    summary="Create Key",
    operation_id="create_key_v1_mcp_keys_post",
)
def create_mcp_key(key_data: McpApiKeyCreate, uid: str = Depends(get_current_user_id)):
    if not key_data.name or len(key_data.name.strip()) == 0:
        raise HTTPException(status_code=422, detail="Key name cannot be empty")

    try:
        raw_key, api_key_data = mcp_api_key_db.create_mcp_key(uid, key_data.name.strip())
    except ApiKeyValidationError as exc:
        message = str(exc)
        if "raw API key" in message:
            detail = _sanitize_api_key_error(exc, "API key name must not contain a raw API key")
        elif "app_id" in message:
            detail = _sanitize_api_key_error(exc, "Invalid MCP API key app_id")
        else:
            detail = _sanitize_api_key_error(exc, "Invalid API key parameters")
        raise HTTPException(status_code=422, detail=detail) from exc
    except Exception as exc:
        detail = _sanitize_api_key_error(exc, "Failed to create API key")
        raise HTTPException(status_code=500, detail=detail) from exc
    return McpApiKeyCreated(**api_key_data.model_dump(), key=raw_key)


@mcp_router.delete(
    "/v1/mcp/keys/{key_id}",
    status_code=204,
    tags=["mcp"],
    summary="Delete Key",
    operation_id="delete_key_v1_mcp_keys__key_id__delete",
)
def delete_mcp_key(key_id: str, uid: str = Depends(get_current_user_id)):
    try:
        mcp_api_key_db.delete_mcp_key(uid, key_id)
    except ApiKeyRevocationUnavailableError as exc:
        record_api_key_revocation_exhausted(key_kind="mcp", log=logger)
        raise HTTPException(status_code=503, detail="API key revocation temporarily unavailable") from exc
    return


@developer_router.get(
    "/v1/dev/keys",
    response_model=List[DevApiKey],
    tags=["API Keys"],
    summary="Get Keys",
    operation_id="listApiKeys",
)
def get_developer_keys(uid: str = Depends(get_current_user_id)):
    keys, repairs = dev_api_key_db.get_dev_keys_for_user_with_repair_info(uid)
    record_api_key_repairs(key_kind="dev", operation="list", repairs=repairs, log=logger)
    return keys


@developer_router.post(
    "/v1/dev/keys",
    response_model=DevApiKeyCreated,
    tags=["API Keys"],
    summary="Create Key",
    operation_id="createApiKey",
)
def create_developer_key(key_data: DevApiKeyCreate, uid: str = Depends(get_current_user_id)):
    """
    Create a new Developer API key with optional scopes.

    - **name**: Descriptive name for the key
    - **scopes**: Optional list of scopes. If not provided, defaults to read-only access.
      Available scopes:
      - conversations:read
      - conversations:write
      - memories:read
      - memories:write
      - action_items:read
      - action_items:write
      - goals:read
      - goals:write
    """
    if not key_data.name or len(key_data.name.strip()) == 0:
        raise HTTPException(status_code=422, detail="Key name cannot be empty")

    if key_data.scopes is not None and not validate_scopes(key_data.scopes):
        raise HTTPException(status_code=400, detail=f"Invalid scopes. Available: {AVAILABLE_SCOPES}")

    try:
        raw_key, api_key_data = dev_api_key_db.create_dev_key(uid, key_data.name.strip(), scopes=key_data.scopes)
    except ApiKeyValidationError as exc:
        message = str(exc)
        if "raw API key" in message:
            detail = _sanitize_api_key_error(exc, "API key name must not contain a raw API key")
        else:
            detail = _sanitize_api_key_error(exc, "Invalid API key parameters")
        raise HTTPException(status_code=422, detail=detail) from exc
    except Exception as exc:
        detail = _sanitize_api_key_error(exc, "Failed to create API key")
        raise HTTPException(status_code=500, detail=detail) from exc
    # Developer status changes affect proactive-notification limits immediately.
    invalidate_developer_cache(uid)
    return DevApiKeyCreated(**api_key_data.model_dump(), key=raw_key)


@developer_router.delete(
    "/v1/dev/keys/{key_id}",
    status_code=204,
    tags=["API Keys"],
    summary="Delete Key",
    operation_id="revokeApiKey",
)
def delete_developer_key(key_id: str, uid: str = Depends(get_current_user_id)):
    try:
        dev_api_key_db.delete_dev_key(uid, key_id)
    except ApiKeyRevocationUnavailableError as exc:
        record_api_key_revocation_exhausted(key_kind="dev", log=logger)
        raise HTTPException(status_code=503, detail="API key revocation temporarily unavailable") from exc
    invalidate_developer_cache(uid)
    return


__all__ = [
    "_sanitize_api_key_error",
    "create_developer_key",
    "create_mcp_key",
    "delete_developer_key",
    "delete_mcp_key",
    "developer_router",
    "get_developer_keys",
    "get_mcp_keys",
    "mcp_router",
]

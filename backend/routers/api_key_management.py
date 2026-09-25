from fastapi import HTTPException, status
from fastapi.security import APIKeyHeader
from pydantic import ValidationError
from typing import Optional

from backend.utils.log_sanitizer import sanitize
from backend.models.api_key_models import ApiKeyValidationError
from backend.services.api_key_service import create_mcp_key, create_developer_key
from backend.core.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def create_mcp_key_endpoint(api_key: str = Depends(api_key_header)):
    try:
        return await create_mcp_key(api_key)
    except ApiKeyValidationError as e:
        sanitized_error = sanitize(str(e))
        logger.warning(f"MCP Key Validation Failed: {sanitized_error}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": sanitized_error}
        )

async def create_developer_key_endpoint(api_key: str = Depends(api_key_header)):
    try:
        return await create_developer_key(api_key)
    except ApiKeyValidationError as e:
        sanitized_error = sanitize(str(e))
        logger.warning(f"Developer Key Validation Failed: {sanitized_error}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": sanitized_error}
        )

```python
# backend/routers/memories.py

from fastapi import HTTPException, status
from typing import Union
from core.exceptions import DeviceScopeValidationError
from core.utils import logger

def _sanitize_memories_error(exc: Exception, fallback: str) -> str:
    """Sanitize and log errors from the memories router."""
    logger.warning(f"Memory error: {exc}")
    return fallback

async def _resolve_get_memories_device_scope(device_scope: str) -> str:
    try:
        return DeviceScope(device_scope).value
    except DeviceScopeValidationError as exc:
        return _sanitize_memories_error(exc, "device_scope must be one of: all, current, explicit")

async def get_memories(
    memory_type: str,
    device_scope: str,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    try:
        # Existing logic...
        return {"result": "success"}
    except ValueError as exc:
        return _sanitize_memories_error(exc, "unsupported memory read view")

# backend/tests/unit/test_memories_error_sanitization.py

from unittest.mock import patch, call
from fastapi import HTTPException
from core.exceptions import DeviceScopeValidationError
from backend.routers.memories import _sanitize_memories_error, _resolve_get_memories_device_scope, get_memories
import logging

def test_sanitize_memories_error():
    with patch.object(logger, "warning") as mock_logger:
        result = _sanitize_memories_error(ValueError("test"), "fallback")
        assert result == "fallback"
        assert mock_logger.assert_called_once_with("Memory error: test")

def test_get_memories_error_handling():
    with patch.object(logger, "warning") as mock_logger:
        try:
            _resolve_get_memories_device_scope("invalid_scope")
        except ValueError as e:
            assert str(e) == "fallback"
        assert mock_logger.assert_called_once_with("Memory error: DeviceScopeValidationError: invalid_scope")
```
"""Unit tests for MCP router category exception detail sanitization.

Verifies that invalid category strings passed to get_memories and get_conversations
return sanitized error details without leaking Python enum class names or internal reprs.
"""

from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

import routers.mcp as mcp_routes


def test_get_memories_invalid_category_is_sanitized():
    """Ensure invalid memory category returns static detail without enum names."""
    leak_category = "malicious_injection_category_xyz"
    mock_auth = MagicMock(uid="test-uid-123")
    with pytest.raises(HTTPException) as exc_info:
        mcp_routes.get_memories(categories=leak_category, auth_context=mock_auth)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid memory category. Please provide valid category names."
    assert "MemoryCategory" not in exc_info.value.detail
    assert leak_category not in exc_info.value.detail


def test_get_conversations_invalid_category_is_sanitized():
    """Ensure invalid conversation category returns static detail without enum names."""
    leak_category = "internal_enum_probe_category_123"
    with pytest.raises(HTTPException) as exc_info:
        mcp_routes.get_conversations(categories=leak_category, uid="test-uid-123")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid conversation category. Please provide valid category names."
    assert "CategoryEnum" not in exc_info.value.detail
    assert leak_category not in exc_info.value.detail

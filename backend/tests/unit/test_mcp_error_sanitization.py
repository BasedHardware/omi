"""CWE-209: MCP category ValueError exception details must not leak to clients.

Covers issue #18780:
  - backend/routers/mcp.py (get_memories — GET /v1/mcp/memories)
  - backend/routers/mcp.py (get_conversations — GET /v1/mcp/conversations)

The fix pattern (mirroring backend/routers/developer.py:395-396 and 1515-1516):
  - Client-facing HTTPException detail is a clean, standardized message:
    "Invalid category. Please provide a valid category."
  - Server-side logger.error records structured error_class without leaking raw
    Python enum representation or unescaped strings back to MCP clients.
  - Production handlers are directly invoked to verify behaviour under invalid inputs.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Response

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

from routers.mcp import get_conversations, get_memories

MCP_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "mcp.py"


def _source() -> str:
    return MCP_SOURCE.read_text(encoding="utf-8")


def test_no_raw_enum_error_leaked_into_category_response_detail():
    source = _source()
    # `detail=f"Invalid category {str(e)}"` leaks raw Enum ValueError representation
    # (e.g. `'bad' is not a valid MemoryCategory`) and unescaped input to clients.
    assert 'detail=f"Invalid category {str(e)}"' not in source
    assert "Invalid category {str(e)}" not in source


def test_mcp_category_handlers_use_standardized_detail_and_logger():
    source = _source()
    assert 'detail="Invalid category. Please provide a valid category."' in source
    assert "Invalid category in MCP memories: {type(e).__name__}" in source
    assert "Invalid category in MCP conversations: {type(e).__name__}" in source


def test_get_memories_production_handler_raises_sanitized_error():
    mock_auth = MagicMock()
    mock_auth.uid = "test_uid"
    resp = Response()

    with patch("routers.mcp.logger.error") as mock_log:
        with pytest.raises(HTTPException) as exc_info:
            get_memories(response=resp, auth_context=mock_auth, categories="invalid_category_123")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid category. Please provide a valid category."
        assert "invalid_category_123" not in exc_info.value.detail
        mock_log.assert_called_once_with("Invalid category in MCP memories: ValueError")


def test_get_conversations_production_handler_raises_sanitized_error():
    resp = Response()

    with patch("routers.mcp.logger.error") as mock_log:
        with pytest.raises(HTTPException) as exc_info:
            get_conversations(response=resp, uid="test_uid", categories="invalid_category_123")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid category. Please provide a valid category."
        assert "invalid_category_123" not in exc_info.value.detail
        mock_log.assert_called_once_with("Invalid category in MCP conversations: ValueError")

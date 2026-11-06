"""CWE-209: MCP category ValueError exception details must not leak to clients.

Covers issue #18780:
  - backend/routers/mcp.py (get_memories — GET /v1/mcp/memories)
  - backend/routers/mcp.py (get_conversations — GET /v1/mcp/conversations)

The fix pattern (mirroring backend/routers/developer.py:395-396 and 1515-1516):
  - Client-facing HTTPException detail is a clean, standardized message:
    "Invalid category. Please provide a valid category."
  - Server-side logger.error records structured error_class without leaking raw
    Python enum representation or unescaped strings back to MCP clients.
"""

from pathlib import Path

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
    assert 'Invalid category in MCP memories: {type(e).__name__}' in source
    assert 'Invalid category in MCP conversations: {type(e).__name__}' in source

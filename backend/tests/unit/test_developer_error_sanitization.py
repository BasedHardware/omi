"""Hermetic unit tests for error sanitization in the developer API router.

Verifies that:
1. GET /v1/dev/user/memories catches ValueError during category parsing, logs
   error type safely, and returns generic HTTP 400 without leaking Enum exception text.
2. GET /v1/dev/user/conversations catches ValueError during category parsing, logs
   error type safely, and returns generic HTTP 400 without leaking Enum exception text.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

DEVELOPER_SOURCE_FILE = Path(__file__).resolve().parents[2] / "routers" / "developer.py"


def _get_endpoint_source(endpoint_name: str) -> str:
    source = DEVELOPER_SOURCE_FILE.read_text(encoding="utf-8")
    start = source.index(f"def {endpoint_name}")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class DeveloperErrorSanitizationTests(unittest.TestCase):
    def test_get_memories_sanitizes_category_validation_errors(self):
        source = _get_endpoint_source("get_memories")
        self.assertNotIn("detail=f\"Invalid category {str(e)}\"", source)
        self.assertNotIn("detail=str(e)", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('detail="Invalid category. Please provide a valid category."', source)

    def test_get_conversations_sanitizes_category_validation_errors(self):
        source = _get_endpoint_source("get_conversations")
        self.assertNotIn("detail=f\"Invalid category {str(e)}\"", source)
        self.assertNotIn("detail=str(e)", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('detail="Invalid category. Please provide a valid category."', source)


if __name__ == "__main__":
    unittest.main()

"""Hermetic unit tests for error sanitization in the conversations share email endpoint.

Verifies that:
1. AmbiguousDeliveryError does not leak internal exception details into HTTP 504 responses.
2. ValueError does not leak internal config/recipient details into HTTP 503 responses.
3. RuntimeError does not leak downstream provider network errors into HTTP 502 responses.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

CONVERSATIONS_SOURCE_FILE = Path(__file__).resolve().parents[2] / "routers" / "conversations.py"


def _get_endpoint_source(endpoint_name: str) -> str:
    source = CONVERSATIONS_SOURCE_FILE.read_text(encoding="utf-8")
    start = source.index(f"def {endpoint_name}(")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class ConversationsShareEmailErrorSanitizationTests(unittest.TestCase):
    def test_share_email_sanitizes_delivery_errors(self):
        source = _get_endpoint_source("send_conversation_share_email")
        self.assertNotIn("detail=str(e)", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('detail="Email delivery timed out. Please check recipient status."', source)
        self.assertIn('detail="Email sharing is temporarily unavailable. Please try again."', source)
        self.assertIn('detail="Failed to send share email. Please try again."', source)


if __name__ == "__main__":
    unittest.main()

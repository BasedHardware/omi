"""Hermetic unit tests for error sanitization in the conversations share email endpoint.

Verifies that:
1. AmbiguousDeliveryError does not leak internal exception details into HTTP 504 responses.
2. ValueError does not leak internal config/recipient details into HTTP 503 responses.
3. RuntimeError does not leak downstream provider network errors into HTTP 502 responses.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
from types import ModuleType
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "01234567890123456789012345678901")

# Ensure required modules are stubbed for hermetic standalone execution
firebase_admin = sys.modules.get("firebase_admin") or ModuleType("firebase_admin")
firebase_admin.__path__ = []
firebase_admin_auth = sys.modules.get("firebase_admin.auth") or ModuleType("firebase_admin.auth")
for exc_name in ["CertificateFetchError", "ExpiredIdTokenError", "InvalidIdTokenError", "RevokedIdTokenError"]:
    if not hasattr(firebase_admin_auth, exc_name):
        setattr(firebase_admin_auth, exc_name, type(exc_name, (Exception,), {}))
sys.modules["firebase_admin"] = firebase_admin
sys.modules["firebase_admin.auth"] = firebase_admin_auth
sys.modules.setdefault("cachetools", MagicMock())
prom = sys.modules.get("prometheus_client")
if prom is None or not hasattr(prom, "start_http_server"):
    sys.modules["prometheus_client"] = MagicMock()

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
        self.assertIn('detail="Email delivery timed out. Please try again."', source)
        self.assertIn('detail="Email sharing is temporarily unavailable. Please try again."', source)
        self.assertIn('detail="Failed to send share email. Please try again."', source)

    def test_share_email_source_line_count_ratchet_declared(self):
        lines = CONVERSATIONS_SOURCE_FILE.read_text(encoding="utf-8").splitlines()
        # Verify the file size is tracked
        self.assertLessEqual(len(lines), 2155)


if __name__ == "__main__":
    unittest.main()

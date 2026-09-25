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
from unittest.mock import MagicMock

CONVERSATIONS_SOURCE_FILE = Path(__file__).resolve().parents[2] / "routers" / "conversations.py"


def _get_endpoint_source(endpoint_name: str) -> str:
    source = CONVERSATIONS_SOURCE_FILE.read_text(encoding="utf-8")
    start = source.index(f"def {endpoint_name}(")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class ConversationsShareEmailErrorSanitizationTests(unittest.TestCase):
    _stubbed_modules: dict = {}

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("ENCRYPTION_SECRET", "01234567890123456789012345678901")

        firebase_admin = sys.modules.get("firebase_admin") or ModuleType("firebase_admin")
        firebase_admin.__path__ = []
        firebase_admin_auth = sys.modules.get("firebase_admin.auth") or ModuleType("firebase_admin.auth")
        for exc_name in ["CertificateFetchError", "ExpiredIdTokenError", "InvalidIdTokenError", "RevokedIdTokenError"]:
            if not hasattr(firebase_admin_auth, exc_name):
                setattr(firebase_admin_auth, exc_name, type(exc_name, (Exception,), {}))

        stubs = {
            "firebase_admin": firebase_admin,
            "firebase_admin.auth": firebase_admin_auth,
            "cachetools": MagicMock(),
            "prometheus_client": MagicMock(),
        }

        for name, mod in stubs.items():
            if name not in sys.modules:
                cls._stubbed_modules[name] = mod
                sys.modules[name] = mod

    @classmethod
    def tearDownClass(cls):
        for name in cls._stubbed_modules:
            sys.modules.pop(name, None)

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

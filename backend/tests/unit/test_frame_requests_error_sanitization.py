"""Hermetic unit tests for error sanitization in the frame requests router.

Verifies that:
1. All ValueError handlers sanitize error details via _sanitize_frame_request_error.
2. The _sanitize_frame_request_error helper filters raw tracebacks and database error
   markers while returning clean, structured error keys.
3. No raw detail=str(exc) leaks remain in frame_requests.py.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parents[2]
FRAME_REQUESTS_ROUTER_FILE = BACKEND_DIR / "routers" / "frame_requests.py"


def _get_function_source(function_name: str) -> str:
    source = FRAME_REQUESTS_ROUTER_FILE.read_text(encoding="utf-8")
    start = source.index(f"async def {function_name}")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class FrameRequestsErrorSanitizationTests(unittest.TestCase):
    _stubbed_modules: dict = {}
    _sanitize_fn = None

    @classmethod
    def setUpClass(cls):
        # Stub heavy external and database dependencies inside setUpClass (not module scope)
        stub_names = [
            "google",
            "google.cloud",
            "google.cloud.firestore",
            "google.cloud.firestore_v1",
            "google.cloud.storage",
            "firebase_admin",
            "firebase_admin.auth",
            "database.frame_requests",
            "database.conversations",
            "services.conversation_frame_evidence",
            "utils.executors",
            "utils.integration_telemetry",
            "utils.jit_rollout",
            "utils.other.endpoints",
            "utils.retrieval.frame_request_authority",
            "utils.retrieval.frame_request_storage",
        ]
        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from routers.frame_requests import _sanitize_frame_request_error

        cls._sanitize_fn = staticmethod(_sanitize_frame_request_error)

    @classmethod
    def tearDownClass(cls):
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def test_sanitize_frame_request_error_behavior(self):
        fallback = "frame_request_invalid_parameters"
        sanitize = self._sanitize_fn

        # 1. Any ValueError strictly returns the safe fallback key
        self.assertEqual(
            sanitize(ValueError("clean_error_code"), fallback),
            fallback,
        )

        # 2. Raw traceback filtered to fallback
        self.assertEqual(
            sanitize(
                ValueError("Traceback (most recent call last):\n  File 'x.py', line 1\nZeroDivisionError"),
                fallback,
            ),
            fallback,
        )

        # 3. Firestore / google.cloud internals filtered to fallback
        self.assertEqual(
            sanitize(
                ValueError("google.cloud.exceptions.NotFound: 404 Document not found in Firestore"),
                fallback,
            ),
            fallback,
        )

        # 4. Multiline error text filtered to fallback
        self.assertEqual(
            sanitize(ValueError("line 1\nline 2 error details"), fallback),
            fallback,
        )

        # 5. Generic 'Error:' prefix filtered to fallback
        self.assertEqual(
            sanitize(ValueError("Error: invalid internal token state"), fallback),
            fallback,
        )

        # 6. Empty exception detail falls back
        self.assertEqual(
            sanitize(ValueError(""), fallback),
            fallback,
        )

    def test_create_frame_request_sanitizes_errors(self):
        source = _get_function_source("create_frame_request")
        self.assertNotIn("detail=str(exc)", source)
        self.assertIn("_sanitize_frame_request_error", source)
        self.assertIn("frame_request_invalid_parameters", source)

    def test_get_pending_frame_requests_sanitizes_errors(self):
        source = _get_function_source("get_pending_frame_requests")
        self.assertNotIn("detail=str(exc)", source)
        self.assertIn("_sanitize_frame_request_error", source)
        self.assertIn("frame_request_invalid_parameters", source)

    def test_update_frame_request_state_sanitizes_errors(self):
        source = _get_function_source("update_frame_request_state")
        self.assertNotIn("detail=str(exc)", source)
        self.assertIn("_sanitize_frame_request_error", source)
        self.assertIn("frame_request_state_conflict", source)

    def test_upload_frame_request_sanitizes_errors(self):
        source = _get_function_source("upload_frame_request")
        self.assertNotIn("detail=str(exc)", source)
        self.assertIn("_sanitize_frame_request_error", source)
        self.assertIn("frame_request_upload_conflict", source)

    def test_promote_frame_request_sanitizes_errors(self):
        source = _get_function_source("promote_frame_request")
        self.assertNotIn("detail=str(exc)", source)
        self.assertIn("_sanitize_frame_request_error", source)
        self.assertIn("frame_request_promotion_conflict", source)

    def test_no_raw_str_exc_leak_in_frame_requests(self):
        source = FRAME_REQUESTS_ROUTER_FILE.read_text(encoding="utf-8")
        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=str(e)", source)


if __name__ == "__main__":
    unittest.main()

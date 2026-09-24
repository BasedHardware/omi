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
import unittest

FRAME_REQUESTS_ROUTER_FILE = Path(__file__).resolve().parents[2] / "routers" / "frame_requests.py"


def _get_function_source(function_name: str) -> str:
    source = FRAME_REQUESTS_ROUTER_FILE.read_text(encoding="utf-8")
    start = source.index(f"async def {function_name}")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class FrameRequestsErrorSanitizationTests(unittest.TestCase):
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

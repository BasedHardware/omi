"""Hermetic error-handling regression suite for plugins/import/manual-import.

Verifies that:
1. Unexpected internal exceptions never leak sensitive file paths, credentials,
   or traceback details into the HTTP 500 response.
2. Upstream provider HTTP errors are sanitized to HTTP status indicators
   rather than reflecting raw upstream HTML bodies, gateway headers, or socket traces.
3. Missing parameter validations return expected 400 responses.
4. No except block in app.py reflects raw exception text into responses.
"""

from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

# Mock openai client during import if needed
with patch("openai.OpenAI"):
    from app import app

SECRET_TRACE = "/srv/secrets/credentials_manual_import.json"
LEAK_MARKERS = (SECRET_TRACE, "RuntimeError", "Traceback", "Exception")


class ManualImportErrorHandlingTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_missing_user_id_returns_400(self):
        response = self.client.post(
            "/submit-memories",
            data=json.dumps({"memories": ["Remember to pick up milk."]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("No user ID provided", data["error"])

    def test_missing_memories_content_returns_400(self):
        response = self.client.post(
            "/submit-memories",
            data=json.dumps({"uid": "test-user-123", "memories": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("No content provided", data["error"])

    def test_unexpected_exception_returns_sanitized_500(self):
        with patch("app.extract_memories_consolidated", side_effect=RuntimeError(SECRET_TRACE)):
            response = self.client.post(
                "/submit-memories",
                data=json.dumps({
                    "uid": "test-user-123",
                    "memories": ["This is a test memory paragraph exceeding fifty characters for consolidation."],
                    "use_ai": False,
                }),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 500)
            data = response.get_json()
            self.assertFalse(data["success"])
            self.assertEqual(data["error"], "Internal error processing memories. Please try again.")
            for marker in LEAK_MARKERS:
                self.assertNotIn(marker, json.dumps(data))

    def test_upstream_http_failure_sanitizes_error_text(self):
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.text = f"<html><body>502 Bad Gateway: {SECRET_TRACE}</body></html>"

        with patch("requests.post", return_value=mock_response):
            response = self.client.post(
                "/submit-memories",
                data=json.dumps({
                    "uid": "test-user-123",
                    "memories": ["This is a test memory paragraph exceeding fifty characters for consolidation."],
                    "use_ai": False,
                }),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertFalse(data["success"])
            self.assertEqual(len(data["results"]), 1)
            self.assertEqual(data["results"][0]["error"], "HTTP 502")
            self.assertNotIn("<html>", data["results"][0]["error"])
            for marker in LEAK_MARKERS:
                self.assertNotIn(marker, json.dumps(data))

    def test_no_except_block_interpolates_raw_exception(self):
        source = (APP_DIR / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        offenders = []
        for handler in ast.walk(tree):
            if not isinstance(handler, ast.ExceptHandler):
                continue
            for stmt in ast.walk(handler):
                if isinstance(stmt, ast.Return):
                    segment = ast.get_source_segment(source, stmt) or ""
                    if re.search(r"str\((e|exc)\)|\{(e|exc)\}", segment):
                        offenders.append(stmt.lineno)
        self.assertEqual(offenders, [], f"raw exception interpolated in return at lines {offenders}")


if __name__ == "__main__":
    unittest.main()

"""Hermetic error-handling regression suite for plugins/import/manual-import.

Standard library only: flask, requests, openai, httpx, and dotenv are stubbed
before loading app.py so the suite runs under plain python3 (the manifest lane).

Run: python3 plugins/import/manual-import/test_error_handling.py
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

APP_DIR = Path(__file__).resolve().parent

# 1. Stub external dependencies hermetically
_flask = types.ModuleType("flask")


class _FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def get_json(self):
        return self._data

    @property
    def data(self):
        return json.dumps(self._data).encode("utf-8")


def _fake_jsonify(data):
    return _FakeResponse(data)


_fake_request = MagicMock()
_fake_app = MagicMock()
_fake_app.route = lambda *args, **kwargs: lambda fn: fn

_flask.Flask = MagicMock(return_value=_fake_app)
_flask.request = _fake_request
_flask.jsonify = _fake_jsonify
_flask.send_from_directory = MagicMock()

_requests = types.ModuleType("requests")
_requests.post = MagicMock()
_requests.get = MagicMock()

_openai = types.ModuleType("openai")
_openai.OpenAI = MagicMock()
_openai.api_key = None

_httpx = types.ModuleType("httpx")
_httpx.Client = MagicMock()
_httpx.Limits = MagicMock()
_httpx.Timeout = MagicMock()

_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *args, **kwargs: None

# 2. Bind stubs and import app module
with patch.dict(
    sys.modules,
    {
        "flask": _flask,
        "requests": _requests,
        "openai": _openai,
        "httpx": _httpx,
        "dotenv": _dotenv,
    },
):
    spec = importlib.util.spec_from_file_location("manual_import_app", APP_DIR / "app.py")
    app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_module)

SECRET_TRACE = "/srv/secrets/credentials_manual_import.json"
LEAK_MARKERS = (SECRET_TRACE, "RuntimeError", "Traceback", "Exception")


class ManualImportErrorHandlingTests(unittest.TestCase):
    def _call_submit_memories(self, payload: dict) -> _FakeResponse:
        _fake_request.json = payload
        _fake_request.get_json = MagicMock(return_value=payload)
        res = app_module.submit_memories()
        if isinstance(res, tuple):
            resp, status_code = res
            resp.status_code = status_code
            return resp
        return res

    def test_missing_user_id_returns_400(self):
        response = self._call_submit_memories({"memories": ["Remember to pick up milk."]})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("No user ID provided", data["error"])

    def test_missing_memories_content_returns_400(self):
        response = self._call_submit_memories({"uid": "test-user-123", "memories": []})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("No content provided", data["error"])

    def test_unexpected_exception_returns_sanitized_500(self):
        with patch.object(app_module, "extract_memories_consolidated", side_effect=RuntimeError(SECRET_TRACE)):
            response = self._call_submit_memories(
                {
                    "uid": "test-user-123",
                    "memories": ["This is a test memory paragraph exceeding fifty characters for consolidation."],
                    "use_ai": False,
                }
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

        with patch.object(app_module.requests, "post", return_value=mock_response):
            response = self._call_submit_memories(
                {
                    "uid": "test-user-123",
                    "memories": ["This is a test memory paragraph exceeding fifty characters for consolidation."],
                    "use_ai": False,
                }
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

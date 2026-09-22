"""Hermetic unit tests for IQ Rating error handling and sanitization.

Verifies that internal exceptions and potential HTML/XSS injection strings
are never rendered into the GET /iq dashboard HTML error responses.

Runs hermetically under standard library python3 -S.
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Lightweight stubs for hermetic stdlib-only execution
if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class APIRouter:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

            def on_event(self, *args, **kwargs):
                return lambda f: f

        class Query:
            def __init__(self, *args, **kwargs):
                pass

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def include_router(self, *args, **kwargs):
                pass

        class HTTPException(Exception):
            def __init__(self, status_code=500, detail=""):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        fastapi.APIRouter = APIRouter
        fastapi.FastAPI = FastAPI
        fastapi.Query = Query
        fastapi.HTTPException = HTTPException
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content="", status_code=200):
                self.content = content
                self.status_code = status_code
                self.body = content

        class JSONResponse:
            def __init__(self, content=None, status_code=200):
                self.content = content
                self.status_code = status_code

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses
else:
    # Ensure HTMLResponse stores content if fastapi is mocked or real
    import fastapi.responses
    if not hasattr(fastapi.responses.HTMLResponse, "__init__") or fastapi.responses.HTMLResponse.__init__ is object.__init__:
        class HTMLResponse:
            def __init__(self, content="", status_code=200):
                self.content = content
                self.status_code = status_code
                self.body = content
        fastapi.responses.HTMLResponse = HTMLResponse

if "requests" not in sys.modules:
    try:
        import requests  # type: ignore
    except ImportError:
        requests = types.ModuleType("requests")
        requests.post = lambda *args, **kwargs: None
        requests.get = lambda *args, **kwargs: None
        sys.modules["requests"] = requests

_PLUGIN_DIR = Path(__file__).resolve().parent
_MAIN_PATH = _PLUGIN_DIR / "main.py"

_spec = importlib.util.spec_from_file_location("iq_rating_main", _MAIN_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Cannot load {_MAIN_PATH}")
main = importlib.util.module_from_spec(_spec)
sys.modules["iq_rating_main"] = main
_spec.loader.exec_module(main)


class IQRatingErrorHandlingTests(unittest.TestCase):
    """Verify that exception text and XSS payloads never leak into HTML responses."""

    def test_iq_rating_page_does_not_leak_internal_paths_or_db_errors(self):
        secret_path = "/var/secrets/sqlite/master.db"
        leak_msg = f"OperationalError: database locked at {secret_path}"

        with patch.object(main, "get_people_for_user", side_effect=RuntimeError(leak_msg)):
            response = asyncio.run(main.iq_rating_page(uid="test_user_123"))

            self.assertIn("An unexpected error occurred while loading IQ ratings.", response.content)
            self.assertNotIn(secret_path, response.content)
            self.assertNotIn("OperationalError", response.content)
            self.assertNotIn(leak_msg, response.content)

    def test_iq_rating_page_does_not_render_xss_in_exception(self):
        xss_payload = "<script>alert('xss')</script><img src=x onerror=alert(1)>"

        with patch.object(main, "get_people_for_user", side_effect=ValueError(xss_payload)):
            response = asyncio.run(main.iq_rating_page(uid="test_user_xss"))

            self.assertIn("An unexpected error occurred while loading IQ ratings.", response.content)
            self.assertNotIn("<script>", response.content)
            self.assertNotIn("alert('xss')", response.content)
            self.assertNotIn("<img src=x", response.content)
            self.assertNotIn(xss_payload, response.content)

    def test_iq_rating_page_logs_exception_server_side_with_exc_info(self):
        with patch.object(main.logger, "error") as mock_logger_error:
            with patch.object(main, "get_people_for_user", side_effect=RuntimeError("internal crash")):
                response = asyncio.run(main.iq_rating_page(uid="test_user_log"))

                self.assertIn("An unexpected error occurred while loading IQ ratings.", response.content)
                self.assertTrue(mock_logger_error.called)
                call_args, call_kwargs = mock_logger_error.call_args
                self.assertTrue(call_kwargs.get("exc_info", False))


if __name__ == "__main__":
    unittest.main()

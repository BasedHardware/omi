"""Hermetic tests for error sanitization in Stack Overflow app.

Verifies that internal exception details (IPs, hostnames, proxy details, tracebacks)
are never leaked in ChatToolResponse.error.
"""

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

# Lightweight stubs for hermetic stdlib-only execution
if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            def __init__(self, message, request=None, response=None):
                super().__init__(message)
                self.request = request
                self.response = response

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                self.is_closed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def aclose(self):
                self.is_closed = True

            async def get(self, *args, **kwargs):
                pass

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
        httpx.AsyncClient = AsyncClient
        sys.modules["httpx"] = httpx

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

        fastapi.FastAPI = FastAPI
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content):
                self.body = content.encode("utf-8") if isinstance(content, str) else content

        responses.HTMLResponse = HTMLResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

        pydantic.BaseModel = BaseModel
        sys.modules["pydantic"] = pydantic

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

if "main" in sys.modules:
    del sys.modules["main"]
import main  # noqa: E402


class TestStackOverflowErrorSanitization(unittest.TestCase):
    def test_search_questions_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=main.httpx.HTTPError("proxy 10.0.0.1:8080 reset")):
                res = await main.search_questions({"query": "python async"})
                self.assertEqual("Stack Exchange search failed due to a network error.", res.error)
                self.assertNotIn("10.0.0.1", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_search_questions_unexpected_exception_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=RuntimeError("internal stack secret crash")):
                res = await main.search_questions({"query": "python async"})
                self.assertEqual("Stack Exchange search failed.", res.error)
                self.assertNotIn("internal stack secret crash", res.error)
                self.assertNotIn("RuntimeError", res.error)

        asyncio.run(_run())

    def test_get_question_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=main.httpx.HTTPError("connect timeout to 192.168.1.1")):
                res = await main.get_question({"question_id": 12345})
                self.assertEqual("Stack Exchange question request failed due to a network error.", res.error)
                self.assertNotIn("192.168.1.1", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_get_question_unexpected_exception_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=KeyError("secret_database_column")):
                res = await main.get_question({"question_id": 12345})
                self.assertEqual("Stack Exchange question request failed.", res.error)
                self.assertNotIn("secret_database_column", res.error)
                self.assertNotIn("KeyError", res.error)

        asyncio.run(_run())

    def test_get_top_answers_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=main.httpx.HTTPError("ssl handshake fail to 172.16.0.1")):
                res = await main.get_top_answers({"question_id": 12345})
                self.assertEqual("Stack Exchange answers request failed due to a network error.", res.error)
                self.assertNotIn("172.16.0.1", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_get_top_answers_unexpected_exception_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=TypeError("unhandled answer type crash")):
                res = await main.get_top_answers({"question_id": 12345})
                self.assertEqual("Stack Exchange answers request failed.", res.error)
                self.assertNotIn("unhandled answer type crash", res.error)
                self.assertNotIn("TypeError", res.error)

        asyncio.run(_run())



    def test_search_questions_value_error_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=ValueError("internal parse secret 10.9.8.7")):
                res = await main.search_questions({"query": "python async"})
                self.assertNotIn("10.9.8.7", res.error)
                self.assertNotIn("internal parse secret", res.error)
                self.assertIn("Stack Exchange search failed", res.error)

        asyncio.run(_run())

    def test_get_question_value_error_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=ValueError("bad payload hostname evil.internal")):
                res = await main.get_question({"question_id": 12345})
                self.assertNotIn("evil.internal", res.error)
                self.assertNotIn("bad payload", res.error)
                self.assertIn("Stack Exchange question request failed", res.error)

        asyncio.run(_run())

    def test_get_top_answers_value_error_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=ValueError("decode failure secret_token_xyz")):
                res = await main.get_top_answers({"question_id": 12345})
                self.assertNotIn("secret_token_xyz", res.error)
                self.assertNotIn("decode failure", res.error)
                self.assertIn("Stack Exchange answers request failed", res.error)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()

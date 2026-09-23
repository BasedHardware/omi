"""Hermetic tests for error sanitization in Public Holidays app.

Verifies that internal exception details (IPs, hostnames, proxy details, tracebacks)
are never leaked in ChatToolResponse.error.
"""

import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

PLUGIN_DIR = Path(__file__).resolve().parent

# Lightweight stubs for hermetic stdlib-only execution
if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            pass

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                self.is_closed = False

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
        import fastapi.exceptions  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.state = types.SimpleNamespace()

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

            def exception_handler(self, *args, **kwargs):
                return lambda f: f

        class Request:
            pass

        fastapi.FastAPI = FastAPI
        fastapi.Request = Request
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            pass

        class JSONResponse:
            def __init__(self, content=None, status_code=200, **kwargs):
                self.content = content
                self.status_code = status_code

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

        exceptions = types.ModuleType("fastapi.exceptions")

        class RequestValidationError(Exception):
            def __init__(self, errors=None):
                self._errors = errors or []

            def errors(self):
                return self._errors

        exceptions.RequestValidationError = RequestValidationError
        sys.modules["fastapi.exceptions"] = exceptions
        fastapi.exceptions = exceptions

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        def Field(default=None, **kwargs):
            return default

        def field_validator(*args, **kwargs):
            return lambda f: f

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

            @classmethod
            def model_validate(cls, data):
                if isinstance(data, dict):
                    return cls(**{k: v for k, v in data.items() if v is not None})
                return cls()

            def model_dump(self):
                return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        pydantic.field_validator = field_validator
        sys.modules["pydantic"] = pydantic

if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

if "main" in sys.modules:
    del sys.modules["main"]
import main  # noqa: E402


class TestPublicHolidaysErrorSanitization(unittest.TestCase):
    def test_get_public_holidays_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=main.httpx.HTTPError("internal proxy 10.1.2.3:8080 timeout")):
                req = main.HolidayRequest(country_code="US", year=2026)
                res = await main.get_public_holidays(req)
                self.assertEqual("holiday lookup failed due to a network error.", res.error)
                self.assertNotIn("10.1.2.3", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_get_public_holidays_unexpected_exception_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=RuntimeError("critical database secret error")):
                req = main.HolidayRequest(country_code="US", year=2026)
                res = await main.get_public_holidays(req)
                self.assertEqual("holiday lookup failed.", res.error)
                self.assertNotIn("critical database secret", res.error)
                self.assertNotIn("RuntimeError", res.error)

        asyncio.run(_run())

    def test_get_next_public_holidays_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=main.httpx.HTTPError("upstream nager dns resolution failure 192.168.1.1")):
                req = main.NextHolidayRequest(country_code="US")
                res = await main.get_next_public_holidays(req)
                self.assertEqual("upcoming holiday lookup failed due to a network error.", res.error)
                self.assertNotIn("192.168.1.1", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_get_next_public_holidays_unexpected_exception_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=RuntimeError("unexpected parsing crash")):
                req = main.NextHolidayRequest(country_code="US")
                res = await main.get_next_public_holidays(req)
                self.assertEqual("upcoming holiday lookup failed.", res.error)
                self.assertNotIn("unexpected parsing crash", res.error)
                self.assertNotIn("RuntimeError", res.error)

        asyncio.run(_run())

    def test_get_long_weekends_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=main.httpx.HTTPError("ssl handshake failure to upstream 172.16.0.5")):
                req = main.LongWeekendRequest(country_code="US", year=2026)
                res = await main.get_long_weekends(req)
                self.assertEqual("long-weekend lookup failed due to a network error.", res.error)
                self.assertNotIn("172.16.0.5", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_get_long_weekends_unexpected_exception_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=RuntimeError("internal weekend calculation bug")):
                req = main.LongWeekendRequest(country_code="US", year=2026)
                res = await main.get_long_weekends(req)
                self.assertEqual("long-weekend lookup failed.", res.error)
                self.assertNotIn("internal weekend calculation bug", res.error)
                self.assertNotIn("RuntimeError", res.error)

        asyncio.run(_run())

    def test_list_supported_countries_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=main.httpx.HTTPError("gateway timeout on 10.0.0.1")):
                res = await main.list_supported_countries()
                self.assertEqual("country list request failed due to a network error.", res.error)
                self.assertNotIn("10.0.0.1", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_list_supported_countries_unexpected_exception_sanitized(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=RuntimeError("internal country list crash")):
                res = await main.list_supported_countries()
                self.assertEqual("country list request failed.", res.error)
                self.assertNotIn("internal country list crash", res.error)
                self.assertNotIn("RuntimeError", res.error)

        asyncio.run(_run())



def _http_status_error(status_code: int, body: str = "internal error 500") -> Exception:
    """Build an HTTPStatusError with .response.status_code for handler tests."""
    err = main.httpx.HTTPStatusError(f"status {status_code}: {body}")
    err.response = types.SimpleNamespace(status_code=status_code)
    return err


class TestPublicHolidaysHTTPStatusError(unittest.TestCase):
    """Lock the HTTPStatusError branches that previously leaked / mis-built status lines."""

    def test_get_public_holidays_http_status_error_includes_status_code(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=_http_status_error(503, "upstream 10.0.0.9 unavailable")):
                req = main.HolidayRequest(country_code="US", year=2026)
                res = await main.get_public_holidays(req)
                self.assertIn("status 503", res.error)
                self.assertIn("holiday lookup failed", res.error)
                self.assertNotIn("10.0.0.9", res.error)
                self.assertNotIn("upstream", res.error)
                self.assertNotIn("HTTPStatusError", res.error)
                self.assertNotIn("{exc", res.error)

        asyncio.run(_run())

    def test_get_next_public_holidays_http_status_error_includes_status_code(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=_http_status_error(429, "nager rate limit")):
                req = main.NextHolidayRequest(country_code="US")
                res = await main.get_next_public_holidays(req)
                self.assertIn("status 429", res.error)
                self.assertIn("upcoming holiday lookup failed", res.error)
                self.assertNotIn("nager", res.error)
                self.assertNotIn("HTTPStatusError", res.error)

        asyncio.run(_run())

    def test_get_long_weekends_http_status_error_includes_status_code(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=_http_status_error(500, "proxy 192.168.1.50")):
                req = main.LongWeekendRequest(country_code="US", year=2026)
                res = await main.get_long_weekends(req)
                self.assertIn("status 500", res.error)
                self.assertIn("long-weekend lookup failed", res.error)
                self.assertNotIn("192.168.1.50", res.error)
                self.assertNotIn("HTTPStatusError", res.error)

        asyncio.run(_run())

    def test_list_supported_countries_http_status_error_includes_status_code(self):
        async def _run():
            with patch.object(main, "_request_json", side_effect=_http_status_error(404, "country endpoint missing")):
                res = await main.list_supported_countries()
                self.assertIn("status 404", res.error)
                self.assertIn("country list request failed", res.error)
                self.assertNotIn("country endpoint missing", res.error)
                self.assertNotIn("HTTPStatusError", res.error)

        asyncio.run(_run())



if __name__ == "__main__":
    unittest.main()

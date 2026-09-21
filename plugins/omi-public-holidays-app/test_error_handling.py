"""Hermetic error handling and exception sanitization tests for Public Holidays App.

Verifies that internal exceptions, system paths, network addresses, and raw
tracebacks never leak into chat tool responses.
Runs under standard library unittest without external network dependencies.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))


class Framework:
    def __init__(self, content="", status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code
        self.kwargs = kwargs
        self.state = types.SimpleNamespace()

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get

    def exception_handler(self, *args, **kwargs):
        return lambda function: function


class ChatToolResponseStub:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def model_dump(self):
        return {"result": self.result, "error": self.error}


def make_module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


def load_holidays_module():
    class HTTPError(Exception):
        pass

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def get(self, *args, **kwargs):
            raise AssertionError("tests must stub the HTTP response")

    httpx_mod = make_module("httpx", HTTPError=HTTPError, AsyncClient=AsyncClient)

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class HolidayRequest(BaseModel):
        country_code: str = "US"
        year: int = 2026
        limit: int = 20

    class NextHolidayRequest(BaseModel):
        country_code: str = "US"
        limit: int = 8

    class LongWeekendRequest(BaseModel):
        country_code: str = "US"
        year: int = 2026
        limit: int = 20

    pydantic_mod = make_module(
        "pydantic",
        BaseModel=BaseModel,
        Field=lambda default=None, **kw: default,
        field_validator=lambda *args, **kwargs: (lambda f: f),
    )

    stubs = {
        "httpx": httpx_mod,
        "fastapi": make_module(
            "fastapi",
            FastAPI=Framework,
            Request=Framework,
        ),
        "fastapi.exceptions": make_module(
            "fastapi.exceptions",
            RequestValidationError=Exception,
        ),
        "fastapi.responses": make_module(
            "fastapi.responses",
            HTMLResponse=Framework,
            JSONResponse=Framework,
        ),
        "pydantic": pydantic_mod,
    }

    spec = importlib.util.spec_from_file_location(
        "holidays_main_test", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_holidays_module()


class PublicHolidaysErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/nager_key.json: connection reset by 192.168.1.88:443"

    async def test_get_public_holidays_sanitizes_exception(self):
        req = app.HolidayRequest(country_code="US", year=2026, limit=10)
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_public_holidays(req)
            self.assertEqual(resp.error, "holiday lookup failed")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.88", str(resp.error))

    async def test_get_next_public_holidays_sanitizes_exception(self):
        req = app.NextHolidayRequest(country_code="US", limit=5)
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_next_public_holidays(req)
            self.assertEqual(resp.error, "upcoming holiday lookup failed")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.88", str(resp.error))

    async def test_get_long_weekends_sanitizes_exception(self):
        req = app.LongWeekendRequest(country_code="US", year=2026, limit=10)
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_long_weekends(req)
            self.assertEqual(resp.error, "long-weekend lookup failed")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.88", str(resp.error))

    async def test_list_supported_countries_sanitizes_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.list_supported_countries()
            self.assertEqual(resp.error, "country list request failed")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.88", str(resp.error))


if __name__ == "__main__":
    unittest.main()

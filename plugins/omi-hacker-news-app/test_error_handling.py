"""Hermetic error handling and exception sanitization tests for Hacker News App.

Verifies that internal exceptions, system paths, private IPs, sensitive tokens,
and raw tracebacks never leak into chat tool responses.
Runs under standard library unittest without external network dependencies.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class ChatToolResponseStub:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error


def make_module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


def load_hn_module():
    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", request=None, response=None):
            super().__init__(message)
            self.response = response or types.SimpleNamespace(status_code=500)

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def get(self, *args, **kwargs):
            raise AssertionError("tests must stub the HTTP response")

        async def aclose(self):
            self.is_closed = True

    httpx_mod = make_module(
        "httpx",
        HTTPError=HTTPError,
        HTTPStatusError=HTTPStatusError,
        AsyncClient=AsyncClient,
    )

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    pydantic_mod = make_module("pydantic", BaseModel=BaseModel)

    stubs = {
        "httpx": httpx_mod,
        "fastapi": make_module(
            "fastapi",
            FastAPI=Framework,
            Body=lambda *args, **kwargs: None,
        ),
        "fastapi.responses": make_module(
            "fastapi.responses",
            HTMLResponse=Framework,
        ),
        "pydantic": pydantic_mod,
    }

    spec = importlib.util.spec_from_file_location(
        "hn_main_test", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_hn_module()


class HackerNewsErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/algolia_master_key.json: connection reset by 192.168.1.99:8080"

    async def test_get_front_page_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_front_page({})
            self.assertEqual(resp.error, "Hacker News request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.99", str(resp.error))

    async def test_get_front_page_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.get_front_page({})
            self.assertEqual(resp.error, "Hacker News request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_front_page_reports_clean_status_code(self):
        fake_response = types.SimpleNamespace(status_code=503)
        exc = app.httpx.HTTPStatusError("Service Unavailable", response=fake_response)
        with patch.object(app, "_request_json", side_effect=exc):
            resp = await app.get_front_page({})
            self.assertEqual(resp.error, "Hacker News request failed with status 503.")

    async def test_search_stories_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.search_stories({"query": "python"})
            self.assertEqual(resp.error, "Hacker News search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.99", str(resp.error))

    async def test_search_stories_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.search_stories({"query": "python"})
            self.assertEqual(resp.error, "Hacker News search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_search_stories_reports_clean_status_code(self):
        fake_response = types.SimpleNamespace(status_code=502)
        exc = app.httpx.HTTPStatusError("Bad Gateway", response=fake_response)
        with patch.object(app, "_request_json", side_effect=exc):
            resp = await app.search_stories({"query": "python"})
            self.assertEqual(resp.error, "Hacker News search failed with status 502.")

    async def test_get_discussion_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_discussion({"item_id": 12345})
            self.assertEqual(resp.error, "Hacker News discussion request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.99", str(resp.error))

    async def test_get_discussion_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.get_discussion({"item_id": 12345})
            self.assertEqual(resp.error, "Hacker News discussion request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_discussion_reports_clean_status_code(self):
        fake_response = types.SimpleNamespace(status_code=504)
        exc = app.httpx.HTTPStatusError("Gateway Timeout", response=fake_response)
        with patch.object(app, "_request_json", side_effect=exc):
            resp = await app.get_discussion({"item_id": 12345})
            self.assertEqual(resp.error, "Hacker News discussion request failed with status 504.")


if __name__ == "__main__":
    unittest.main()

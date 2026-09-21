"""Hermetic error handling and exception sanitization tests for Stack Overflow App.

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


def load_so_module():
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
        ),
        "fastapi.responses": make_module(
            "fastapi.responses",
            HTMLResponse=Framework,
        ),
        "pydantic": pydantic_mod,
    }

    spec = importlib.util.spec_from_file_location(
        "so_main_test", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_so_module()


class StackOverflowErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/stack_key.json: connection reset by 192.168.1.66:443"

    async def test_search_questions_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.search_questions({"query": "python"})
            self.assertEqual(resp.error, "Stack Exchange search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.66", str(resp.error))

    async def test_search_questions_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.search_questions({"query": "python"})
            self.assertEqual(resp.error, "Stack Exchange search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_question_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_question({"question_id": 12345})
            self.assertEqual(resp.error, "Stack Exchange question request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.66", str(resp.error))

    async def test_get_question_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.get_question({"question_id": 12345})
            self.assertEqual(resp.error, "Stack Exchange question request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_top_answers_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_top_answers({"question_id": 12345})
            self.assertEqual(resp.error, "Stack Exchange answers request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.66", str(resp.error))

    async def test_get_top_answers_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.get_top_answers({"question_id": 12345})
            self.assertEqual(resp.error, "Stack Exchange answers request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))


if __name__ == "__main__":
    unittest.main()

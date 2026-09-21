"""Hermetic error handling and exception sanitization tests for Open Library App.

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


class BaseModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class ChatToolResponse(BaseModel):
    def __init__(self, result=None, error=None, **kwargs):
        super().__init__(result=result, error=error, **kwargs)


def make_module(name, **attributes):
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


def load_openlibrary_module():
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
            raise AssertionError("stub get")

        async def aclose(self):
            self.is_closed = True

    httpx_mod = make_module(
        "httpx",
        HTTPError=HTTPError,
        HTTPStatusError=HTTPStatusError,
        AsyncClient=AsyncClient,
    )

    stubs = {
        "httpx": httpx_mod,
        "fastapi": make_module("fastapi", FastAPI=Framework),
        "fastapi.responses": make_module("fastapi.responses", HTMLResponse=Framework),
        "pydantic": make_module("pydantic", BaseModel=BaseModel),
    }

    for k, v in stubs.items():
        sys.modules.setdefault(k, v)

    spec = importlib.util.spec_from_file_location(
        "openlibrary_main_test", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_openlibrary_module()


class OpenLibraryErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/ol_token.json: connection reset by 192.168.1.77:443"

    async def test_search_books_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.search_books({"query": "Dune"})
            self.assertEqual(resp.error, "Open Library search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.77", str(resp.error))

    async def test_search_books_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.search_books({"query": "Dune"})
            self.assertEqual(resp.error, "Open Library search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_book_details_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_book_details({"work_id": "OL45883W"})
            self.assertEqual(resp.error, "Open Library details request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.77", str(resp.error))

    async def test_get_book_details_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.get_book_details({"work_id": "OL45883W"})
            self.assertEqual(resp.error, "Open Library details request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_search_subject_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.search_subject({"subject": "science_fiction"})
            self.assertEqual(resp.error, "Open Library subject search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.77", str(resp.error))

    async def test_search_subject_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.search_subject({"subject": "science_fiction"})
            self.assertEqual(resp.error, "Open Library subject search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))


if __name__ == "__main__":
    unittest.main()

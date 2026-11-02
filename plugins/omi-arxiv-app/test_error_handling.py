"""Hermetic error handling and exception sanitization tests for arXiv App.

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
from unittest.mock import patch, AsyncMock


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get

    def exception_handler(self, *args, **kwargs):
        return lambda function: function


class Model:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def model_dump(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class HTTPError(Exception):
    pass


class HTTPStatusError(HTTPError):
    def __init__(self, message="", response=None):
        super().__init__(message)
        self.response = response or types.SimpleNamespace(status_code=500)


def make_module(name, **attributes):
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


def load_arxiv_module():
    fastapi_responses = make_module(
        "fastapi.responses",
        HTMLResponse=lambda *a, **k: None,
        JSONResponse=lambda *a, **k: None,
    )
    fastapi_exceptions = make_module(
        "fastapi.exceptions",
        RequestValidationError=Exception,
    )
    stubs = {
        "fastapi": make_module(
            "fastapi",
            FastAPI=Framework,
            Request=object,
            responses=fastapi_responses,
            exceptions=fastapi_exceptions,
        ),
        "fastapi.responses": fastapi_responses,
        "fastapi.exceptions": fastapi_exceptions,
        "httpx": make_module(
            "httpx",
            AsyncClient=object,
            HTTPError=HTTPError,
            HTTPStatusError=HTTPStatusError,
        ),
        "pydantic": make_module(
            "pydantic",
            BaseModel=Model,
            Field=lambda default=None, **k: default,
        ),
    }
    spec = importlib.util.spec_from_file_location("arxiv_error_test", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_arxiv_module()


class ArxivErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/tokens.json: connection reset by 192.168.1.55:443"

    async def test_search_papers_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_arxiv", new=AsyncMock(side_effect=RuntimeError(self.sensitive_leak))):
            resp = await app.search_papers({"query": "deep learning"})
            self.assertEqual(resp.error, "arXiv search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.55", str(resp.error))
            self.assertNotIn("secrets", str(resp.error))

    async def test_search_papers_sanitizes_network_http_error(self):
        with patch.object(app, "_request_arxiv", new=AsyncMock(side_effect=app.httpx.HTTPError(self.sensitive_leak))):
            resp = await app.search_papers({"query": "deep learning"})
            self.assertEqual(resp.error, "arXiv search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.55", str(resp.error))
            self.assertNotIn("secrets", str(resp.error))

    async def test_get_paper_details_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_arxiv", new=AsyncMock(side_effect=RuntimeError(self.sensitive_leak))):
            resp = await app.get_paper_details({"paper_id": "1706.03762"})
            self.assertEqual(resp.error, "arXiv details request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.55", str(resp.error))
            self.assertNotIn("secrets", str(resp.error))

    async def test_get_paper_details_sanitizes_network_http_error(self):
        with patch.object(app, "_request_arxiv", new=AsyncMock(side_effect=app.httpx.HTTPError(self.sensitive_leak))):
            resp = await app.get_paper_details({"paper_id": "1706.03762"})
            self.assertEqual(resp.error, "arXiv details request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.55", str(resp.error))
            self.assertNotIn("secrets", str(resp.error))

    async def test_search_author_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_arxiv", new=AsyncMock(side_effect=RuntimeError(self.sensitive_leak))):
            resp = await app.search_author({"author": "Vaswani"})
            self.assertEqual(resp.error, "arXiv author search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.55", str(resp.error))
            self.assertNotIn("secrets", str(resp.error))

    async def test_search_author_sanitizes_network_http_error(self):
        with patch.object(app, "_request_arxiv", new=AsyncMock(side_effect=app.httpx.HTTPError(self.sensitive_leak))):
            resp = await app.search_author({"author": "Vaswani"})
            self.assertEqual(resp.error, "arXiv author search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.55", str(resp.error))
            self.assertNotIn("secrets", str(resp.error))


if __name__ == "__main__":
    unittest.main()

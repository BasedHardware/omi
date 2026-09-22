"""Hermetic tests: arXiv chat tool endpoints must never leak raw exception text.

Loads the production module with framework-only stubs so no network, credentials,
or full FastAPI runtime is required.
"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch
import asyncio

# The test sentinel — a realistic internal error string that must never appear
# in any client-facing response.
_SENTINEL = "FATAL: /var/secrets/twitter_key.json: connection reset by 192.168.1.99:443"


def _load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            self._lifespan = kwargs.get("lifespan")

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

        def exception_handler(self, *args, **kwargs):
            return lambda handler: handler

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if v is not None}

    class HTTPError(Exception):
        pass

    class TimeoutException(HTTPError):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, *args, **kwargs):
            super().__init__(*args)
            self.response = type("R", (), {"status_code": 500})()

    httpx_mod = ModuleType("httpx")
    httpx_mod.AsyncClient = object
    httpx_mod.HTTPError = HTTPError
    httpx_mod.TimeoutException = TimeoutException
    httpx_mod.HTTPStatusError = HTTPStatusError

    fastapi_mod = ModuleType("fastapi")
    fastapi_mod.FastAPI = FastAPI
    fastapi_mod.Request = object
    fastapi_mod.Body = lambda *args, **kwargs: None

    responses_mod = ModuleType("fastapi.responses")
    responses_mod.HTMLResponse = str
    responses_mod.JSONResponse = dict

    exceptions_mod = ModuleType("fastapi.exceptions")
    exceptions_mod.RequestValidationError = Exception

    pydantic_mod = ModuleType("pydantic")
    pydantic_mod.BaseModel = BaseModel
    pydantic_mod.Field = lambda *a, **kw: None

    models_mod = ModuleType("models")
    models_mod.ChatToolResponse = type("ChatToolResponse", (BaseModel,), {})

    class _SearchPapersRequest(BaseModel):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.query = kwargs.get("query")
            self.title = kwargs.get("title")
            self.author = kwargs.get("author")
            self.category = kwargs.get("category")
            self.limit = kwargs.get("limit", 5)
            self.sort_by = kwargs.get("sort_by", "relevance")

    class _GetPaperDetailsRequest(BaseModel):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.paper_id = kwargs.get("paper_id")

    class _SearchAuthorRequest(BaseModel):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.author = kwargs.get("author")
            self.limit = kwargs.get("limit", 5)

    models_mod.SearchPapersRequest = _SearchPapersRequest
    models_mod.GetPaperDetailsRequest = _GetPaperDetailsRequest
    models_mod.SearchAuthorRequest = _SearchAuthorRequest

    spec = importlib.util.spec_from_file_location(
        "arxiv_app", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "httpx": httpx_mod,
            "fastapi": fastapi_mod,
            "fastapi.responses": responses_mod,
            "fastapi.exceptions": exceptions_mod,
            "pydantic": pydantic_mod,
            "models": models_mod,
        },
    ):
        spec.loader.exec_module(module)
    return module, httpx_mod


app, httpx_stub = _load_app()


def _assert_no_leak(test_case, text, context=""):
    """Verify the text does not contain the sentinel."""
    text = str(text)
    test_case.assertNotIn(_SENTINEL, text, f"Exception text leaked in {context}")
    test_case.assertNotIn("192.168.1.99", text, f"Internal IP leaked in {context}")
    test_case.assertNotIn("/var/secrets/", text, f"Internal path leaked in {context}")


class TestArxivErrorHandling(unittest.TestCase):
    """Verify arXiv chat tool endpoints return generic errors on failure."""

    def test_search_papers_network_error(self):
        """search_papers must return a generic error on httpx.HTTPError."""

        async def run():
            with patch.object(app, "_request_arxiv", new_callable=AsyncMock) as mock_req:
                mock_req.side_effect = httpx_stub.HTTPError(_SENTINEL)
                response = await app.search_papers({"query": "quantum computing"})
                self.assertIsNotNone(response.error)
                _assert_no_leak(self, response.error, "search_papers")
                self.assertIn("failed", response.error.lower())

        asyncio.run(run())

    def test_get_paper_details_network_error(self):
        """get_paper_details must return a generic error on httpx.HTTPError."""

        async def run():
            with patch.object(app, "_request_arxiv", new_callable=AsyncMock) as mock_req:
                mock_req.side_effect = httpx_stub.HTTPError(_SENTINEL)
                response = await app.get_paper_details({"paper_id": "2401.01234"})
                self.assertIsNotNone(response.error)
                _assert_no_leak(self, response.error, "get_paper_details")
                self.assertIn("failed", response.error.lower())

        asyncio.run(run())

    def test_search_author_network_error(self):
        """search_author must return a generic error on httpx.HTTPError."""

        async def run():
            with patch.object(app, "_request_arxiv", new_callable=AsyncMock) as mock_req:
                mock_req.side_effect = httpx_stub.HTTPError(_SENTINEL)
                response = await app.search_author({"author": "Einstein", "limit": 5})
                self.assertIsNotNone(response.error)
                _assert_no_leak(self, response.error, "search_author")
                self.assertIn("failed", response.error.lower())

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()

"""Hermetic tests: Hacker News chat tool endpoints must never leak raw exception text.

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

_SENTINEL = "FATAL: /var/secrets/twitter_key.json: connection reset by 192.168.1.99:443"


def _load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if v is not None}

    class HTTPError(Exception):
        pass

    httpx_mod = ModuleType("httpx")
    httpx_mod.AsyncClient = object
    httpx_mod.HTTPError = HTTPError

    fastapi_mod = ModuleType("fastapi")
    fastapi_mod.FastAPI = FastAPI
    fastapi_mod.Body = lambda *args, **kwargs: None

    responses_mod = ModuleType("fastapi.responses")
    responses_mod.HTMLResponse = str

    pydantic_mod = ModuleType("pydantic")
    pydantic_mod.BaseModel = BaseModel

    spec = importlib.util.spec_from_file_location(
        "hacker_news_app", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "httpx": httpx_mod,
            "fastapi": fastapi_mod,
            "fastapi.responses": responses_mod,
            "pydantic": pydantic_mod,
        },
    ):
        spec.loader.exec_module(module)
    return module, httpx_mod


app, httpx_stub = _load_app()


def _assert_no_leak(test_case, text, context=""):
    text = str(text)
    test_case.assertNotIn(_SENTINEL, text, f"Exception text leaked in {context}")
    test_case.assertNotIn("192.168.1.99", text, f"Internal IP leaked in {context}")
    test_case.assertNotIn("/var/secrets/", text, f"Internal path leaked in {context}")


class TestHackerNewsErrorHandling(unittest.TestCase):

    def test_get_front_page_network_error(self):
        async def run():
            with patch.object(app, "_request_json", new_callable=AsyncMock) as mock_req:
                mock_req.side_effect = httpx_stub.HTTPError(_SENTINEL)
                response = await app.get_front_page({"limit": 5})
                self.assertIsNotNone(response.error)
                _assert_no_leak(self, response.error, "get_front_page")
                self.assertIn("failed", response.error.lower())

        asyncio.run(run())

    def test_search_stories_network_error(self):
        async def run():
            with patch.object(app, "_request_json", new_callable=AsyncMock) as mock_req:
                mock_req.side_effect = httpx_stub.HTTPError(_SENTINEL)
                response = await app.search_stories({"query": "python"})
                self.assertIsNotNone(response.error)
                _assert_no_leak(self, response.error, "search_stories")
                self.assertIn("failed", response.error.lower())

        asyncio.run(run())

    def test_get_discussion_network_error(self):
        async def run():
            with patch.object(app, "_request_json", new_callable=AsyncMock) as mock_req:
                mock_req.side_effect = httpx_stub.HTTPError(_SENTINEL)
                response = await app.get_discussion({"item_id": 12345})
                self.assertIsNotNone(response.error)
                _assert_no_leak(self, response.error, "get_discussion")
                self.assertIn("failed", response.error.lower())

        asyncio.run(run())

    def test_get_front_page_generic_exception(self):
        async def run():
            with patch.object(app, "_request_json", new_callable=AsyncMock) as mock_req:
                mock_req.side_effect = RuntimeError(_SENTINEL)
                response = await app.get_front_page({"limit": 5})
                self.assertIsNotNone(response.error)
                _assert_no_leak(self, response.error, "get_front_page generic")
                self.assertIn("failed", response.error.lower())

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()

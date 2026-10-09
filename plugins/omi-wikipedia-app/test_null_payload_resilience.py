"""Hermetic tests for null nested payload resilience and client pooling in Wikipedia App.

Covers Issue #20994:
1. Chained lookups on null values in `_format_summary` (null `content_urls`, null `desktop`).
2. Chained lookups and malformed items in `search_articles` (null `query`, non-dict items in search).
3. Chained lookups and malformed items in `get_random_article` (null `query`, non-dict items in random).
4. Application client pooling via lifespan and `_get_wikipedia_client`.
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


class Model:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class HTTPError(Exception):
    pass


class HTTPStatusError(HTTPError):
    def __init__(self, message="", response=None):
        super().__init__(message)
        self.response = response


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        self.is_closed = False

    async def aclose(self):
        self.is_closed = True


fastapi_responses = types.ModuleType("fastapi.responses")
fastapi_responses.HTMLResponse = lambda *a, **k: None

stubs = {
    "fastapi": types.ModuleType("fastapi"),
    "fastapi.responses": fastapi_responses,
    "httpx": types.ModuleType("httpx"),
    "pydantic": types.ModuleType("pydantic"),
}
stubs["fastapi"].FastAPI = Framework
stubs["fastapi"].responses = fastapi_responses
stubs["httpx"].AsyncClient = DummyAsyncClient
stubs["httpx"].HTTPError = HTTPError
stubs["httpx"].HTTPStatusError = HTTPStatusError
stubs["pydantic"].BaseModel = Model

spec = importlib.util.spec_from_file_location(
    "wikipedia_resilience_test", Path(__file__).with_name("main.py")
)
app = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(app)


class WikipediaNullPayloadResilienceTests(unittest.IsolatedAsyncioTestCase):
    def test_format_summary_with_null_content_urls(self):
        data = {
            "title": "Quantum Computing",
            "extract": "Quantum computing is a rapidly-emerging technology.",
            "content_urls": None,
        }
        summary = app._format_summary(data, "en")
        self.assertIn("Quantum Computing", summary)
        self.assertIn("https://en.wikipedia.org/wiki/Quantum_Computing", summary)

    def test_format_summary_with_null_desktop_urls(self):
        data = {
            "title": "Quantum Computing",
            "extract": "Quantum computing is a rapidly-emerging technology.",
            "content_urls": {"desktop": None},
        }
        summary = app._format_summary(data, "en")
        self.assertIn("Quantum Computing", summary)
        self.assertIn("https://en.wikipedia.org/wiki/Quantum_Computing", summary)

    def test_format_summary_with_valid_desktop_page_url(self):
        data = {
            "title": "Quantum Computing",
            "extract": "Quantum computing is a rapidly-emerging technology.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Custom_URL"}},
        }
        summary = app._format_summary(data, "en")
        self.assertIn("https://en.wikipedia.org/wiki/Custom_URL", summary)

    async def test_search_articles_handles_null_query_object(self):
        with patch.object(app, "_request_json", return_value={"query": None}):
            resp = await app.search_articles({"query": "Ada Lovelace"})
            self.assertEqual(resp.result, "No Wikipedia articles found for 'Ada Lovelace'.")
            self.assertIsNone(resp.error)

    async def test_search_articles_filters_corrupted_non_dict_items(self):
        payload_with_bad_items = {
            "query": {
                "search": [
                    "corrupted_string_item",
                    42,
                    {"title": "Valid Article", "snippet": "A valid article snippet."},
                ]
            }
        }
        with patch.object(app, "_request_json", return_value=payload_with_bad_items):
            resp = await app.search_articles({"query": "Ada Lovelace"})
            self.assertIsNone(resp.error)
            self.assertIn("Valid Article", resp.result)
            self.assertIn("A valid article snippet.", resp.result)

    async def test_get_random_article_handles_null_query_object(self):
        with patch.object(app, "_request_json", return_value={"query": None}):
            resp = await app.get_random_article({})
            self.assertEqual(resp.result, "No random Wikipedia article was returned.")
            self.assertIsNone(resp.error)

    async def test_get_random_article_handles_non_dict_random_items(self):
        with patch.object(app, "_request_json", return_value={"query": {"random": ["invalid_item"]}}):
            resp = await app.get_random_article({})
            self.assertEqual(resp.result, "No random Wikipedia article was returned.")
            self.assertIsNone(resp.error)

    async def test_client_pooling_reuses_single_instance(self):
        client1 = await app._get_wikipedia_client()
        client2 = await app._get_wikipedia_client()
        self.assertIs(client1, client2)

    async def test_lifespan_manages_client_lifecycle(self):
        async with app.lifespan(app.app):
            client = await app._get_wikipedia_client()
            self.assertFalse(client.is_closed)
        self.assertTrue(client.is_closed)


if __name__ == "__main__":
    unittest.main()

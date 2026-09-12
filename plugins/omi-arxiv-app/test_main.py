"""Hermetic arXiv search_query encoding regressions.

Import the production module with framework-only stubs, then exercise the
query builder and chat-tool handlers. No network, credentials, or
third-party runtime packages are required.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch
from urllib.parse import urlencode


def load_app():
    class DummyFastAPI:
        def __init__(self, **_kwargs):
            self.routes = []

        def get(self, path, **_kwargs):
            return self._route("GET", path)

        def post(self, path, **_kwargs):
            return self._route("POST", path)

        def _route(self, method, path):
            def decorator(func):
                self.routes.append((method, path, func))
                return func

            return decorator

    class DummyBaseModel:
        def __init__(self, **kwargs):
            self.result = None
            self.error = None
            for key, value in kwargs.items():
                setattr(self, key, value)

    class DummyHTMLResponse:
        def __init__(self, content, **_kwargs):
            self.content = content

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = DummyHTMLResponse
    fastapi.responses = responses
    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel
    httpx = ModuleType("httpx")
    httpx.HTTPError = Exception
    httpx.HTTPStatusError = type("HTTPStatusError", (Exception,), {})
    httpx.AsyncClient = object

    spec = importlib.util.spec_from_file_location(
        "arxiv_app", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "httpx": httpx,
            "fastapi": fastapi,
            "fastapi.responses": responses,
            "pydantic": pydantic,
        },
    ):
        spec.loader.exec_module(module)
    return module


app = load_app()


ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234</id>
    <title>Attention Is All You Need</title>
    <published>2024-01-01T00:00:00Z</published>
    <updated>2024-01-02T00:00:00Z</updated>
    <summary>A transformer paper.</summary>
    <author><name>Ada Lovelace</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
"""


class ArxivSearchQueryEncodingTest(unittest.TestCase):
    def test_multi_word_query_is_not_prequoted(self):
        query = app._build_search_query({"query": "machine learning"})
        self.assertEqual(query, "all:machine learning")
        encoded = urlencode({"search_query": query})
        self.assertIn("machine+learning", encoded)
        self.assertNotIn("%2B", encoded)

    def test_field_join_uses_boolean_and_with_spaces(self):
        query = app._build_search_query(
            {"query": "transformer", "title": "attention", "author": "Vaswani"}
        )
        self.assertEqual(
            query, "all:transformer AND ti:attention AND au:Vaswani"
        )
        encoded = urlencode({"search_query": query})
        self.assertIn("+AND+", encoded)
        self.assertNotIn("%2BAND%2B", encoded)

    def test_quoted_phrase_is_not_percent_encoded_twice(self):
        query = app._build_search_query({"query": '"quantum criticality"'})
        self.assertEqual(query, 'all:"quantum criticality"')
        encoded = urlencode({"search_query": query})
        self.assertIn("%22quantum+criticality%22", encoded)
        self.assertNotIn("%2522", encoded)

    def test_search_papers_passes_unencoded_query_to_arxiv(self):
        captured = {}

        async def fake_request(params):
            captured.update(params)
            return ATOM_FEED

        with patch.object(app, "_request_arxiv", fake_request):
            result = asyncio.run(
                app.search_papers({"query": "machine learning", "title": "attention"})
            )
        self.assertIsNone(result.error)
        self.assertEqual(
            captured["search_query"],
            "all:machine learning AND ti:attention",
        )
        self.assertIn("Attention Is All You Need", result.result)

    def test_search_author_passes_unencoded_author_name(self):
        captured = {}

        async def fake_request(params):
            captured.update(params)
            return ATOM_FEED

        with patch.object(app, "_request_arxiv", fake_request):
            result = asyncio.run(app.search_author({"author": "Yann LeCun"}))
        self.assertIsNone(result.error)
        self.assertEqual(captured["search_query"], "au:Yann LeCun")
        encoded = urlencode({"search_query": captured["search_query"]})
        self.assertIn("Yann+LeCun", encoded)
        self.assertNotIn("%2B", encoded)


if __name__ == "__main__":
    unittest.main()

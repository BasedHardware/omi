import asyncio
import sys
import types
import unittest
from urllib.parse import urlencode


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
        for key, value in kwargs.items():
            setattr(self, key, value)


def install_dependency_stubs():
    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    sys.modules.setdefault("fastapi", fastapi)

    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = lambda *args, **kwargs: None
    sys.modules.setdefault("fastapi.responses", fastapi_responses)
    fastapi.responses = fastapi_responses

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel
    sys.modules.setdefault("pydantic", pydantic)

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = Exception
    httpx.HTTPStatusError = type("HTTPStatusError", (Exception,), {})
    httpx.AsyncClient = object
    sys.modules.setdefault("httpx", httpx)


install_dependency_stubs()
import main

ATOM_NO_ENTRIES = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>"""


class ArxivSearchQueryTest(unittest.TestCase):
    def test_build_search_query_leaves_a_single_space_unencoded(self):
        # Regression for #13574: main.py must hand httpx a raw, unencoded
        # query string. httpx's own params encoding turns each space into
        # a literal "+" exactly once. Pre-encoding here (the old
        # quote_plus behavior) made httpx encode that "+" a second time
        # into "%2B", which arXiv does not treat as AND/space.
        query = main._build_search_query({"query": "machine learning"})
        self.assertEqual(query, "all:machine learning")

        wire_form = urlencode({"search_query": query})
        self.assertEqual(wire_form, "search_query=all%3Amachine+learning")
        self.assertNotIn("%2B", wire_form)

    def test_build_search_query_joins_multiple_fields_with_and(self):
        query = main._build_search_query({"title": "transformer", "author": "smith"})
        self.assertEqual(query, "ti:transformer AND au:smith")

        wire_form = urlencode({"search_query": query})
        self.assertEqual(wire_form, "search_query=ti%3Atransformer+AND+au%3Asmith")
        self.assertNotIn("%2B", wire_form)

    def test_build_search_query_single_token_is_unaffected(self):
        query = main._build_search_query({"query": "transformer"})
        self.assertEqual(query, "all:transformer")

    def test_search_papers_sends_unencoded_query_to_request_layer(self):
        captured_params = {}

        async def fake_request_arxiv(params):
            captured_params.update(params)
            return ATOM_NO_ENTRIES

        original = main._request_arxiv
        main._request_arxiv = fake_request_arxiv
        try:
            result = asyncio.run(main.search_papers({"query": "machine learning"}))
        finally:
            main._request_arxiv = original

        self.assertIsNone(result.error)
        self.assertEqual(captured_params["search_query"], "all:machine learning")

    def test_search_author_sends_unencoded_author_query(self):
        captured_params = {}

        async def fake_request_arxiv(params):
            captured_params.update(params)
            return ATOM_NO_ENTRIES

        original = main._request_arxiv
        main._request_arxiv = fake_request_arxiv
        try:
            result = asyncio.run(main.search_author({"author": "Yoshua Bengio"}))
        finally:
            main._request_arxiv = original

        self.assertIsNone(result.error)
        self.assertEqual(captured_params["search_query"], "au:Yoshua Bengio")


if __name__ == "__main__":
    unittest.main()

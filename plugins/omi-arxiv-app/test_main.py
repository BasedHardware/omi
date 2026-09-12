"""Hermetic arXiv search-encoding regressions.

Imports the production module with framework-only stubs, then exercises the
real `_build_search_query` and the real `search_papers`/`search_author`
handlers while capturing the params dict handed to the HTTP layer. The wire
shape is modeled with `urllib.parse.urlencode`, which is what httpx applies to
`params=` (space -> `+`, `:` -> `%3A`). No network, credentials, or third-party
runtime packages are required.
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
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        pass

    httpx = ModuleType("httpx")
    httpx.AsyncClient = object
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel

    spec = importlib.util.spec_from_file_location("arxiv_app", Path(__file__).with_name("main.py"))
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

EMPTY_FEED = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">'
    "</feed>"
)


def captured_params(payload):
    """Run the real handler, capture the params dict sent to the HTTP layer."""
    seen = {}

    async def fake_request(params):
        seen.update(params)
        return EMPTY_FEED

    async def run():
        with patch.object(app, "_request_arxiv", side_effect=fake_request):
            return await app.search_papers(payload)

    response = asyncio.run(run())
    return seen, response


def wire(search_query):
    """The encoded `search_query` as it leaves the client (httpx's urlencode)."""
    return urlencode({"search_query": search_query})


class BuildSearchQueryTests(unittest.TestCase):
    def test_multi_word_query_stays_unencoded(self):
        self.assertEqual(app._build_search_query({"query": "machine learning"}), "all:machine learning")

    def test_field_parts_join_with_bare_and(self):
        built = app._build_search_query({"query": "transformer", "title": "attention"})
        self.assertEqual(built, "all:transformer AND ti:attention")

    def test_empty_payload_resolves_none(self):
        self.assertIsNone(app._build_search_query({}))


class WireEncodingTests(unittest.TestCase):
    """`+` is the documented arXiv encoding for space and AND separators;

    `%2B` decodes to a literal plus sign, which arXiv does not treat as a
    separator — so the pre-encoded value must never reach `params=`."""

    def test_multi_word_wire_shape_matches_arxiv_manual(self):
        _, response = captured_params({"query": "machine learning"})
        self.assertIsNone(response.error)
        self.assertEqual(wire(captured_params({"query": "machine learning"})[0]["search_query"]),
                         "search_query=all%3Amachine+learning")

    def test_combined_fields_wire_shape_matches_arxiv_manual(self):
        seen, _ = captured_params({"query": "transformer", "title": "attention"})
        self.assertEqual(
            wire(seen["search_query"]),
            "search_query=all%3Atransformer+AND+ti%3Aattention",
        )

    def test_wire_contains_no_literal_plus_escape(self):
        seen, _ = captured_params({"query": "machine learning", "author": "john smith"})
        self.assertNotIn("%2B", wire(seen["search_query"]))
        self.assertEqual(wire(seen["search_query"]),
                         "search_query=all%3Amachine+learning+AND+au%3Ajohn+smith")


class SearchAuthorTests(unittest.TestCase):
    def test_author_name_reaches_the_wire_unencoded(self):
        seen = {}

        async def fake_request(params):
            seen.update(params)
            return EMPTY_FEED

        async def run():
            with patch.object(app, "_request_arxiv", side_effect=fake_request):
                return await app.search_author({"author": "Yann LeCun"})

        asyncio.run(run())
        self.assertEqual(seen["search_query"], "au:Yann LeCun")
        self.assertEqual(wire(seen["search_query"]), "search_query=au%3AYann+LeCun")


if __name__ == "__main__":
    unittest.main()

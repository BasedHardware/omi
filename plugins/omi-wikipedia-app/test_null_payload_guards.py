"""Regression tests for issue #20994: the Wikipedia REST/Action APIs return
explicit JSON null for several fields instead of omitting them, which made
chained ``.get(..., {})`` lookups raise AttributeError. Also covers malformed
(non-dict) list items and the pooled-client fallback.
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


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


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


fastapi_responses = module("fastapi.responses", HTMLResponse=lambda *a, **k: None)
stubs = {
    "fastapi": module("fastapi", FastAPI=Framework, responses=fastapi_responses),
    "fastapi.responses": fastapi_responses,
    "httpx": module(
        "httpx",
        AsyncClient=object,
        HTTPError=HTTPError,
        HTTPStatusError=HTTPStatusError,
    ),
    "pydantic": module("pydantic", BaseModel=Model),
}
spec = importlib.util.spec_from_file_location(
    "wikipedia_null_payload_test", Path(__file__).with_name("main.py")
)
wikipedia = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(wikipedia)


def run(coroutine):
    return asyncio.run(coroutine)


class NullContentUrlsTests(unittest.TestCase):
    """get_article_summary: content_urls / desktop can be JSON null."""

    def _summary(self, data):
        with patch.object(wikipedia, "_request_json", return_value=data):
            return run(wikipedia.get_article_summary({"title": "Ada Lovelace"}))

    def test_null_content_urls_falls_back_to_a_built_url(self):
        result = self._summary({"title": "Ada Lovelace", "extract": "...", "content_urls": None})
        self.assertIsNone(result.error)
        self.assertIn("en.wikipedia.org", result.result)

    def test_null_desktop_falls_back_to_a_built_url(self):
        result = self._summary(
            {"title": "Ada Lovelace", "extract": "...", "content_urls": {"desktop": None}}
        )
        self.assertIsNone(result.error)
        self.assertIn("en.wikipedia.org", result.result)


class NullQueryTests(unittest.TestCase):
    """search_articles / get_random_article: query can be JSON null."""

    def test_search_articles_handles_null_query(self):
        with patch.object(wikipedia, "_request_json", return_value={"query": None}):
            result = run(wikipedia.search_articles({"query": "ada"}))
        self.assertEqual(result.error, None)
        self.assertIn("No Wikipedia articles found", result.result)

    def test_search_articles_skips_malformed_non_dict_items(self):
        payload = {"query": {"search": [{"title": "Ada Lovelace"}, "garbage", None, 42]}}
        with patch.object(wikipedia, "_request_json", return_value=payload):
            result = run(wikipedia.search_articles({"query": "ada"}))
        self.assertIsNone(result.error)
        self.assertIn("Ada Lovelace", result.result)

    def test_get_random_article_handles_null_query(self):
        with patch.object(wikipedia, "_request_json", return_value={"query": None}):
            result = run(wikipedia.get_random_article({}))
        self.assertEqual(result.error, None)
        self.assertEqual(result.result, "No random Wikipedia article was returned.")

    def test_get_random_article_skips_a_non_dict_first_item(self):
        with patch.object(wikipedia, "_request_json", return_value={"query": {"random": ["garbage"]}}):
            result = run(wikipedia.get_random_article({}))
        self.assertEqual(result.error, None)
        self.assertEqual(result.result, "No random Wikipedia article was returned.")


class PooledClientFallbackTests(unittest.TestCase):
    """_request_json still works when no app-level client has been started."""

    def test_falls_back_to_a_throwaway_client_when_unpooled(self):
        self.assertIsNone(wikipedia._pooled_client)

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"ok": True}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, url, params=None):
                return FakeResponse()

        with patch.object(wikipedia.httpx, "AsyncClient", FakeClient):
            result = run(wikipedia._request_json("https://en.wikipedia.org/w/api.php"))
        self.assertEqual(result, {"ok": True})


if __name__ == "__main__":
    unittest.main()

"""Hermetic error handling and exception sanitization tests for Wikipedia App.

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


def make_module(name, **attributes):
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


def load_wikipedia_module():
    fastapi_responses = make_module("fastapi.responses", HTMLResponse=lambda *a, **k: None)
    stubs = {
        "fastapi": make_module("fastapi", FastAPI=Framework, responses=fastapi_responses),
        "fastapi.responses": fastapi_responses,
        "httpx": make_module(
            "httpx",
            AsyncClient=object,
            HTTPError=HTTPError,
            HTTPStatusError=HTTPStatusError,
        ),
        "pydantic": make_module("pydantic", BaseModel=Model),
    }
    spec = importlib.util.spec_from_file_location(
        "wikipedia_error_test", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_wikipedia_module()


class WikipediaErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/tokens.json: connection reset by 192.168.1.55:443"

    async def test_search_articles_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.search_articles({"query": "Ada Lovelace"})
            self.assertEqual(resp.error, "Wikipedia search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.55", str(resp.error))

    async def test_search_articles_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.search_articles({"query": "Ada Lovelace"})
            self.assertEqual(resp.error, "Wikipedia search failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_article_summary_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_article_summary({"title": "Ada Lovelace"})
            self.assertEqual(resp.error, "Wikipedia article request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.55", str(resp.error))

    async def test_get_article_summary_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.get_article_summary({"title": "Ada Lovelace"})
            self.assertEqual(resp.error, "Wikipedia article request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_random_article_sanitizes_unexpected_exception(self):
        with patch.object(app, "_request_json", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_random_article({})
            self.assertEqual(resp.error, "Wikipedia random article request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.55", str(resp.error))

    async def test_get_random_article_sanitizes_network_http_error(self):
        with patch.object(app, "_request_json", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.get_random_article({})
            self.assertEqual(resp.error, "Wikipedia random article request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_search_articles_handles_null_nested_fields_and_non_dict_items(self):
        for payload in (
            {"query": None},
            {"query": {"search": None}},
            {"query": {"search": ["not-a-dict", 123, None]}},
        ):
            with self.subTest(payload=payload):
                with patch.object(app, "_request_json", return_value=payload):
                    resp = await app.search_articles({"query": "Ada Lovelace"})
                    self.assertIsNone(resp.error)
                    self.assertIn("No Wikipedia articles found", resp.result)

    async def test_format_summary_handles_null_content_urls_and_desktop(self):
        for payload in (
            {"title": "Ada Lovelace", "extract": "Mathematician", "content_urls": None},
            {"title": "Ada Lovelace", "extract": "Mathematician", "content_urls": {"desktop": None}},
            {"title": "Ada Lovelace", "extract": "Mathematician", "content_urls": {"desktop": {"page": None}}},
        ):
            with self.subTest(payload=payload):
                with patch.object(app, "_request_json", return_value=payload):
                    resp = await app.get_article_summary({"title": "Ada Lovelace"})
                    self.assertIsNone(resp.error)
                    self.assertIn("https://en.wikipedia.org/wiki/Ada_Lovelace", resp.result)

    async def test_get_random_article_handles_null_query_and_non_dict_items(self):
        for payload in (
            {"query": None},
            {"query": {"random": None}},
            {"query": {"random": ["invalid", None]}},
        ):
            with self.subTest(payload=payload):
                with patch.object(app, "_request_json", return_value=payload):
                    resp = await app.get_random_article({})
                    self.assertIsNone(resp.error)
                    self.assertEqual(resp.result, "No random Wikipedia article was returned.")

    async def test_endpoints_reject_non_dict_upstream_payloads(self):
        with patch.object(app, "_request_json", return_value=["unexpected", "list"]):
            resp_summary = await app.get_article_summary({"title": "Ada Lovelace"})
            self.assertEqual(resp_summary.error, "Wikipedia article request failed.")


if __name__ == "__main__":
    unittest.main()

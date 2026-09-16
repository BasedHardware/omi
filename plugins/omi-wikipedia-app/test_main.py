"""Hermetic regression suite for the Wikipedia app (#14146).

Covers: pooled httpx client via FastAPI lifespan with fallback for unmanaged
contexts, null/non-dict Wikipedia payloads that must produce clean chat-tool
responses instead of AttributeError/TypeError, and defensive validation of
query/title inputs. Standard library + httpx only, no network — every HTTP
response is injected through a fake async client returning real httpx
Response objects (so raise_for_status/json behavior is exercised for real).
"""
import asyncio
import json
import unittest
from typing import Any
from unittest.mock import patch

import httpx

import main


def make_response(payload: Any, status_code: int = 200) -> httpx.Response:
    """Build a real httpx.Response from a Python payload (dict/list/str/None)."""
    if isinstance(payload, (dict, list)):
        content = json.dumps(payload).encode()
        headers = {"content-type": "application/json"}
    else:
        content = b"" if payload is None else str(payload).encode()
        headers = {}
    return httpx.Response(status_code, headers=headers, content=content,
                          request=httpx.Request("GET", "https://en.wikipedia.org/x"))


class FakeRouter:
    """Map request paths to responses; records every request."""

    def __init__(self):
        self.routes = []  # (predicate, response_factory)
        self.requests = []

    def add(self, predicate, factory):
        self.routes.append((predicate, factory))

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for predicate, factory in self.routes:
            if predicate(request):
                return factory(request)
        raise AssertionError(f"unexpected request: {request.url}")


class FakeAsyncClient:
    """Stands in for httpx.AsyncClient; routes get() through a FakeRouter."""
    instances = []

    def __init__(self, router, **kwargs):
        self.router = router
        self.kwargs = kwargs
        self.closed = False
        FakeAsyncClient.instances.append(self)

    async def get(self, url, params=None):
        return await self.router.handler(httpx.Request("GET", url, params=params))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def aclose(self):
        self.closed = True


def install_router(router):
    """Route every httpx.AsyncClient the app creates through `router`."""
    FakeAsyncClient.instances = []

    def factory(**kwargs):
        return FakeAsyncClient(router, **kwargs)

    return patch.object(main.httpx, "AsyncClient", factory)


class LifespanPoolingTests(unittest.TestCase):
    def test_lifespan_manages_one_pooled_client(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response({"ok": True}))
        with install_router(router):
            async def scenario():
                async with main.lifespan(main.app):
                    self.assertIsNotNone(main._client)
                    managed = main._client
                    await main._request_json("https://en.wikipedia.org/a")
                    await main._request_json("https://en.wikipedia.org/b")
                    self.assertIs(main._client, managed)
                    self.assertEqual(len(FakeAsyncClient.instances), 1)
                self.assertIsNone(main._client)
                self.assertTrue(managed.closed)

            asyncio.run(scenario())

    def test_unmanaged_context_falls_back_to_one_off_client(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response({"ok": True}))
        with install_router(router):
            self.assertIsNone(main._client)
            data = asyncio.run(main._request_json("https://en.wikipedia.org/a"))
            self.assertEqual(data, {"ok": True})
            self.assertIsNone(main._client)
            self.assertEqual(len(FakeAsyncClient.instances), 1)

    def test_each_unmanaged_request_gets_its_own_client(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response({"ok": True}))
        with install_router(router):
            async def scenario():
                await main._request_json("https://en.wikipedia.org/a")
                await main._request_json("https://en.wikipedia.org/b")
                self.assertEqual(len(FakeAsyncClient.instances), 2)

            asyncio.run(scenario())


class FormatSummaryTests(unittest.TestCase):
    def test_normal_summary(self):
        text = main._format_summary(
            {"title": "Python", "description": "A language", "extract": "It is nice.",
             "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Python"}}},
            "en")
        self.assertIn("Python", text)
        self.assertIn("https://en.wikipedia.org/wiki/Python", text)

    def test_null_content_urls_falls_back_to_article_url(self):
        text = main._format_summary({"title": "Python", "content_urls": None}, "en")
        self.assertIn("https://en.wikipedia.org/wiki/Python", text)

    def test_non_dict_content_urls_does_not_crash(self):
        text = main._format_summary({"title": "Python", "content_urls": "https://x"}, "en")
        self.assertIn("Python", text)

    def test_null_desktop_page_falls_back(self):
        text = main._format_summary(
            {"title": "Python", "content_urls": {"desktop": {"page": None}}}, "en")
        self.assertIn("https://en.wikipedia.org/wiki/Python", text)

    def test_empty_data_gets_placeholders(self):
        text = main._format_summary({}, "en")
        self.assertIn("Untitled", text)
        self.assertIn("https://en.wikipedia.org/wiki/Untitled", text)

    def test_missing_extract_uses_placeholder(self):
        text = main._format_summary({"title": "X"}, "en")
        self.assertIn("No summary was returned", text)


class CleanSnippetAndUrlTests(unittest.TestCase):
    def test_strips_html_and_entities(self):
        self.assertEqual(main._clean_snippet("<b>Ada</b> &amp; Grace"), "Ada & Grace")

    def test_none_and_empty_are_safe(self):
        self.assertEqual(main._clean_snippet(None), "")
        self.assertEqual(main._clean_snippet(""), "")

    def test_article_url_quotes_spaces(self):
        self.assertEqual(
            main._article_url("en", "Ada Lovelace"),
            "https://en.wikipedia.org/wiki/Ada_Lovelace")


class SearchArticlesTests(unittest.TestCase):
    def search(self, router, payload):
        with install_router(router):
            return asyncio.run(main.search_articles(payload))

    def test_happy_path(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response(
            {"query": {"search": [{"title": "Python", "snippet": "<b>lang</b>"}]}}))
        resp = self.search(router, {"query": "python"})
        self.assertIsNone(resp.error)
        self.assertIn("Python", resp.result)
        self.assertIn("lang", resp.result)

    def test_null_payload_returns_no_results_not_crash(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response(None))
        resp = self.search(router, {"query": "python"})
        self.assertIsNone(resp.error)
        self.assertIn("No Wikipedia articles found", resp.result)

    def test_html_error_page_payload_is_safe(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response("<html>504 Gateway</html>"))
        resp = self.search(router, {"query": "python"})
        self.assertIn("No Wikipedia articles found", resp.result)

    def test_query_payload_null_is_safe(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response({"query": None}))
        resp = self.search(router, {"query": "python"})
        self.assertIn("No Wikipedia articles found", resp.result)

    def test_non_dict_search_list_is_safe(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response({"query": {"search": "oops"}}))
        resp = self.search(router, {"query": "python"})
        self.assertIn("No Wikipedia articles found", resp.result)

    def test_non_dict_search_items_are_skipped(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response(
            {"query": {"search": ["garbage", None, {"title": "Python"}]}}))
        resp = self.search(router, {"query": "python"})
        self.assertIn("1. Python", resp.result)

    def test_missing_query_field(self):
        router = FakeRouter()
        resp = self.search(router, {})
        self.assertEqual(resp.error, "Missing required field: query")

    def test_non_string_query_is_rejected(self):
        router = FakeRouter()
        for bad in (None, 123, {}, ["x"]):
            resp = self.search(router, {"query": bad})
            self.assertEqual(resp.error, "Missing required field: query")

    def test_whitespace_only_query_is_rejected(self):
        router = FakeRouter()
        resp = self.search(router, {"query": "   "})
        self.assertEqual(resp.error, "Missing required field: query")

    def test_http_status_error_reported_cleanly(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response("oops", status_code=504))
        resp = self.search(router, {"query": "python"})
        self.assertIn("504", resp.error)


class GetArticleSummaryTests(unittest.TestCase):
    def summary(self, router, payload):
        with install_router(router):
            return asyncio.run(main.get_article_summary(payload))

    def test_happy_path(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response(
            {"title": "Python", "extract": "A language.",
             "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Python"}}}))
        resp = self.summary(router, {"title": "Python"})
        self.assertIsNone(resp.error)
        self.assertIn("A language.", resp.result)

    def test_null_payload_yields_placeholder_summary(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response(None))
        resp = self.summary(router, {"title": "Python"})
        self.assertIsNone(resp.error)
        self.assertIn("No summary was returned", resp.result)

    def test_disambiguation_flagged(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response(
            {"type": "disambiguation", "title": "Mercury", "extract": "May refer to"}))
        resp = self.summary(router, {"title": "Mercury"})
        self.assertIn("disambiguation", resp.result)

    def test_missing_title_field(self):
        router = FakeRouter()
        resp = self.summary(router, {})
        self.assertEqual(resp.error, "Missing required field: title")

    def test_non_string_title_is_rejected(self):
        router = FakeRouter()
        for bad in (None, 42, {}, []):
            resp = self.summary(router, {"title": bad})
            self.assertEqual(resp.error, "Missing required field: title")

    def test_404_maps_to_friendly_error(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response(None, status_code=404))
        resp = self.summary(router, {"title": "Nosuch"})
        self.assertIn("No Wikipedia article found", resp.error)


class GetRandomArticleTests(unittest.TestCase):
    def random_article(self, router):
        with install_router(router):
            return asyncio.run(main.get_random_article({}))

    def test_happy_path(self):
        router = FakeRouter()
        router.add(lambda req: "list=random" in str(req.url),
                   lambda req: make_response({"query": {"random": [{"title": "Hat"}]}}))
        router.add(lambda req: True, lambda req: make_response(
            {"title": "Hat", "extract": "Headwear.",
             "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Hat"}}}))
        resp = self.random_article(router)
        self.assertIsNone(resp.error)
        self.assertIn("Headwear.", resp.result)

    def test_null_random_payload_is_safe(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response(None))
        resp = self.random_article(router)
        self.assertIn("No random Wikipedia article was returned", resp.result)

    def test_query_null_is_safe(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response({"query": None}))
        resp = self.random_article(router)
        self.assertIn("No random Wikipedia article was returned", resp.result)

    def test_non_dict_random_item_is_handled(self):
        router = FakeRouter()
        router.add(lambda req: True, lambda req: make_response({"query": {"random": ["garbage"]}}))
        resp = self.random_article(router)
        self.assertIn("without a title", resp.result)

    def test_null_summary_followup_is_safe(self):
        router = FakeRouter()

        def route(req):
            if "list=random" in str(req.url):
                return make_response({"query": {"random": [{"title": "Hat"}]}})
            return make_response(None)

        router.add(lambda req: True, route)
        resp = self.random_article(router)
        self.assertIsNone(resp.error)
        self.assertIn("No summary was returned", resp.result)


class SafeLimitAndLanguageTests(unittest.TestCase):
    def test_limit_clamping(self):
        self.assertEqual(main._safe_limit(None), 5)
        self.assertEqual(main._safe_limit(""), 5)
        self.assertEqual(main._safe_limit("7"), 7)
        self.assertEqual(main._safe_limit(99), 10)
        self.assertEqual(main._safe_limit(0), 1)
        self.assertEqual(main._safe_limit("abc"), 5)

    def test_language_hardening(self):
        self.assertEqual(main._safe_language(None), "en")
        self.assertEqual(main._safe_language(" EN "), "en")
        self.assertEqual(main._safe_language("../etc"), "en")
        self.assertEqual(main._safe_language("de"), "de")


if __name__ == "__main__":
    unittest.main()

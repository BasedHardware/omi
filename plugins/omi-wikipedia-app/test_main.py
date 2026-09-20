"""Hermetic Wikipedia app input validation and URL hardening regression tests.

Exercises language normalization, safe path segment encoding (traversal prevention),
and handler type coercion without live network or external dependencies.
"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch


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
        def __init__(self, message, response=None):
            super().__init__(message)
            self.response = response or ModuleType("Response")
            if not hasattr(self.response, "status_code"):
                self.response.status_code = 500

    httpx = ModuleType("httpx")
    httpx.AsyncClient = object
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Body = lambda *args, **kwargs: None
    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel

    target_file = Path(__file__).with_name("main.py")
    if not target_file.exists():
        target_file = Path(__file__).with_name("omi_wikipedia_main.py")

    spec = importlib.util.spec_from_file_location("wikipedia_app", target_file)
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


class SafeLanguageTests(unittest.TestCase):
    def test_valid_language_codes(self):
        cases = {
            "en": "en",
            "FR": "fr",
            "es": "es",
            "de": "de",
            "pt-br": "pt-br",
            "zh-classical": "zh-classical",
            "simple": "simple",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(app._safe_language(raw), expected)

    def test_rejects_unicode_idna_injection(self):
        # Unicode characters that trigger IDNA hostname rewriting must be rejected
        cases = ["ß", "мо", "рус", "日本語", "é"]
        for bad in cases:
            with self.subTest(bad=bad):
                self.assertEqual(app._safe_language(bad), "en")

    def test_rejects_malformed_hyphens(self):
        cases = ["-en", "en-", "--", "-pt-br-", "en--us"]
        for bad in cases:
            with self.subTest(bad=bad):
                self.assertEqual(app._safe_language(bad), "en")

    def test_rejects_non_strings_and_excessive_length(self):
        cases = [None, 2026, True, False, ["en"], {"lang": "en"}, "a" * 25]
        for bad in cases:
            with self.subTest(bad=bad):
                self.assertEqual(app._safe_language(bad), "en")


class SafePathSegmentTests(unittest.TestCase):
    def test_percent_encodes_forward_slashes_to_prevent_traversal(self):
        # Without safe="", slash is preserved, permitting path traversal
        traversal = "../../../../w/api.php"
        encoded = app._safe_path_segment(traversal)
        self.assertNotIn("/", encoded)
        self.assertIn("%2F", encoded)
        self.assertEqual(encoded, "..%2F..%2F..%2F..%2Fw%2Fapi.php")

    def test_spaces_replaced_with_underscores(self):
        title = "Albert Einstein"
        self.assertEqual(app._safe_path_segment(title), "Albert_Einstein")


class SearchArticlesHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_articles_rejects_non_string_queries(self):
        bad_queries = [2026, 3.5, ["wiki"], {"q": "wiki"}, None, "", "   "]
        for q in bad_queries:
            with self.subTest(query=q):
                response = await app.search_articles({"query": q})
                self.assertEqual(response.error, "Missing required field: query")
                self.assertIsNone(response.result)

    async def test_search_articles_handles_non_dict_payload(self):
        response = await app.search_articles(None)
        self.assertEqual(response.error, "Missing required field: query")

    async def test_search_articles_sanitizes_language(self):
        mock_data = {"query": {"search": [{"title": "Test", "snippet": "Sample"}]}}
        provider = AsyncMock(return_value=mock_data)
        with patch.object(app, "_request_json", provider):
            response = await app.search_articles({"query": "Ada Lovelace", "language": "мо"})
            self.assertIsNone(response.error)
            # Language must fall back to "en", never "мо"
            provider.assert_awaited_once()
            called_url = provider.await_args[0][0]
            self.assertTrue(called_url.startswith("https://en.wikipedia.org/"))


class GetArticleSummaryHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_rejects_non_string_titles(self):
        bad_titles = [2026, ["quantum"], None, "", "   "]
        for t in bad_titles:
            with self.subTest(title=t):
                response = await app.get_article_summary({"title": t})
                self.assertEqual(response.error, "Missing required field: title")

    async def test_summary_traversal_is_contained(self):
        mock_data = {
            "title": "repro",
            "extract": "Summary text",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/repro"}}
        }
        provider = AsyncMock(return_value=mock_data)
        with patch.object(app, "_request_json", provider):
            response = await app.get_article_summary({"title": "../../../../w/api.php"})
            self.assertIsNone(response.error)
            called_url = provider.await_args[0][0]
            self.assertIn("..%2F..%2F..%2F..%2Fw%2Fapi.php", called_url)
            self.assertNotIn("/page/summary/../", called_url)


class GetRandomArticleHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_random_article_handles_none_payload(self):
        mock_random = {"query": {"random": [{"title": "Curie"}]}}
        mock_summary = {"title": "Curie", "extract": "Nobel laureate"}
        with patch.object(app, "_request_json", AsyncMock(side_effect=[mock_random, mock_summary])):
            response = await app.get_random_article(None)
            self.assertIsNone(response.error)
            self.assertIn("Curie", response.result)


if __name__ == "__main__":
    unittest.main()

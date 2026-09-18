import asyncio
import math
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Provide lightweight stubs for third-party runtime dependencies so test_main.py
# runs hermetically on any clean standard library Python environment without
# requiring FastAPI, httpx, or Pydantic to be installed.
if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            def __init__(self, message, request=None, response=None):
                super().__init__(message)
                self.request = request
                self.response = response

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                pass

        class Request:
            def __init__(self, method, url):
                self.method = method
                self.url = url

        class Response:
            def __init__(self, status_code, request=None):
                self.status_code = status_code
                self.request = request

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
        httpx.AsyncClient = AsyncClient
        httpx.Request = Request
        httpx.Response = Response
        sys.modules["httpx"] = httpx

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

        fastapi.FastAPI = FastAPI
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content):
                self.body = content.encode("utf-8") if isinstance(content, str) else content

        responses.HTMLResponse = HTMLResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

        pydantic.BaseModel = BaseModel
        sys.modules["pydantic"] = pydantic

# Add plugin directory to path so main can be loaded hermetically
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main


class SafeLimitAndLanguageTests(unittest.TestCase):
    def test_safe_limit_defaults_and_clamping(self):
        self.assertEqual(main._safe_limit(None), 5)
        self.assertEqual(main._safe_limit(""), 5)
        self.assertEqual(main._safe_limit(3), 3)
        self.assertEqual(main._safe_limit("8"), 8)
        self.assertEqual(main._safe_limit("4.0"), 4)
        self.assertEqual(main._safe_limit(0), 1)
        self.assertEqual(main._safe_limit(-10), 1)
        self.assertEqual(main._safe_limit(100), main.MAX_LIMIT)

    def test_safe_limit_rejects_dirty_types_and_overflow(self):
        self.assertEqual(main._safe_limit(True), 5)
        self.assertEqual(main._safe_limit(False), 5)
        self.assertEqual(main._safe_limit([10]), 5)
        self.assertEqual(main._safe_limit({"limit": 5}), 5)
        self.assertEqual(main._safe_limit(float("inf")), 5)
        self.assertEqual(main._safe_limit(float("nan")), 5)
        self.assertEqual(main._safe_limit("invalid_number"), 5)

    def test_safe_language_valid_and_normalization(self):
        self.assertEqual(main._safe_language("en"), "en")
        self.assertEqual(main._safe_language("  ZH-CN  "), "zh-cn")
        self.assertEqual(main._safe_language("simple"), "simple")
        self.assertEqual(main._safe_language("es"), "es")

    def test_safe_language_invalid_and_dirty_types(self):
        self.assertEqual(main._safe_language(None), main.DEFAULT_LANGUAGE)
        self.assertEqual(main._safe_language(""), main.DEFAULT_LANGUAGE)
        self.assertEqual(main._safe_language("   "), main.DEFAULT_LANGUAGE)
        self.assertEqual(main._safe_language(True), main.DEFAULT_LANGUAGE)
        self.assertEqual(main._safe_language(123), main.DEFAULT_LANGUAGE)
        self.assertEqual(main._safe_language(["en"]), main.DEFAULT_LANGUAGE)
        self.assertEqual(main._safe_language("toolonglanguagecodehere"), main.DEFAULT_LANGUAGE)
        self.assertEqual(main._safe_language("en;rm -rf /"), main.DEFAULT_LANGUAGE)
        self.assertEqual(main._safe_language("en_US"), main.DEFAULT_LANGUAGE)


class TitleCleaningAndSnippetSanitizationTests(unittest.TestCase):
    def test_clean_title_standard_and_underscores(self):
        self.assertEqual(main._clean_title("Alan Turing"), "Alan Turing")
        self.assertEqual(main._clean_title("Alan_Turing"), "Alan Turing")
        self.assertEqual(main._clean_title("  Artificial Intelligence  "), "Artificial Intelligence")

    def test_clean_title_from_full_wikipedia_url(self):
        url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
        self.assertEqual(main._clean_title(url), "Artificial intelligence")

        url_with_fragment = "https://en.wikipedia.org/wiki/Python_(programming_language)#Syntax"
        self.assertEqual(main._clean_title(url_with_fragment), "Python (programming language)")

        wiki_prefix = "/wiki/Quantum_computing"
        self.assertEqual(main._clean_title(wiki_prefix), "Quantum computing")

        url_encoded = "https://en.wikipedia.org/wiki/AC%2FDC"
        self.assertEqual(main._clean_title(url_encoded), "AC/DC")

    def test_clean_title_dirty_types(self):
        self.assertEqual(main._clean_title(None), "")
        self.assertEqual(main._clean_title(True), "")
        self.assertEqual(main._clean_title(123), "")
        self.assertEqual(main._clean_title("   "), "")

    def test_clean_snippet_html_and_invisible_chars(self):
        html_snippet = 'Search for <span class="searchmatch">Deep</span> learning &amp; AI'
        self.assertEqual(main._clean_snippet(html_snippet), "Search for Deep learning & AI")

        dirty_unicode = "Deep\u200bLearning\ufeff\u200e Model"
        self.assertEqual(main._clean_snippet(dirty_unicode), "DeepLearning Model")

    def test_clean_snippet_dirty_types(self):
        self.assertEqual(main._clean_snippet(None), "")
        self.assertEqual(main._clean_snippet(""), "")
        self.assertEqual(main._clean_snippet(123), "")
        self.assertEqual(main._clean_snippet(True), "")

    def test_article_url_encoding(self):
        url = main._article_url("en", "Albert Einstein")
        self.assertEqual(url, "https://en.wikipedia.org/wiki/Albert_Einstein")

        url_slash = main._article_url("en", "AC/DC")
        self.assertEqual(url_slash, "https://en.wikipedia.org/wiki/AC%2FDC")


class FormatSummaryDefensiveTests(unittest.TestCase):
    def test_format_summary_complete(self):
        data = {
            "title": "Machine Learning",
            "description": "Subfield of artificial intelligence",
            "extract": "Machine learning is an umbrella term for solving problems...",
            "content_urls": {
                "desktop": {
                    "page": "https://en.wikipedia.org/wiki/Machine_Learning"
                }
            }
        }
        res = main._format_summary(data, "en")
        self.assertIn("Machine Learning", res)
        self.assertIn("Subfield of artificial intelligence", res)
        self.assertIn("https://en.wikipedia.org/wiki/Machine_Learning", res)

    def test_format_summary_missing_description_and_content_urls_none(self):
        data = {
            "title": "Minimal Title",
            "extract": "Some summary text",
            "content_urls": None
        }
        res = main._format_summary(data, "en")
        self.assertIn("Minimal Title", res)
        self.assertIn("Some summary text", res)
        self.assertIn("https://en.wikipedia.org/wiki/Minimal_Title", res)

    def test_format_summary_desktop_url_none(self):
        data = {
            "title": "Test Page",
            "content_urls": {"desktop": None}
        }
        res = main._format_summary(data, "en")
        self.assertIn("Test Page", res)
        self.assertIn("https://en.wikipedia.org/wiki/Test_Page", res)

    def test_format_summary_non_dict_data(self):
        self.assertEqual(main._format_summary(None, "en"), "No summary information available.")
        self.assertEqual(main._format_summary("raw string", "en"), "No summary information available.")


class ToolEndpointsTests(unittest.TestCase):
    def test_root_and_health_and_manifest(self):
        loop = asyncio.new_event_loop()
        try:
            r = loop.run_until_complete(main.root())
            body_bytes = r.body if isinstance(r.body, bytes) else r.body.encode("utf-8")
            self.assertIn(b"Wikipedia x Omi", body_bytes)

            h = loop.run_until_complete(main.health())
            self.assertEqual(h, {"status": "ok"})

            m = loop.run_until_complete(main.get_omi_tools_manifest())
            self.assertEqual(len(m["tools"]), 3)
            tool_names = [t["name"] for t in m["tools"]]
            self.assertIn("search_articles", tool_names)
            self.assertIn("get_article_summary", tool_names)
            self.assertIn("get_random_article", tool_names)
        finally:
            loop.close()

    def test_search_articles_missing_or_empty_query(self):
        loop = asyncio.new_event_loop()
        try:
            r1 = loop.run_until_complete(main.search_articles({}))
            self.assertEqual(r1.error, "Missing required field: query")

            r2 = loop.run_until_complete(main.search_articles({"query": "   "}))
            self.assertEqual(r2.error, "Missing required field: query")

            r3 = loop.run_until_complete(main.search_articles("not_a_dict"))
            self.assertEqual(r3.error, "Invalid request payload")
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_search_articles_success(self, mock_request):
        mock_request.return_value = {
            "query": {
                "search": [
                    {
                        "title": "Quantum Computing",
                        "snippet": "A field focused on <span class=\"searchmatch\">quantum</span> physics"
                    }
                ]
            }
        }
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.search_articles({"query": "Quantum", "limit": 3}))
            self.assertIsNone(resp.error)
            self.assertIn("Wikipedia search results for 'Quantum':", resp.result)
            self.assertIn("1. Quantum Computing", resp.result)
            self.assertIn("quantum physics", resp.result)
            self.assertIn("https://en.wikipedia.org/wiki/Quantum_Computing", resp.result)
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_search_articles_empty_results_and_malformed_response(self, mock_request):
        loop = asyncio.new_event_loop()
        try:
            mock_request.return_value = {"query": {"search": []}}
            resp = loop.run_until_complete(main.search_articles({"query": "xyznonexistent"}))
            self.assertEqual(resp.result, "No Wikipedia articles found for 'xyznonexistent'.")

            mock_request.return_value = {"query": None}
            resp2 = loop.run_until_complete(main.search_articles({"query": "xyz"}))
            self.assertEqual(resp2.result, "No Wikipedia articles found for 'xyz'.")
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_search_articles_http_error(self, mock_request):
        mock_request.side_effect = main.httpx.HTTPError("Connection failed")
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.search_articles({"query": "error_case"}))
            self.assertIn("Wikipedia search failed: Connection failed", resp.error)
        finally:
            loop.close()

    def test_get_article_summary_missing_title(self):
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.get_article_summary({}))
            self.assertEqual(resp.error, "Missing required field: title")

            resp2 = loop.run_until_complete(main.get_article_summary({"title": "   "}))
            self.assertEqual(resp2.error, "Missing required field: title")
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_article_summary_success(self, mock_request):
        mock_request.return_value = {
            "title": "Turing Award",
            "extract": "An annual prize given by the ACM...",
            "description": "Annual computer science prize",
            "content_urls": {
                "desktop": {"page": "https://en.wikipedia.org/wiki/Turing_Award"}
            }
        }
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.get_article_summary({"title": "Turing Award"}))
            self.assertIsNone(resp.error)
            self.assertIn("Turing Award", resp.result)
            self.assertIn("Annual computer science prize", resp.result)
            self.assertIn("https://en.wikipedia.org/wiki/Turing_Award", resp.result)
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_article_summary_disambiguation(self, mock_request):
        mock_request.return_value = {
            "type": "disambiguation",
            "title": "Mercury",
            "extract": "Mercury most commonly refers to the chemical element or the planet.",
        }
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.get_article_summary({"title": "Mercury"}))
            self.assertIn("This is a disambiguation page. Use search_articles for more specific matches.", resp.result)
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_article_summary_404_handled(self, mock_request):
        response_404 = main.httpx.Response(404, request=main.httpx.Request("GET", "https://en.wikipedia.org/test"))
        mock_request.side_effect = main.httpx.HTTPStatusError("Not found", request=response_404.request, response=response_404)
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.get_article_summary({"title": "NonExistentArticle"}))
            self.assertEqual(resp.error, "No Wikipedia article found for 'NonExistentArticle'. Try search_articles first.")
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_random_article_success(self, mock_request):
        def mock_side_effect(url, params=None):
            if "w/api.php" in url:
                return {"query": {"random": [{"title": "Random Science Topic"}]}}
            return {
                "title": "Random Science Topic",
                "extract": "Fascinating science extract...",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Random_Science_Topic"}}
            }

        mock_request.side_effect = mock_side_effect
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.get_random_article())
            self.assertIsNone(resp.error)
            self.assertIn("Random Wikipedia article:", resp.result)
            self.assertIn("Random Science Topic", resp.result)
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_random_article_empty_items(self, mock_request):
        mock_request.return_value = {"query": {"random": []}}
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.get_random_article({}))
            self.assertEqual(resp.result, "No random Wikipedia article was returned.")
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()

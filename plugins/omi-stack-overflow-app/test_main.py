import asyncio
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
                self.is_closed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def aclose(self):
                self.is_closed = True

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


class HelperSanitizationTests(unittest.TestCase):
    def test_safe_limit(self):
        self.assertEqual(main._safe_limit(None), 5)
        self.assertEqual(main._safe_limit(""), 5)
        self.assertEqual(main._safe_limit(3), 3)
        self.assertEqual(main._safe_limit("8"), 8)
        self.assertEqual(main._safe_limit("4.0"), 4)
        self.assertEqual(main._safe_limit(0), 1)
        self.assertEqual(main._safe_limit(-10), 1)
        self.assertEqual(main._safe_limit(100), main.MAX_LIMIT)
        self.assertEqual(main._safe_limit(True), 5)
        self.assertEqual(main._safe_limit(False), 5)
        self.assertEqual(main._safe_limit(float("inf")), 5)
        self.assertEqual(main._safe_limit(float("nan")), 5)
        self.assertEqual(main._safe_limit("invalid"), 5)

    def test_safe_site(self):
        self.assertEqual(main._safe_site(None), main.DEFAULT_SITE)
        self.assertEqual(main._safe_site(""), main.DEFAULT_SITE)
        self.assertEqual(main._safe_site("  SUPERUSER  "), "superuser")
        self.assertEqual(main._safe_site("askubuntu"), "askubuntu")
        self.assertEqual(main._safe_site("invalid;site"), main.DEFAULT_SITE)
        self.assertEqual(main._safe_site(123), main.DEFAULT_SITE)

    def test_safe_tags(self):
        self.assertIsNone(main._safe_tags(None))
        self.assertIsNone(main._safe_tags(""))
        self.assertIsNone(main._safe_tags(True))
        self.assertEqual(main._safe_tags("python, react; fastapi"), "python;react;fastapi")
        self.assertEqual(main._safe_tags(["python", "c++", "node.js"]), "python;c++;node.js")
        self.assertEqual(main._safe_tags("tag1, tag2, tag3, tag4, tag5, tag6"), "tag1;tag2;tag3;tag4;tag5")
        self.assertIsNone(main._safe_tags("invalid!tag, another@tag"))

    def test_coerce_bool(self):
        self.assertTrue(main._coerce_bool(True))
        self.assertFalse(main._coerce_bool(False))
        self.assertTrue(main._coerce_bool("true"))
        self.assertTrue(main._coerce_bool("1"))
        self.assertTrue(main._coerce_bool("yes"))
        self.assertFalse(main._coerce_bool("false"))
        self.assertFalse(main._coerce_bool("0"))
        self.assertFalse(main._coerce_bool("no"))
        self.assertIsNone(main._coerce_bool(None))
        self.assertIsNone(main._coerce_bool(""))
        self.assertIsNone(main._coerce_bool("maybe"))

    def test_clean_text(self):
        html = '<pre><code>def test():\n    return 42</code></pre><p>Hello &amp; world</p>'
        cleaned = main._clean_text(html)
        self.assertIn("def test():", cleaned)
        self.assertIn("return 42", cleaned)
        self.assertIn("Hello & world", cleaned)

        unicode_dirty = "Python\u200b\ufeffCode"
        self.assertEqual(main._clean_text(unicode_dirty), "PythonCode")
        self.assertEqual(main._clean_text(None), "")
        self.assertEqual(main._clean_text(123), "")

    def test_format_date(self):
        self.assertEqual(main._format_date(1609459200), "2021-01-01")
        self.assertEqual(main._format_date(None), "unknown date")
        self.assertEqual(main._format_date("invalid"), "unknown date")

    def test_parse_question_target_standard(self):
        self.assertEqual(main._parse_question_target(12345), (12345, None))
        self.assertEqual(main._parse_question_target("12345"), (12345, None))
        self.assertEqual(main._parse_question_target("#12345"), (12345, None))
        self.assertEqual(main._parse_question_target("question: 12345"), (12345, None))
        self.assertEqual(main._parse_question_target("ID: 12345"), (12345, None))

    def test_parse_question_target_from_url(self):
        url = "https://stackoverflow.com/questions/11227809/why-is-processing-a-sorted-array-faster"
        self.assertEqual(main._parse_question_target(url), (11227809, "stackoverflow"))

        short_url = "https://superuser.com/q/98765"
        self.assertEqual(main._parse_question_target(short_url), (98765, "superuser"))

        serverfault_url = "https://serverfault.com/questions/54321/nginx-configuration"
        self.assertEqual(main._parse_question_target(serverfault_url), (54321, "serverfault"))

        stackexchange_url = "https://codereview.stackexchange.com/questions/223344"
        self.assertEqual(main._parse_question_target(stackexchange_url), (223344, "codereview"))

    def test_parse_question_target_invalids(self):
        self.assertEqual(main._parse_question_target(None), (None, None))
        self.assertEqual(main._parse_question_target(True), (None, None))
        self.assertEqual(main._parse_question_target(""), (None, None))
        self.assertEqual(main._parse_question_target("not_an_id"), (None, None))
        self.assertEqual(main._parse_question_target(-5), (None, None))

    def test_question_url(self):
        self.assertEqual(main._question_url("stackoverflow", 123), "https://stackoverflow.com/questions/123")
        self.assertEqual(main._question_url("superuser", 456), "https://superuser.com/questions/456")
        self.assertEqual(main._question_url("askubuntu", 789), "https://askubuntu.com/questions/789")


class QuestionAndAnswerFormattingTests(unittest.TestCase):
    def test_format_question(self):
        item = {
            "title": "Why is &lt;div&gt; not centering?",
            "question_id": 1001,
            "score": 42,
            "answer_count": 5,
            "view_count": 1000,
            "accepted_answer_id": 2002,
            "tags": ["css", "html"],
            "link": "https://stackoverflow.com/q/1001",
        }
        res = main._format_question(item, 1, "stackoverflow")
        self.assertIn("1. Why is <div> not centering?", res)
        self.assertIn("42 score | 5 answers | 1000 views | accepted", res)
        self.assertIn("Tags: css, html", res)
        self.assertIn("https://stackoverflow.com/q/1001", res)

    def test_format_question_unaccepted_and_defaults(self):
        item = {"question_id": 1002}
        res = main._format_question(item, 2, "stackoverflow")
        self.assertIn("2. Untitled question", res)
        self.assertIn("0 score | 0 answers | 0 views | not accepted", res)
        self.assertIn("Tags: no tags", res)

    def test_format_answer_owner_present(self):
        item = {
            "owner": {"display_name": "Jon Skeet"},
            "score": 999,
            "is_accepted": True,
            "body": "<p>Here is the exact solution.</p>",
        }
        res = main._format_answer(item, 1)
        self.assertIn("1. Jon Skeet | 999 score | accepted", res)
        self.assertIn("Here is the exact solution.", res)

    def test_format_answer_owner_none_defensive(self):
        # When user is deleted or anonymous, owner is None in API response
        item = {
            "owner": None,
            "score": 10,
            "is_accepted": False,
            "body": "Anonymous contribution",
        }
        res = main._format_answer(item, 2)
        self.assertIn("2. unknown | 10 score", res)
        self.assertIn("Anonymous contribution", res)

    def test_format_answer_non_dict(self):
        self.assertIn("unknown | 0 score", main._format_answer(None, 1))


class ToolEndpointsTests(unittest.TestCase):
    def test_root_and_health_and_manifest(self):
        loop = asyncio.new_event_loop()
        try:
            r = loop.run_until_complete(main.root())
            body_bytes = r.body if isinstance(r.body, bytes) else r.body.encode("utf-8")
            self.assertIn(b"Stack Overflow x Omi", body_bytes)

            h = loop.run_until_complete(main.health())
            self.assertEqual(h, {"status": "ok"})

            m = loop.run_until_complete(main.get_omi_tools_manifest())
            self.assertEqual(len(m["tools"]), 3)
            tool_names = [t["name"] for t in m["tools"]]
            self.assertIn("search_questions", tool_names)
            self.assertIn("get_question", tool_names)
            self.assertIn("get_top_answers", tool_names)
        finally:
            loop.close()

    def test_search_questions_missing_query(self):
        loop = asyncio.new_event_loop()
        try:
            r1 = loop.run_until_complete(main.search_questions({}))
            self.assertEqual(r1.error, "Missing required field: query")

            r2 = loop.run_until_complete(main.search_questions({"query": "   "}))
            self.assertEqual(r2.error, "Missing required field: query")

            r3 = loop.run_until_complete(main.search_questions("not_a_dict"))
            self.assertEqual(r3.error, "Invalid request payload")
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_search_questions_success(self, mock_request):
        mock_request.return_value = {
            "items": [
                {
                    "title": "How to sort a dictionary by value?",
                    "question_id": 5001,
                    "score": 100,
                    "answer_count": 8,
                    "view_count": 50000,
                    "accepted_answer_id": 6001,
                    "tags": ["python", "sorting"],
                    "link": "https://stackoverflow.com/q/5001",
                }
            ]
        }
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.search_questions({"query": "sort dict", "limit": 2}))
            self.assertIsNone(resp.error)
            self.assertIn("Stack Exchange results for 'sort dict' on stackoverflow:", resp.result)
            self.assertIn("1. How to sort a dictionary by value?", resp.result)
            self.assertIn("Tags: python, sorting", resp.result)
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_search_questions_empty_results(self, mock_request):
        mock_request.return_value = {"items": []}
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.search_questions({"query": "xyzunlikelyquery"}))
            self.assertEqual(resp.result, "No Stack Exchange questions found for 'xyzunlikelyquery'.")
        finally:
            loop.close()

    def test_get_question_missing_or_invalid_id(self):
        loop = asyncio.new_event_loop()
        try:
            r1 = loop.run_until_complete(main.get_question({}))
            self.assertEqual(r1.error, "Missing required field: question_id")

            r2 = loop.run_until_complete(main.get_question({"question_id": "not_an_id"}))
            self.assertIn("question_id must be an integer ID", r2.error)
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_question_by_url_success(self, mock_request):
        mock_request.return_value = {
            "items": [
                {
                    "title": "Why is processing a sorted array faster?",
                    "question_id": 11227809,
                    "creation_date": 1340798400,
                    "score": 25000,
                    "answer_count": 20,
                    "view_count": 1500000,
                    "tags": ["c++", "performance", "cpu-architecture"],
                    "link": "https://stackoverflow.com/questions/11227809",
                    "body": "Branch prediction causes branch mispredictions in unsorted arrays.",
                }
            ]
        }
        loop = asyncio.new_event_loop()
        try:
            url_target = "https://stackoverflow.com/questions/11227809/why-is-processing-a-sorted-array-faster"
            resp = loop.run_until_complete(main.get_question({"question_id": url_target}))
            self.assertIsNone(resp.error)
            self.assertIn("Why is processing a sorted array faster?", resp.result)
            self.assertIn("Question ID: 11227809", resp.result)
            self.assertIn("Branch prediction causes", resp.result)
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_question_404(self, mock_request):
        mock_request.return_value = {"items": []}
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.get_question({"question_id": 999999999}))
            self.assertEqual(resp.error, "No question found for ID 999999999 on stackoverflow.")
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_top_answers_by_url_success(self, mock_request):
        mock_request.return_value = {
            "items": [
                {
                    "owner": {"display_name": "Mysticial"},
                    "score": 30000,
                    "is_accepted": True,
                    "body": "You are a victim of branch prediction fail.",
                }
            ]
        }
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(
                main.get_top_answers({"question_id": "https://stackoverflow.com/q/11227809"})
            )
            self.assertIsNone(resp.error)
            self.assertIn("Top answers for question 11227809 on stackoverflow:", resp.result)
            self.assertIn("Mysticial | 30000 score | accepted", resp.result)
            self.assertIn("branch prediction fail", resp.result)
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_question_error_handling(self, mock_request):
        mock_request.side_effect = ValueError("Rate limit exceeded")
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.get_question({"question_id": 123}))
            self.assertIn("Rate limit exceeded", resp.error)
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_top_answers_empty_results(self, mock_request):
        mock_request.return_value = {"items": []}
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.get_top_answers({"question_id": 123}))
            self.assertIn("No answers found for question ID 123", resp.result)
        finally:
            loop.close()

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_top_answers_owner_none_endpoint(self, mock_request):
        mock_request.return_value = {
            "items": [
                {
                    "owner": None,
                    "score": 5,
                    "is_accepted": False,
                    "body": "Useful snippet",
                }
            ]
        }
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(main.get_top_answers({"question_id": 123}))
            self.assertIsNone(resp.error)
            self.assertIn("unknown | 5 score", resp.result)
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()

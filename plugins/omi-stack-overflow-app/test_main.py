"""Hermetic unit tests for Omi Stack Overflow Integration App.

Runs with standard library unittest without requiring external network access.
"""

from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Provide lightweight stubs for third-party runtime dependencies if missing
if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            def __init__(self, message="", *, request=None, response=None):
                super().__init__(message)
                self.response = response or types.SimpleNamespace(status_code=500)

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                self.is_closed = False

            async def aclose(self):
                self.is_closed = True

            async def get(self, *args, **kwargs):
                pass

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
        httpx.AsyncClient = AsyncClient
        sys.modules["httpx"] = httpx

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.exceptions  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.exception_handlers = {}

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

            def exception_handler(self, exc_class):
                def decorator(f):
                    self.exception_handlers[exc_class] = f
                    return f
                return decorator

        fastapi.FastAPI = FastAPI
        class Request:
            pass
        fastapi.Request = Request
        sys.modules["fastapi"] = fastapi

        exc_mod = types.ModuleType("fastapi.exceptions")
        class RequestValidationError(Exception):
            def __init__(self, errors=None):
                self._errors = errors or []
            def errors(self):
                return self._errors
        exc_mod.RequestValidationError = RequestValidationError
        sys.modules["fastapi.exceptions"] = exc_mod
        fastapi.exceptions = exc_mod

        responses = types.ModuleType("fastapi.responses")
        class HTMLResponse:
            def __init__(self, content="", **kwargs):
                self.content = content
        class JSONResponse:
            def __init__(self, content=None, status_code=200, **kwargs):
                self.content = content
                self.status_code = status_code
        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

HAVE_REAL_PYDANTIC = False
if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
        HAVE_REAL_PYDANTIC = True
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        def Field(default=None, **kwargs):
            return default

        def field_validator(*args, **kwargs):
            return lambda f: f

        class BaseModel:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        pydantic.field_validator = field_validator
        sys.modules["pydantic"] = pydantic
else:
    HAVE_REAL_PYDANTIC = getattr(sys.modules["pydantic"], "__file__", None) is not None

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main
import models


class StackOverflowModelTests(unittest.TestCase):
    def test_safe_limit_bounds_and_fallbacks(self):
        self.assertEqual(models._safe_limit(5), 5)
        self.assertEqual(models._safe_limit("8"), 8)
        self.assertEqual(models._safe_limit(0), 1)
        self.assertEqual(models._safe_limit(-3), 1)
        self.assertEqual(models._safe_limit(50), 10)
        self.assertEqual(models._safe_limit(None, default=5), 5)
        self.assertEqual(models._safe_limit("", default=3), 3)
        self.assertEqual(models._safe_limit("invalid", default=5), 5)

    def test_safe_site_normalization(self):
        self.assertEqual(models._safe_site("stackoverflow"), "stackoverflow")
        self.assertEqual(models._safe_site("SERVERFAULT"), "serverfault")
        self.assertEqual(models._safe_site("  askubuntu  "), "askubuntu")
        self.assertEqual(models._safe_site(None), "stackoverflow")
        self.assertEqual(models._safe_site(""), "stackoverflow")
        self.assertEqual(models._safe_site("invalid site name with spaces"), "stackoverflow")
        self.assertEqual(models._safe_site("../hack"), "stackoverflow")

    def test_safe_tags_sanitization(self):
        self.assertEqual(models._safe_tags(["python", "asyncio"]), "python;asyncio")
        self.assertEqual(models._safe_tags("python, fastapi, react"), "python;fastapi;react")
        self.assertEqual(models._safe_tags("c++, c#"), "c++;c#")
        self.assertEqual(models._safe_tags(None), None)
        self.assertEqual(models._safe_tags(""), None)
        self.assertEqual(models._safe_tags(["valid", "invalid tag", "ok"]), "valid;ok")
        # caps at 5
        self.assertEqual(len(models._safe_tags("t1,t2,t3,t4,t5,t6").split(";")), 5)

    def test_coerce_bool(self):
        self.assertTrue(models._coerce_bool(True))
        self.assertFalse(models._coerce_bool(False))
        self.assertTrue(models._coerce_bool("1"))
        self.assertTrue(models._coerce_bool("true"))
        self.assertTrue(models._coerce_bool("yes"))
        self.assertFalse(models._coerce_bool("0"))
        self.assertFalse(models._coerce_bool("false"))
        self.assertFalse(models._coerce_bool("no"))
        self.assertIsNone(models._coerce_bool(None))
        self.assertIsNone(models._coerce_bool(""))
        self.assertIsNone(models._coerce_bool("maybe"))

    @unittest.skipUnless(HAVE_REAL_PYDANTIC, "Requires real pydantic package with validator support")
    def test_search_questions_request_validation(self):
        req = models.SearchQuestionsRequest(query="python asyncio", limit=8, site="superuser")
        self.assertEqual(req.query, "python asyncio")
        self.assertEqual(req.limit, 8)
        self.assertEqual(req.site, "superuser")

        # Null-coercion for optionals from Omi agent
        req_nulls = models.SearchQuestionsRequest(query="test", site=None, tags=None, accepted=None, limit=None)
        self.assertEqual(req_nulls.site, "stackoverflow")
        self.assertEqual(req_nulls.limit, 5)
        self.assertIsNone(req_nulls.tags)
        self.assertIsNone(req_nulls.accepted)

        with self.assertRaises(ValueError):
            models.SearchQuestionsRequest(query="")
        with self.assertRaises(ValueError):
            models.SearchQuestionsRequest(query="   ")

    @unittest.skipUnless(HAVE_REAL_PYDANTIC, "Requires real pydantic package with validator support")
    def test_get_question_request_validation(self):
        req = models.GetQuestionRequest(question_id=12345)
        self.assertEqual(req.question_id, 12345)
        self.assertEqual(req.site, "stackoverflow")

        req_str = models.GetQuestionRequest(question_id="9988", site="askubuntu")
        self.assertEqual(req_str.question_id, 9988)
        self.assertEqual(req_str.site, "askubuntu")

        with self.assertRaises(ValueError):
            models.GetQuestionRequest(question_id=None)
        with self.assertRaises(ValueError):
            models.GetQuestionRequest(question_id="not_an_int")

    @unittest.skipUnless(HAVE_REAL_PYDANTIC, "Requires real pydantic package with validator support")
    def test_get_top_answers_request_validation(self):
        req = models.GetTopAnswersRequest(question_id=55, limit=5)
        self.assertEqual(req.question_id, 55)
        self.assertEqual(req.limit, 5)

        req_null = models.GetTopAnswersRequest(question_id=55, site=None, limit=None)
        self.assertEqual(req_null.limit, 3)
        self.assertEqual(req_null.site, "stackoverflow")

        with self.assertRaises(ValueError):
            models.GetTopAnswersRequest(question_id=None)


class StackOverflowHelperTests(unittest.TestCase):
    def test_clean_text_removes_html_and_unescapes(self):
        html = "<p>Use <code>json.loads()</code> &amp; enjoy!</p><pre>data = []</pre>"
        cleaned = main._clean_text(html)
        self.assertIn("Use `json.loads()` & enjoy!", cleaned)
        self.assertIn("data = []", cleaned)
        self.assertNotIn("<p>", cleaned)
        self.assertNotIn("<code>", cleaned)
        self.assertEqual(main._clean_text(None), "")
        self.assertEqual(main._clean_text(""), "")

    def test_format_date_handles_valid_and_invalid_timestamps(self):
        self.assertEqual(main._format_date(1700000000), "2023-11-14")
        self.assertEqual(main._format_date(None), "unknown date")
        self.assertEqual(main._format_date(0), "unknown date")

    def test_question_url_generation(self):
        self.assertEqual(main._question_url("stackoverflow", 42), "https://stackoverflow.com/questions/42")
        self.assertEqual(main._question_url("serverfault", 100), "https://serverfault.com/questions/100")
        self.assertEqual(main._question_url("askubuntu", 200), "https://askubuntu.com/questions/200")
        self.assertEqual(main._question_url("customsite", 300), "https://customsite.stackexchange.com/questions/300")

    def test_format_answer_safe_with_null_owner(self):
        # Defensively tests regression where owner: None raises AttributeError
        item = {
            "owner": None,
            "score": 15,
            "is_accepted": True,
            "body": "<p>This is the accepted solution.</p>",
        }
        res = main._format_answer(item, 1)
        self.assertIn("1. unknown | 15 score | accepted", res)
        self.assertIn("This is the accepted solution.", res)

    def test_format_answer_safe_with_non_dict_owner(self):
        item = {
            "owner": "deleted user",
            "score": 0,
            "is_accepted": False,
            "body": "Some text",
        }
        res = main._format_answer(item, 2)
        self.assertIn("2. unknown | 0 score", res)

    def test_format_answer_truncates_long_body(self):
        long_body = "x" * 2000
        item = {"owner": {"display_name": "DevGuy"}, "score": 2, "body": long_body}
        res = main._format_answer(item, 1)
        self.assertIn("DevGuy", res)
        self.assertTrue(res.endswith("..."))
        self.assertLessEqual(len(res), 1700)

    def test_format_question_safe_with_null_and_malformed_tags(self):
        # Null tags
        item = {
            "title": "Problem with code",
            "question_id": 101,
            "score": 5,
            "answer_count": 1,
            "view_count": 20,
            "tags": None,
            "link": "https://stackoverflow.com/q/101",
        }
        res = main._format_question(item, 1, "stackoverflow")
        self.assertIn("Tags: no tags", res)

        # Non-list tags
        item["tags"] = "single-tag"
        res2 = main._format_question(item, 1, "stackoverflow")
        self.assertIn("Tags: single-tag", res2)

        # List with non-string elements
        item["tags"] = ["python", None, 123]
        res3 = main._format_question(item, 1, "stackoverflow")
        self.assertIn("Tags: python, 123", res3)


class StackOverflowEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_endpoint(self):
        res = await main.root()
        self.assertIn("Stack Overflow x Omi", res.body.decode("utf-8") if hasattr(res, "body") else res.content)

    async def test_health_endpoint(self):
        res = await main.health()
        self.assertEqual(res, {"status": "ok"})

    async def test_tools_manifest(self):
        manifest = await main.get_omi_tools_manifest()
        self.assertIn("tools", manifest)
        tool_names = [t["name"] for t in manifest["tools"]]
        self.assertIn("search_questions", tool_names)
        self.assertIn("get_question", tool_names)
        self.assertIn("get_top_answers", tool_names)

    async def test_search_questions_success(self):
        api_payload = {
            "items": [
                {
                    "title": "How to do async in Python?",
                    "question_id": 999,
                    "score": 42,
                    "answer_count": 3,
                    "view_count": 1500,
                    "accepted_answer_id": 1001,
                    "tags": ["python", "asyncio"],
                    "link": "https://stackoverflow.com/questions/999",
                }
            ]
        }
        req = models.SearchQuestionsRequest(query="python asyncio", site="stackoverflow", limit=5)
        with patch.object(main, "_request_json", new=AsyncMock(return_value=api_payload)):
            res = await main.search_questions(req)

        self.assertIsNone(res.error)
        self.assertIn("Stack Exchange results for 'python asyncio' on stackoverflow:", res.result)
        self.assertIn("How to do async in Python?", res.result)
        self.assertIn("42 score | 3 answers | 1500 views | accepted", res.result)

    async def test_search_questions_empty_results(self):
        api_payload = {"items": []}
        req = models.SearchQuestionsRequest(query="xyz9999nonexistent")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=api_payload)):
            res = await main.search_questions(req)

        self.assertIsNone(res.error)
        self.assertIn("No Stack Exchange questions found for 'xyz9999nonexistent'.", res.result)

    async def test_search_questions_filters_non_dict_items(self):
        api_payload = {"items": ["invalid item", None, {"title": "Valid question", "question_id": 12}]}
        req = models.SearchQuestionsRequest(query="test")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=api_payload)):
            res = await main.search_questions(req)

        self.assertIsNone(res.error)
        self.assertIn("Valid question", res.result)

    async def test_search_questions_api_error(self):
        req = models.SearchQuestionsRequest(query="test")
        with patch.object(main, "_request_json", new=AsyncMock(side_effect=ValueError("API quota exceeded"))):
            res = await main.search_questions(req)

        self.assertIsNone(res.result)
        self.assertIn("Stack Exchange search failed: API quota exceeded", res.error)

    async def test_get_question_success(self):
        api_payload = {
            "items": [
                {
                    "title": "FastAPI with Pydantic v2",
                    "question_id": 54321,
                    "creation_date": 1700000000,
                    "score": 10,
                    "answer_count": 2,
                    "view_count": 500,
                    "tags": ["fastapi", "pydantic"],
                    "body": "<p>Here is my question details.</p>",
                    "link": "https://stackoverflow.com/questions/54321",
                }
            ]
        }
        req = models.GetQuestionRequest(question_id=54321)
        with patch.object(main, "_request_json", new=AsyncMock(return_value=api_payload)):
            res = await main.get_question(req)

        self.assertIsNone(res.error)
        self.assertIn("FastAPI with Pydantic v2", res.result)
        self.assertIn("Question ID: 54321", res.result)
        self.assertIn("Here is my question details.", res.result)

    async def test_get_question_not_found(self):
        api_payload = {"items": []}
        req = models.GetQuestionRequest(question_id=999999)
        with patch.object(main, "_request_json", new=AsyncMock(return_value=api_payload)):
            res = await main.get_question(req)

        self.assertIsNone(res.result)
        self.assertIn("No question found for ID 999999 on stackoverflow.", res.error)

    async def test_get_top_answers_success_with_null_owner(self):
        api_payload = {
            "items": [
                {
                    "owner": None,
                    "score": 25,
                    "is_accepted": True,
                    "body": "<p>Best answer ever.</p>",
                },
                {
                    "owner": {"display_name": "Alice"},
                    "score": 8,
                    "is_accepted": False,
                    "body": "<p>Alternative approach.</p>",
                }
            ]
        }
        req = models.GetTopAnswersRequest(question_id=123)
        with patch.object(main, "_request_json", new=AsyncMock(return_value=api_payload)):
            res = await main.get_top_answers(req)

        self.assertIsNone(res.error)
        self.assertIn("Top answers for question 123 on stackoverflow:", res.result)
        self.assertIn("unknown | 25 score | accepted", res.result)
        self.assertIn("Alice | 8 score", res.result)

    async def test_get_top_answers_empty(self):
        api_payload = {"items": []}
        req = models.GetTopAnswersRequest(question_id=123)
        with patch.object(main, "_request_json", new=AsyncMock(return_value=api_payload)):
            res = await main.get_top_answers(req)

        self.assertIsNone(res.error)
        self.assertIn("No answers found for question ID 123 on stackoverflow.", res.result)

    async def test_request_json_backoff_and_error(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error_id": 400, "error_message": "Bad Request"}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp

        with patch.object(main, "_get_stack_client", new=AsyncMock(return_value=mock_client)):
            with self.assertRaises(ValueError) as ctx:
                await main._request_json("/test")
            self.assertIn("Bad Request", str(ctx.exception))

        mock_resp.json.return_value = {"backoff": 10}
        with patch.object(main, "_get_stack_client", new=AsyncMock(return_value=mock_client)):
            with self.assertRaises(ValueError) as ctx:
                await main._request_json("/test")
            self.assertIn("10 second backoff", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

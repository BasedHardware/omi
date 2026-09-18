"""
Hermetic regression tests for Omi Stack Overflow Integration App.
Tests generic code preservation, null owner handling, safe limits, endpoints, and error handling.
Runs with Python standard library only (stubs FastAPI/Pydantic if absent).
"""

import asyncio
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

# --- Hermetic stubs for environments without FastAPI/Pydantic installed ---
if "fastapi" not in sys.modules:
    fastapi_mod = ModuleType("fastapi")

    class DummyFastAPI:
        def __init__(self, *args, **kwargs):
            self.state = SimpleNamespace()

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    fastapi_mod.FastAPI = DummyFastAPI
    fastapi_responses = ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = lambda content, *args, **kwargs: content
    fastapi_mod.responses = fastapi_responses
    sys.modules["fastapi"] = fastapi_mod
    sys.modules["fastapi.responses"] = fastapi_responses

if "pydantic" not in sys.modules:
    pydantic_mod = ModuleType("pydantic")

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    pydantic_mod.BaseModel = DummyBaseModel
    sys.modules["pydantic"] = pydantic_mod

import httpx
import main


def _run(coro):
    return asyncio.run(coro)


class TestHelpersAndSanitization(unittest.TestCase):
    def test_clean_text_preserves_generic_types(self):
        # Regression test: unescaping before stripping tags must not erase code generics
        html_code = "<p>In C++, you should use <code>std::vector&lt;int&gt;</code> for dynamic arrays.</p>"
        cleaned = main._clean_text(html_code)
        self.assertIn("std::vector<int>", cleaned)

        html_generic = "Use <code>Map&lt;String, List&lt;Integer&gt;&gt;</code> in Java."
        cleaned2 = main._clean_text(html_generic)
        self.assertIn("Map<String, List<Integer>>", cleaned2)

    def test_safe_limit_boolean_coercion_and_bounds(self):
        self.assertEqual(main._safe_limit(None), 5)
        self.assertEqual(main._safe_limit(""), 5)
        self.assertEqual(main._safe_limit(True), 5)
        self.assertEqual(main._safe_limit(False), 5)
        self.assertEqual(main._safe_limit("invalid"), 5)
        self.assertEqual(main._safe_limit(3), 3)
        self.assertEqual(main._safe_limit(0), 1)
        self.assertEqual(main._safe_limit(50), 10)

    def test_safe_site(self):
        self.assertEqual(main._safe_site("stackoverflow"), "stackoverflow")
        self.assertEqual(main._safe_site("askubuntu"), "askubuntu")
        self.assertEqual(main._safe_site(None), "stackoverflow")
        self.assertEqual(main._safe_site("invalid$site!"), "stackoverflow")

    def test_format_answer_with_null_owner(self):
        # Regression test: Stack Overflow deleted accounts return owner as null
        answer_with_null_owner = {
            "owner": None,
            "score": 42,
            "is_accepted": True,
            "body": "<p>Here is the solution.</p>",
        }
        formatted = main._format_answer(answer_with_null_owner, 1)
        self.assertIn("unknown | 42 score | accepted", formatted)
        self.assertIn("Here is the solution.", formatted)


class TestSearchQuestionsEndpoint(unittest.TestCase):
    def test_search_missing_or_empty_query(self):
        res1 = _run(main.search_questions({}))
        self.assertIn("Missing required field: query", res1.error)

        res2 = _run(main.search_questions({"query": "   "}))
        self.assertIn("Missing required field: query", res2.error)

        res3 = _run(main.search_questions(None))
        self.assertIn("Request payload must be a JSON object", res3.error)

    def test_search_questions_success(self):
        sample_so_response = {
            "items": [
                {
                    "question_id": 12345,
                    "title": "How to sort a list in Python?",
                    "score": 150,
                    "answer_count": 8,
                    "view_count": 12000,
                    "accepted_answer_id": 12346,
                    "tags": ["python", "sorting"],
                    "link": "https://stackoverflow.com/questions/12345",
                }
            ]
        }
        with patch.object(main, "_request_json", new=AsyncMock(return_value=sample_so_response)):
            res = _run(main.search_questions({"query": "sort list python"}))

        self.assertIsNone(getattr(res, "error", None))
        self.assertIn("How to sort a list in Python?", res.result)
        self.assertIn("150 score | 8 answers | 12000 views | accepted", res.result)
        self.assertIn("https://stackoverflow.com/questions/12345", res.result)

    def test_search_questions_no_results(self):
        sample_empty = {"items": []}
        with patch.object(main, "_request_json", new=AsyncMock(return_value=sample_empty)):
            res = _run(main.search_questions({"query": "unlikelyquerynonexistent999"}))

        self.assertIsNone(getattr(res, "error", None))
        self.assertIn("No Stack Exchange questions found", res.result)


class TestGetQuestionEndpoint(unittest.TestCase):
    def test_get_question_missing_id(self):
        res1 = _run(main.get_question({}))
        self.assertIn("Missing required field: question_id", res1.error)

        res2 = _run(main.get_question(None))
        self.assertIn("Request payload must be a JSON object", res2.error)

    def test_get_question_success(self):
        sample_q = {
            "items": [
                {
                    "question_id": 99999,
                    "title": "Understanding Python asyncio",
                    "score": 300,
                    "answer_count": 5,
                    "view_count": 50000,
                    "body": "<p>Can someone explain <code>asyncio.run()</code>?</p>",
                    "tags": ["python", "asyncio"],
                    "link": "https://stackoverflow.com/questions/99999",
                }
            ]
        }
        with patch.object(main, "_request_json", new=AsyncMock(return_value=sample_q)):
            res = _run(main.get_question({"question_id": 99999}))

        self.assertIsNone(getattr(res, "error", None))
        self.assertIn("Understanding Python asyncio", res.result)
        self.assertIn("Can someone explain `asyncio.run()`?", res.result)


class TestGetTopAnswersEndpoint(unittest.TestCase):
    def test_get_top_answers_success(self):
        sample_answers = {
            "items": [
                {
                    "owner": {"display_name": "PythonExpert"},
                    "score": 95,
                    "is_accepted": True,
                    "body": "<p>Use <code>asyncio.gather()</code> for concurrent execution.</p>",
                }
            ]
        }
        with patch.object(main, "_request_json", new=AsyncMock(return_value=sample_answers)):
            res = _run(main.get_top_answers({"question_id": 99999}))

        self.assertIsNone(getattr(res, "error", None))
        self.assertIn("PythonExpert | 95 score | accepted", res.result)
        self.assertIn("Use `asyncio.gather()` for concurrent execution.", res.result)


class TestServiceRoutes(unittest.TestCase):
    def test_health_endpoint(self):
        res = _run(main.health())
        self.assertEqual(res, {"status": "ok"})

    def test_manifest_endpoint(self):
        manifest = _run(main.get_omi_tools_manifest())
        self.assertIn("tools", manifest)
        names = [t["name"] for t in manifest["tools"]]
        self.assertIn("search_questions", names)
        self.assertIn("get_question", names)
        self.assertIn("get_top_answers", names)


if __name__ == "__main__":
    unittest.main()

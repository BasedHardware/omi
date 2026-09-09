"""Hermetic handler regressions; no third-party dependencies or HTTP transport.

Import the entire production module with framework-only import stubs, then
replace its provider seam. These tests exercise real handlers and formatting,
not FastAPI routing, Pydantic validation, or the live Stack Exchange service.
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
    spec = importlib.util.spec_from_file_location("stack_overflow_app", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        "httpx": httpx,
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "pydantic": pydantic,
    }):
        spec.loader.exec_module(module)
    return module


app = load_app()

# Stack Exchange question contract: is_answered means at least one positively
# scored answer; accepted_answer_id identifies the owner's accepted answer.
# https://api.stackexchange.com/docs/types/question
STATES = (
    ("accepted", {"is_answered": True, "answer_count": 2, "accepted_answer_id": 99}, "accepted"),
    ("answered_unaccepted", {"is_answered": True, "answer_count": 2}, "not accepted"),
    ("unanswered", {"is_answered": False, "answer_count": 0}, "not accepted"),
)


def question(state):
    return {
        "question_id": 42,
        "title": "Python &amp; APIs",
        "score": 7,
        "view_count": 100,
        "tags": ["python"],
        "link": "https://stackoverflow.com/questions/42",
        "body": "<p>Question body text</p>",
        **state,
    }


class QuestionHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_acceptance_states(self):
        for name, state, status in STATES:
            with self.subTest(state=name):
                provider = AsyncMock(return_value={"items": [question(state)]})
                with patch.object(app, "_request_json", provider):
                    response = await app.search_questions({"query": "python", "accepted": status == "accepted"})
                self.assertIsNone(response.error)
                self.assertIn(f"   7 score | {state['answer_count']} answers | 100 views | {status}\n", response.result)
                self.assertIn("1. Python & APIs", response.result)
                self.assertIn("https://stackoverflow.com/questions/42", response.result)
                provider.assert_awaited_once_with("/search/advanced", {
                    "site": "stackoverflow", "q": "python", "pagesize": 5,
                    "order": "desc", "sort": "relevance",
                    "accepted": "true" if status == "accepted" else "false",
                })

    async def test_question_details_for_all_answer_states(self):
        for name, state, _ in STATES:
            with self.subTest(state=name):
                provider = AsyncMock(return_value={"items": [question(state)]})
                with patch.object(app, "_request_json", provider):
                    response = await app.get_question({"question_id": "42"})
                self.assertIsNone(response.error)
                self.assertIn("Python & APIs\nQuestion ID: 42\n", response.result)
                self.assertIn(f"Score: 7 | Answers: {state['answer_count']} | Views: 100\n", response.result)
                self.assertIn("Question body:\nQuestion body text", response.result)
                provider.assert_awaited_once_with("/questions/42", {
                    "site": "stackoverflow", "filter": "withbody", "pagesize": 1,
                })

    async def test_provider_errors_are_returned_by_both_handlers(self):
        for handler, payload, prefix in (
            (app.search_questions, {"query": "python"}, "Stack Exchange search failed"),
            (app.get_question, {"question_id": 42}, "Stack Exchange question request failed"),
        ):
            with self.subTest(handler=handler.__name__):
                with patch.object(app, "_request_json", AsyncMock(side_effect=ValueError("provider unavailable"))):
                    response = await handler(payload)
                self.assertIsNone(response.result)
                self.assertEqual(response.error, f"{prefix}: provider unavailable")


if __name__ == "__main__":
    unittest.main()

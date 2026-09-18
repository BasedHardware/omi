"""Hermetic Stack Overflow plugin regressions (issue #14126).

Import the production module with framework-only stubs, then exercise its real
formatters and handlers. No network, credentials, or third-party runtime
packages are required. The suite pins the crash paths the issue reported:
null owner objects, null/non-list tags, non-dict API payloads, and the
HTTP-200 validation-error envelope the Omi chat agent requires.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            self.handlers = {}

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

        def exception_handler(self, *args, **kwargs):
            return lambda handler: handler

        def add_middleware(self, *args, **kwargs):
            pass

    class _Field:
        def __init__(self, default=None, **kwargs):
            self.default = default

    def Field(default=None, **kwargs):
        return default

    def _passthrough_decorator(*dargs, **dkwargs):
        def wrap(fn):
            return fn
        return wrap

    class BaseModel:
        def __init__(self, **kwargs):
            self.result = kwargs.get("result")
            self.error = kwargs.get("error")
            for key, value in kwargs.items():
                setattr(self, key, value)

        def model_dump(self):
            return dict(self.__dict__)

    class RequestValidationError(Exception):
        def __init__(self, errors=None):
            super().__init__("validation error")
            self._errors = errors or []

        def errors(self):
            return self._errors

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", response=None):
            super().__init__(message)
            self.response = response or type("R", (), {"status_code": 500})()

    httpx = ModuleType("httpx")
    httpx.AsyncClient = object
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = object
    exceptions = ModuleType("fastapi.exceptions")
    exceptions.RequestValidationError = RequestValidationError
    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.JSONResponse = lambda status_code=200, content=None: {
        "status_code": status_code, "content": content}

    models = ModuleType("models")
    models.ChatToolResponse = BaseModel
    models.SearchQuestionsRequest = BaseModel
    models.GetQuestionRequest = BaseModel
    models.GetTopAnswersRequest = BaseModel

    spec = importlib.util.spec_from_file_location(
        "stack_overflow_app", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        "httpx": httpx,
        "fastapi": fastapi,
        "fastapi.exceptions": exceptions,
        "fastapi.responses": responses,
        "models": models,
    }):
        spec.loader.exec_module(module)
    module._RequestValidationError = RequestValidationError
    return module


app = load_app()


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FormatAnswerGuardsTest(unittest.TestCase):
    """Deleted/anonymized users arrive as "owner": null — get() with a
    default only helps when the key is absent, not when it stores None."""

    def test_null_owner_renders_unknown(self):
        out = app._format_answer({"owner": None, "score": 4, "body": "b"}, 1)
        self.assertIn("unknown", out)

    def test_missing_owner_renders_unknown(self):
        out = app._format_answer({"score": 4, "body": "b"}, 1)
        self.assertIn("unknown", out)

    def test_owner_missing_display_name_renders_unknown(self):
        out = app._format_answer({"owner": {}, "score": 1, "body": "x"}, 1)
        self.assertIn("unknown", out)

    def test_owner_display_name_used(self):
        out = app._format_answer(
            {"owner": {"display_name": "alice"}, "score": 9, "body": "b"}, 1)
        self.assertIn("alice", out)

    def test_null_score_renders_zero_not_none(self):
        out = app._format_answer({"owner": None, "score": None, "body": "b"}, 1)
        self.assertIn("0 score", out)
        self.assertNotIn("None", out)

    def test_non_dict_item_does_not_crash(self):
        out = app._format_answer(None, 1)
        self.assertIn("unknown", out)


class FormatQuestionGuardsTest(unittest.TestCase):
    def test_null_tags_render_no_tags(self):
        out = app._format_question(
            {"title": "q", "tags": None, "score": 1}, 1, "stackoverflow")
        self.assertIn("no tags", out)

    def test_non_list_tags_render_no_tags(self):
        out = app._format_question(
            {"title": "q", "tags": "python", "score": 1}, 1, "stackoverflow")
        self.assertIn("no tags", out)

    def test_non_string_tag_members_skipped(self):
        out = app._format_question(
            {"title": "q", "tags": ["python", 7, None, "django"], "score": 1},
            1, "stackoverflow")
        self.assertIn("python, django", out)

    def test_null_counts_render_zero(self):
        out = app._format_question(
            {"title": "q", "tags": [], "score": None,
             "answer_count": None, "view_count": None}, 1, "stackoverflow")
        self.assertIn("0 score", out)
        self.assertIn("0 answers", out)
        self.assertIn("0 views", out)

    def test_non_dict_item_renders_untitled(self):
        out = app._format_question("not-a-dict", 1, "stackoverflow")
        self.assertIn("Untitled question", out)


class RequestJsonGuardsTest(unittest.TestCase):
    """_request_json must reject non-dict payloads before .get() is called."""

    def _patch_client(self, payload):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        class Client:
            is_closed = False

            async def get(self, *a, **k):
                return Resp()

        return patch.object(app, "_get_stack_client", return_value=Client())

    def test_list_payload_raises_value_error(self):
        with self._patch_client([1, 2, 3]):
            with self.assertRaises(ValueError):
                run(app._request_json("/x"))

    def test_none_payload_raises_value_error(self):
        with self._patch_client(None):
            with self.assertRaises(ValueError):
                run(app._request_json("/x"))

    def test_error_id_raises_with_message(self):
        with self._patch_client({"error_id": 502, "error_message": "throttled"}):
            with self.assertRaises(ValueError):
                run(app._request_json("/x"))

    def test_dict_payload_returns(self):
        with self._patch_client({"items": []}):
            self.assertEqual(run(app._request_json("/x")), {"items": []})


class HandlerGuardsTest(unittest.TestCase):
    """Endpoint handlers must degrade on malformed items, not crash."""

    def _patch_request_json(self, payload):
        async def fake(*a, **k):
            return payload
        return patch.object(app, "_request_json", side_effect=fake)

    def test_search_questions_skips_non_dict_items(self):
        req = app.SearchQuestionsRequest(
            query="json", site="stackoverflow", limit=5, tags=None,
            accepted=None)
        with self._patch_request_json(
                {"items": [None, {"title": "real q", "question_id": 1,
                                  "tags": ["x"], "score": 2}, "junk"]}):
            out = run(app.search_questions(req))
        self.assertIsNone(out.error)
        self.assertIn("real q", out.result)
        self.assertNotIn("None", out.result)

    def test_search_questions_empty(self):
        req = app.SearchQuestionsRequest(
            query="x", site="stackoverflow", limit=5, tags=None, accepted=None)
        with self._patch_request_json({"items": []}):
            out = run(app.search_questions(req))
        self.assertIn("No Stack Exchange questions", out.result)

    def test_get_question_null_counts(self):
        req = app.GetQuestionRequest(question_id=5, site="stackoverflow")
        with self._patch_request_json({"items": [{
                "title": "q", "tags": None, "score": None,
                "answer_count": None, "view_count": None,
                "creation_date": 1, "question_id": 5}]}):
            out = run(app.get_question(req))
        self.assertIsNone(out.error)
        self.assertIn("Score: 0", out.result)

    def test_get_top_answers_null_owner(self):
        req = app.GetTopAnswersRequest(
            question_id=9, site="stackoverflow", limit=3)
        with self._patch_request_json({"items": [{
                "owner": None, "score": 3, "body": "use json.loads"}]}):
            out = run(app.get_top_answers(req))
        self.assertIsNone(out.error)
        self.assertIn("unknown", out.result)

    def test_get_top_answers_items_not_list(self):
        req = app.GetTopAnswersRequest(
            question_id=9, site="stackoverflow", limit=3)
        with self._patch_request_json({"items": "nope"}):
            out = run(app.get_top_answers(req))
        self.assertIn("No answers found", out.result)

    def test_search_questions_http_error_envelope(self):
        req = app.SearchQuestionsRequest(
            query="x", site="stackoverflow", limit=5, tags=None, accepted=None)

        async def boom(*a, **k):
            raise app.httpx.HTTPError("connection refused")

        with patch.object(app, "_request_json", side_effect=boom):
            out = run(app.search_questions(req))
        self.assertIsNone(out.result)
        self.assertIn("failed", out.error)


class ValidationHandlerTest(unittest.TestCase):
    """Raw 422s crash the Omi chat agent — the handler must return HTTP 200
    with the error inside the ChatToolResponse envelope."""

    def test_validation_error_returns_200_envelope(self):
        exc = app._RequestValidationError(
            errors=[{"loc": ["body", "query"], "msg": "field required"}])
        resp = run(app.validation_exception_handler(None, exc))
        self.assertEqual(resp["status_code"], 200)
        self.assertIn("query", resp["content"]["error"])

    def test_validation_error_without_loc(self):
        exc = app._RequestValidationError(errors=[{"msg": "bad body"}])
        resp = run(app.validation_exception_handler(None, exc))
        self.assertEqual(resp["status_code"], 200)
        self.assertIn("bad body", resp["content"]["error"])


if __name__ == "__main__":
    unittest.main()

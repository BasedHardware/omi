"""Hermetic regression tests for plugins/iq_rating/main.py.

Standard library only: fastapi, fastapi.responses and requests are replaced
with minimal stubs before importing the module under test so the suite runs
without site-packages (the manifest lane runs plain python3).

Covers the crash reported in #13980: OpenAI chat-completion responses whose
`choices` array is empty (or whose payload is not a dict at all) raised
IndexError/TypeError at `result["choices"][0]["message"]["content"]` in both
`filter_names_with_openai` and `calculate_iq_with_ai`, and a non-list
`context_snippets` value raised TypeError on the `[:10]` slice. Both now
degrade to the existing fallback paths instead of taking down the run.
"""

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_module_stubs():
    fastapi = types.ModuleType("fastapi")

    class _Router:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get
        put = get
        delete = get
        on_event = get

    class _App(_Router):
        def include_router(self, *args, **kwargs):
            pass

    fastapi.FastAPI = _App
    fastapi.APIRouter = _Router
    fastapi.Query = lambda default=None, **kwargs: default
    fastapi.HTTPException = type("HTTPException", (Exception,), {})

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.JSONResponse = dict

    sys.modules["fastapi"] = fastapi
    sys.modules["fastapi.responses"] = responses
    sys.modules["requests"] = types.ModuleType("requests")


_install_module_stubs()

import main  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _person(name="Alice", snippets=None):
    return {
        "name": name,
        "id": name.lower(),
        "mention_count": 3,
        "context_snippets": ["said something smart"] if snippets is None else snippets,
    }


class FilterNamesTests(unittest.TestCase):
    def setUp(self):
        self._key = main.OPENAI_API_KEY
        main.OPENAI_API_KEY = "test-key"

    def tearDown(self):
        main.OPENAI_API_KEY = self._key

    def test_empty_choices_does_not_crash(self):
        with mock.patch.object(main, "requests") as req:
            req.post.return_value = _FakeResponse(200, {"choices": []})
            result = main.filter_names_with_openai(["Alice", "Bob"])
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_null_content_does_not_crash(self):
        with mock.patch.object(main, "requests") as req:
            req.post.return_value = _FakeResponse(
                200, {"choices": [{"message": {"role": "assistant", "content": None}}]}
            )
            result = main.filter_names_with_openai(["Alice", "Bob"])
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_non_dict_payload_does_not_crash(self):
        with mock.patch.object(main, "requests") as req:
            req.post.return_value = _FakeResponse(200, ["not", "a", "dict"])
            result = main.filter_names_with_openai(["Alice"])
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_valid_response_still_filters(self):
        with mock.patch.object(main, "requests") as req:
            req.post.return_value = _FakeResponse(
                200, {"choices": [{"message": {"content": "Alice, Bob"}}]}
            )
            result = main.filter_names_with_openai(["Alice", "Bob"])
        self.assertEqual(result, ["Alice", "Bob"])


class CalculateIqTests(unittest.TestCase):
    def setUp(self):
        self._key = main.OPENAI_API_KEY
        main.OPENAI_API_KEY = "test-key"

    def tearDown(self):
        main.OPENAI_API_KEY = self._key

    def test_empty_choices_falls_back_to_random(self):
        people = {"alice": _person("Alice"), "bob": _person("Bob")}
        with mock.patch.object(main, "requests") as req, \
             mock.patch.object(main.time, "sleep", lambda *_: None):
            req.post.return_value = _FakeResponse(200, {"choices": []})
            result = main.calculate_iq_with_ai(people)
        self.assertEqual(set(result), {"alice", "bob"})
        for v in result.values():
            self.assertIn("iq", v)
            self.assertGreaterEqual(v["iq"], 70)
            self.assertLessEqual(v["iq"], 160)

    def test_null_content_and_choices_guard(self):
        people = {"alice": _person("Alice")}
        with mock.patch.object(main, "requests") as req, \
             mock.patch.object(main.time, "sleep", lambda *_: None):
            req.post.return_value = _FakeResponse(
                200, {"choices": [{"message": {"role": "assistant", "content": None}}]}
            )
            result = main.calculate_iq_with_ai(people)
        self.assertIn("alice", result)
        self.assertIn("iq", result["alice"])

    def test_non_list_context_snippets_does_not_crash(self):
        people = {
            "bob": {
                "name": "Bob",
                "id": "bob",
                "mention_count": 15,
                "context_snippets": ("tuple snippet", None, 12345, "good guy"),
            },
            "charlie": {
                "name": "Charlie",
                "id": "charlie",
                "mention_count": 10,
                "context_snippets": None,
            },
        }
        with mock.patch.object(main, "requests") as req, \
             mock.patch.object(main.time, "sleep", lambda *_: None):
            req.post.return_value = _FakeResponse(200, {"choices": []})
            result = main.calculate_iq_with_ai(people)
        self.assertIn("bob", result)
        self.assertIn("charlie", result)

    def test_non_dict_payload_falls_back(self):
        people = {"alice": _person("Alice")}
        with mock.patch.object(main, "requests") as req, \
             mock.patch.object(main.time, "sleep", lambda *_: None):
            req.post.return_value = _FakeResponse(200, "not a dict")
            result = main.calculate_iq_with_ai(people)
        self.assertIn("alice", result)
        self.assertIn("iq", result["alice"])

    def test_valid_response_scores(self):
        people = {"alice": _person("Alice")}
        payload = {
            "choices": [
                {"message": {"content": '[{"name": "Alice", "iq": 130, "is_name": true}]'}}
            ]
        }
        with mock.patch.object(main, "requests") as req, \
             mock.patch.object(main.time, "sleep", lambda *_: None):
            req.post.return_value = _FakeResponse(200, payload)
            result = main.calculate_iq_with_ai(people)
        self.assertIn("iq", result["alice"])
        self.assertEqual(result["alice"]["iq"], 130)


if __name__ == "__main__":
    unittest.main()

"""Regression: a null `content` in a chat completion must not discard results.

OpenAI-compatible responses set `"content": null` whenever the model answers
with tool calls instead of text, and some providers do the same on a refusal.
`message.get("content", "")` does not apply its default for a present-but-null
key, so `.strip()` raised AttributeError on a documented response shape.

In `filter_names_with_openai` the `try` wraps the whole batch loop, so that
AttributeError escaped the loop and the function returned the *unfiltered*
input — defeating the `# On error, skip this batch` intent and letting
non-names through silently. `analyze_iq_with_openai` had the per-batch variant.

Runs under standard library unittest without third-party dependencies.
"""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class Router:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get
    delete = get
    put = get
    patch = get
    on_event = get

    def include_router(self, *args, **kwargs):
        return None


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


class Response:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


fastapi_responses = module(
    "fastapi.responses",
    HTMLResponse=lambda *a, **k: None,
    JSONResponse=lambda *a, **k: None,
)
stubs = {
    "fastapi": module(
        "fastapi",
        APIRouter=Router,
        FastAPI=Router,
        Query=lambda *a, **k: None,
        HTTPException=Exception,
        responses=fastapi_responses,
    ),
    "fastapi.responses": fastapi_responses,
    "requests": module("requests", post=lambda *a, **k: None, get=lambda *a, **k: None),
}

spec = importlib.util.spec_from_file_location(
    "iq_rating_under_test", Path(__file__).with_name("main.py")
)
iq = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(iq)


def completion(content):
    return {"choices": [{"message": {"content": content}}]}


class CompletionText(unittest.TestCase):
    def test_returns_stripped_text(self):
        self.assertEqual(iq._completion_text({"content": "  Ada, Alan  "}), "Ada, Alan")

    def test_null_content_yields_empty_string(self):
        # The tool-call shape: content is null, tool_calls carries the payload.
        self.assertEqual(iq._completion_text({"content": None, "tool_calls": []}), "")

    def test_missing_content_yields_empty_string(self):
        self.assertEqual(iq._completion_text({"role": "assistant"}), "")

    def test_non_string_content_yields_empty_string(self):
        # Some gateways return content as a list of parts.
        for value in ([{"type": "text", "text": "hi"}], 42, True, {"text": "hi"}):
            with self.subTest(value=value):
                self.assertEqual(iq._completion_text({"content": value}), "")

    def test_non_dict_message_yields_empty_string(self):
        for value in (None, "text", [], 7):
            with self.subTest(value=value):
                self.assertEqual(iq._completion_text(value), "")


class FilterNamesSurvivesNullContent(unittest.TestCase):
    """The whole-loop `try` made one null answer discard every batch."""

    def setUp(self):
        self.key = patch.object(iq, "OPENAI_API_KEY", "sk-test")
        self.key.start()
        self.addCleanup(self.key.stop)

    def test_null_content_does_not_return_the_unfiltered_input(self):
        names = [f"name{n}" for n in range(60)]  # two batches of 50
        replies = [completion(None), completion("name50, name51")]
        calls = {"n": 0}

        def fake_post(*args, **kwargs):
            index = min(calls["n"], len(replies) - 1)
            calls["n"] += 1
            return Response(replies[index])

        with patch.object(iq.requests, "post", fake_post):
            result = iq.filter_names_with_openai(names)

        # Before the fix this raised inside the loop and returned `names`.
        self.assertNotEqual(result, names)
        self.assertEqual(result, ["name50", "name51"])

    def test_all_null_content_yields_no_names_rather_than_all(self):
        names = ["ada", "alan"]
        with patch.object(iq.requests, "post", lambda *a, **k: Response(completion(None))):
            self.assertEqual(iq.filter_names_with_openai(names), [])

    def test_normal_answer_still_filters(self):
        names = ["ada", "chair"]
        with patch.object(iq.requests, "post", lambda *a, **k: Response(completion("ada"))):
            self.assertEqual(iq.filter_names_with_openai(names), ["ada"])

    def test_none_sentinel_still_means_no_valid_names(self):
        names = ["chair", "table"]
        with patch.object(iq.requests, "post", lambda *a, **k: Response(completion("NONE"))):
            self.assertEqual(iq.filter_names_with_openai(names), [])

    def test_empty_input_short_circuits(self):
        self.assertEqual(iq.filter_names_with_openai([]), [])


if __name__ == "__main__":
    unittest.main()

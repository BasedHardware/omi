"""Hermetic regression tests for plugins/omi-stack-overflow-app/main.py.

Standard library only: httpx, fastapi, and pydantic are replaced with minimal
stubs before importing the module under test so the suite runs without
site-packages (the manifest lane runs plain python3).

Covers BasedHardware/omi#14126: Stack Exchange answers/questions with an
explicit `"owner": None` or `"tags": None` (as returned for deleted/anonymized
users and some deleted-question payloads) crashed `_format_answer`/
`_format_question` with AttributeError/TypeError instead of formatting
cleanly.
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = ("httpx", "fastapi", "fastapi.responses", "pydantic")


def _install_module_stubs():
    httpx = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", *, response=None):
            super().__init__(message)
            self.response = response

    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.AsyncClient = object
    sys.modules["httpx"] = httpx

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
    responses.HTMLResponse = str
    sys.modules["fastapi.responses"] = responses

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **data):
            for name, default in getattr(type(self), "__annotations__", {}).items():
                setattr(self, name, getattr(type(self), name, None))
            for key, value in data.items():
                setattr(self, key, value)

    pydantic.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic


_saved_modules = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
_install_module_stubs()
try:
    import main  # noqa: E402
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original
    del _name, _original, _saved_modules


class FormatQuestionTests(unittest.TestCase):
    def _item(self, **overrides):
        item = {
            "title": "How do I parse JSON?",
            "question_id": 1,
            "score": 3,
            "answer_count": 2,
            "view_count": 10,
            "is_answered": True,
            "accepted_answer_id": None,
            "tags": ["python"],
            "link": "https://stackoverflow.com/q/1",
        }
        item.update(overrides)
        return item

    def test_uses_accepted_answer_id_not_is_answered(self):
        out = main._format_question(self._item(), 1, "stackoverflow")
        self.assertIn("| not accepted", out)
        self.assertEqual(out.count("accepted"), 1)  # only inside "not accepted"

    def test_marks_accepted_when_id_present(self):
        out = main._format_question(self._item(accepted_answer_id=99), 1, "stackoverflow")
        self.assertIn("accepted", out)
        self.assertNotIn("not accepted", out)

    def test_null_tags_does_not_raise(self):
        out = main._format_question(self._item(tags=None), 1, "stackoverflow")
        self.assertIn("Tags: no tags", out)

    def test_non_string_tags_are_stringified(self):
        out = main._format_question(self._item(tags=[1, "python", None]), 1, "stackoverflow")
        self.assertIn("Tags: 1, python, None", out)


class FormatAnswerTests(unittest.TestCase):
    def test_null_owner_does_not_raise(self):
        item = {"owner": None, "score": 5, "is_accepted": False, "body": "<p>Use json.loads</p>"}
        out = main._format_answer(item, 1)
        self.assertIn("unknown", out)

    def test_missing_owner_display_name_falls_back_to_unknown(self):
        item = {"owner": {}, "score": 5, "is_accepted": False, "body": "<p>Use json.loads</p>"}
        out = main._format_answer(item, 1)
        self.assertIn("unknown", out)

    def test_present_owner_display_name_is_used(self):
        item = {
            "owner": {"display_name": "jdoe"},
            "score": 5,
            "is_accepted": True,
            "body": "<p>Use json.loads</p>",
        }
        out = main._format_answer(item, 1)
        self.assertIn("jdoe", out)
        self.assertIn("accepted", out)


if __name__ == "__main__":
    unittest.main()

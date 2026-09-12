"""Hermetic regression tests for question extraction in plugins/notifications/hey_omi.py.

Standard library only: third-party imports (fastapi, pydantic, openai,
requests, tenacity) are replaced with minimal stubs before importing the
module under test so the suite runs without site-packages.

Covers the dropped-question defect: the webhook extracted the question
spoken after "hey omi" by splitting the segment on the literal 'omi,' —
so a user who says "hey omi what is the weather" without the comma lost
every word of the question, and the next segment's text was answered
instead (or nothing was answered at all).
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("HEY_OMI_APP_ID", "test-app-id")
os.environ.setdefault("HEY_OMI_APP_SECRET", "test-app-secret")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_module_stubs():
    openai = types.ModuleType("openai")

    class _OpenAI:
        def __init__(self, *args, **kwargs):
            pass

    openai.OpenAI = _OpenAI
    sys.modules["openai"] = openai

    tenacity = types.ModuleType("tenacity")
    tenacity.retry = lambda *a, **k: (lambda f: f)
    tenacity.stop_after_attempt = lambda *a, **k: None
    tenacity.wait_exponential = lambda *a, **k: None
    sys.modules["tenacity"] = tenacity

    requests = types.ModuleType("requests")
    requests.post = lambda *a, **k: types.SimpleNamespace(
        status_code=200, raise_for_status=lambda: None
    )
    sys.modules["requests"] = requests

    fastapi = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass

        def post(self, *args, **kwargs):
            return lambda f: f

        def get(self, *args, **kwargs):
            return lambda f: f

    fastapi.APIRouter = APIRouter
    fastapi.Request = object
    fastapi.HTTPException = HTTPException
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")
    responses.JSONResponse = dict
    sys.modules["fastapi.responses"] = responses

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for klass in reversed(type(self).__mro__):
                for field in getattr(klass, "__annotations__", {}):
                    if field in kwargs:
                        setattr(self, field, kwargs[field])
                    elif hasattr(type(self), field):
                        setattr(self, field, getattr(type(self), field))
                    else:
                        setattr(self, field, None)

        def dict(self):
            return dict(self.__dict__)

    pydantic.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic


_install_module_stubs()
import hey_omi  # noqa: E402


class _Clock:
    """Controllable time source patched over hey_omi.time.time."""

    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now


class HeyOmiQuestionExtractionTests(unittest.TestCase):
    def setUp(self):
        hey_omi.message_buffer.buffers.clear()
        hey_omi.notification_cooldowns.clear()
        self.clock = _Clock()
        self.openai_calls = []
        self.notifications = []
        self._patches = [
            mock.patch.object(hey_omi.time, "time", self.clock),
            mock.patch.object(
                hey_omi,
                "get_openai_response",
                lambda text: self.openai_calls.append(text) or "test answer",
            ),
            mock.patch.object(
                hey_omi,
                "send_omi_notification",
                lambda uid, msg: self.notifications.append((uid, msg)) or True,
            ),
        ]
        for patcher in self._patches:
            patcher.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def _post(self, session_id, texts, uid="u1"):
        segments = [{"text": t} for t in texts]
        request = hey_omi.WebhookRequest(
            session_id=session_id, segments=segments, uid=uid
        )
        return asyncio.run(hey_omi.webhook(request))

    def _buffer(self, session_id):
        return hey_omi.message_buffer.buffers[session_id]

    def test_question_without_comma_is_collected(self):
        # "hey omi <question>" with no comma is the common spoken form; the
        # words after the trigger must reach collected_question.
        self._post("s1", ["hey omi what is the weather"])
        self.assertTrue(self._buffer("s1")["trigger_detected"])
        self.assertEqual(
            self._buffer("s1")["collected_question"], ["what is the weather"]
        )

    def test_hey_comma_variant_without_second_comma_is_collected(self):
        self._post("s1", ["hey, omi tell me a joke"])
        self.assertEqual(
            self._buffer("s1")["collected_question"], ["tell me a joke"]
        )

    def test_question_with_comma_still_collected(self):
        self._post("s1", ["hey omi, what time is it"])
        self.assertEqual(
            self._buffer("s1")["collected_question"], ["what time is it"]
        )

    def test_bare_trigger_collects_no_question(self):
        self._post("s1", ["hey omi"])
        self.assertTrue(self._buffer("s1")["trigger_detected"])
        self.assertEqual(self._buffer("s1")["collected_question"], [])

    def test_partial_trigger_question_without_comma_is_collected(self):
        # Trigger split across two segments: "hey" then "omi <question>".
        self._post("s1", ["hey", "omi what is the plan"])
        self.assertTrue(self._buffer("s1")["trigger_detected"])
        self.assertEqual(
            self._buffer("s1")["collected_question"], ["what is the plan"]
        )

    def test_comma_free_question_reaches_openai_after_window(self):
        self._post("s1", ["hey omi what is the weather?"])
        self.clock.now += 11
        self._post("s1", ["some later words"])
        self.assertEqual(self.openai_calls, ["what is the weather?"])
        self.assertEqual(self.notifications, [("u1", "test answer")])

    def test_leading_omi_does_not_pollute_trigger_question(self):
        # A stray 'omi' earlier in the segment must not anchor extraction:
        # the question lives after the trigger phrase itself.
        self._post("s1", ["omi hey omi, what time is it"])
        self.assertEqual(
            self._buffer("s1")["collected_question"], ["what time is it"]
        )


if __name__ == "__main__":
    unittest.main()

"""Hermetic regression tests for plugins/notifications/hey_omi.py.

Standard library only: third-party imports (fastapi, pydantic, openai,
requests, tenacity) are replaced with minimal stubs before importing the
module under test so the suite runs without site-packages.

Covers the stale-trigger defect: once "hey omi" arms the session but no
question is collected inside the aggregation window, the armed state used
to survive forever — and because complete-trigger detection requires
`not trigger_detected`, every later "hey omi" in that session was ignored.
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


class HeyOmiWebhookTests(unittest.TestCase):
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

    def test_normal_trigger_collects_question_and_notifies(self):
        self._post("s1", ["hey omi, what time is it?"])
        self.assertTrue(self._buffer("s1")["trigger_detected"])
        self.assertEqual(self._buffer("s1")["collected_question"], ["what time is it?"])

        self.clock.now += 11  # past the 10s aggregation window
        self._post("s1", ["anything else"])

        self.assertEqual(self.openai_calls, ["what time is it?"])
        self.assertEqual(len(self.notifications), 1)

    def test_stale_trigger_expires_and_new_trigger_is_detected(self):
        # Arm the trigger with no question.
        self._post("s1", ["hey omi"])
        self.assertTrue(self._buffer("s1")["trigger_detected"])

        # Past the 15s hard cap with no question: a new "hey omi" must work.
        self.clock.now += 20
        self._post("s1", ["hey omi, what time is it?"])

        self.assertTrue(self._buffer("s1")["trigger_detected"])
        self.assertEqual(self._buffer("s1")["collected_question"], ["what time is it?"])

        self.clock.now += 11
        self._post("s1", ["follow up"])
        self.assertEqual(self.openai_calls, ["what time is it?"])
        self.assertEqual(len(self.notifications), 1)

    def test_stale_trigger_without_question_fires_no_notification(self):
        self._post("s1", ["hey omi"])
        self.clock.now += 20
        self._post("s1", ["unrelated chatter with a question mark?"])

        self.assertEqual(self.openai_calls, [])
        self.assertEqual(self.notifications, [])
        # The dead trigger must be cleared rather than left armed forever.
        self.assertFalse(self._buffer("s1")["trigger_detected"])

    def test_armed_trigger_with_question_is_not_expired(self):
        self._post("s1", ["hey omi, what is the weather?"])
        self.clock.now += 20  # beyond 15s cap, but a question was collected
        self._post("s1", ["more context"])

        # Existing design fires the collected question on the first
        # post-window segment; expiry must not drop it.
        self.assertEqual(len(self.notifications), 1)
        self.assertIn("what is the weather", self.openai_calls[0])

    def test_stale_question_without_mark_does_not_swallow_new_trigger(self):
        # Cubic P2: a collected fragment with no '?' used to keep the
        # trigger armed, so a later "hey omi" was ignored.
        self._post("s1", ["hey omi, tell me the weather"])
        self.assertEqual(self._buffer("s1")["collected_question"], ["tell me the weather"])

        self.clock.now += 20
        self._post("s1", ["hey omi, what time is it?"])

        self.assertTrue(self._buffer("s1")["trigger_detected"])
        self.assertEqual(self._buffer("s1")["collected_question"], ["what time is it?"])
        self.assertEqual(self.openai_calls, [])

        self.clock.now += 11
        self._post("s1", ["follow up"])
        self.assertEqual(self.openai_calls, ["what time is it?"])
        self.assertEqual(len(self.notifications), 1)


if __name__ == "__main__":
    unittest.main()

"""Hermetic regression tests for question extraction and hardening in plugins/notifications/hey_omi.py.

Standard library only: third-party imports (fastapi, pydantic, openai,
requests, tenacity) are replaced with minimal stubs before importing the
module under test so the suite runs without site-packages.

Covers:
1. Question extraction with and without commas across triggers.
2. Safe lazy credential handling without import-time crashes.
3. Memory leak defense in session buffer and cooldown dictionary pruning.
4. Malformed and None segment input guards.
5. Defensive OpenAI response fallbacks and timeout protection.
6. Validation and exception classification in OMI notification delivery.
7. Health, status, and setup-status endpoints.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_module_stubs():
    openai = types.ModuleType("openai")

    class _OpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=lambda *a, **k: types.SimpleNamespace(
                        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="stubbed answer"))]
                    )
                )
            )

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
    requests.exceptions = types.SimpleNamespace(
        RequestException=Exception,
        Timeout=Exception,
        HTTPError=Exception,
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
        self._post("s1", ["omi hey omi, what time is it"])
        self.assertEqual(
            self._buffer("s1")["collected_question"], ["what time is it"]
        )


class HeyOmiHardeningTests(unittest.TestCase):
    def setUp(self):
        hey_omi.message_buffer.buffers.clear()
        hey_omi.notification_cooldowns.clear()
        self.clock = _Clock(2000.0)
        self.patch_time = mock.patch.object(hey_omi.time, "time", self.clock)
        self.patch_time.start()
        self.addCleanup(self.patch_time.stop)

    def test_credential_helpers_without_env_vars(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            key = hey_omi.get_openai_api_key()
            app_id, app_secret = hey_omi.get_omi_credentials()
            self.assertIsInstance(key, str)
            self.assertIsInstance(app_id, str)
            self.assertIsInstance(app_secret, str)

    def test_unconfigured_openai_returns_fallback_immediately(self):
        with mock.patch.object(hey_omi, "get_openai_client", return_value=None):
            answer = hey_omi.get_openai_response("what is the time?")
            self.assertEqual(answer, hey_omi.FALLBACK_OPENAI_RESPONSE)

    def test_openai_response_empty_text_returns_fallback(self):
        answer = hey_omi.get_openai_response("")
        self.assertEqual(answer, hey_omi.FALLBACK_OPENAI_RESPONSE)
        whitespace_answer = hey_omi.get_openai_response("   ")
        self.assertEqual(whitespace_answer, hey_omi.FALLBACK_OPENAI_RESPONSE)

    def test_openai_response_handles_api_exception(self):
        fake_client = mock.MagicMock()
        fake_client.chat.completions.create.side_effect = RuntimeError("API unavailable")
        with mock.patch.object(hey_omi, "get_openai_client", return_value=fake_client):
            answer = hey_omi.get_openai_response("query")
            self.assertEqual(answer, hey_omi.FALLBACK_OPENAI_RESPONSE)

    def test_send_omi_notification_missing_args(self):
        self.assertFalse(hey_omi.send_omi_notification("", "hello"))
        self.assertFalse(hey_omi.send_omi_notification("   ", "hello"))
        self.assertFalse(hey_omi.send_omi_notification("uid-1", ""))
        self.assertFalse(hey_omi.send_omi_notification("uid-1", "   "))

    def test_send_omi_notification_missing_credentials(self):
        with mock.patch.object(hey_omi, "get_omi_credentials", return_value=("", "")):
            result = hey_omi.send_omi_notification("uid-1", "test alert")
            self.assertFalse(result)

    def test_send_omi_notification_network_failure(self):
        with mock.patch.object(hey_omi, "get_omi_credentials", return_value=("app-1", "secret-1")), \
             mock.patch.object(hey_omi.requests, "post", side_effect=ConnectionError("Failed")):
            result = hey_omi.send_omi_notification("uid-1", "test alert")
            self.assertFalse(result)

    def test_send_omi_notification_success(self):
        fake_resp = mock.MagicMock(status_code=200)
        fake_resp.raise_for_status.return_value = None
        with mock.patch.object(hey_omi, "get_omi_credentials", return_value=("app-1", "secret-1")), \
             mock.patch.object(hey_omi.requests, "post", return_value=fake_resp) as mock_post:
            result = hey_omi.send_omi_notification("uid-1", "test alert")
            self.assertTrue(result)
            mock_post.assert_called_once()

    def test_malformed_segments_gracefully_skipped(self):
        malformed = [None, 12345, "invalid", {}, {"text": None}, {"text": ""}, {"text": "   "}]
        cleaned = hey_omi._extract_segments_text(malformed)
        self.assertEqual(cleaned, [])

        req = hey_omi.WebhookRequest(session_id="s-malformed", segments=malformed, uid="u1")
        resp = asyncio.run(hey_omi.webhook(req))
        self.assertEqual(resp.status, "success")

    def test_missing_session_id_raises_http_400(self):
        req = hey_omi.WebhookRequest(session_id="", segments=[], uid="u1")
        with self.assertRaises(hey_omi.HTTPException) as ctx:
            asyncio.run(hey_omi.webhook(req))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cooldown_blocks_rapid_duplicate_dispatch(self):
        session_id = "s-cooldown"
        buf = hey_omi.message_buffer.get_buffer(session_id)
        buf["trigger_detected"] = True
        buf["response_sent"] = False
        hey_omi.notification_cooldowns[session_id] = self.clock.now - 5.0  # 5s ago (cooldown is 15s)

        req = hey_omi.WebhookRequest(session_id=session_id, segments=[{"text": "more words"}], uid="u1")
        resp = asyncio.run(hey_omi.webhook(req))
        self.assertEqual(resp.status, "success")
        self.assertTrue(buf["trigger_detected"])

    def test_cleanup_old_sessions_evicts_buffers_and_cooldowns(self):
        hey_omi.message_buffer.get_buffer("active-sess")
        buf_old = hey_omi.message_buffer.get_buffer("old-sess")
        buf_old["last_activity"] = self.clock.now - 4000  # > 1 hour old

        hey_omi.notification_cooldowns["active-sess"] = self.clock.now
        hey_omi.notification_cooldowns["old-sess"] = self.clock.now - 4000
        hey_omi.notification_cooldowns["orphan-cooldown"] = self.clock.now - 5000

        hey_omi.message_buffer.cleanup_old_sessions()

        self.assertIn("active-sess", hey_omi.message_buffer.buffers)
        self.assertNotIn("old-sess", hey_omi.message_buffer.buffers)
        self.assertIn("active-sess", hey_omi.notification_cooldowns)
        self.assertNotIn("old-sess", hey_omi.notification_cooldowns)
        self.assertNotIn("orphan-cooldown", hey_omi.notification_cooldowns)

    def test_health_endpoint(self):
        res = asyncio.run(hey_omi.health())
        self.assertEqual(res["status"], "healthy")
        self.assertEqual(res["service"], "notifications")
        self.assertIn("configured", res)

    def test_status_endpoint(self):
        res = asyncio.run(hey_omi.status())
        self.assertIn("active_sessions", res)
        self.assertIn("uptime", res)
        self.assertIn("configured", res)

    def test_setup_status_endpoint_success_and_error(self):
        res = asyncio.run(hey_omi.setup_status())
        self.assertTrue(res["is_setup_completed"])

        with mock.patch.object(hey_omi, "get_omi_credentials", side_effect=RuntimeError("DB unreachable")):
            with self.assertRaises(hey_omi.HTTPException) as ctx:
                asyncio.run(hey_omi.setup_status())
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Internal setup error")


if __name__ == "__main__":
    unittest.main()

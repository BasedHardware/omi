"""Hermetic regression tests for plugins/omi-twitter-app/main_simple.py.

Standard library only: fastapi, tweepy, openai, and dotenv are replaced
with minimal stubs before importing the module under test so the suite
runs without site-packages.

Covers the non-dict-segment crash: OMI may POST a JSON list of raw strings
(a documented payload shape in the webhook), and `process_segments` used
to call seg.get() unconditionally, raising AttributeError and producing a
500 instead of processing the transcript.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock

os.environ.setdefault("STORAGE_DIR", "/tmp/omi-twitter-test-storage")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_module_stubs():
    fastapi = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    class Request:
        pass

    def Query(default=None, **kwargs):
        return default

    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.HTTPException = HTTPException
    fastapi.Query = Query
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")

    class _Resp:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    responses.HTMLResponse = _Resp
    responses.RedirectResponse = _Resp
    responses.JSONResponse = _Resp
    sys.modules["fastapi.responses"] = responses

    tweepy = types.ModuleType("tweepy")

    class TweepyException(Exception):
        pass

    class Client:
        def __init__(self, *args, **kwargs):
            pass

    class OAuth2UserHandler:
        def __init__(self, *args, **kwargs):
            pass

    tweepy.TweepyException = TweepyException
    tweepy.Client = Client
    tweepy.OAuth2UserHandler = OAuth2UserHandler
    sys.modules["tweepy"] = tweepy

    openai = types.ModuleType("openai")

    class AsyncOpenAI:
        def __init__(self, *args, **kwargs):
            pass

    openai.AsyncOpenAI = AsyncOpenAI
    sys.modules["openai"] = openai

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv


_install_module_stubs()
import main_simple  # noqa: E402
from simple_storage import SimpleSessionStorage, sessions  # noqa: E402


class ProcessSegmentsTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.session = SimpleSessionStorage.get_or_create_session("sess-1", "u1")
        self.user = {"uid": "u1", "access_token": "tok"}

    def _run(self, segs):
        return asyncio.run(main_simple.process_segments(self.session, segs, self.user))

    def test_string_segment_does_not_crash(self):
        # Bare-string list: previously AttributeError on seg.get("text").
        result = self._run(["just some words"])
        self.assertEqual(result, "listening")

    def test_string_segment_with_trigger_starts_recording(self):
        result = self._run(["tweet now buy the dip"])
        self.assertEqual(result, "collecting_1")
        self.assertEqual(self.session["tweet_mode"], "recording")
        self.assertEqual(self.session["accumulated_text"], "buy the dip")

    def test_mixed_dict_and_string_segments(self):
        result = self._run([{"text": "hello "}, "world"])
        self.assertEqual(result, "listening")

    def test_recording_collects_three_segments(self):
        self._run(["tweet now first part"])
        r2 = self._run(["second part"])
        self.assertEqual(r2, "collecting_2")

        # Third segment completes collection; stub the AI + post path.
        with mock.patch.object(
            main_simple.tweet_detector,
            "ai_extract_tweet_from_segments",
            new=mock.AsyncMock(return_value="cleaned tweet text"),
        ), mock.patch.object(
            main_simple.twitter_client,
            "post_tweet",
            new=mock.AsyncMock(return_value={"success": True, "tweet_id": "42"}),
        ):
            r3 = self._run(["third part"])
        self.assertIn("Tweet posted", r3)
        self.assertEqual(self.session["tweet_mode"], "idle")


if __name__ == "__main__":
    unittest.main()

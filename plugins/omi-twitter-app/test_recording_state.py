"""Hermetic regression tests for issue #14363 in omi-twitter-app.

Verifies that:
- Trigger-only voice segments ("Tweet now") extract None but store "" in session state.
- Subsequent segments append cleanly to accumulated_text without TypeError or leading space hitches.
- Dirty session state with accumulated_text=None safely heals to string accumulator.
- Full 3-segment lifecycle posts tweets and resets session state cleanly.
- Edge failure conditions (empty AI text, AI None, API failure, client None) reset session gracefully.
- Webhook segments with {"text": None} (VAD null drops) are coerced defensively without TypeError.

Plain Python 3 standard library only - zero external dependencies required.
"""

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

PLUGIN_DIR = Path(__file__).resolve().parent

# ---- Module stubs to enable hermetic loading without 3rd-party pip packages ----

_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules["dotenv"] = _dotenv

_tweepy = types.ModuleType("tweepy")
_tweepy.Client = lambda *args, **kwargs: types.SimpleNamespace()


class _TweepyException(Exception):
    pass


_tweepy.TweepyException = _TweepyException
sys.modules["tweepy"] = _tweepy

_openai = types.ModuleType("openai")
_openai.AsyncOpenAI = lambda *args, **kwargs: types.SimpleNamespace()
sys.modules["openai"] = _openai

_fastapi = types.ModuleType("fastapi")


class _FastAPI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def get(self, *args, **kwargs):
        return lambda fn: fn

    def post(self, *args, **kwargs):
        return lambda fn: fn


_fastapi.FastAPI = _FastAPI
_fastapi.Request = lambda *args, **kwargs: None
_fastapi.HTTPException = Exception
_fastapi.Query = lambda default=None, **kwargs: default
sys.modules["fastapi"] = _fastapi

_responses = types.ModuleType("fastapi.responses")
_responses.HTMLResponse = lambda *args, **kwargs: None
_responses.RedirectResponse = lambda *args, **kwargs: None
_responses.JSONResponse = lambda *args, **kwargs: None
_fastapi.responses = _responses
sys.modules["fastapi.responses"] = _responses

# In-memory session storage mock to eliminate disk I/O and Windows encoding issues
_storage = types.ModuleType("simple_storage")


class MemorySessionStorage:
    sessions = {}

    @classmethod
    def get_or_create_session(cls, session_id: str, uid: str = "test-uid") -> dict:
        if session_id not in cls.sessions:
            cls.sessions[session_id] = {
                "session_id": session_id,
                "uid": uid,
                "transcript": "",
                "tweet_mode": "idle",
                "tweet_content": "",
                "segments_count": 0,
                "last_segment_time": None,
                "accumulated_text": "",
            }
        return cls.sessions[session_id]

    @classmethod
    def update_session(cls, session_id: str, **kwargs):
        session = cls.get_or_create_session(session_id)
        session.update(kwargs)

    @classmethod
    def reset_session(cls, session_id: str):
        if session_id in cls.sessions:
            cls.sessions[session_id].update({
                "transcript": "",
                "tweet_mode": "idle",
                "tweet_content": "",
                "segments_count": 0,
                "last_segment_time": None,
                "accumulated_text": "",
            })


_storage.SimpleSessionStorage = MemorySessionStorage
_storage.SimpleUserStorage = types.SimpleNamespace()
_storage.OAuthStateStorage = types.SimpleNamespace()
_storage.users = {}
_storage.save_users = lambda: None
sys.modules["simple_storage"] = _storage

if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

# Import main_simple
import main_simple


class TwitterRecordingAccumulatorTests(unittest.TestCase):
    """Hermetic 12-case suite validating recording accumulator state and lifecycle."""

    def setUp(self):
        MemorySessionStorage.sessions.clear()
        self.session_id = "test_session_14363"
        self.user = {"uid": "user_omi_1", "access_token": "token_abc_123"}
        self.session = MemorySessionStorage.get_or_create_session(self.session_id, self.user["uid"])

        # Patch stdout print to prevent noisy logs and cross-platform encoding hitches
        self.print_patcher = patch("builtins.print")
        self.print_patcher.start()

    def tearDown(self):
        self.print_patcher.stop()

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_01_trigger_only_stores_empty_string_not_none(self):
        """Case 1: 'Tweet now' trigger with no body must store empty string, not None."""
        segments = [{"text": "Tweet now"}]
        result = self.run_async(main_simple.process_segments(self.session, segments, self.user))

        self.assertEqual(result, "collecting_1")
        self.assertEqual(self.session["tweet_mode"], "recording")
        self.assertEqual(self.session["segments_count"], 1)
        self.assertEqual(self.session["accumulated_text"], "")
        self.assertIsNotNone(self.session["accumulated_text"])

    def test_02_trigger_with_content_stores_extracted_body(self):
        """Case 2: Trigger with text immediately stores the trailing tweet body."""
        segments = [{"text": "Tweet now building the future of memory devices"}]
        result = self.run_async(main_simple.process_segments(self.session, segments, self.user))

        self.assertEqual(result, "collecting_1")
        self.assertEqual(self.session["tweet_mode"], "recording")
        self.assertEqual(self.session["segments_count"], 1)
        self.assertEqual(self.session["accumulated_text"], "building the future of memory devices")

    def test_03_subsequent_segment_appends_to_empty_accumulator_without_type_error(self):
        """Case 3: Segment 2 following trigger-only segment appends cleanly without TypeError."""
        # Step 1: Trigger only
        self.run_async(main_simple.process_segments(self.session, [{"text": "Tweet now"}], self.user))
        self.assertEqual(self.session["accumulated_text"], "")

        # Step 2: Second segment
        result = self.run_async(
            main_simple.process_segments(self.session, [{"text": "first thought after trigger"}], self.user)
        )

        self.assertEqual(result, "collecting_2")
        self.assertEqual(self.session["segments_count"], 2)
        self.assertEqual(self.session["accumulated_text"], "first thought after trigger")

    def test_04_subsequent_segment_heals_legacy_none_in_session(self):
        """Case 4: Dirty session with accumulated_text=None safely heals to string."""
        # Force dirty session state as legacy code would leave it
        self.session["tweet_mode"] = "recording"
        self.session["accumulated_text"] = None
        self.session["segments_count"] = 1

        result = self.run_async(
            main_simple.process_segments(self.session, [{"text": "resilient against legacy none"}], self.user)
        )

        self.assertEqual(result, "collecting_2")
        self.assertEqual(self.session["segments_count"], 2)
        self.assertEqual(self.session["accumulated_text"], "resilient against legacy none")

    def test_05_three_segments_full_pipeline_success(self):
        """Case 5: Full 3-segment collection extracts tweet with AI, posts, and resets."""
        with patch.object(
            main_simple.tweet_detector,
            "ai_extract_tweet_from_segments",
            new_callable=AsyncMock,
            return_value="Building open-source wearable AI with Omi",
        ), patch.object(
            main_simple.twitter_client,
            "post_tweet",
            new_callable=AsyncMock,
            return_value={"success": True, "tweet_id": "987654321"},
        ) as mock_post:
            # Segment 1
            self.run_async(main_simple.process_segments(self.session, [{"text": "Tweet now"}], self.user))
            # Segment 2
            self.run_async(main_simple.process_segments(self.session, [{"text": "Building open-source"}], self.user))
            # Segment 3
            result = self.run_async(
                main_simple.process_segments(self.session, [{"text": "wearable AI with Omi"}], self.user)
            )

            self.assertEqual(result, "✅ Tweet posted: 'Building open-source wearable AI with Omi'")
            mock_post.assert_awaited_once_with("token_abc_123", "Building open-source wearable AI with Omi")
            # Session must be reset to idle
            self.assertEqual(self.session["tweet_mode"], "idle")
            self.assertEqual(self.session["segments_count"], 0)
            self.assertEqual(self.session["accumulated_text"], "")

    def test_06_three_segments_empty_ai_content_resets_session(self):
        """Case 6: AI extracting empty or <=3 chars must abort post and reset session."""
        with patch.object(
            main_simple.tweet_detector,
            "ai_extract_tweet_from_segments",
            new_callable=AsyncMock,
            return_value="  ok ",  # len <= 3 when stripped
        ), patch.object(
            main_simple.twitter_client,
            "post_tweet",
            new_callable=AsyncMock,
        ) as mock_post:
            self.run_async(main_simple.process_segments(self.session, [{"text": "Tweet now"}], self.user))
            self.run_async(main_simple.process_segments(self.session, [{"text": "mumble"}], self.user))
            result = self.run_async(main_simple.process_segments(self.session, [{"text": "cough"}], self.user))

            self.assertEqual(result, "❌ No valid tweet content")
            mock_post.assert_not_called()
            self.assertEqual(self.session["tweet_mode"], "idle")
            self.assertEqual(self.session["accumulated_text"], "")

    def test_07_three_segments_twitter_api_failure_resets_session(self):
        """Case 7: Twitter API post error returns failure and resets session cleanly."""
        with patch.object(
            main_simple.tweet_detector,
            "ai_extract_tweet_from_segments",
            new_callable=AsyncMock,
            return_value="Valid tweet message for twitter",
        ), patch.object(
            main_simple.twitter_client,
            "post_tweet",
            new_callable=AsyncMock,
            return_value={"success": False, "error": "Rate limit exceeded (429)"},
        ):
            self.run_async(main_simple.process_segments(self.session, [{"text": "Tweet now"}], self.user))
            self.run_async(main_simple.process_segments(self.session, [{"text": "seg 2"}], self.user))
            result = self.run_async(main_simple.process_segments(self.session, [{"text": "seg 3"}], self.user))

            self.assertEqual(result, "❌ Failed: Rate limit exceeded (429)")
            self.assertEqual(self.session["tweet_mode"], "idle")
            self.assertEqual(self.session["accumulated_text"], "")

    def test_08_three_segments_twitter_client_returns_none(self):
        """Case 8: Twitter client returning None (network crash) handles gracefully."""
        with patch.object(
            main_simple.tweet_detector,
            "ai_extract_tweet_from_segments",
            new_callable=AsyncMock,
            return_value="Another valid tweet text",
        ), patch.object(
            main_simple.twitter_client,
            "post_tweet",
            new_callable=AsyncMock,
            return_value=None,
        ):
            self.run_async(main_simple.process_segments(self.session, [{"text": "Tweet now"}], self.user))
            self.run_async(main_simple.process_segments(self.session, [{"text": "seg 2"}], self.user))
            result = self.run_async(main_simple.process_segments(self.session, [{"text": "seg 3"}], self.user))

            self.assertEqual(result, "❌ Failed: Failed")
            self.assertEqual(self.session["tweet_mode"], "idle")

    def test_09_idle_non_trigger_returns_listening(self):
        """Case 9: Ordinary conversation in idle mode returns listening with no state change."""
        segments = [{"text": "What is the weather outside today?"}]
        result = self.run_async(main_simple.process_segments(self.session, segments, self.user))

        self.assertEqual(result, "listening")
        self.assertEqual(self.session["tweet_mode"], "idle")
        self.assertEqual(self.session["segments_count"], 0)
        self.assertEqual(self.session["accumulated_text"], "")

    def test_10_multiple_text_pieces_in_segment_payload_joined(self):
        """Case 10: Multi-item segments payload joins correctly across all text keys."""
        segments = [{"text": "Tweet now"}, {"text": "live from the conference stage"}]
        result = self.run_async(main_simple.process_segments(self.session, segments, self.user))

        self.assertEqual(result, "collecting_1")
        self.assertEqual(self.session["tweet_mode"], "recording")
        self.assertEqual(self.session["accumulated_text"], "live from the conference stage")

    def test_11_three_segments_ai_returning_none_resets_session_without_attribute_error(self):
        """Case 11: AI returning None must not throw AttributeError on strip and must reset session."""
        with patch.object(
            main_simple.tweet_detector,
            "ai_extract_tweet_from_segments",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            main_simple.twitter_client,
            "post_tweet",
            new_callable=AsyncMock,
        ) as mock_post:
            self.run_async(main_simple.process_segments(self.session, [{"text": "Tweet now"}], self.user))
            self.run_async(main_simple.process_segments(self.session, [{"text": "segment two"}], self.user))
            result = self.run_async(main_simple.process_segments(self.session, [{"text": "segment three"}], self.user))

            self.assertEqual(result, "❌ No valid tweet content")
            mock_post.assert_not_called()
            self.assertEqual(self.session["tweet_mode"], "idle")
            self.assertEqual(self.session["accumulated_text"], "")

    def test_12_segments_with_null_text_elements_handled_cleanly(self):
        """Case 12: Incoming webhook segments with {'text': None} must not crash str.join."""
        segments = [{"text": None}, {"text": "Tweet now"}, {"text": None}, {"text": "hello"}]
        result = self.run_async(main_simple.process_segments(self.session, segments, self.user))

        self.assertEqual(result, "collecting_1")
        self.assertEqual(self.session["tweet_mode"], "recording")
        self.assertEqual(self.session["accumulated_text"], "hello")


if __name__ == "__main__":
    unittest.main()

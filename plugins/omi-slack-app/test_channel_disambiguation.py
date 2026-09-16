"""Hermetic regression suite for disambiguated fuzzy matching and caller handling (#14112).

Tests:
1. MessageDetector.ai_extract_message_and_channel returns candidate list on ambiguous fuzzy matches
   (e.g., 'marketing' matching both 'marketing-us' and 'marketing-eu').
2. Unique fuzzy matches correctly resolve without duplicates in log or state.
3. Short channel substring false positives (e.g. channel 'it' in 'wait') are rejected.
4. Exact matches maintain top priority.
5. Caller-level regression: process_segments refuses to fall back to user's selected_channel
   when the channel is ambiguous, returning an interactive clarification prompt instead of misdelivering.
6. Caller-level regression: process_segments continues using default channel when no channel was mentioned.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, AsyncMock, patch


class Response:
    def __init__(self, content, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


def load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ChannelDisambiguationTests(unittest.TestCase):
    def setUp(self):
        # Setup mocks for OpenAI & Dotenv
        self.mock_completions = AsyncMock()
        self.mock_openai_client = Mock()
        self.mock_openai_client.chat.completions.create = self.mock_completions
        
        dotenv_mod = types.ModuleType("dotenv")
        dotenv_mod.load_dotenv = Mock()
        
        openai_mod = types.ModuleType("openai")
        openai_mod.AsyncOpenAI = Mock(return_value=self.mock_openai_client)

        # Framework and storage mocks for main.py
        framework = types.ModuleType("fastapi")
        app = Mock()
        for method in ("get", "post", "on_event"):
            getattr(app, method).side_effect = lambda *a, **k: lambda f: f
        framework.FastAPI = lambda **kwargs: app
        framework.Request = object
        framework.HTTPException = Exception
        framework.Query = lambda *a, **k: None

        responses = types.ModuleType("fastapi.responses")
        responses.HTMLResponse = responses.RedirectResponse = responses.JSONResponse = Response

        storage = types.ModuleType("simple_storage")
        storage.SimpleUserStorage = Mock()
        self.session_storage = Mock()
        self.session_storage.get_session_idle_time = Mock(return_value=None)
        storage.SimpleSessionStorage = self.session_storage

        slack = types.ModuleType("slack_sdk")
        slack.WebClient = Mock()
        errors = types.ModuleType("slack_sdk.errors")
        errors.SlackApiError = Exception

        self.mock_slack_client = Mock()
        self.mock_slack_client.send_message = AsyncMock(return_value={"success": True})
        self.mock_slack_client.list_channels = Mock(return_value=[
            {"id": "C_DEF", "name": "default-alerts"},
            {"id": "C_MKT_US", "name": "marketing-us"},
            {"id": "C_MKT_EU", "name": "marketing-eu"},
            {"id": "C_DEP", "name": "deploy-alerts"},
            {"id": "C_IT", "name": "it"},
        ])

        modules = {
            "dotenv": dotenv_mod,
            "openai": openai_mod,
            "fastapi": framework,
            "fastapi.responses": responses,
            "simple_storage": storage,
            "slack_sdk": slack,
            "slack_sdk.errors": errors,
            "requests": types.ModuleType("requests"),
        }

        self.orig_modules = {k: sys.modules.get(k) for k in modules}
        sys.modules.update(modules)

        # Load message_detector and main under test
        base_dir = Path(__file__).parent
        detector_path = base_dir / "message_detector.py"
        if not detector_path.exists():
            detector_path = base_dir / "message_detector_clean.py"

        main_path = base_dir / "main.py"
        if not main_path.exists():
            main_path = base_dir / "main_patched.py"

        detector_mod = types.ModuleType("message_detector")
        self.detector_impl = load_module("message_detector_impl", detector_path)
        self.detector_impl.client = self.mock_openai_client
        detector_mod.MessageDetector = self.detector_impl.MessageDetector

        with patch.dict(sys.modules, {"message_detector": detector_mod, "slack_client": self.mock_slack_client}):
            self.handler = load_module("slack_main_impl", main_path)
            self.handler.slack_client = self.mock_slack_client
            self.handler.message_detector = self.detector_impl.MessageDetector

        self.MessageDetector = self.detector_impl.MessageDetector

    def tearDown(self):
        for k, v in self.orig_modules.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def _mock_ai(self, channel_str, message_str):
        resp = Mock()
        choice = Mock()
        choice.message.content = f"CHANNEL: {channel_str}\nMESSAGE: {message_str}"
        resp.choices = [choice]
        self.mock_completions.return_value = resp

    # --- Unit-level detector tests ---

    def test_ambiguous_fuzzy_match_returns_candidates_list(self):
        self._mock_ai("marketing", "Review Q3 numbers")
        channels = [
            {"name": "marketing-us", "id": "C_MKT_US"},
            {"name": "marketing-eu", "id": "C_MKT_EU"},
            {"name": "general", "id": "C_GEN"}
        ]
        cid, cname, msg = asyncio.run(
            self.MessageDetector.ai_extract_message_and_channel("send to marketing review Q3 numbers", channels)
        )
        self.assertIsNone(cid, "Ambiguous channel must not resolve to any channel ID")
        self.assertIsInstance(cname, list, "Ambiguous return must be a list of candidate names")
        self.assertEqual(sorted(cname), ["marketing-eu", "marketing-us"])
        self.assertEqual(msg, "Review Q3 numbers")

    def test_unambiguous_fuzzy_match_resolves(self):
        self._mock_ai("deploy", "Deployment started for v2.0")
        channels = [
            {"name": "deploy-alerts", "id": "C_DEP"},
            {"name": "random", "id": "C_RND"}
        ]
        cid, cname, msg = asyncio.run(
            self.MessageDetector.ai_extract_message_and_channel("send to deploy deployment started for v2.0", channels)
        )
        self.assertEqual(cid, "C_DEP")
        self.assertEqual(cname, "deploy-alerts")
        self.assertEqual(msg, "Deployment started for v2.0")

    def test_short_channel_substring_false_positive_rejected(self):
        self._mock_ai("wait", "Please hold on a second")
        channels = [
            {"name": "it", "id": "C_IT"},
            {"name": "general", "id": "C_GEN"}
        ]
        cid, cname, msg = asyncio.run(
            self.MessageDetector.ai_extract_message_and_channel("wait please hold on a second", channels)
        )
        self.assertIsNone(cid)
        self.assertEqual(cname, "wait", "Unmatched raw channel name returned as string")
        self.assertEqual(msg, "Please hold on a second")

    def test_exact_match_takes_absolute_priority(self):
        self._mock_ai("marketing", "All-hands update")
        channels = [
            {"name": "marketing", "id": "C_MKT_EXACT"},
            {"name": "marketing-us", "id": "C_MKT_US"},
            {"name": "marketing-eu", "id": "C_MKT_EU"}
        ]
        cid, cname, msg = asyncio.run(
            self.MessageDetector.ai_extract_message_and_channel("to marketing all hands update", channels)
        )
        self.assertEqual(cid, "C_MKT_EXACT")
        self.assertEqual(cname, "marketing")
        self.assertEqual(msg, "All-hands update")

    # --- Caller-level integration tests (main.py process_segments) ---

    def test_caller_skips_default_channel_and_prompts_on_ambiguity(self):
        """Regression test for Blocker 1: ambiguous channel must NOT fall back to selected_channel."""
        self._mock_ai("marketing", "Review Q3 numbers please")
        
        session = {
            "session_id": "test_session_123",
            "message_mode": "idle"
        }
        user = {
            "uid": "u1",
            "access_token": "xoxp-test",
            "selected_channel": "C_DEF"  # Default is default-alerts
        }
        
        # Test mode path in process_segments
        result = asyncio.run(
            self.handler.process_segments(session, [{"text": "send slack message in marketing review Q3 numbers please"}], user)
        )
        
        # Must not have sent message to default channel
        self.mock_slack_client.send_message.assert_not_called()
        self.assertIn("Ambiguous channel", result)
        self.assertIn("#marketing-us", result)
        self.assertIn("#marketing-eu", result)

    def test_caller_uses_default_channel_when_no_channel_mentioned(self):
        """When no channel is mentioned, default selected_channel is used (existing UX)."""
        self._mock_ai("UNKNOWN", "Hello everyone this is general update")
        
        session = {
            "session_id": "test_session_456",
            "message_mode": "idle"
        }
        user = {
            "uid": "u1",
            "access_token": "xoxp-test",
            "selected_channel": "C_DEF"
        }
        
        result = asyncio.run(
            self.handler.process_segments(session, [{"text": "send slack message hello everyone this is general update"}], user)
        )
        
        # Message was sent to default channel
        self.mock_slack_client.send_message.assert_called_once_with(
            access_token="xoxp-test",
            channel_id="C_DEF",
            text="Hello everyone this is general update"
        )
        self.assertIn("Message sent to #default-alerts", result)


if __name__ == "__main__":
    unittest.main()

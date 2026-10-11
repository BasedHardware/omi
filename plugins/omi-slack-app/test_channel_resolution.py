"""Hermetic regression: a spoken channel name posts to exactly one channel.

The fuzzy channel match accepted the first workspace channel that contained
the spoken name, so "send slack message to dev saying ..." posted to
whichever of #dev-ops and #frontend-dev came first in the listing. A named
channel that did not resolve also fell through to the user's default
channel, so the message went out anyway, to a channel the user never named.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock


class Response:
    def __init__(self, content, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def with_stubs(modules, loader):
    originals = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        return loader()
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class ResolveChannelTests(unittest.TestCase):
    def setUp(self):
        openai = types.ModuleType("openai")
        self.client = Mock()
        openai.AsyncOpenAI = Mock(return_value=self.client)
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None
        module = with_stubs({"openai": openai, "dotenv": dotenv},
                            lambda: load("message_detector_under_test", "message_detector.py"))
        self.detector = module.MessageDetector
        self.resolve = module.MessageDetector.resolve_channel
        self.channels = {"general": "C1", "dev-ops": "C2", "frontend-dev": "C3", "Marketing": "C4"}

    def test_exact_name_wins_case_insensitive(self):
        self.assertEqual(self.resolve("marketing", self.channels), ("C4", "Marketing", ["Marketing"]))
        self.assertEqual(self.resolve("#General", self.channels), ("C1", "general", ["general"]))

    def test_single_fuzzy_match_resolves(self):
        self.assertEqual(self.resolve("ops", self.channels), ("C2", "dev-ops", ["dev-ops"]))
        self.assertEqual(self.resolve("the general channel", self.channels)[:2], ("C1", "general"))

    def test_ambiguous_fuzzy_match_refuses(self):
        channel_id, name, candidates = self.resolve("dev", self.channels)
        self.assertIsNone(channel_id)
        self.assertIsNone(name)
        self.assertEqual(sorted(candidates), ["dev-ops", "frontend-dev"])

    def test_unknown_and_empty_names_refuse(self):
        self.assertEqual(self.resolve("random", self.channels), (None, None, []))
        self.assertEqual(self.resolve("#", self.channels), (None, None, []))

    def extract(self, model_reply, channels):
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message.content = model_reply
        self.client.chat.completions.create = AsyncMock(return_value=response)
        return asyncio.run(self.detector.ai_extract_message_and_channel("send slack message", channels))

    def test_extraction_keeps_spoken_name_when_ambiguous(self):
        channels = [{"id": "C2", "name": "dev-ops"}, {"id": "C3", "name": "frontend-dev"}]
        self.assertEqual(self.extract("CHANNEL: dev\nMESSAGE: Build is green", channels), (None, "dev", "Build is green"))

    def test_extraction_resolves_single_fuzzy_match(self):
        channels = [{"id": "C2", "name": "dev-ops"}, {"id": "C3", "name": "frontend-dev"}]
        self.assertEqual(self.extract("CHANNEL: ops\nMESSAGE: Build is green", channels), ("C2", "dev-ops", "Build is green"))


class NamedChannelNeverFallsBackTests(unittest.TestCase):
    """process_segments must not post to the default channel when the user
    named a channel that did not resolve."""

    def setUp(self):
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
        storage.SimpleSessionStorage = self.session_storage
        detector = types.ModuleType("message_detector")
        self.detector = Mock()
        self.detector.detect_trigger.return_value = False
        detector.MessageDetector = Mock(return_value=self.detector)
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None
        slack = types.ModuleType("slack_sdk")
        slack.WebClient = Mock()
        errors = types.ModuleType("slack_sdk.errors")
        errors.SlackApiError = Exception
        modules = {"fastapi": framework, "fastapi.responses": responses,
                   "simple_storage": storage, "message_detector": detector,
                   "dotenv": dotenv, "requests": types.ModuleType("requests"),
                   "slack_sdk": slack, "slack_sdk.errors": errors}

        def loader():
            client_mod = load("slack_client_for_resolution", "slack_client.py")
            sys.modules["slack_client"] = client_mod
            try:
                return load("slack_handler_for_resolution", "main.py")
            finally:
                sys.modules.pop("slack_client", None)

        self.handler = with_stubs(modules, loader)
        self.handler.slack_client.list_channels = Mock(return_value=[{"id": "C1", "name": "general"}, {"id": "C2", "name": "dev-ops"}])
        self.handler.slack_client.send_message = AsyncMock(return_value={"success": True})

    def fifth_segment(self):
        session = {"session_id": "omi_session_u1", "uid": "u1", "message_mode": "recording",
                   "accumulated_text": "send slack message to dev saying the build is green", "segments_count": 4}
        user = {"uid": "u1", "access_token": "token", "selected_channel": "C1"}
        return asyncio.run(self.handler.process_segments(session, ["okay"], user))

    def test_unresolved_named_channel_is_not_sent_to_default(self):
        self.detector.ai_extract_message_and_channel = AsyncMock(return_value=(None, "dev", "The build is green"))
        result = self.fifth_segment()
        self.handler.slack_client.send_message.assert_not_called()
        self.assertIn("dev", result)
        self.assertTrue(result.startswith("❌"))

    def test_no_channel_named_still_uses_default(self):
        self.detector.ai_extract_message_and_channel = AsyncMock(return_value=(None, None, "The build is green"))
        result = self.fifth_segment()
        self.handler.slack_client.send_message.assert_awaited_once()
        self.assertEqual(self.handler.slack_client.send_message.await_args.kwargs["channel_id"], "C1")
        self.assertTrue(result.startswith("✅"))

    def test_resolved_channel_is_sent(self):
        self.detector.ai_extract_message_and_channel = AsyncMock(return_value=("C2", "dev-ops", "The build is green"))
        self.fifth_segment()
        self.assertEqual(self.handler.slack_client.send_message.await_args.kwargs["channel_id"], "C2")


if __name__ == "__main__":
    unittest.main()

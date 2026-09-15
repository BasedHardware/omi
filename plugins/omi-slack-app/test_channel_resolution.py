"""Hermetic regression for #14112: ambiguous spoken channel names must not
resolve to whichever channel the Slack API happened to list first.

`resolve_channel` replaces the old first-substring-hit loop: an exact
case-insensitive match still wins outright, otherwise every bidirectional
substring candidate is scored by difflib.SequenceMatcher and only a single
closest candidate resolves. A genuine tie returns None so the caller falls
back to the user's selected channel instead of sending the voice-dictated
message to a channel the user never named — all three send paths in main.py
call slack_client.send_message immediately, with no confirmation step.

Only the openai and dotenv import boundaries are stubbed; the production
module executes for real. No network or credentials are required.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


def load_detector_module():
    openai = types.ModuleType("openai")
    openai.AsyncOpenAI = Mock()
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None
    spec = importlib.util.spec_from_file_location(
        "message_detector_under_test", Path(__file__).with_name("message_detector.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"openai": openai, "dotenv": dotenv}):
        spec.loader.exec_module(module)
    return module


detector = load_detector_module()


class ResolveChannelTests(unittest.TestCase):
    def test_exact_match_case_insensitive_wins(self):
        channel_map = {"general": "C1", "general-chat": "C2", "dev-ops": "C3"}
        self.assertEqual(detector.resolve_channel("GENERAL", channel_map), ("C1", "general"))

    def test_exact_match_returns_canonical_casing(self):
        self.assertEqual(detector.resolve_channel("devops", {"DevOps": "C1"}), ("C1", "DevOps"))

    def test_unique_closest_substring_match_resolves(self):
        channel_map = {"dev-ops": "C1", "dev-secrets": "C2"}
        self.assertEqual(detector.resolve_channel("dev", channel_map), ("C1", "dev-ops"))

    def test_closest_match_independent_of_slack_api_order(self):
        # Regression for #14112: the old loop took the first substring hit, so
        # this ordering sent "dev" to dev-secrets. The closest match must win
        # no matter which order list_channels happened to return.
        channel_map = {"dev-secrets": "C2", "dev-ops": "C1"}
        self.assertEqual(detector.resolve_channel("dev", channel_map), ("C1", "dev-ops"))

    def test_ambiguous_tie_returns_none(self):
        channel_map = {"dev-a": "C1", "dev-b": "C2"}
        self.assertIsNone(detector.resolve_channel("dev", channel_map))

    def test_three_way_tie_returns_none(self):
        channel_map = {"dev-a": "C1", "dev-b": "C2", "dev-c": "C3"}
        self.assertIsNone(detector.resolve_channel("dev", channel_map))

    def test_lower_scoring_tie_does_not_block_unique_best(self):
        # "abc-dev-xyz" and "123-dev-456" tie at 6/14, but "dev-ops" (0.6)
        # is strictly closer to "dev" and must still resolve.
        channel_map = {"abc-dev-xyz": "C2", "dev-ops": "C1", "123-dev-456": "C3"}
        self.assertEqual(detector.resolve_channel("dev", channel_map), ("C1", "dev-ops"))

    def test_channel_name_inside_spoken_name_resolves(self):
        # Voice transcription may add words: "random stuff" should find #random.
        self.assertEqual(detector.resolve_channel("random stuff", {"random": "C1"}), ("C1", "random"))

    def test_no_substring_match_returns_none(self):
        self.assertIsNone(detector.resolve_channel("nonexistent", {"general": "C1"}))

    def test_non_substring_channels_not_considered(self):
        channel_map = {"general": "C1", "dev-ops": "C2"}
        self.assertIsNone(detector.resolve_channel("xyz", channel_map))

    def test_empty_spoken_name_returns_none(self):
        for spoken in ("", None):
            with self.subTest(spoken=spoken):
                self.assertIsNone(detector.resolve_channel(spoken, {"general": "C1"}))

    def test_empty_channel_map_returns_none(self):
        self.assertIsNone(detector.resolve_channel("general", {}))

    def test_empty_channel_name_never_resolves(self):
        # "" is a substring of every string; a nameless entry must not hijack
        # an unrelated spoken name as a zero-score "match".
        self.assertIsNone(detector.resolve_channel("anything", {"": "C9"}))
        self.assertIsNone(detector.resolve_channel("anything", {"": "C9", "general": "C1"}))

    def test_case_insensitive_fuzzy_match(self):
        self.assertEqual(detector.resolve_channel("DEV", {"dev-ops": "C1"}), ("C1", "dev-ops"))


class AiExtractChannelResolutionTests(unittest.TestCase):
    """The production path the bug lived in: the AI-extracted channel name is
    resolved against the workspace map and the result feeds send_message."""

    def extract(self, ai_reply, channels):
        response = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=ai_reply))]
        )
        client = Mock()
        client.chat.completions.create = AsyncMock(return_value=response)
        with patch.object(detector, "client", client):
            return asyncio.run(
                detector.MessageDetector.ai_extract_message_and_channel("voice text", channels)
            )

    def test_extract_resolves_closest_not_first_listed(self):
        # Old code sent this to dev-secrets because Slack listed it first.
        channels = [{"name": "dev-secrets", "id": "C2"}, {"name": "dev-ops", "id": "C1"}]
        channel_id, channel_name, message = self.extract("CHANNEL: dev\nMESSAGE: hello team", channels)
        self.assertEqual(channel_id, "C1")
        self.assertEqual(channel_name, "dev-ops")
        self.assertEqual(message, "hello team")

    def test_extract_ambiguous_tie_returns_no_channel_but_keeps_message(self):
        # (None, spoken, message) lets the caller fall back to the user's
        # selected channel instead of guessing.
        channels = [{"name": "dev-a", "id": "C1"}, {"name": "dev-b", "id": "C2"}]
        channel_id, channel_name, message = self.extract("CHANNEL: dev\nMESSAGE: hello team", channels)
        self.assertIsNone(channel_id)
        self.assertEqual(channel_name, "dev")
        self.assertEqual(message, "hello team")

    def test_extract_unknown_channel_returns_none_none_message(self):
        channels = [{"name": "general", "id": "C1"}]
        channel_id, channel_name, message = self.extract("CHANNEL: UNKNOWN\nMESSAGE: just chatting", channels)
        self.assertIsNone(channel_id)
        self.assertIsNone(channel_name)
        self.assertEqual(message, "just chatting")

    def test_extract_exact_channel_name(self):
        channels = [{"name": "marketing", "id": "C7"}, {"name": "marketing-eu", "id": "C8"}]
        channel_id, channel_name, message = self.extract("CHANNEL: marketing\nMESSAGE: campaign live", channels)
        self.assertEqual(channel_id, "C7")
        self.assertEqual(channel_name, "marketing")
        self.assertEqual(message, "campaign live")

    def test_extract_strips_hash_prefix_and_resolves(self):
        channels = [{"name": "general", "id": "C1"}]
        channel_id, channel_name, _ = self.extract("CHANNEL: #general\nMESSAGE: hi", channels)
        self.assertEqual(channel_id, "C1")
        self.assertEqual(channel_name, "general")


if __name__ == "__main__":
    unittest.main()

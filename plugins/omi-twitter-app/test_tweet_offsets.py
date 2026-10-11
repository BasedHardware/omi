"""Hermetic regression tests for TweetDetector's trigger offsets."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


def load_detector():
    openai = ModuleType("openai")
    openai.AsyncOpenAI = lambda **_kwargs: SimpleNamespace()
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None
    spec = importlib.util.spec_from_file_location("tweet_detector", Path(__file__).with_name("tweet_detector.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"openai": openai, "dotenv": dotenv}):
        spec.loader.exec_module(module)
    return module


TweetDetector = load_detector().TweetDetector


class TweetOffsetTests(unittest.TestCase):
    def test_leading_spaces_do_not_shift_the_slice(self):
        self.assertEqual(TweetDetector.extract_tweet_content("  Tweet now hello"), "hello")

    def test_leading_newlines_and_end_phrase(self):
        self.assertEqual(
            TweetDetector.extract_tweet_content("\n\nTweet this AI is cool end tweet"),
            "AI is cool",
        )

    def test_webhook_join_with_empty_first_segment(self):
        self.assertEqual(
            TweetDetector.extract_tweet_content(" Tweet now shipping the voice poster today"),
            "shipping the voice poster today",
        )

    def test_mixed_case_trigger_preserves_content_case(self):
        self.assertEqual(
            TweetDetector.extract_tweet_content("   TWEET NOW Big News from OMI"),
            "Big News from OMI",
        )

    def test_controls_remain_unchanged(self):
        self.assertEqual(TweetDetector.extract_tweet_content("Tweet now hello end tweet"), "hello")
        self.assertEqual(TweetDetector.extract_tweet_content("Tweet now hello   "), "hello")
        self.assertIsNone(TweetDetector.extract_tweet_content("ordinary text"))


if __name__ == "__main__":
    unittest.main()

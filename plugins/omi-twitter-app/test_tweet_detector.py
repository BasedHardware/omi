"""
Hermetic test suite for the Twitter App tweet detection module.

Exercises trigger phrase identification, text normalization,
tweet content extraction, and explicit ending phrase stripping
under pure standard library Python (including python3 -S).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


def load_detector():
    openai = ModuleType("openai")
    openai.AsyncOpenAI = Mock()

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    stubs = {
        "openai": openai,
        "dotenv": dotenv,
    }

    detector_path = Path(__file__).resolve().parent / "tweet_detector.py"
    spec = importlib.util.spec_from_file_location("tweet_detector", detector_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module.TweetDetector


TweetDetector = load_detector()


class TweetDetectorTests(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(TweetDetector.normalize_text("  Tweet NOW  "), "tweet now")

    def test_detect_trigger_present(self):
        self.assertTrue(TweetDetector.detect_trigger("Hey Omi, tweet now I am enjoying this conference"))
        self.assertTrue(TweetDetector.detect_trigger("post this tweet Hello world"))
        self.assertTrue(TweetDetector.detect_trigger("tweet this exciting announcement"))

    def test_detect_trigger_absent(self):
        self.assertFalse(TweetDetector.detect_trigger("Just reading some tweets"))
        self.assertFalse(TweetDetector.detect_trigger("Random conversation about lunch"))

    def test_detect_end_phrases(self):
        self.assertTrue(TweetDetector.detect_end("That was great, end tweet"))
        self.assertTrue(TweetDetector.detect_end("See everyone tomorrow that's the tweet"))
        self.assertFalse(TweetDetector.detect_end("Keep continuing the thought"))

    def test_extract_tweet_content_clean(self):
        text = "Omi, tweet now Had a great time meeting the team today"
        extracted = TweetDetector.extract_tweet_content(text)
        self.assertEqual(extracted, "Had a great time meeting the team today")

    def test_extract_tweet_content_with_end_phrase(self):
        text = "Please tweet this AI agents are getting really good end tweet"
        extracted = TweetDetector.extract_tweet_content(text)
        self.assertEqual(extracted, "AI agents are getting really good")

    def test_extract_tweet_content_no_trigger(self):
        text = "Regular conversation without any command"
        self.assertIsNone(TweetDetector.extract_tweet_content(text))


if __name__ == "__main__":
    unittest.main()

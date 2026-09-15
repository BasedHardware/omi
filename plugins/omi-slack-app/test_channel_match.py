"""Hermetic regression for MessageDetector.resolve_channel.

ai_extract_message_and_channel used to fall back to "whichever channel in
channel_map.items() happens to satisfy `a in b or b in a` first" when the
spoken channel name had no exact match. Dict iteration order is whatever the
Slack API returned the channels in, not a relevance signal, so a spoken name
like "dev" with both "dev-ops" and "dev-secrets" in the workspace picked
one of them arbitrarily and sent the voice-dictated message there with no
confirmation step. This asserts the replacement picks the closer match when
there is one, and refuses to guess when candidates are equally close.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResolveChannelTests(unittest.TestCase):
    def setUp(self):
        openai = types.ModuleType("openai")
        openai.AsyncOpenAI = lambda **kwargs: None
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None
        modules = {"openai": openai, "dotenv": dotenv}
        originals = {name: sys.modules.get(name) for name in modules}
        sys.modules.update(modules)
        try:
            self.detector = load("message_detector_under_test", "message_detector.py").MessageDetector
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

    def test_exact_match_wins_regardless_of_order(self):
        channel_map = {"dev-secrets": "C2", "dev": "C1", "dev-ops": "C3"}
        self.assertEqual(self.detector.resolve_channel("dev", channel_map), ("C1", "dev"))

    def test_exact_match_is_case_insensitive(self):
        channel_map = {"General": "C1"}
        self.assertEqual(self.detector.resolve_channel("general", channel_map), ("C1", "General"))

    def test_single_closest_fuzzy_match_wins(self):
        # "gen" is a substring of both, but "general" is the closer match.
        channel_map = {"general": "C1", "generated-reports": "C2"}
        self.assertEqual(self.detector.resolve_channel("gen", channel_map), ("C1", "general"))

    def test_closer_length_wins_over_an_equally_valid_longer_substring_match(self):
        channel_map = {"dev-ops": "C1", "dev-secrets-vault": "C2"}
        self.assertEqual(self.detector.resolve_channel("dev", channel_map), ("C1", "dev-ops"))

    def test_equally_close_candidates_are_left_unresolved(self):
        # "dev-abc" and "dev-xyz" are equidistant from "dev" -- the old code
        # picked whichever came first in the dict (Slack API response order).
        channel_map = {"dev-abc": "C1", "dev-xyz": "C2"}
        self.assertEqual(self.detector.resolve_channel("dev", channel_map), (None, None))

    def test_no_candidates_returns_none(self):
        channel_map = {"general": "C1", "random": "C2"}
        self.assertEqual(self.detector.resolve_channel("engineering", channel_map), (None, None))


if __name__ == "__main__":
    unittest.main()

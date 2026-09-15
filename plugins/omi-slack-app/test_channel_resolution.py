"""Hermetic regression tests for Slack channel resolution (#14112).

Tests resolve_channel and MessageDetector to ensure:
1. Exact (case-insensitive) match wins outright.
2. Closest SequenceMatcher ratio candidate wins when substring matches.
3. Ambiguous tie between equal top-scoring candidates resolves to (None, None).
4. Non-matching channels resolve to (None, None).
"""
import difflib
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Hermetically mock external dependencies (openai, dotenv) before loading message_detector
openai = types.ModuleType("openai")
openai.AsyncOpenAI = Mock()
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda: None

modules = {"openai": openai, "dotenv": dotenv}
originals = {name: sys.modules.get(name) for name in modules}
sys.modules.update(modules)

try:
    message_detector_mod = load("message_detector_under_test", "message_detector.py")
    resolve_channel = message_detector_mod.resolve_channel
    MessageDetector = message_detector_mod.MessageDetector
finally:
    for name, original in originals.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


class ChannelResolutionTests(unittest.TestCase):
    def setUp(self):
        self.channel_map = {
            "general": "C_GEN",
            "random": "C_RND",
            "dev-ops": "C_DEVOPS",
            "dev-secrets": "C_DEVSEC",
            "dev-api": "C_DEVAPI",
        }

    def test_exact_case_insensitive_match_wins_outright(self):
        # Spoken matches exact channel name regardless of case or '#' prefix
        channel_id, name = resolve_channel("General", self.channel_map)
        self.assertEqual(channel_id, "C_GEN")
        self.assertEqual(name, "general")

        channel_id, name = resolve_channel("#random", self.channel_map)
        self.assertEqual(channel_id, "C_RND")
        self.assertEqual(name, "random")

        # Exact match beats partial match even if shorter
        cmap = {"dev": "C_DEV", "dev-ops": "C_DEVOPS"}
        channel_id, name = resolve_channel("dev", cmap)
        self.assertEqual(channel_id, "C_DEV")
        self.assertEqual(name, "dev")

    def test_closest_sequencematcher_candidate_selected(self):
        # "dev" between "dev-ops" (len 7, ratio 0.6) and "dev-secrets" (len 11, ratio ~0.428)
        cmap = {
            "dev-ops": "C_DEVOPS",
            "dev-secrets": "C_DEVSEC"
        }
        channel_id, name = resolve_channel("dev", cmap)
        self.assertEqual(channel_id, "C_DEVOPS")
        self.assertEqual(name, "dev-ops")

    def test_ambiguous_tie_resolves_to_none(self):
        # "dev" between "dev-ops" (ratio 0.6) and "dev-api" (ratio 0.6) is an ambiguous tie
        cmap = {
            "dev-ops": "C_DEVOPS",
            "dev-api": "C_DEVAPI"
        }
        channel_id, name = resolve_channel("dev", cmap)
        self.assertIsNone(channel_id)
        self.assertIsNone(name)

    def test_no_match_returns_none(self):
        channel_id, name = resolve_channel("marketing", self.channel_map)
        self.assertIsNone(channel_id)
        self.assertIsNone(name)

        # Empty or None spoken name
        self.assertEqual(resolve_channel("", self.channel_map), (None, None))
        self.assertEqual(resolve_channel(None, self.channel_map), (None, None))
        self.assertEqual(resolve_channel("general", {}), (None, None))

    def test_message_detector_static_method(self):
        # MessageDetector.resolve_channel exposes the helper
        channel_id, name = MessageDetector.resolve_channel("general", self.channel_map)
        self.assertEqual(channel_id, "C_GEN")
        self.assertEqual(name, "general")


if __name__ == "__main__":
    unittest.main()

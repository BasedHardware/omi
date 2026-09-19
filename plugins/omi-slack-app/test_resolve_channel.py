from pathlib import Path
import importlib.util
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Stub external dependencies so the suite runs hermetically on pure stdlib
_openai = types.ModuleType("openai")
class _AsyncOpenAI:
    def __init__(self, *args, **kwargs):
        self.chat = MagicMock()
_openai.AsyncOpenAI = _AsyncOpenAI

_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *args, **kwargs: None

app_dir = Path(__file__).parent
detector_file = app_dir / "message_detector.py"

spec = importlib.util.spec_from_file_location("message_detector", detector_file)
message_detector = importlib.util.module_from_spec(spec)

with patch.dict(sys.modules, {"openai": _openai, "dotenv": _dotenv}):
    spec.loader.exec_module(message_detector)

resolve_channel = message_detector.resolve_channel


class ResolveChannelTests(unittest.TestCase):

    def setUp(self):
        self.channels = {
            "general": "C_GENERAL",
            "random": "C_RANDOM",
            "dev-ops": "C_DEVOPS",
            "dev-secrets": "C_DEVSECRETS",
            "marketing": "C_MARKETING",
            "engineering": "C_ENGINEERING",
        }

    def test_exact_match(self):
        """Exact channel name match wins case-insensitively with or without #."""
        cid, name = resolve_channel("general", self.channels)
        self.assertEqual(cid, "C_GENERAL")
        self.assertEqual(name, "general")

        cid, name = resolve_channel("#Marketing", self.channels)
        self.assertEqual(cid, "C_MARKETING")
        self.assertEqual(name, "marketing")

    def test_closest_substring_match_chosen_over_distant_candidate(self):
        """When multiple partial candidates match, the closest one by SequenceMatcher is chosen."""
        # "dev" matches both "dev-ops" and "dev-secrets"
        cid, name = resolve_channel("dev", self.channels)
        self.assertEqual(cid, "C_DEVOPS")
        self.assertEqual(name, "dev-ops")

    def test_tie_between_equally_close_candidates_resolves_to_none(self):
        """When multiple candidates tie for the highest score, resolve_channel returns None to prevent arbitrary guessing."""
        tied_channels = {
            "dev-1": "C_DEV1",
            "dev-2": "C_DEV2",
        }
        cid, name = resolve_channel("dev", tied_channels)
        self.assertIsNone(cid)
        self.assertIsNone(name)

    def test_spoken_superset_of_channel_name(self):
        """When spoken name contains the channel name as substring, it resolves properly."""
        cid, name = resolve_channel("engineering team", self.channels)
        self.assertEqual(cid, "C_ENGINEERING")
        self.assertEqual(name, "engineering")

    def test_no_match(self):
        """Unmatched spoken channel returns (None, None)."""
        cid, name = resolve_channel("finance", self.channels)
        self.assertIsNone(cid)
        self.assertIsNone(name)

    def test_empty_inputs(self):
        """Empty or None spoken name or channel map safely returns (None, None)."""
        self.assertEqual(resolve_channel("", self.channels), (None, None))
        self.assertEqual(resolve_channel(None, self.channels), (None, None))
        self.assertEqual(resolve_channel("general", {}), (None, None))
        self.assertEqual(resolve_channel("general", None), (None, None))


if __name__ == "__main__":
    unittest.main()

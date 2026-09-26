# Hermetic unit tests for error sanitization in the speaker tag prompts router.

from __future__ import annotations

import re
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ROUTER_FILE = BACKEND_DIR / "routers" / "speaker_tag_prompts.py"


class TestSpeakerTagPromptsErrorSanitization(unittest.TestCase):
    def test_router_file_exists(self):
        self.assertTrue(ROUTER_FILE.exists(), f"Router file not found: {ROUTER_FILE}")

    def test_no_raw_str_error_leak_in_exceptions(self):
        text = ROUTER_FILE.read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"detail\s*=\s*str\s*\(\s*(?:error|e|exc)\s*\)", text),
            "Raw exception string detail found in router HTTPException!",
        )

    def test_sanitize_helper_defined(self):
        text = ROUTER_FILE.read_text(encoding="utf-8")
        self.assertIn("def _sanitize_speaker_tag_prompt_error", text)
        self.assertIn("speaker_tag_prompt_invalid_submission", text)
        self.assertIn("speaker_tag_prompt_forbidden", text)
        self.assertIn("speaker_tag_prompt_not_found", text)
        self.assertIn("speaker_tag_prompt_state_conflict", text)


if __name__ == "__main__":
    unittest.main()

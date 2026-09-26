# Hermetic unit tests for error sanitization in the desktop TTS updates router.

from __future__ import annotations

import re
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ROUTER_FILE = BACKEND_DIR / "routers" / "desktop_tts_updates.py"


class TestDesktopTtsUpdatesErrorSanitization(unittest.TestCase):
    def test_router_file_exists(self):
        self.assertTrue(ROUTER_FILE.exists(), f"Router file not found: {ROUTER_FILE}")

    def test_logger_configured(self):
        text = ROUTER_FILE.read_text(encoding="utf-8")
        self.assertIn("logger = logging.getLogger(__name__)", text)

    def test_no_raw_exception_detail_leakage(self):
        text = ROUTER_FILE.read_text(encoding="utf-8")
        self.assertNotIn('detail=f"Failed to promote: {exc}"', text)
        self.assertIsNone(
            re.search(r"detail\s*=\s*str\s*\(\s*(?:error|e|exc)\s*\)", text),
            "Raw exception string detail found in router HTTPException!",
        )

    def test_promote_release_sanitizes_unrecognized_errors(self):
        text = ROUTER_FILE.read_text(encoding="utf-8")
        self.assertIn("Failed to promote release: invalid release state", text)
        self.assertIn("Failed to promote: {err_msg}", text)
        self.assertIn("release not found", text)
        self.assertIn("release is already stable", text)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / ".github" / "scripts" / "check_opentofu_gha_wif_notifications.py"


class GhaWifNotificationsCheckerTests(unittest.TestCase):
    def test_checker_passes_on_slice(self) -> None:
        result = subprocess.run([sys.executable, str(CHECKER)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)


if __name__ == "__main__":
    unittest.main()

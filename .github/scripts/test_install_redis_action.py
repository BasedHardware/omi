#!/usr/bin/env python3
"""The hermetic e2e gauntlets must install Redis through the shared timed action."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/backend-hermetic-e2e.yml"
ACTION = ROOT / ".github/actions/install-redis/action.yml"


class InstallRedisActionTests(unittest.TestCase):
    def test_action_bounds_apt_timeouts(self) -> None:
        text = ACTION.read_text(encoding="utf-8")
        self.assertNotIn("timeout-minutes:", text)
        self.assertIn("timeout 90 sudo apt-get update", text)
        self.assertIn("Acquire::Retries=3", text)
        self.assertIn("Acquire::http::Timeout=10", text)
        self.assertIn("redis-server", text)

    def test_hermetic_gauntlets_use_the_shared_action(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(text.count("uses: ./.github/actions/install-redis"), 3)
        self.assertEqual(text.count("timeout-minutes: 2\n        uses: ./.github/actions/install-redis"), 3)
        self.assertNotIn("sudo apt-get update", text)
        self.assertNotIn("sudo apt-get install --yes redis-server", text)


if __name__ == "__main__":
    unittest.main()

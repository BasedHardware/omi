#!/usr/bin/env python3
"""GitHub only runs workflows at the repository root (#11408)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class NestedWorkflowsRemovedTests(unittest.TestCase):
    def test_component_local_workflow_directories_are_gone(self) -> None:
        nested = [
            ROOT / "desktop/macos/.github/workflows",
            ROOT / "plugins/omi-github-app/.github/workflows",
        ]
        for path in nested:
            self.assertFalse(path.exists(), f"{path} is unreachable by GitHub Actions")

    def test_macos_install_smoke_is_promoted_to_root(self) -> None:
        promoted = ROOT / ".github/workflows/desktop-macos-test-install.yml"
        self.assertTrue(promoted.is_file())
        self.assertIn("name: Test macOS Installation", promoted.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

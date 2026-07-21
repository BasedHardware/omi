#!/usr/bin/env python3
"""Regression contract for production-family Codemagic backend routing."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github/scripts/check-mobile-production-routing.py"
SPEC = importlib.util.spec_from_file_location("check_mobile_production_routing", MODULE_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class MobileProductionRoutingContractTests(unittest.TestCase):
    def test_current_config_is_pinned(self) -> None:
        self.assertEqual(CHECKER.validate(ROOT), [])

    def test_rejects_production_family_mutation_to_development_or_arbitrary_url(self) -> None:
        original = (ROOT / "codemagic.yaml").read_text(encoding="utf-8")
        for bad in ("https://api.omi.dev/", "https://staging.example.test/"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "codemagic.yaml").write_text(
                    original.replace('API_BASE_URL=https://api.omi.me/', f'API_BASE_URL={bad}', 1), encoding="utf-8"
                )
                self.assertTrue(CHECKER.validate(root))

    def test_each_production_workflow_rejects_missing_wrong_or_conflicting_assignment(self) -> None:
        original = (ROOT / "codemagic.yaml").read_text(encoding="utf-8")
        for workflow in CHECKER.WORKFLOWS:
            block = CHECKER._workflow_block(original, workflow)
            self.assertIsNotNone(block)
            assert block is not None
            for mutation in ("missing", "wrong", "conflicting"):
                with self.subTest(workflow=workflow, mutation=mutation), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    if mutation == "missing":
                        changed = block.replace("echo API_BASE_URL=https://api.omi.me/ >> .env\n", "", 1)
                    elif mutation == "wrong":
                        changed = block.replace(
                            "echo API_BASE_URL=https://api.omi.me/",
                            "echo API_BASE_URL=https://api.omi.dev/",
                            1,
                        )
                    else:
                        changed = block.replace(
                            "echo API_BASE_URL=https://api.omi.me/ >> .env",
                            "echo API_BASE_URL=https://api.omi.me/ >> .env\n          echo API_BASE_URL=https://staging.example.test/ >> .env",
                            1,
                        )
                    (root / "codemagic.yaml").write_text(original.replace(block, changed, 1), encoding="utf-8")
                    self.assertTrue(CHECKER.validate(root))


if __name__ == "__main__":
    unittest.main()

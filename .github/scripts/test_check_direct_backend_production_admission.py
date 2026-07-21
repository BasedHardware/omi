#!/usr/bin/env python3
"""Static inventory for direct production backend workflow source admission."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github/scripts/check-direct-backend-production-admission.py"
SPEC = importlib.util.spec_from_file_location("check_direct_backend_production_admission", MODULE_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class DirectBackendProductionAdmissionTests(unittest.TestCase):
    def test_inventory_is_admitted_and_uses_checked_out_source_identity(self) -> None:
        self.assertEqual(CHECKER.validate(ROOT), [])

    def test_rejects_branch_bypass_and_github_sha_image_mislabeling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in CHECKER.WORKFLOWS:
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            target = root / CHECKER.WORKFLOWS[0]
            text = target.read_text(encoding="utf-8")
            target.write_text(
                text.replace(
                    "ref: ${{ github.event.inputs.environment == 'prod' && 'main' || github.event.inputs.branch }}",
                    "ref: ${{ github.event.inputs.branch }}",
                    1,
                ),
                encoding="utf-8",
            )
            self.assertTrue(CHECKER.validate(root))
            text = target.read_text(encoding="utf-8")
            target.write_text(text.replace("${IMAGE_TAG}", "${GITHUB_SHA::7}", 1), encoding="utf-8")
            self.assertTrue(CHECKER.validate(root))


if __name__ == "__main__":
    unittest.main()

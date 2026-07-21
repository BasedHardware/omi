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

    def test_each_direct_writer_rejects_each_source_admission_mutation_in_a_fresh_fixture(self) -> None:
        mutations = {
            "caller_ref": (CHECKER.CHECKOUT, "ref: ${{ github.event.inputs.branch }}"),
            "fresh_origin": (CHECKER.ORIGIN_MAIN_FETCH, "git fetch --no-tags origin main"),
            "ancestry": (CHECKER.ANCESTRY_GUARD, "git merge-base --is-ancestor HEAD origin/main"),
            "head_identity": (CHECKER.HEAD_IDENTITY, "CHECKED_OUT_SHA=${GITHUB_SHA}"),
            "image_identity": (CHECKER.IMAGE_IDENTITY, "IMAGE_TAG=${GITHUB_SHA::7}"),
            "diagnostic": (CHECKER.DIAGNOSTIC, "ERROR: source admission failed"),
        }
        for relative in CHECKER.WORKFLOWS:
            for name, (expected, replacement) in mutations.items():
                with self.subTest(workflow=relative, mutation=name), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for fixture_relative in CHECKER.WORKFLOWS:
                        source = ROOT / fixture_relative
                        target = root / fixture_relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                    target = root / relative
                    text = target.read_text(encoding="utf-8")
                    self.assertIn(expected, text)
                    target.write_text(text.replace(expected, replacement, 1), encoding="utf-8")
                    self.assertTrue(CHECKER.validate(root))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Mutation tests for the rollback-first Cloud Run-only production boundary."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github/scripts/check-gcp-backend-production-boundary.py"
SPEC = importlib.util.spec_from_file_location("check_gcp_backend_production_boundary", MODULE_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class GcpBackendProductionBoundaryTests(unittest.TestCase):
    def test_current_workflow_preserves_the_rollback_first_cloud_run_only_boundary(self) -> None:
        self.assertEqual(CHECKER.validate(ROOT), [])

    def test_rejects_production_boundary_regressions(self) -> None:
        original = (ROOT / ".github/workflows/gcp_backend.yml").read_text(encoding="utf-8")
        mutations = {
            "defaults_to_all": ("default: 'cloud-run-only'", "default: 'all'"),
            "permits_prod_all": (CHECKER.PROD_ALL_REJECTION, "if false; then"),
            "reintroduces_tagged_url": ("Production has no tagged candidate URL", "Production has no tagged candidate URL\n# resolve_cloud_run_tagged_url.py"),
            "moves_smoke_before_serving_verification": (CHECKER.PROD_SMOKE, "Smoke production candidate API"),
            "omits_schema_valid_unauthenticated_smoke": (
                "schema-valid inert tag reaches the authorization wall",
                "unexpected response",
            ),
            "uses_invalid_empty_reservation_body": (
                '--data \'{"tag":"macos-unauthenticated-smoke"}\'',
                "--data '{}')",
            ),
            "omits_smoke_rollback": (CHECKER.ROLLBACK_CONDITION, "false"),
            "leaks_smoke_token_to_output": (
                "trap 'rm -f \"$token_file\"' EXIT",
                "trap 'rm -f \"$token_file\"' EXIT\n          echo firebase-production-serving-token >> \"$GITHUB_OUTPUT\"",
            ),
        }
        for name, (expected, replacement) in mutations.items():
            with self.subTest(mutation=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                workflow = root / ".github/workflows/gcp_backend.yml"
                workflow.parent.mkdir(parents=True)
                self.assertIn(expected, original)
                workflow.write_text(original.replace(expected, replacement, 1), encoding="utf-8")
                self.assertTrue(CHECKER.validate(root))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Mutation-sensitive contract for the canonical full-stack production boundary."""

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
    def test_current_workflow_preserves_the_canonical_full_stack_boundary(self) -> None:
        self.assertEqual(CHECKER.validate(ROOT), [])

    def test_rejects_full_stack_boundary_and_canonical_audience_mutations(self) -> None:
        original = (ROOT / ".github/workflows/gcp_backend.yml").read_text(encoding="utf-8")
        mutations = {
            "blocks_prod_all": (
                '          fi\n\n  repair-traffic:',
                '          fi\n'
                '          if [[ "$DEPLOY_ENVIRONMENT" == "prod" && "$DEPLOY_TARGETS" == "all" ]]; then\n'
                "            exit 1\n"
                "          fi\n\n  repair-traffic:",
            ),
            "omits_full_stack_candidate_probe": (
                "if: ${{ github.event.inputs.environment == 'prod' }}",
                "if: ${{ github.event.inputs.environment == 'prod' && github.event.inputs.deploy_targets == 'cloud-run-only' }}",
            ),
            "omits_candidate_tag": (
                "${{ format('--tag={0}', env.TRANSCRIPTION_CANDIDATE_TAG) }}",
                "",
            ),
            "candidate_as_audience": (
                'identity_audience="$(gcloud run services describe "${{ env.SERVICE }}"',
                'identity_audience="$candidate_url"\n          # gcloud run services describe "${{ env.SERVICE }}"',
            ),
            "environment_override": (
                'identity_audience="$(gcloud run services describe "${{ env.SERVICE }}"',
                'identity_audience="${{ vars.BACKEND_CLOUD_RUN_IAM_AUDIENCE }}"\n'
                '          # gcloud run services describe "${{ env.SERVICE }}"',
            ),
            "missing_audience_distinction": (
                '[[ "$identity_audience" != "$candidate_url" ]] || {\n'
                "            echo 'ERROR: canonical Cloud Run IAM audience must differ from tagged candidate URL' >&2; exit 1;\n"
                '          }',
                'true',
            ),
            "candidate_target_replaced": (
                '--candidate-url "${{ steps.transcription-candidate.outputs.url }}"',
                '--candidate-url "${{ steps.transcription-candidate.outputs.identity_audience }}"',
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

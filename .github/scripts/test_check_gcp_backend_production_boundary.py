#!/usr/bin/env python3
"""Mutation tests for the rollback-first Cloud Run-only production boundary."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / ".github" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / ".github" / "scripts"))
from workflow_composite_contract import backend_deploy_contract_text
UPDATES_SOURCE = (ROOT / "backend/routers/updates.py").read_text(encoding="utf-8")

MODULE_PATH = ROOT / ".github/scripts/check-gcp-backend-production-boundary.py"
SPEC = importlib.util.spec_from_file_location("check_gcp_backend_production_boundary", MODULE_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class GcpBackendProductionBoundaryTests(unittest.TestCase):
    def stage_contract(self, root: Path) -> None:
        workflow_path = root / CHECKER.WORKFLOW
        composite_path = root / CHECKER.DEPLOY_BACKEND_STACK_ACTION
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        composite_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / CHECKER.WORKFLOW, workflow_path)
        shutil.copy2(ROOT / CHECKER.DEPLOY_BACKEND_STACK_ACTION, composite_path)

    def mutate_contract(self, root: Path, expected: str, replacement: str) -> None:
        workflow_path = root / CHECKER.WORKFLOW
        composite_path = root / CHECKER.DEPLOY_BACKEND_STACK_ACTION
        workflow = workflow_path.read_text(encoding="utf-8")
        composite = composite_path.read_text(encoding="utf-8")
        contract = backend_deploy_contract_text(workflow, root, CHECKER.DEPLOY_BACKEND_STACK_ACTION)
        self.assertIn(expected, contract)
        if expected in workflow:
            workflow_path.write_text(workflow.replace(expected, replacement, 1), encoding="utf-8")
        else:
            composite_path.write_text(composite.replace(expected, replacement, 1), encoding="utf-8")

    def test_current_workflow_preserves_the_rollback_first_cloud_run_only_boundary(self) -> None:
        self.assertEqual(CHECKER.validate(ROOT), [])

    def test_production_reservation_smoke_uses_a_schema_valid_inert_tag(self) -> None:
        workflow = (ROOT / CHECKER.WORKFLOW).read_text(encoding="utf-8")
        contract = backend_deploy_contract_text(workflow, ROOT, CHECKER.DEPLOY_BACKEND_STACK_ACTION)
        smoke = contract[contract.index(CHECKER.PROD_SMOKE) :]
        match = re.search(r'''--data '\{"tag":"(?P<tag>[^"]+)"\}'\)''', smoke)
        if match is None:
            self.fail("production reservation smoke must send an exact tag body")

        schema = re.search(
            r'class QualifiedBetaPromotionRequest\(BaseModel\):.*?tag: str = Field\(pattern=r"(?P<pattern>[^"]+)"\)',
            UPDATES_SOURCE,
            re.DOTALL,
        )
        if schema is None:
            self.fail("qualified Beta tag schema must remain statically inspectable")
        self.assertRegex(match.group("tag"), re.compile(schema.group("pattern")))

        reserve = UPDATES_SOURCE[
            UPDATES_SOURCE.index("async def reserve_beta_candidate_endpoint(") :
            UPDATES_SOURCE.index('@router.put("/v2/desktop/beta/admission")')
        ]
        self.assertIn("if not _has_beta_promotion_authorization(authorization):", reserve)
        self.assertIn('raise HTTPException(status_code=401, detail="Unauthorized")', reserve)

    def test_rejects_production_boundary_regressions(self) -> None:
        mutations = {
            "defaults_to_all": ("default: 'cloud-run-only'", "default: 'all'"),
            "permits_prod_all": (CHECKER.PROD_ALL_REJECTION, "if false; then"),
            "reintroduces_tagged_url": (
                "inputs.deploy_profile == 'manual' && inputs.environment == 'development'",
                "inputs.deploy_profile == 'manual' && inputs.environment == 'prod'",
            ),
            "moves_smoke_before_serving_verification": (CHECKER.PROD_SMOKE, "Smoke production candidate API"),
            "omits_schema_valid_unauthenticated_smoke": (
                "schema-valid inert tag reaches the authorization wall",
                "unexpected response",
            ),
            "uses_invalid_empty_reservation_body": (
                '--data \'{"tag":"v0.0.0+1-macos"}\'',
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
                self.stage_contract(root)
                self.mutate_contract(root, expected, replacement)
                self.assertTrue(CHECKER.validate(root))

    def test_commented_composite_reference_does_not_expand_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.stage_contract(root)
            workflow_path = root / CHECKER.WORKFLOW
            composite_path = root / CHECKER.DEPLOY_BACKEND_STACK_ACTION
            workflow_path.write_text(
                workflow_path.read_text(encoding="utf-8").replace(
                    "        uses: ./.github/actions/deploy-backend-stack",
                    "        # uses: ./.github/actions/deploy-backend-stack",
                ),
                encoding="utf-8",
            )
            composite_path.write_text(
                composite_path.read_text(encoding="utf-8").replace(
                    CHECKER.PROD_ALL_REJECTION,
                    "if false; then",
                ),
                encoding="utf-8",
            )
            self.assertTrue(CHECKER.validate(root))


if __name__ == "__main__":
    unittest.main()

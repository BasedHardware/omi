#!/usr/bin/env python3
"""Static release-control contract for the one-path desktop operator model."""

# omi-test-quality: source-inspection -- static contract: GitHub workflow authority is YAML-only.
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def codemagic() -> str:
    return (ROOT / "codemagic.yaml").read_text(encoding="utf-8")


class DesktopReleaseFlowContractTests(unittest.TestCase):
    def test_canonical_release_and_qualification_use_lowercase_dmg_asset(self) -> None:
        build_identity = codemagic().split("- name: Resolve trusted source and build identity", 1)[1]
        build_identity = build_identity.split("- name: ", 1)[0]
        preview_branch, canonical_branch = build_identity.split("          else\n", 1)
        qualification = workflow("desktop_qualify_beta.yml")

        self.assertIn('DMG_PATH="$BUILD_DIR/Omi-Preview.dmg"', preview_branch)
        self.assertIn('DMG_PATH="$BUILD_DIR/omi.dmg"', canonical_branch)
        self.assertNotIn('DMG_PATH="$BUILD_DIR/$APP_NAME.dmg"', canonical_branch)
        self.assertIn("--pattern 'Omi.zip' --pattern 'omi.dmg'", qualification)
        self.assertIn("STABLE_DMG=/tmp/desktop-beta-qualification/assets/omi.dmg", qualification)
        self.assertIn('--asset "omi.dmg=$STABLE_DMG"', qualification)

    def test_has_one_automatic_candidate_to_beta_authority(self) -> None:
        candidate = workflow("desktop_auto_release.yml")
        qualification = workflow("desktop_qualify_beta.yml")
        beta = workflow("desktop_promote_beta.yml")
        self.assertIn("schedule:", candidate)
        self.assertNotIn("workflow_dispatch:", candidate)
        self.assertIn("uses: ./.github/workflows/desktop_promote_beta.yml", qualification)
        self.assertIn("workflow_call:", beta)
        self.assertNotIn("workflow_dispatch:", beta)
        self.assertEqual(beta.count("/v2/desktop/beta/promote-qualified"), 1)

    def test_beta_qualification_workflow_uses_supported_exact_cli(self) -> None:
        qualification = workflow("desktop_qualify_beta.yml")
        qualification_script = (ROOT / "desktop/macos/scripts/qualify-desktop-beta.sh").read_text(
            encoding="utf-8"
        )
        qualify_step_name = "      - name: Qualify exact candidate on hermetic stack"
        qualify_step = qualification.split(qualify_step_name, 1)[1]
        qualify_step = qualify_step.split("\n      - name:", 1)[0]
        invoked_options = tuple(
            re.findall(r"^\s+(--[a-z0-9-]+)(?:\s+[^\\]+)? \\$", qualify_step, re.MULTILINE)
        )
        supported_options = set(re.findall(r"^    (--[a-z0-9-]+)\)$", qualification_script, re.MULTILINE))

        self.assertEqual(
            invoked_options,
            (
                "--automatic",
                "--github-actions-artifact",
                "--signed-smoke-result",
                "--candidate-gate-result",
            ),
        )
        self.assertTrue(set(invoked_options).issubset(supported_options))
        self.assertNotIn("--no-promote", qualify_step)

    def test_stable_is_manual_and_uses_one_explicit_confirmation(self) -> None:
        stable = workflow("desktop_promote_prod.yml")
        self.assertIn("workflow_dispatch:", stable)
        self.assertNotIn("\n  schedule:", stable)
        self.assertNotIn("\n  push:", stable)
        self.assertIn("confirm:", stable)
        self.assertIn("promote-stable", stable)
        self.assertNotIn("operation:", stable)
        self.assertNotIn("repoint", stable)
        self.assertNotIn("qualification_run_id", stable)
        self.assertNotIn("expected_current_release_id:", stable)

    def test_beta_recovery_is_the_only_manual_beta_entry_point(self) -> None:
        recovery = workflow("desktop_recover_beta.yml")
        beta = workflow("desktop_promote_beta.yml")
        qualification_script = (ROOT / "desktop/macos/scripts/qualify-desktop-beta.sh").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", recovery)
        for required in ("release_tag:", "confirm:", "reason:", "recover-beta", "github.actor"):
            self.assertIn(required, recovery)
        self.assertIn("uses: ./.github/workflows/desktop_promote_beta.yml", recovery)
        self.assertNotIn("/v2/desktop/beta/promote-qualified", recovery)
        self.assertNotIn("gh workflow run desktop_promote_beta.yml", qualification_script)
        self.assertNotIn("workflow_dispatch:", beta)

    def test_backend_release_vector_verifies_after_prod_traffic_shift(self) -> None:
        backend = workflow("gcp_backend.yml")
        shift = backend.index("      - name: Shift Cloud Run traffic to validated revisions")
        verify = backend.index("      - name: Verify serving backend release vector")
        status = backend.index("      - name: Cloud Run deploy status report", verify)
        self.assertLess(shift, verify)
        self.assertLess(verify, status)
        evidence = backend[verify:status]
        self.assertIn("$DEPLOY_CONTROL_SCRIPTS/verify_backend_release_vector.py", evidence)
        self.assertIn("--deploy-run-id \"${{ github.run_id }}\"", evidence)
        self.assertIn("--deploy-run-attempt \"${{ github.run_attempt }}\"", evidence)


if __name__ == "__main__":
    unittest.main()

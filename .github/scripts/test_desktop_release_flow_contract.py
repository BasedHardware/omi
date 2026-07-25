#!/usr/bin/env python3
"""Workflow contracts for M1-Studio-only macOS Beta qualification."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DesktopReleaseFlowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (ROOT / ".github/workflows/desktop_qualify_beta.yml").read_text(encoding="utf-8")
        self.codemagic = (ROOT / "codemagic.yaml").read_text(encoding="utf-8")

    def test_only_m1_studio_can_qualify(self) -> None:
        self.assertIn("qualify-m1-studio:", self.workflow)
        self.assertIn("omi-qual-m1-studio", self.workflow)
        self.assertIn("needs: qualify-m1-studio", self.workflow)
        self.assertNotIn("codemagic-lane", self.workflow)
        self.assertNotIn("omi-qual-m4-mini", self.workflow)
        self.assertNotIn("omi-desktop-qualification:", self.codemagic)
        self.assertNotIn("desktop_codemagic_qualification", self.workflow)

    def test_m1_qualification_binds_the_immutable_tag(self) -> None:
        for fragment in (
            "ref: ${{ inputs.release_tag }}",
            'git rev-parse "$RELEASE_TAG^{commit}"',
            "git rev-parse 'HEAD^{commit}'",
            "check-desktop-auto-beta-candidate.py",
            "--automatic --github-actions-artifact",
            "group: desktop-beta-qualification-m1",
            "cancel-in-progress: false",
        ):
            self.assertIn(fragment, self.workflow)

    def test_run_staging_evidence_and_cleanup_are_isolated_and_rerun_safe(self) -> None:
        for fragment in (
            "${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}",
            "Refusing reused staging directory",
            "OMI_QUALIFICATION_CLEANUP_CONTEXT",
            "Finalize only this authenticated qualification lease",
            "if: always()",
            "qualification-lease release",
            "desktop-qualification-evidence-${{ inputs.release_tag }}-m1-${{ github.run_id }}-${{ github.run_attempt }}",
            "overwrite: false",
            "qualification-evidence-${TARGET_SHA}-${digest}.json",
        ):
            self.assertIn(fragment, self.workflow)

    def test_normal_codemagic_candidate_build_still_dispatches_m1_workflow(self) -> None:
        self.assertIn("omi-desktop-swift-release:", self.codemagic)
        self.assertIn("Dispatch trusted macOS beta qualification", self.codemagic)
        self.assertIn("gh workflow run desktop_qualify_beta.yml", self.codemagic)


if __name__ == "__main__":
    unittest.main()

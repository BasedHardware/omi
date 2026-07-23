#!/usr/bin/env python3
"""Regression tests for the automatic desktop candidate gate."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("plan-desktop-release.py")
WORKFLOW = Path(__file__).parents[1] / "workflows" / "desktop_auto_release.yml"
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("plan_desktop_release", SCRIPT)
assert SPEC and SPEC.loader
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)

REPOSITORY = "BasedHardware/omi"
SOURCE_SHA = "a" * 40
LATER_NON_DESKTOP_SHA = "b" * 40
LATEST_TAG = "v0.0.1+1-macos"
RELEASABLE_PATH = "desktop/macos/Desktop/Sources/AppDelegate.swift"


class DesktopCandidateSourceCheckTests(unittest.TestCase):
    def test_codemagic_config_is_a_releasable_desktop_input(self) -> None:
        expected_args = [
            "diff",
            "--name-only",
            "--diff-filter=ACDMR",
            f"{LATEST_TAG}..HEAD",
            "--",
            "desktop/macos",
            "codemagic.yaml",
            ".github/scripts/plan-desktop-release.py",
            ".github/workflows/desktop_auto_release.yml",
            ".github/workflows/desktop-swift-ci.yml",
        ]

        with patch.object(planner, "git", return_value="codemagic.yaml\ndesktop/macos/AGENTS.md") as git:
            changes = planner.releasable_desktop_changes_since(LATEST_TAG)

        git.assert_called_once_with(expected_args)
        self.assertEqual(changes, ["codemagic.yaml"])

    def test_exact_source_sha_success_for_every_required_check_passes_the_gate(self) -> None:
        checked: list[tuple[str, str]] = []

        def successful_check(_repository: str, sha: str, check_name: str):
            checked.append((sha, check_name))
            return "completed", "success", None

        with patch.object(planner, "github_check_status", side_effect=successful_check):
            self.assertIsNone(planner.required_source_checks_reason(REPOSITORY, SOURCE_SHA))

        self.assertEqual(
            checked,
            [(SOURCE_SHA, check_name) for check_name in planner.REQUIRED_SOURCE_CHECK_NAMES],
        )

    def test_each_missing_skipped_or_failed_exact_source_check_blocks_the_gate(self) -> None:
        for blocked_name in (
            "Release Eligibility",
            "Desktop Swift Build & Tests",
            "Desktop Swift Release Compile",
        ):
            for blocked_status, blocked_conclusion, expected in (
                (None, None, "missing"),
                ("completed", "skipped", "skipped"),
                ("completed", "failure", "failure"),
            ):
                with self.subTest(check=blocked_name, conclusion=blocked_conclusion):
                    def check_status(_repository: str, _sha: str, check_name: str):
                        if check_name == blocked_name:
                            return blocked_status, blocked_conclusion, None
                        return "completed", "success", None

                    with patch.object(planner, "github_check_status", side_effect=check_status):
                        reason = planner.required_source_checks_reason(REPOSITORY, SOURCE_SHA) or ""
                    self.assertIn(blocked_name, reason)
                    self.assertIn(expected, reason)

    def test_backend_or_docs_commit_after_desktop_commit_keeps_exact_releasable_source(self) -> None:
        checked_shas: list[str] = []

        def fake_git(args: list[str], *, check: bool = True) -> str:
            if args == ["rev-parse", "HEAD"]:
                return LATER_NON_DESKTOP_SHA
            if args == ["log", "--first-parent", "-1", "--format=%H", "HEAD", "--", RELEASABLE_PATH]:
                return SOURCE_SHA
            self.fail(f"unexpected git invocation: {args}")

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[RELEASABLE_PATH]),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "git", side_effect=fake_git),
                patch.object(planner, "required_source_checks_reason", side_effect=lambda _, sha: checked_shas.append(sha)),
                patch.object(planner, "active_release_reason", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertEqual(checked_shas, [SOURCE_SHA])
        self.assertIn(f"source_sha={SOURCE_SHA}", outputs)
        self.assertNotIn(f"source_sha={LATER_NON_DESKTOP_SHA}", outputs)
        self.assertIn("should_release=true", outputs)

    def test_workflow_has_no_input_manual_trigger_and_tags_the_changelog_commit(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        # workflow_dispatch stays bare (no manual inputs). Candidates are cut on a
        # fixed 6-hourly schedule (12am/6am/12pm/6pm America/New_York = 04:00/10:00/
        # 16:00/22:00 UTC in EDT); no per-merge push trigger. No `inputs:` may
        # appear in the trigger block.
        self.assertIn("  workflow_dispatch:\n", workflow)
        self.assertNotIn("inputs:", workflow.split("\njobs:", 1)[0])
        self.assertNotIn("\n  push:", workflow.split("\njobs:", 1)[0])
        self.assertIn("- cron: '0 4,10,16,22 * * *'", workflow)
        self.assertNotIn("break_glass", workflow)
        self.assertIn("source_sha: ${{ steps.plan.outputs.source_sha }}", workflow)
        self.assertIn("ref: ${{ steps.recheck.outputs.source_sha }}", workflow)
        self.assertLess(workflow.index('git commit -m "chore: consolidate changelog for v${VERSION}"'), workflow.index('git tag "$RELEASE_TAG"'))

    def test_pre_tag_readiness_workflow_contract(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        readiness_script = (ROOT / "desktop/macos/scripts/pre-tag-readiness.sh").read_text(encoding="utf-8")
        upload_step = workflow.split("      - name: Upload readiness evidence", 1)[1]
        upload_step = upload_step.split("\n      - name:", 1)[0]
        self.assertIn("if-no-files-found: error", upload_step)
        self.assertIn("+refs/heads/main:refs/remotes/origin/main", readiness_script)
        self.assertNotIn("fetch --quiet --force origin main", readiness_script)
        self.assertIn("pre-tag-readiness:", workflow)
        self.assertIn("verify-pre-tag-readiness.py verify", workflow)
        # Regression: the gate runs on the trusted M1 under macOS bash 3.2, where
        # `"${arr[@]}"` on an EMPTY array under `set -u` traps "unbound variable"
        # and failed the readiness gate on every release with KEEP_STACK != 1 (the
        # normal path), silently blocking all auto-tagging. Optional array flags
        # must use the bash-3.2-safe `${arr[@]+"${arr[@]}"}` expansion.
        self.assertNotIn('--readiness "${KEEP_FLAG[@]}"', readiness_script)
        self.assertIn('${KEEP_FLAG[@]+"${KEEP_FLAG[@]}"}', readiness_script)


if __name__ == "__main__":
    unittest.main()

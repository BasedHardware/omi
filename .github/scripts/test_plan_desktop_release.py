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
SPEC = importlib.util.spec_from_file_location("plan_desktop_release", SCRIPT)
assert SPEC and SPEC.loader
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)

REPOSITORY = "BasedHardware/omi"
SOURCE_SHA = "a" * 40
LATEST_TAG = "v0.0.1+1-macos"
RELEASABLE_PATH = "desktop/macos/Desktop/Sources/AppDelegate.swift"


class DesktopCandidateSourceCheckTests(unittest.TestCase):
    def test_exact_source_sha_success_passes_the_gate(self) -> None:
        with patch.object(planner, "github_check_status", return_value=("completed", "success", None)):
            self.assertIsNone(planner.required_release_eligibility_reason(REPOSITORY, SOURCE_SHA))

    def test_missing_or_failed_source_check_blocks_the_gate(self) -> None:
        with patch.object(planner, "github_check_status", return_value=(None, None, None)):
            self.assertIn("missing", planner.required_release_eligibility_reason(REPOSITORY, SOURCE_SHA) or "")
        with patch.object(planner, "github_check_status", return_value=("completed", "failure", None)):
            self.assertIn("failure", planner.required_release_eligibility_reason(REPOSITORY, SOURCE_SHA) or "")

    def test_automatic_planner_gates_exact_head_release_eligibility(self) -> None:
        checked_shas: list[str] = []

        def fake_git(args: list[str], *, check: bool = True) -> str:
            if args == ["rev-parse", "HEAD"]:
                return SOURCE_SHA
            self.fail(f"unexpected git invocation: {args}")

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[RELEASABLE_PATH]),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "git", side_effect=fake_git),
                patch.object(planner, "required_release_eligibility_reason", side_effect=lambda _, sha: checked_shas.append(sha)),
                patch.object(planner, "active_release_reason", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertEqual(checked_shas, [SOURCE_SHA])
        self.assertIn(f"source_sha={SOURCE_SHA}", outputs)
        self.assertIn("should_release=true", outputs)

    def test_workflow_is_schedule_only_and_tags_the_changelog_commit(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("schedule:", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertNotIn("break_glass", workflow)
        self.assertLess(workflow.index('git commit -m "chore: consolidate changelog for v${VERSION}"'), workflow.index('git tag "$RELEASE_TAG"'))


if __name__ == "__main__":
    unittest.main()

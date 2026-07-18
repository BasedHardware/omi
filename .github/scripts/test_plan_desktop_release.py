#!/usr/bin/env python3
"""Regression tests for the desktop candidate source-check gate."""

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
OTHER_SHA = "b" * 40
LATEST_TAG = "v0.0.1+1-macos"
RELEASABLE_PATH = "desktop/macos/Desktop/Sources/AppDelegate.swift"


class DesktopCandidateSourceCheckTests(unittest.TestCase):
    def source_gate_reason(
        self,
        check_results: dict[str, tuple[str | None, str | None, str | None]],
    ) -> str | None:
        queried_shas: list[str] = []

        def check_status(repository: str, sha: str, check_name: str) -> tuple[str | None, str | None, str | None]:
            self.assertEqual(repository, REPOSITORY)
            self.assertEqual(check_name, planner.DESKTOP_SWIFT_CHECK_NAME)
            queried_shas.append(sha)
            return check_results.get(sha, (None, None, None))

        with patch.object(planner, "github_check_status", side_effect=check_status):
            reason = planner.required_desktop_swift_check_reason(REPOSITORY, SOURCE_SHA)

        self.assertEqual(queried_shas, [SOURCE_SHA])
        return reason

    def test_exact_source_sha_success_passes_the_gate(self) -> None:
        reason = self.source_gate_reason({SOURCE_SHA: ("completed", "success", None)})

        self.assertIsNone(reason)

    def test_pending_source_check_blocks_the_gate(self) -> None:
        reason = self.source_gate_reason({SOURCE_SHA: ("in_progress", None, None)})

        self.assertIn("in_progress", reason or "")

    def test_missing_source_check_blocks_the_gate(self) -> None:
        reason = self.source_gate_reason({})

        self.assertIn("missing", reason or "")

    def test_failed_source_check_blocks_the_gate(self) -> None:
        reason = self.source_gate_reason({SOURCE_SHA: ("completed", "failure", None)})

        self.assertIn("failure", reason or "")

    def test_success_for_a_different_sha_does_not_satisfy_the_gate(self) -> None:
        reason = self.source_gate_reason({OTHER_SHA: ("completed", "success", None)})

        self.assertIn("missing", reason or "")

    def test_queued_release_checks_the_latest_releasable_source_not_an_unrelated_head(self) -> None:
        checked_shas: list[str] = []

        def fake_git(args: list[str], *, check: bool = True) -> str:
            if args == ["rev-parse", "HEAD"]:
                return OTHER_SHA
            if args == ["log", "-1", "--format=%H", f"{LATEST_TAG}..HEAD", "--", RELEASABLE_PATH]:
                return SOURCE_SHA
            self.fail(f"unexpected git invocation: {args}")

        def source_check(repository: str, sha: str) -> str | None:
            self.assertEqual(repository, REPOSITORY)
            checked_shas.append(sha)
            return None

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[RELEASABLE_PATH]),
                patch.object(planner, "git", side_effect=fake_git),
                patch.object(planner, "required_desktop_swift_check_reason", side_effect=source_check),
                patch.object(planner, "active_release_reason", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY, "--mode", "release_now"]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)

            outputs = output_path.read_text(encoding="utf-8")

        self.assertEqual(checked_shas, [SOURCE_SHA])
        self.assertIn(f"source_sha={SOURCE_SHA}", outputs)
        self.assertIn("should_release=true", outputs)

    def test_force_release_still_blocks_when_the_source_check_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=None),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[]),
                patch.object(planner, "git", return_value=SOURCE_SHA),
                patch.object(planner, "required_desktop_swift_check_reason", return_value="required check is missing"),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY, "--mode", "force_release"]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)

            outputs = output_path.read_text(encoding="utf-8")

        self.assertIn(f"source_sha={SOURCE_SHA}", outputs)
        self.assertIn("should_release=false", outputs)
        self.assertIn("required check is missing", outputs)

    def test_force_release_keeps_its_normal_path_after_source_check_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=None),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[]),
                patch.object(planner, "git", return_value=SOURCE_SHA),
                patch.object(planner, "required_desktop_swift_check_reason", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY, "--mode", "force_release"]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)

            outputs = output_path.read_text(encoding="utf-8")

        self.assertIn("should_release=true", outputs)
        self.assertIn("Ready to release 0 changed desktop app file(s).", outputs)

    def test_workflow_tags_the_post_consolidation_changelog_commit(self) -> None:
        # Static wiring contract: GitHub Actions cannot be exercised without a
        # candidate release, so ensure Codemagic's tag contains the release notes.
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('git commit -m "chore: consolidate changelog for v${VERSION}"', workflow)
        self.assertIn('git tag "$RELEASE_TAG"', workflow)
        self.assertNotIn('git tag "$RELEASE_TAG" "$SOURCE_SHA"', workflow)
        self.assertLess(
            workflow.index('git commit -m "chore: consolidate changelog for v${VERSION}"'),
            workflow.index('git tag "$RELEASE_TAG"'),
        )


if __name__ == "__main__":
    unittest.main()

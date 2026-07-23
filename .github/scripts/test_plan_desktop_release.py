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


def _parse_push_filter(workflow_text: str) -> tuple[list[str], set[str]]:
    """Extract `on.push.branches` and `on.push.paths` from the release workflow.

    A deliberately small parser for the workflow's fixed shape (a `push:` block
    with an inline `branches: [main]` and a `paths:` list of single-quoted
    strings), so the check needs no PyYAML in any lane. Raises if the expected
    structure is missing rather than silently returning empty results.
    """
    lines = workflow_text.splitlines()
    branches: list[str] = []
    paths: set[str] = set()
    in_push = False
    in_paths = False
    for raw in lines:
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip(" "))
        if indent <= 2 and stripped.endswith(":") and stripped != "push:":
            # Left the push block on any sibling/parent key (e.g. schedule:).
            if in_push and indent <= 2:
                in_push = False
            in_paths = False
        if stripped == "push:":
            in_push = True
            continue
        if not in_push:
            continue
        if stripped.startswith("branches:"):
            inside = stripped.split("branches:", 1)[1].strip().strip("[]")
            branches = [b.strip().strip("'\"") for b in inside.split(",") if b.strip()]
            in_paths = False
        elif stripped == "paths:":
            in_paths = True
        elif in_paths and stripped.startswith("- "):
            paths.add(stripped[2:].strip().strip("'\""))
        elif in_paths and not stripped.startswith("- ") and stripped:
            in_paths = False
    if not branches or not paths:
        raise AssertionError("Could not parse push.branches/push.paths from desktop_auto_release.yml")
    return branches, paths


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
        # workflow_dispatch stays bare (no manual inputs). Continuous deployment:
        # auto-release fires on macOS-affecting merges to main (push); the schedule
        # remains a backstop. No `inputs:` may appear in the trigger block.
        self.assertIn("  workflow_dispatch:\n", workflow)
        self.assertNotIn("inputs:", workflow.split("\njobs:", 1)[0])
        self.assertIn("  push:\n    branches: [main]", workflow)
        self.assertIn("- cron: '17 * * * *'", workflow)
        self.assertNotIn("break_glass", workflow)
        self.assertIn("source_sha: ${{ steps.plan.outputs.source_sha }}", workflow)
        self.assertIn("ref: ${{ steps.recheck.outputs.source_sha }}", workflow)
        self.assertLess(workflow.index('git commit -m "chore: consolidate changelog for v${VERSION}"'), workflow.index('git tag "$RELEASE_TAG"'))

    def test_candidate_creation_has_no_selfhosted_pre_tag_gate(self) -> None:
        # Continuous deployment: candidate creation (tag-release) must depend only
        # on the hosted planner gate, NOT on a self-hosted pre-candidate readiness
        # job. A self-hosted gate before immutable tag creation was a single point
        # of failure (a down runner blocked ALL releases) and contradicted "create
        # on every change, then qualify". Heavy validation belongs to
        # desktop_qualify_beta.yml, which runs AFTER the candidate exists.
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("pre-tag-readiness:", workflow)
        self.assertNotIn("desktop-pre-tag-readiness-evidence", workflow)
        self.assertNotIn("verify-pre-tag-readiness.py", workflow)
        tag_release = workflow.split("\n  tag-release:\n", 1)[1].split("\n  ", 1)[0]
        self.assertIn("needs: [plan-release]", tag_release)

    def test_push_paths_cover_releasable_desktop_paths(self) -> None:
        # Continuous deployment: every releasable desktop input the planner
        # recognizes must also be in the workflow's push filter, or a merge
        # touching only that input would be releasable yet never get the immediate
        # push trigger (only the schedule backstop would catch it). A directory
        # entry maps to '<dir>/**'.
        #
        # Parse the push filter without PyYAML: this check runs in the `local` and
        # `ci` lanes across environments that do not all ship PyYAML.
        branches, push_paths = _parse_push_filter(WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(branches, ["main"])
        for path in planner.DESKTOP_RELEASE_PATHS:
            expected = f"{path}/**" if (ROOT / path).is_dir() else path
            self.assertIn(
                expected,
                push_paths,
                f"releasable desktop path {path!r} (expected push filter {expected!r}) "
                "is missing from desktop_auto_release.yml push.paths",
            )


if __name__ == "__main__":
    unittest.main()

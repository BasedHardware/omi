#!/usr/bin/env python3
"""Regression tests for the automatic desktop candidate gate."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from contextlib import redirect_stdout
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
UNRELATED_DEV_HARNESS_PATH = "scripts/dev-harness/dev_harness/config.py"


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


def _successful_check(_repository: str, _sha: str, _check_name: str):
    return "completed", "success", "https://example.test/check", None


def _active_producers(_repository: str, _workflow_file: str):
    return "active", None


class DesktopCandidateSourceCheckTests(unittest.TestCase):
    def test_github_check_status_reads_all_exact_sha_runs_and_chooses_the_newest_match(self) -> None:
        response = [
            {
                "check_runs": [
                    {
                        "id": 101,
                        "name": "Release Eligibility",
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": "https://example.test/old",
                        "started_at": "2026-07-25T21:00:00Z",
                        "completed_at": "2026-07-25T21:02:00Z",
                    },
                    {
                        "id": 102,
                        "name": "Unrelated check",
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": "2026-07-25T21:03:00Z",
                        "completed_at": "2026-07-25T21:04:00Z",
                    },
                ]
            },
            {
                "check_runs": [
                    {
                        "id": 103,
                        "name": "Release Eligibility",
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://example.test/new",
                        "started_at": "2026-07-25T21:28:00Z",
                        "completed_at": "2026-07-25T21:28:16Z",
                    }
                ]
            },
        ]
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(response), stderr="")

        with patch.object(planner.subprocess, "run", return_value=completed) as run:
            status, conclusion, html_url, error = planner.github_check_status(
                REPOSITORY, SOURCE_SHA, "Release Eligibility"
            )

        self.assertEqual(
            (status, conclusion, html_url, error), ("completed", "success", "https://example.test/new", None)
        )
        run.assert_called_once_with(
            [
                "gh",
                "api",
                "--paginate",
                "--slurp",
                f"repos/{REPOSITORY}/commits/{SOURCE_SHA}/check-runs?filter=all&per_page=100",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_github_check_status_uses_numeric_id_to_break_timestamp_ties(self) -> None:
        response = [
            {
                "check_runs": [
                    {
                        "id": 99_999_999_999,
                        "name": "Release Eligibility",
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": "2026-07-25T21:28:00Z",
                        "completed_at": "2026-07-25T21:28:16Z",
                    },
                    {
                        "id": 100_000_000_000,
                        "name": "Release Eligibility",
                        "status": "completed",
                        "conclusion": "failure",
                        "started_at": "2026-07-25T21:28:00Z",
                        "completed_at": "2026-07-25T21:28:16Z",
                    },
                ]
            }
        ]
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(response), stderr="")

        with patch.object(planner.subprocess, "run", return_value=completed):
            status, conclusion, _html_url, error = planner.github_check_status(
                REPOSITORY, SOURCE_SHA, "Release Eligibility"
            )

        self.assertEqual((status, conclusion, error), ("completed", "failure", None))

    def test_codemagic_config_is_a_releasable_desktop_input(self) -> None:
        expected_args = [
            "diff",
            "--name-only",
            "--diff-filter=ACDMR",
            f"{LATEST_TAG}..HEAD",
            "--",
            *planner.DESKTOP_RELEASE_PATHS,
        ]

        with patch.object(planner, "git", return_value="codemagic.yaml\ndesktop/macos/AGENTS.md") as git:
            changes = planner.releasable_desktop_changes_since(LATEST_TAG)

        git.assert_called_once_with(expected_args)
        self.assertEqual(changes, ["codemagic.yaml"])
        self.assertNotIn("scripts/dev-harness/dev_harness/qualification.py", planner.DESKTOP_RELEASE_PATHS)
        self.assertNotIn(".github/workflows/desktop_qualify_beta.yml", planner.DESKTOP_RELEASE_PATHS)
        self.assertNotIn(".github/scripts/verify-pre-tag-readiness.py", planner.DESKTOP_RELEASE_PATHS)

    def test_unrelated_dev_harness_change_after_latest_tag_does_not_create_candidate(self) -> None:
        git_calls: list[list[str]] = []

        def scoped_git(args: list[str], *, check: bool = True) -> str:
            git_calls.append(args)
            if args[0] == "diff":
                return UNRELATED_DEV_HARNESS_PATH if UNRELATED_DEV_HARNESS_PATH in args else ""
            self.fail(f"unexpected git invocation: {args}")

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "git", side_effect=scoped_git),
                patch.object(planner, "evaluate_source_checks") as evaluate,
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertEqual(
            git_calls,
            [
                [
                    "diff",
                    "--name-only",
                    "--diff-filter=ACDMR",
                    f"{LATEST_TAG}..HEAD",
                    "--",
                    *planner.DESKTOP_RELEASE_PATHS,
                ]
            ],
        )
        evaluate.assert_not_called()
        self.assertIn("source_sha=", outputs)
        self.assertIn("should_release=false", outputs)
        self.assertIn("No releasable desktop app changes", outputs)

    def test_disabled_producer_workflow_blocks_with_enable_recipe(self) -> None:
        def workflow_state(_repository: str, workflow_file: str):
            if workflow_file.endswith("release-eligibility.yml"):
                return "disabled_manually", None
            return "active", None

        with (
            patch.object(planner, "github_workflow_state", side_effect=workflow_state),
            patch.object(planner, "github_check_status", side_effect=_successful_check),
        ):
            gate = planner.evaluate_source_checks(REPOSITORY, SOURCE_SHA)

        self.assertEqual(gate.state, "blocked")
        self.assertIn("disabled_manually", gate.reason or "")
        self.assertIn("gh workflow enable .github/workflows/release-eligibility.yml", gate.reason or "")
        self.assertIn(f"ci-evidence/{SOURCE_SHA}", gate.reason or "")

    def test_in_progress_required_check_defers(self) -> None:
        def check_status(_repository: str, _sha: str, check_name: str):
            if check_name == "Desktop Swift Build & Tests":
                return "in_progress", None, "https://example.test/run", None
            return "completed", "success", "https://example.test/ok", None

        with (
            patch.object(planner, "github_workflow_state", side_effect=_active_producers),
            patch.object(planner, "github_check_status", side_effect=check_status),
        ):
            gate = planner.evaluate_source_checks(REPOSITORY, SOURCE_SHA)

        self.assertEqual(gate.state, "defer")
        self.assertIn("Desktop Swift Build & Tests", gate.reason or "")
        self.assertIn("in_progress", gate.reason or "")

    def test_all_green_required_checks_are_ready(self) -> None:
        with (
            patch.object(planner, "github_workflow_state", side_effect=_active_producers),
            patch.object(planner, "github_check_status", side_effect=_successful_check),
        ):
            gate = planner.evaluate_source_checks(REPOSITORY, SOURCE_SHA)

        self.assertEqual(gate.state, "ready")

    def test_missing_run_on_old_commit_blocks_with_ci_evidence_recipe(self) -> None:
        def check_status(_repository: str, _sha: str, check_name: str):
            if check_name == "Release Eligibility":
                return None, None, None, None
            return "completed", "success", "https://example.test/ok", None

        with (
            patch.object(planner, "github_workflow_state", side_effect=_active_producers),
            patch.object(planner, "github_check_status", side_effect=check_status),
            patch.object(planner, "github_workflow_runs_for_sha", return_value=([], None)),
            patch.object(planner, "commit_age_seconds", return_value=11 * 60),
        ):
            gate = planner.evaluate_source_checks(REPOSITORY, SOURCE_SHA)

        self.assertEqual(gate.state, "blocked")
        self.assertIn("push events do not replay", gate.reason or "")
        self.assertIn("gh workflow run .github/workflows/release-eligibility.yml --ref ci-evidence/", gate.reason or "")

    def test_missing_run_on_young_commit_defers(self) -> None:
        def check_status(_repository: str, _sha: str, check_name: str):
            if check_name == "Release Eligibility":
                return None, None, None, None
            return "completed", "success", "https://example.test/ok", None

        with (
            patch.object(planner, "github_workflow_state", side_effect=_active_producers),
            patch.object(planner, "github_check_status", side_effect=check_status),
            patch.object(planner, "github_workflow_runs_for_sha", return_value=([], None)),
            patch.object(planner, "commit_age_seconds", return_value=60),
        ):
            gate = planner.evaluate_source_checks(REPOSITORY, SOURCE_SHA)

        self.assertEqual(gate.state, "defer")
        self.assertIn("event-delivery grace", gate.reason or "")

    def test_completed_producing_run_with_absent_check_blocks_with_rerun(self) -> None:
        def check_status(_repository: str, _sha: str, check_name: str):
            if check_name == "Desktop Swift Release Compile":
                return None, None, None, None
            return "completed", "success", "https://example.test/ok", None

        runs = [
            {
                "id": 4242,
                "status": "completed",
                "html_url": "https://github.com/BasedHardware/omi/actions/runs/4242",
            }
        ]
        with (
            patch.object(planner, "github_workflow_state", side_effect=_active_producers),
            patch.object(planner, "github_check_status", side_effect=check_status),
            patch.object(planner, "github_workflow_runs_for_sha", return_value=(runs, None)),
        ):
            gate = planner.evaluate_source_checks(REPOSITORY, SOURCE_SHA)

        self.assertEqual(gate.state, "blocked")
        self.assertIn("gh run rerun 4242", gate.reason or "")

    def test_in_progress_producing_run_for_missing_check_defers(self) -> None:
        def check_status(_repository: str, _sha: str, check_name: str):
            if check_name == "Release Eligibility":
                return None, None, None, None
            return "completed", "success", "https://example.test/ok", None

        runs = [
            {
                "id": 99,
                "status": "in_progress",
                "html_url": "https://github.com/BasedHardware/omi/actions/runs/99",
            }
        ]
        with (
            patch.object(planner, "github_workflow_state", side_effect=_active_producers),
            patch.object(planner, "github_check_status", side_effect=check_status),
            patch.object(planner, "github_workflow_runs_for_sha", return_value=(runs, None)),
        ):
            gate = planner.evaluate_source_checks(REPOSITORY, SOURCE_SHA)

        self.assertEqual(gate.state, "defer")
        self.assertIn("https://github.com/BasedHardware/omi/actions/runs/99", gate.reason or "")

    def test_failed_exact_source_check_blocks_the_gate(self) -> None:
        for blocked_conclusion in ("skipped", "failure", "cancelled"):
            with self.subTest(conclusion=blocked_conclusion):

                def check_status(_repository: str, _sha: str, check_name: str, conclusion=blocked_conclusion):
                    if check_name == "Desktop Swift Build & Tests":
                        return "completed", conclusion, "https://example.test/fail", None
                    return "completed", "success", "https://example.test/ok", None

                with (
                    patch.object(planner, "github_workflow_state", side_effect=_active_producers),
                    patch.object(planner, "github_check_status", side_effect=check_status),
                ):
                    gate = planner.evaluate_source_checks(REPOSITORY, SOURCE_SHA)
                self.assertEqual(gate.state, "blocked")
                self.assertIn("Desktop Swift Build & Tests", gate.reason or "")
                self.assertIn(blocked_conclusion, gate.reason or "")
                self.assertIn("https://example.test/fail", gate.reason or "")

    def test_exact_source_sha_success_for_every_required_check_passes_the_gate(self) -> None:
        checked: list[tuple[str, str]] = []

        def successful_check(_repository: str, sha: str, check_name: str):
            checked.append((sha, check_name))
            return "completed", "success", None, None

        with (
            patch.object(planner, "github_workflow_state", side_effect=_active_producers),
            patch.object(planner, "github_check_status", side_effect=successful_check),
        ):
            gate = planner.required_source_checks_gate(REPOSITORY, SOURCE_SHA)

        self.assertEqual(gate.state, "ready")
        self.assertEqual(
            checked,
            [(SOURCE_SHA, check_name) for check_name in planner.REQUIRED_SOURCE_CHECK_NAMES],
        )

    def test_planner_main_defers_with_warning_and_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            stdout = io.StringIO()
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[RELEASABLE_PATH]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(
                    planner,
                    "evaluate_source_checks",
                    return_value=planner.SourceCheckGate("defer", "required check is in_progress"),
                ),
                patch.object(planner, "active_release_reason", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
                redirect_stdout(stdout),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertIn("::warning::required check is in_progress", stdout.getvalue())
        self.assertIn("should_release=false", outputs)

    def test_codemagic_source_gate_never_waits_for_github_compile_queue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            stdout = io.StringIO()
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[RELEASABLE_PATH]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(planner, "evaluate_source_checks") as github_checks,
                patch.object(planner, "active_release_reason", return_value=None),
                patch.object(
                    sys,
                    "argv",
                    [str(SCRIPT), "--repository", REPOSITORY, "--codemagic-source-gate"],
                ),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
                redirect_stdout(stdout),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        github_checks.assert_not_called()
        self.assertIn("Codemagic owns candidate compile", stdout.getvalue())
        self.assertIn(f"source_sha={SOURCE_SHA}", outputs)
        self.assertIn("should_release=true", outputs)

    def test_planner_main_blocks_with_error_and_exit_one_when_no_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            stdout = io.StringIO()
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[RELEASABLE_PATH]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(
                    planner,
                    "evaluate_source_checks",
                    return_value=planner.SourceCheckGate(
                        "blocked",
                        "push events do not replay. Mint evidence with: gh workflow run x",
                    ),
                ),
                patch.object(planner, "newest_green_fallback_source", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
                redirect_stdout(stdout),
            ):
                self.assertEqual(planner.main(), 1)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertIn("::error::push events do not replay", stdout.getvalue())
        self.assertIn("should_release=false", outputs)

    def test_missing_old_commit_falls_back_to_newest_green_sha(self) -> None:
        fallback_sha = "b" * 40
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[RELEASABLE_PATH]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(
                    planner,
                    "evaluate_source_checks",
                    return_value=planner.SourceCheckGate("blocked", "push events do not replay"),
                ),
                patch.object(
                    planner,
                    "newest_green_fallback_source",
                    return_value=(fallback_sha, "newest green releasable SHA"),
                ),
                patch.object(planner, "active_release_reason", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertIn(f"source_sha={fallback_sha}", outputs)
        self.assertIn("should_release=true", outputs)

    def test_existing_exact_source_tag_preserves_active_or_published_candidate(self) -> None:
        for lifecycle in ("active", "published"):
            with self.subTest(lifecycle=lifecycle):
                with (
                    patch.object(planner, "candidate_tags_for_source", return_value=[LATEST_TAG]),
                    patch.object(
                        planner,
                        "normal_candidate_lifecycle",
                        return_value=(lifecycle, f"normal candidate is {lifecycle}"),
                    ),
                ):
                    reason = planner.existing_source_candidate_reason(REPOSITORY, SOURCE_SHA)

                self.assertIn(LATEST_TAG, reason or "")
                self.assertIn("already owns exact source SHA", reason or "")
                self.assertIn(lifecycle, reason or "")

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
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(
                    planner,
                    "evaluate_source_checks",
                    side_effect=lambda _, sha: checked_shas.append(sha) or planner.SourceCheckGate("ready"),
                ),
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

    def test_duplicate_planner_invocation_does_not_create_another_tag_for_the_same_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=[RELEASABLE_PATH]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(
                    planner,
                    "candidate_tags_for_source",
                    return_value=[LATEST_TAG],
                ),
                patch.object(planner, "normal_candidate_lifecycle", return_value=("active", "candidate is active")),
                patch.object(planner, "evaluate_source_checks") as evaluate,
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        evaluate.assert_not_called()
        self.assertIn("should_release=false", outputs)
        self.assertIn("Desktop candidate already exists", outputs)
        self.assertIn(LATEST_TAG, outputs)

    def test_read_only_status_watcher_reports_only_lifecycle_transitions(self) -> None:
        observations = [
            ("waiting", "", "no immutable candidate tag exists"),
            ("waiting", "", "no immutable candidate tag exists"),
            ("active", LATEST_TAG, "Release OMI Desktop (Swift) is in_progress"),
        ]
        output = io.StringIO()
        with (
            patch.object(planner, "source_candidate_status", side_effect=observations),
            patch.object(planner.time, "sleep") as sleep,
            redirect_stdout(output),
        ):
            self.assertEqual(
                planner.watch_source_candidate(REPOSITORY, SOURCE_SHA, max_polls=3, poll_seconds=30),
                0,
            )

        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("lifecycle=waiting", lines[0])
        self.assertIn("lifecycle=active", lines[1])
        self.assertIn(LATEST_TAG, lines[1])
        self.assertEqual(sleep.call_args_list, [((30,), {}), ((30,), {})])

    def test_workflow_is_a_single_ubuntu_plan_and_tag_job(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n", workflow)
        self.assertNotIn("inputs:", workflow.split("\njobs:", 1)[0])
        trigger = workflow.split("\njobs:", 1)[0]
        self.assertNotIn("\n  push:", trigger)
        self.assertNotIn("break_glass", workflow)
        self.assertIn("plan-and-tag:", workflow)
        self.assertNotIn("tag-release:", workflow)
        self.assertNotIn("plan-release:", workflow)
        self.assertNotIn("omi-qual", workflow)
        self.assertNotIn("self-hosted", workflow)
        self.assertNotIn("CI_GATE_TIMEOUT_SECONDS", workflow)
        self.assertNotIn("source-check-wait-seconds", workflow)
        self.assertNotIn("source-check-poll-seconds", workflow)
        self.assertNotIn("pre-tag-readiness", workflow)
        self.assertNotIn("verify-pre-tag-readiness.py", workflow)
        self.assertIn("timeout-minutes: 30", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("group: desktop-release-planner-main", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("ref: ${{ steps.plan.outputs.source_sha }}", workflow)
        self.assertLess(
            workflow.index("Create and regular-merge PR to sync changelog back to main"),
            workflow.index("Publish immutable tag from merged release source"),
        )
        self.assertNotIn("Replan release source after changelog sync", workflow)
        self.assertNotIn("Select final release plan", workflow)
        self.assertIn('PLANNED_SOURCE_SHA="${{ steps.plan.outputs.source_sha }}"', workflow)
        self.assertIn("if: steps.plan.outputs.should_release == 'true'", workflow)
        self.assertIn("python3 .github/scripts/publish-desktop-candidate-tag.py", workflow)
        self.assertIn("python3 .github/scripts/check-codemagic-tag-intake.py", workflow)
        self.assertIn("--timeout-seconds 0", workflow)
        self.assertIn('test "$(git rev-parse "$RELEASE_TAG^{commit}")" = "$CANDIDATE_SHA"', workflow)
        self.assertIn('CANDIDATE_SHA="$CHANGELOG_COMMIT"', workflow)
        self.assertIn('CANDIDATE_SHA="$PLANNED_SOURCE_SHA"', workflow)
        self.assertNotIn('CANDIDATE_SHA="$MAIN_SHA"', workflow)
        self.assertIn('BRANCH="${BRANCH}-recovery-${GITHUB_RUN_ID}"', workflow)
        self.assertIn("--codemagic-source-gate", workflow)
        self.assertNotIn("wait_for_required_source_checks", Path(SCRIPT).read_text(encoding="utf-8"))

    def test_auto_release_is_an_hourly_train_plus_manual_dispatch(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        trigger = workflow.split("\njobs:", 1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertIn("schedule:", trigger)
        self.assertIn('cron: "7 * * * *"', trigger)
        self.assertNotIn("\n  push:", trigger)
        with self.assertRaises(AssertionError):
            _parse_push_filter(workflow)
        self.assertIn(
            "--min-tag-interval-seconds 3600",
            workflow,
        )
        self.assertNotIn("--min-tag-interval-seconds 3300", workflow)

    def test_hourly_train_defers_while_the_latest_candidate_is_young(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "candidate_publication_age_seconds", return_value=120),
                patch.object(planner, "releasable_desktop_changes_since") as changes,
                patch.object(
                    sys,
                    "argv",
                    [str(SCRIPT), "--repository", REPOSITORY, "--min-tag-interval-seconds", "3600"],
                ),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        changes.assert_not_called()
        self.assertIn("should_release=false", outputs)
        self.assertIn("Hourly release train", outputs)

    def test_train_throttle_reads_release_publication_time_not_commit_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            release_json = json.dumps(
                {
                    "tagName": LATEST_TAG,
                    "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
            )
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=release_json, stderr="")
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner.subprocess, "run", return_value=completed),
                patch.object(planner, "tag_creation_age_seconds") as tag_age,
                patch.object(planner, "releasable_desktop_changes_since") as changes,
                patch.object(
                    sys,
                    "argv",
                    [str(SCRIPT), "--repository", REPOSITORY, "--min-tag-interval-seconds", "3600"],
                ),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        tag_age.assert_not_called()
        changes.assert_not_called()
        self.assertIn("should_release=false", outputs)
        self.assertIn("Hourly release train", outputs)

    def test_train_throttle_uses_tag_creation_time_before_release_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            no_release = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="release not found")
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner.subprocess, "run", return_value=no_release),
                patch.object(planner, "tag_creation_age_seconds", return_value=120) as tag_age,
                patch.object(planner, "releasable_desktop_changes_since") as changes,
                patch.object(
                    sys,
                    "argv",
                    [str(SCRIPT), "--repository", REPOSITORY, "--min-tag-interval-seconds", "3600"],
                ),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        tag_age.assert_called_once_with(LATEST_TAG)
        changes.assert_not_called()
        self.assertIn("should_release=false", outputs)
        self.assertIn("Hourly release train", outputs)

    def test_manual_dispatch_ignores_the_train_interval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "candidate_publication_age_seconds", return_value=1) as age,
                patch.object(planner, "releasable_desktop_changes_since", return_value=[]),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        age.assert_not_called()
        self.assertNotIn("Hourly release train", outputs)

    def test_blocked_newest_sha_falls_back_to_the_newest_green_releasable_sha(self) -> None:
        fallback_sha = "b" * 40
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=["desktop/macos/a.swift"]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(
                    planner,
                    "evaluate_source_checks",
                    return_value=planner.SourceCheckGate("blocked", "required check failed"),
                ),
                patch.object(planner, "releasable_desktop_shas_since", return_value=[SOURCE_SHA, fallback_sha]),
                patch.object(
                    planner,
                    "required_source_checks_gate",
                    return_value=planner.SourceCheckGate("ready"),
                ),
                patch.object(planner, "active_release_reason", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertIn(f"source_sha={fallback_sha}", outputs)
        self.assertIn("should_release=true", outputs)

    def test_blocked_newest_sha_prefers_a_green_sha_ahead_over_an_older_one(self) -> None:
        """A green tip unblocks the train, and ships newer code than the backward fallback.

        Aug 14 2026: main's tip had every required check green while the newest
        desktop-touching commit below it was red on a flaky Swift suite. The
        train shipped an older tree (or wedged) and nothing surfaced it. A
        first-parent commit above the blocked SHA contains everything the
        blocked SHA contains, so its own green exact-SHA checks prove that tree.
        """
        ahead_sha = "c" * 40
        older_green_sha = "b" * 40
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=["desktop/macos/a.swift"]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(
                    planner,
                    "evaluate_source_checks",
                    return_value=planner.SourceCheckGate("blocked", "required check failed"),
                ),
                patch.object(planner, "first_parent_shas_after", return_value=[ahead_sha]),
                patch.object(planner, "releasable_desktop_shas_since", return_value=[SOURCE_SHA, older_green_sha]),
                patch.object(
                    planner,
                    "required_source_checks_gate",
                    return_value=planner.SourceCheckGate("ready"),
                ),
                patch.object(planner, "active_release_reason", return_value=None),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 0)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertIn(f"source_sha={ahead_sha}", outputs)
        self.assertNotIn(f"source_sha={older_green_sha}", outputs)
        self.assertIn("should_release=true", outputs)

    def test_sha_ahead_with_a_skipped_or_absent_check_is_not_treated_as_green(self) -> None:
        """The forward hop needs a genuine `ready`, never a skipped or missing check.

        A commit that does not touch desktop paths skips the Swift jobs. Those
        skipped (or absent) checks prove nothing, so such a commit must not
        carry the train forward.
        """
        ahead_sha = "c" * 40
        gates = {
            ahead_sha: planner.SourceCheckGate("blocked", "completed with skipped"),
        }

        def gate_for(_repository: str, sha: str) -> planner.SourceCheckGate:
            return gates.get(sha, planner.SourceCheckGate("blocked", "required check is missing"))

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=["desktop/macos/a.swift"]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(
                    planner,
                    "evaluate_source_checks",
                    return_value=planner.SourceCheckGate("blocked", "required check failed"),
                ),
                patch.object(planner, "first_parent_shas_after", return_value=[ahead_sha]),
                patch.object(planner, "releasable_desktop_shas_since", return_value=[SOURCE_SHA]),
                patch.object(planner, "required_source_checks_gate", side_effect=gate_for),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 1)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertIn("should_release=false", outputs)
        self.assertIn("source gate blocked", outputs)

    def test_blocked_newest_sha_without_a_green_fallback_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output"
            with (
                patch.object(planner, "latest_desktop_tag", return_value=LATEST_TAG),
                patch.object(planner, "releasable_desktop_changes_since", return_value=["desktop/macos/a.swift"]),
                patch.object(planner, "latest_releasable_desktop_sha", return_value=SOURCE_SHA),
                patch.object(planner, "latest_change_age_seconds", return_value=601),
                patch.object(planner, "existing_source_candidate_reason", return_value=None),
                patch.object(
                    planner,
                    "evaluate_source_checks",
                    return_value=planner.SourceCheckGate("blocked", "required check failed"),
                ),
                patch.object(planner, "releasable_desktop_shas_since", return_value=[SOURCE_SHA]),
                patch.object(sys, "argv", [str(SCRIPT), "--repository", REPOSITORY]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_path)}, clear=False),
            ):
                self.assertEqual(planner.main(), 1)
            outputs = output_path.read_text(encoding="utf-8")

        self.assertIn("should_release=false", outputs)
        self.assertIn("source gate blocked", outputs)


if __name__ == "__main__":
    unittest.main()

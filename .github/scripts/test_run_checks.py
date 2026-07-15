#!/usr/bin/env python3
"""Regression tests and drift guard for the deterministic check manifest."""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
import importlib.util
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from run_checks import Check, execute_checks, load_manifest, resolve_checks, validate_manifest


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
MANIFEST_PATH = REPO_ROOT / ".github/checks-manifest.yaml"
WORKFLOWS_DIR = REPO_ROOT / ".github/workflows"
SCRIPT_REFERENCE_RE = re.compile(r"(?P<path>(?:\.github|backend|desktop/macos)/scripts/[A-Za-z0-9_.-]+\.py)")


def load_deferred_marker_module():
    path = SCRIPT_DIR / "deferred-work-marker-count.py"
    spec = importlib.util.spec_from_file_location("deferred_work_marker_count", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def deterministic_workflow_references(workflows_dir: Path) -> set[str]:
    references: set[str] = set()
    for workflow in sorted(workflows_dir.glob("*.y*ml")):
        for match in SCRIPT_REFERENCE_RE.finditer(workflow.read_text(encoding="utf-8")):
            path = match.group("path")
            name = Path(path).name
            if (
                (path.startswith(".github/scripts/") and (name.startswith(("check_", "check-")) or name.endswith("-count.py")))
                or (path.startswith("backend/scripts/") and name.startswith(("scan_", "check_")))
                or (path.startswith("desktop/macos/scripts/") and name.startswith(("check_", "check-")))
            ):
                references.add(path)
    return references


def registered_script_paths() -> set[str]:
    manifest = load_manifest(MANIFEST_PATH)
    return {token for check in manifest.checks for token in check.command if token.endswith(".py")}


class ManifestContractTests(unittest.TestCase):
    def test_manifest_is_valid(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        self.assertEqual(validate_manifest(manifest, REPO_ROOT), [])

    def test_removing_ci_lane_is_invalid(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        first = manifest.checks[0]
        local_only = Check(first.id, first.command, first.triggers, ("local",), first.reason)
        invalid = type(manifest)((local_only, *manifest.checks[1:]), manifest.exempt)
        self.assertTrue(any("missing required lanes: ci" in error for error in validate_manifest(invalid, REPO_ROOT)))

    def test_workflow_checks_are_registered_or_exempt(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        registered = registered_script_paths()
        exempt = {item.path for item in manifest.exempt}
        missing = sorted(deterministic_workflow_references(WORKFLOWS_DIR) - registered - exempt)
        self.assertEqual(missing, [], f"workflow checks missing from manifest/exempt: {missing}")

    def test_ci_lane_is_reachable_from_repo_checks(self) -> None:
        workflow = (WORKFLOWS_DIR / "repo-checks.yml").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"run_checks\.py\s+--lane\s+ci")
        manifest = load_manifest(MANIFEST_PATH)
        self.assertTrue(any("ci" in check.lanes for check in manifest.checks))

    def test_unregistered_fake_workflow_check_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflows = Path(tmp)
            fake_name = "check_" + "something.py"
            (workflows / "fake.yml").write_text(
                f"steps:\n  - run: python3 .github/scripts/{fake_name}\n",
                encoding="utf-8",
            )
            self.assertEqual(deterministic_workflow_references(workflows), {f".github/scripts/{fake_name}"})


class RunnerBehaviorTests(unittest.TestCase):
    def test_trigger_matching_selects_only_relevant_checks(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        selected = {check.id for check in resolve_checks(manifest, ["app/lib/widgets/example.dart"], "ci")}
        self.assertIn("brand-ui", selected)
        self.assertNotIn("backend-async-blockers", selected)
        self.assertNotIn("backend-route-policy-baseline", selected)

    def test_backend_route_change_selects_route_policy_baseline_in_both_lanes(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        changed = ["backend/routers/chat_sessions.py"]
        for lane in ("local", "ci"):
            selected = {check.id for check in resolve_checks(manifest, changed, lane)}
            self.assertIn("backend-route-policy-baseline", selected)

    def test_failure_class_protocol_runs_in_both_lanes(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        for lane in ("local", "ci"):
            selected = {check.id for check in resolve_checks(manifest, ["app/lib/example.dart"], lane)}
            self.assertIn("failure-class-protocol", selected)

    def test_backend_datetime_sort_sentinel_ratchet_runs_for_backend_sources(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        for lane in ("local", "ci"):
            selected = {check.id for check in resolve_checks(manifest, ["backend/routers/example.py"], lane)}
            self.assertIn("backend-datetime-sort-sentinel-ratchet", selected)

    def test_failure_is_propagated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fail = root / "fail.py"
            fail.write_text("raise SystemExit(7)\n", encoding="utf-8")
            changed = root / "changed.txt"
            changed.write_text("example.txt\n", encoding="utf-8")
            body = root / "body.txt"
            body.write_text("", encoding="utf-8")
            check = Check("fails", (sys.executable, str(fail)), ("all",), ("ci",), "fixture")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                result = execute_checks(
                    root,
                    [check],
                    changed_files_path=changed,
                    base="base",
                    head="HEAD",
                    pr_body_file=body,
                )
            self.assertEqual(result, 1)


class DeferredMarkerTests(unittest.TestCase):
    def test_new_marker_requires_tracking_issue(self) -> None:
        module = load_deferred_marker_module()
        marker = "TO" + "DO"
        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix=".manifest-marker-") as tmp:
            root = Path(tmp)
            candidate = root / "fixture.txt"
            changed = root / "changed.txt"
            relative = candidate.relative_to(REPO_ROOT).as_posix()
            changed.write_text(f"{relative}\n", encoding="utf-8")

            candidate.write_text(f"{marker}: missing owner\n", encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(module.check_new_markers("origin/main", changed), 1)

            candidate.write_text(f"{marker}(#9448): owned follow-up\n", encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(module.check_new_markers("origin/main", changed), 0)


if __name__ == "__main__":
    unittest.main()

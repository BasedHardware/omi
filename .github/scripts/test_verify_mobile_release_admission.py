#!/usr/bin/env python3
"""Hermetic fixtures for mobile release admission and aggregate semantics."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github/scripts/verify_mobile_release_admission.py"
SPEC = importlib.util.spec_from_file_location("verify_mobile_release_admission", MODULE_PATH)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GUARD
SPEC.loader.exec_module(GUARD)

SHA = "a" * 40
CURRENT_MAIN = "b" * 40
REPOSITORY = "BasedHardware/omi"


def proof(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "repository": REPOSITORY,
        "source_sha": SHA,
        "current_main": {
            "branch": "main",
            "sha": CURRENT_MAIN,
            "source_sha_is_ancestor_of_current_main": True,
        },
        "release_eligibility": {
            "workflow_name": "Release Eligibility",
            "workflow_path": ".github/workflows/release-eligibility.yml",
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 1,
            "head_branch": "main",
            "head_sha": SHA,
            "repository": REPOSITORY,
        },
        "mobile_aggregate": {
            "check_name": "Mobile Release Eligibility",
            "workflow_name": "Mobile App Checks",
            "workflow_path": ".github/workflows/mobile-app-checks.yml",
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 1,
            "head_branch": "main",
            "head_sha": SHA,
            "repository": REPOSITORY,
        },
    }
    value.update(overrides)
    return value


def with_nested(value: dict[str, object], section: str, **overrides: object) -> dict[str, object]:
    updated = dict(value)
    updated[section] = {**value[section], **overrides}  # type: ignore[arg-type]
    return updated


class MobileReleaseAdmissionTests(unittest.TestCase):
    def assert_admitted(self, value: object = ..., *, sha: str = SHA, repository: str = REPOSITORY) -> None:
        GUARD.validate_admission(proof() if value is ... else value, sha=sha, repository=repository)

    def test_accepts_exact_success_with_current_main_advanced(self) -> None:
        self.assert_admitted()

    def test_accepts_exact_current_main_tip(self) -> None:
        self.assert_admitted(proof(current_main={
            "branch": "main",
            "sha": SHA,
            "source_sha_is_ancestor_of_current_main": True,
        }))

    def test_rejects_wrong_source_sha(self) -> None:
        with self.assertRaisesRegex(GUARD.MobileReleaseAdmissionError, "requested source SHA"):
            self.assert_admitted(with_nested(proof(), "release_eligibility", head_sha="c" * 40))
        with self.assertRaisesRegex(GUARD.MobileReleaseAdmissionError, "requested source SHA"):
            self.assert_admitted(sha="c" * 40)

    def test_rejects_source_that_is_not_current_main_ancestor(self) -> None:
        with self.assertRaisesRegex(GUARD.MobileReleaseAdmissionError, "ancestor"):
            self.assert_admitted(proof(current_main={
                "branch": "main",
                "sha": CURRENT_MAIN,
                "source_sha_is_ancestor_of_current_main": False,
            }))

    def test_rejects_wrong_repository_event_or_workflow_identity(self) -> None:
        cases = (
            ("top-level repository", proof(repository="fork/omi")),
            ("release repository", with_nested(proof(), "release_eligibility", repository="fork/omi")),
            ("release event", with_nested(proof(), "release_eligibility", event="pull_request")),
            ("release workflow", with_nested(proof(), "release_eligibility", workflow_name="Build")),
            ("aggregate workflow", with_nested(proof(), "mobile_aggregate", workflow_name="Build")),
            ("aggregate check", with_nested(proof(), "mobile_aggregate", check_name="Dart Analyze & Tests")),
        )
        for name, value in cases:
            with self.subTest(name=name), self.assertRaises(GUARD.MobileReleaseAdmissionError):
                self.assert_admitted(value)

    def test_rejects_rerun_or_non_first_attempt(self) -> None:
        for attempt in (2, "1", True, 0):
            with self.subTest(attempt=attempt), self.assertRaisesRegex(
                GUARD.MobileReleaseAdmissionError, "first attempt"
            ):
                self.assert_admitted(with_nested(proof(), "release_eligibility", run_attempt=attempt))

    def test_rejects_missing_pending_or_cancelled_release_proof(self) -> None:
        for name, value in (
            ("missing", {**proof(), "release_eligibility": None}),
            ("pending", with_nested(proof(), "release_eligibility", status="in_progress")),
            ("cancelled", with_nested(proof(), "release_eligibility", conclusion="cancelled")),
        ):
            with self.subTest(name=name), self.assertRaises(GUARD.MobileReleaseAdmissionError):
                self.assert_admitted(value)

    def test_rejects_malformed_proof_and_shas(self) -> None:
        malformed = (
            None,
            [],
            {},
            {**proof(), "schema_version": "1"},
            {**proof(), "source_sha": "main"},
            {**proof(), "current_main": {"branch": "main"}},
        )
        for value in malformed:
            with self.subTest(value=value), self.assertRaises(GUARD.MobileReleaseAdmissionError):
                self.assert_admitted(value)

    def test_rejects_failed_pending_cancelled_or_wrong_sha_aggregate(self) -> None:
        cases = (
            ("failure", {"conclusion": "failure"}),
            ("pending", {"status": "in_progress"}),
            ("cancelled", {"conclusion": "cancelled"}),
            ("wrong sha", {"head_sha": "c" * 40}),
        )
        for name, overrides in cases:
            with self.subTest(name=name), self.assertRaises(GUARD.MobileReleaseAdmissionError):
                self.assert_admitted(with_nested(proof(), "mobile_aggregate", **overrides))

    def test_accepts_legitimate_inapplicable_jobs_as_skipped(self) -> None:
        results = {
            "changes": "success",
            "generated-files": "skipped",
            "analyze-and-test": "skipped",
            "journeys-hermetic": "skipped",
            "android-compile-smoke": "success",
            "android-unit-tests": "success",
            "ios-compile-check": "skipped",
            "dart-tests-kiritimati": "skipped",
        }
        GUARD.validate_mobile_job_results(results)
        self.assert_admitted(with_nested(proof(), "mobile_aggregate", job_results=results))

    def test_rejects_failed_job_even_when_aggregate_shape_is_present(self) -> None:
        results = {
            "changes": "success",
            "generated-files": "skipped",
            "analyze-and-test": "failure",
            "journeys-hermetic": "skipped",
            "android-compile-smoke": "skipped",
            "android-unit-tests": "skipped",
            "ios-compile-check": "skipped",
            "dart-tests-kiritimati": "skipped",
        }
        with self.assertRaisesRegex(GUARD.MobileReleaseAdmissionError, "failed"):
            self.assert_admitted(with_nested(proof(), "mobile_aggregate", job_results=results))

    def test_rejects_skipped_change_detection(self) -> None:
        results = {
            "changes": "skipped",
            "generated-files": "skipped",
            "analyze-and-test": "skipped",
            "journeys-hermetic": "skipped",
            "android-compile-smoke": "skipped",
            "android-unit-tests": "skipped",
            "ios-compile-check": "skipped",
            "dart-tests-kiritimati": "skipped",
        }
        with self.assertRaisesRegex(GUARD.MobileReleaseAdmissionError, "changes"):
            self.assert_admitted(with_nested(proof(), "mobile_aggregate", job_results=results))

    def test_cli_rejects_malformed_json_without_network_or_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proof.json"
            path.write_text("not json", encoding="utf-8")
            with self.assertRaises(GUARD.MobileReleaseAdmissionError):
                GUARD._read_proof(path)

    def test_cli_accepts_explicit_valid_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proof.json"
            path.write_text(json.dumps(proof()), encoding="utf-8")
            with patch.object(
                sys,
                "argv",
                [
                    "verify_mobile_release_admission.py",
                    "--sha",
                    SHA,
                    "--repository",
                    REPOSITORY,
                    "--proof",
                    str(path),
                ],
            ):
                self.assertEqual(GUARD.main(), 0)

    def test_workflow_publishes_the_documented_aggregate_contract(self) -> None:
        workflow = (ROOT / ".github/workflows/mobile-app-checks.yml").read_text(encoding="utf-8")
        self.assertIn("name: Mobile Release Eligibility", workflow)
        self.assertIn("if: ${{ always() }}", workflow)
        self.assertIn("success|skipped", workflow)
        for job_id in (
            "changes",
            "generated-files",
            "analyze-and-test",
            "journeys-hermetic",
            "android-compile-smoke",
            "android-unit-tests",
            "ios-compile-check",
            "dart-tests-kiritimati",
        ):
            self.assertIn(f"      - {job_id}", workflow)


if __name__ == "__main__":
    unittest.main()

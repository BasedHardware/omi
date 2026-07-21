#!/usr/bin/env python3
"""Hermetic subprocess tests for scripts/failure-class."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CLI = REPOSITORY_ROOT / "scripts" / "failure-class"
SEED_DIRECTORY = REPOSITORY_ROOT / ".github" / "failure-classes"
REPORT_FIXTURE = REPOSITORY_ROOT / "scripts" / "fixtures" / "failure_class" / "report-events.json"
SEED_IDS = {
    "FC-malformed-doc-read",
    "FC-unbounded-module-cache",
    "FC-trapping-dict-merge",
    "FC-per-hop-timeout",
    "FC-split-mutation-authority",
}


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=False, text=True, capture_output=True)


class FailureClassCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        definitions = self.root / ".github" / "failure-classes"
        definitions.parent.mkdir(parents=True)
        shutil.copytree(SEED_DIRECTORY, definitions)
        run(["git", "init", "-q"], self.root)
        run(["git", "config", "user.email", "failure-class@example.test"], self.root)
        run(["git", "config", "user.name", "Failure Class Test"], self.root)
        self.write("src/example.txt", "initial\n")
        self.commit("chore: seed failure classes")
        self.base = self.git("rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def git(self, *args: str) -> str:
        result = run(["git", *args], self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def write(self, relative_path: str, content: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def commit(self, subject: str) -> None:
        self.git("add", ".")
        self.git("commit", "-qm", subject)

    def add_fix_commit(self) -> None:
        self.write("src/example.txt", "fixed\n")
        self.commit("fix(backend): protect read boundary")

    def body(self, content: str) -> Path:
        return self.write("pr-body.md", content)

    def cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return run([sys.executable, str(CLI), *arguments, "--root", str(self.root), "--format", "json"], self.root)

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"CLI did not emit JSON: {exc}\nstdout={result.stdout}\nstderr={result.stderr}")

    def validate(self, body: Path) -> subprocess.CompletedProcess[str]:
        return self.cli("validate", "--base", self.base, "--head", "HEAD", "--pr-body-file", str(body))

    def test_seed_definitions_are_valid_without_fix_commit(self) -> None:
        result = self.validate(self.body("## Summary\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["validation"]["definition_count"], 5)
        self.assertEqual({path.stem for path in SEED_DIRECTORY.glob("*.json")}, SEED_IDS)

    def test_valid_existing_declaration(self) -> None:
        self.add_fix_commit()
        result = self.validate(self.body("Failure-Class: FC-malformed-doc-read\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["validation"]["declaration"], "FC-malformed-doc-read")

    def test_missing_declaration_for_fix_commit_fails(self) -> None:
        self.add_fix_commit()
        result = self.validate(self.body("## Summary\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing_declaration", [item["code"] for item in payload["errors"]])

    def test_unknown_declaration_fails(self) -> None:
        self.add_fix_commit()
        result = self.validate(self.body("Failure-Class: FC-not-in-registry\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown_failure_class", [item["code"] for item in payload["errors"]])

    def test_dormant_class_declaration_requires_explicit_reopen(self) -> None:
        definition_path = self.root / ".github" / "failure-classes" / "FC-malformed-doc-read.json"
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        definition.update({"status": "dormant", "dormant_since": "2026-07-05T00:00:00Z"})
        definition_path.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
        self.add_fix_commit()

        result = self.validate(self.body("Failure-Class: FC-malformed-doc-read\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 1)
        self.assertIn("dormant_failure_class_requires_reopen", [item["code"] for item in payload["errors"]])

    def test_existing_class_fix_cannot_mutate_registry(self) -> None:
        definition_path = self.root / ".github" / "failure-classes" / "FC-malformed-doc-read.json"
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        definition["canonical_prevention"] = "An incident fix must not update this registry record."
        definition_path.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
        self.add_fix_commit()

        result = self.validate(self.body("Failure-Class: FC-malformed-doc-read\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 1)
        self.assertIn("instance_fix_mutates_registry", [item["code"] for item in payload["errors"]])

    def test_registry_only_dormant_transition_is_valid(self) -> None:
        definition_path = self.root / ".github" / "failure-classes" / "FC-malformed-doc-read.json"
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        definition.update({"status": "dormant", "dormant_since": "2026-07-05T00:00:00Z"})
        definition_path.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
        self.commit("harden: record a dormant failure class")

        result = self.validate(self.body("## Registry lifecycle transition\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload["ok"])

    def test_new_declaration_requires_and_accepts_new_definition(self) -> None:
        definition = {
            "schema_version": 1,
            "id": "FC-new-test-boundary",
            "violated_contract": "Test boundaries retain their contract.",
            "canonical_prevention": "Keep the guard at the shared boundary.",
            "evidence_prs": [1234],
            "status": "open",
        }
        self.write(
            ".github/failure-classes/FC-new-test-boundary.json",
            json.dumps(definition, indent=2) + "\n",
        )
        self.write("src/example.txt", "new class\n")
        self.commit("fix: register a newly observed class")
        result = self.validate(self.body("Failure-Class: new\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload["ok"])

    def test_new_declaration_without_added_definition_fails(self) -> None:
        self.add_fix_commit()
        result = self.validate(self.body("Failure-Class: new\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 1)
        self.assertIn("new_definition_required", [item["code"] for item in payload["errors"]])

    def test_prepare_emits_append_patch_and_registry_only_candidates(self) -> None:
        self.add_fix_commit()
        result = self.cli("prepare", "--base", self.base, "--head", "HEAD", "--pr-body-file", str(self.body("## Summary\n")))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload["requires_declaration"])
        self.assertEqual(payload["pr_body_patch"]["operation"], "append")
        self.assertEqual(payload["pr_body_patch"]["text"], "Failure-Class: none\n")
        self.assertEqual(len(payload["advisory_candidates"]), 5)
        self.assertIn("no class was inferred", payload["candidate_source"])

    def test_explain_emits_versioned_definition(self) -> None:
        result = self.cli("explain", "FC-trapping-dict-merge")
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["failure_class"]["id"], "FC-trapping-dict-merge")
        self.assertEqual(payload["failure_class"]["evidence_prs"], [6506, 9288])

    def test_report_fixture_marks_old_open_instance_closure_eligible(self) -> None:
        result = self.cli(
            "report",
            "--events-file",
            str(REPORT_FIXTURE),
            "--since",
            "14d",
            "--now",
            "2026-07-16T00:00:00Z",
        )
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload["advisory"])
        self.assertFalse(payload["automatic_state_changes"])
        by_id = {item["id"]: item for item in payload["classes"]}
        self.assertTrue(by_id["FC-malformed-doc-read"]["closure_eligible"])
        self.assertFalse(by_id["FC-trapping-dict-merge"]["closure_eligible"])
        self.assertEqual(by_id["FC-malformed-doc-read"]["last_reported_instance"]["number"], 9494)

    def test_report_flags_recurrence_after_a_dormant_transition(self) -> None:
        definition_path = self.root / ".github" / "failure-classes" / "FC-trapping-dict-merge.json"
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        definition.update({"status": "dormant", "dormant_since": "2026-07-05T00:00:00Z"})
        definition_path.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")

        result = self.cli(
            "report",
            "--events-file",
            str(REPORT_FIXTURE),
            "--since",
            "14d",
            "--now",
            "2026-07-16T00:00:00Z",
        )
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        by_id = {item["id"]: item for item in payload["classes"]}
        self.assertTrue(by_id["FC-trapping-dict-merge"]["reopen_required"])
        self.assertFalse(by_id["FC-trapping-dict-merge"]["closure_eligible"])


if __name__ == "__main__":
    unittest.main()

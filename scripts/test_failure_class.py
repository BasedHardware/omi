#!/usr/bin/env python3
"""Hermetic subprocess tests for scripts/failure-class."""

from __future__ import annotations

import json
import os
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
# The registry grows as classes are declared; derive the seed set instead of
# pinning a count that goes stale the next time a class is added.
SEED_IDS = {path.stem for path in SEED_DIRECTORY.glob("*.json")}


# Disposable repositories must not inherit the caller's git context. Under a
# pre-commit or pre-push hook, GIT_DIR and core.hooksPath point at the real
# checkout, so an unisolated `git init`/`git config`/`git add .` in a temp
# directory writes to the repository under test.
GIT_ISOLATION = ["-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false"]


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    if command and command[0] == "git":
        command = [command[0], *GIT_ISOLATION, *command[1:]]
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return subprocess.run(command, cwd=cwd, check=False, text=True, capture_output=True, env=environment)


class FailureClassCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        definitions = self.root / ".github" / "failure-classes"
        definitions.parent.mkdir(parents=True)
        shutil.copytree(SEED_DIRECTORY, definitions)
        self.seed_canonical_prevention_artifacts(definitions)
        run(["git", "init", "-q"], self.root)
        run(["git", "config", "user.email", "failure-class@example.test"], self.root)
        run(["git", "config", "user.name", "Failure Class Test"], self.root)
        self.write("src/example.txt", "initial\n")
        self.commit("chore: seed failure classes")
        self.base = self.git("rev-parse", "HEAD")

    def seed_canonical_prevention_artifacts(self, definitions: Path) -> None:
        """Materialize the guard artifacts the copied registry declares.

        `canonical_prevention_artifact` paths are validated against the CLI's
        --root, so the synthetic repository must contain them for the seed
        definitions to stay valid outside the real checkout.
        """
        for definition_path in sorted(definitions.glob("*.json")):
            data = json.loads(definition_path.read_text(encoding="utf-8"))
            for relative in data.get("canonical_prevention_artifact", []):
                artifact = self.root / relative
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.touch()

    def tearDown(self) -> None:
        # The synthetic repo's `.git` can still be receiving background writes when the
        # test finishes, so a strict rmtree races them and raises "Directory not empty".
        # Cleanup failures say nothing about the assertions, which have already run — a
        # temp directory the OS will reclaim must never be able to fail the suite.
        shutil.rmtree(self.temp_directory.name, ignore_errors=True)
        self.temp_directory._finalizer.detach()  # type: ignore[attr-defined]

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
        self.assertEqual(payload["validation"]["definition_count"], len(SEED_IDS))
        self.assertIn("FC-split-mutation-authority", SEED_IDS)

    def set_definition_field(self, class_id: str, field: str, value: object) -> None:
        path = self.root / ".github" / "failure-classes" / f"{class_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data[field] = value
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def test_canonical_prevention_artifact_accepts_an_existing_path(self) -> None:
        self.write("backend/guards/read_boundary.py", "# guard\n")
        self.set_definition_field(
            "FC-malformed-doc-read", "canonical_prevention_artifact", ["backend/guards/read_boundary.py"]
        )
        result = self.validate(self.body("## Summary\n"))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.payload(result)["ok"])

    def test_canonical_prevention_artifact_must_exist(self) -> None:
        self.set_definition_field(
            "FC-malformed-doc-read", "canonical_prevention_artifact", ["backend/guards/absent.py"]
        )
        result = self.validate(self.body("## Summary\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing_canonical_prevention_artifact", [item["code"] for item in payload["errors"]])

    def test_canonical_prevention_artifact_rejects_a_malformed_value(self) -> None:
        self.set_definition_field("FC-malformed-doc-read", "canonical_prevention_artifact", [])
        result = self.validate(self.body("## Summary\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid_canonical_prevention_artifact", [item["code"] for item in payload["errors"]])

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

    def test_instance_fix_may_record_guard_artifact_for_declared_class(self) -> None:
        self.write("backend/guards/read_boundary.py", "# guard\n")
        self.set_definition_field(
            "FC-malformed-doc-read", "canonical_prevention_artifact", ["backend/guards/read_boundary.py"]
        )
        self.add_fix_commit()

        result = self.validate(self.body("Failure-Class: FC-malformed-doc-read\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload["ok"])

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

    def write_new_definition(self, class_id: str, evidence_prs: object) -> None:
        definition = {
            "schema_version": 1,
            "id": class_id,
            "violated_contract": "Test boundaries retain their contract.",
            "canonical_prevention": "Keep the guard at the shared boundary.",
            "evidence_prs": evidence_prs,
            "status": "open",
        }
        self.write(
            f".github/failure-classes/{class_id}.json",
            json.dumps(definition, indent=2) + "\n",
        )

    def test_new_definition_may_declare_empty_evidence_prs(self) -> None:
        """A class born in this PR has no merged PR to cite.

        `evidence_prs` records merged PRs, and the PR fixing a class's first instance
        has no number until it is opened. Requiring non-empty made `Failure-Class: new`
        unsatisfiable without inventing a number or pushing with --no-verify.
        """
        self.write_new_definition("FC-new-test-boundary", [])
        self.write("src/example.txt", "new class\n")
        self.commit("fix: register a newly observed class")
        result = self.validate(self.body("Failure-Class: new\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload["ok"])

    def test_empty_evidence_prs_stays_valid_once_the_class_is_merged(self) -> None:
        """The allowance must not depend on the class being new in the range.

        A rule scoped to 'added by this change' would pass in the authoring PR and then
        fail on every run afterwards, because the merged definition is no longer new.
        """
        self.set_definition_field("FC-malformed-doc-read", "evidence_prs", [])
        result = self.validate(self.body("## Summary\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload["ok"])

    def test_evidence_prs_still_rejects_non_positive_entries(self) -> None:
        self.set_definition_field("FC-malformed-doc-read", "evidence_prs", [0])
        result = self.validate(self.body("## Summary\n"))
        payload = self.payload(result)
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid_evidence_prs", [item["code"] for item in payload["errors"]])

    def test_pipe_separated_declaration_reports_the_declaration_not_the_registry(self) -> None:
        """The old template read as a pipe-separated value, and the resulting error
        pointed at the registry instead of at the malformed line."""
        self.write_new_definition("FC-new-test-boundary", [])
        self.write("src/example.txt", "new class\n")
        self.commit("fix: register a newly observed class")
        result = self.validate(self.body("Failure-Class: FC-new-test-boundary | new\n"))
        payload = self.payload(result)
        codes = [item["code"] for item in payload["errors"]]
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid_declaration", codes)
        self.assertNotIn("instance_fix_mutates_registry", codes)
        declaration_error = next(item for item in payload["errors"] if item["code"] == "invalid_declaration")
        self.assertIn("|", declaration_error["message"])
        self.assertEqual(
            declaration_error["accepted_forms"],
            ["Failure-Class: FC-<lower-kebab-slug>", "Failure-Class: new", "Failure-Class: none"],
        )

    def test_prepare_narrows_candidates_to_matching_scope_hints(self) -> None:
        self.set_definition_field("FC-malformed-doc-read", "scope_hints", ["src/**"])
        self.write("src/example.txt", "touched\n")
        self.commit("fix(backend): protect read boundary")
        result = self.cli(
            "prepare", "--base", self.base, "--head", "HEAD", "--pr-body-file", str(self.body("## Summary\n"))
        )
        payload = self.payload(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([item["id"] for item in payload["advisory_candidates"]], ["FC-malformed-doc-read"])
        self.assertEqual(payload["candidates_total"], len(SEED_IDS))
        self.assertIn("advisory", payload["candidate_narrowing"])

    def test_prepare_lists_every_candidate_when_nothing_matches_scope(self) -> None:
        """Narrowing to nothing would read as 'no class can apply' — a classification
        this CLI does not make."""
        for class_id in SEED_IDS:
            self.set_definition_field(class_id, "scope_hints", ["nowhere/**"])
        self.add_fix_commit()
        result = self.cli(
            "prepare", "--base", self.base, "--head", "HEAD", "--pr-body-file", str(self.body("## Summary\n"))
        )
        self.assertEqual(self.payload(result)["candidates_shown"], len(SEED_IDS))

    def test_prepare_all_candidates_flag_disables_narrowing(self) -> None:
        self.set_definition_field("FC-malformed-doc-read", "scope_hints", ["src/**"])
        self.add_fix_commit()
        result = self.cli(
            "prepare", "--base", self.base, "--head", "HEAD",
            "--pr-body-file", str(self.body("## Summary\n")), "--all-candidates",
        )
        self.assertEqual(self.payload(result)["candidates_shown"], len(SEED_IDS))

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
        self.assertEqual(len(payload["advisory_candidates"]), len(SEED_IDS))
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

#!/usr/bin/env python3
"""Hermetic subprocess tests for the failure-class guard-artifact ratchet.

Each test builds a real, disposable git repository with real first-parent
history and runs the checker against it, so production counting, threshold, and
allowlist behavior execute end to end. No source strings are asserted.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPOSITORY_ROOT / ".github" / "scripts" / "check_failure_class_guard_ratchet.py"
NOW = "2026-07-24T00:00:00Z"
# Disposable repositories must not inherit the caller's git context. Running
# under a pre-commit or pre-push hook exports GIT_DIR and a hooks path that
# would otherwise reach back into the real checkout.
GIT_ISOLATION = ("-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false")


def load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_failure_class_guard_ratchet", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHECKER_MODULE = load_checker_module()


def clean_environment(**overrides: str) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(overrides)
    return environment


def git(root: Path, *args: str, date: str | None = None) -> subprocess.CompletedProcess[str]:
    overrides = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}
    return subprocess.run(
        ["git", *GIT_ISOLATION, *args],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
        env=clean_environment(**overrides),
    )


def run_checker(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), "--now", NOW, *extra],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
        env=clean_environment(),
    )


class GuardRatchetTests(unittest.TestCase):
    def test_git_output_is_decoded_as_utf8(self) -> None:
        output = "fix(ci): preserve Windows history \u2014 \u96ea\n"
        completed = subprocess.CompletedProcess(["git", "log"], 0, stdout=output, stderr="")

        with patch.object(CHECKER_MODULE.subprocess, "run", return_value=completed) as run:
            self.assertEqual(CHECKER_MODULE.run_git(Path("repo"), "log"), output)

        self.assertEqual(run.call_args.kwargs.get("encoding"), "utf-8")
        self.assertNotIn("text", run.call_args.kwargs)

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        (self.root / ".github" / "failure-classes").mkdir(parents=True)
        (self.root / ".github" / "scripts").mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "ratchet@example.test")
        self.git("config", "user.name", "Ratchet Test")
        # An old root commit so the window is measurable in every test.
        self.commit("chore: seed repository", date="2026-01-01T00:00:00Z")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def git(self, *args: str, date: str | None = None) -> str:
        result = git(self.root, *args, date=date)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def commit(self, message: str, *, date: str) -> None:
        self.git("commit", "-q", "--allow-empty", "-m", message, date=date)

    def declare(self, class_id: str, *, count: int, date: str = "2026-07-01T00:00:00Z") -> None:
        """Add `count` first-parent integration changes declaring `class_id`."""
        for index in range(count):
            self.commit(f"fix(scope): instance {index}\n\nFailure-Class: {class_id}\n", date=date)

    def define(self, class_id: str, *, artifact: list[str] | None = None) -> None:
        definition = {
            "schema_version": 1,
            "id": class_id,
            "violated_contract": "contract",
            "canonical_prevention": "prevention",
            "evidence_prs": [1],
            "status": "open",
        }
        if artifact is not None:
            definition["canonical_prevention_artifact"] = artifact
        path = self.root / ".github" / "failure-classes" / f"{class_id}.json"
        path.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")

    def allow(self, entries: list[dict[str, object]]) -> None:
        path = self.root / ".github" / "scripts" / "failure_class_guard_ratchet_allowlist.json"
        path.write_text(
            json.dumps({"schema_version": 1, "grandfathered": entries}, indent=2) + "\n", encoding="utf-8"
        )

    def pr_body(self, class_id: str) -> Path:
        path = self.root / "pr-body.md"
        path.write_text(f"## Summary\n\nFailure-Class: {class_id}\n", encoding="utf-8")
        return path

    def check(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_checker(self.root, *extra)

    def test_over_threshold_without_artifact_fails(self) -> None:
        self.define("FC-recurring-thing")
        self.declare("FC-recurring-thing", count=3)
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("FC-recurring-thing", result.stderr)

    def test_over_threshold_with_artifact_passes(self) -> None:
        self.define("FC-recurring-thing", artifact=["guards/recurring.py"])
        self.declare("FC-recurring-thing", count=5)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_under_threshold_passes(self) -> None:
        self.define("FC-recurring-thing")
        self.declare("FC-recurring-thing", count=2)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_grandfathered_class_passes(self) -> None:
        self.define("FC-recurring-thing")
        self.declare("FC-recurring-thing", count=9)
        self.allow(
            [
                {
                    "id": "FC-recurring-thing",
                    "declarations_at_baseline": 9,
                    "reason": "over threshold when the ratchet landed",
                }
            ]
        )
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GRANDFATHERED", result.stdout)

    def test_grandfathered_class_fails_on_new_recurrence(self) -> None:
        self.define("FC-recurring-thing")
        self.declare("FC-recurring-thing", count=10)
        self.allow(
            [
                {
                    "id": "FC-recurring-thing",
                    "declarations_at_baseline": 9,
                    "reason": "only the first nine are grandfathered",
                }
            ]
        )
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("FC-recurring-thing", result.stderr)
        self.assertIn("baseline", result.stderr)

    def test_grandfathered_class_with_artifact_must_leave_the_allowlist(self) -> None:
        self.define("FC-recurring-thing", artifact=["guards/recurring.py"])
        self.declare("FC-recurring-thing", count=9)
        self.allow([{"id": "FC-recurring-thing", "declarations_at_baseline": 9, "reason": "stale entry"}])
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("only shrinks", result.stderr)

    def test_declarations_outside_the_window_do_not_count(self) -> None:
        self.define("FC-recurring-thing")
        self.declare("FC-recurring-thing", count=5, date="2026-01-05T00:00:00Z")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pr_body_declaration_counts_toward_the_window(self) -> None:
        self.define("FC-recurring-thing")
        self.declare("FC-recurring-thing", count=2)
        # A `pull_request` run checks out the merge ref, whose message declares
        # nothing: the pending change exists only in the body.
        self.commit("Merge 1111111 into 2222222", date="2026-07-02T00:00:00Z")
        body = self.pr_body("FC-recurring-thing")
        result = self.check("--pr-body-file", str(body))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("FC-recurring-thing", result.stderr)

    def test_a_landed_declaration_is_not_counted_twice_from_its_own_pr_body(self) -> None:
        """A main push re-reads the merged PR body while HEAD already carries the
        same declaration; counting both turns a green PR red right after merge."""
        self.define("FC-recurring-thing")
        self.declare("FC-recurring-thing", count=1)
        self.commit(
            "fix(scope): the change being pushed (#4242)\n\nFailure-Class: FC-recurring-thing\n",
            date="2026-07-02T00:00:00Z",
        )
        body = self.pr_body("FC-recurring-thing")
        result = self.check("--pr-body-file", str(body))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_pr_body_still_counts_when_the_squash_message_omits_the_trailer(self) -> None:
        """Subtracting HEAD must not swallow a declaration history never saw."""
        self.define("FC-recurring-thing")
        self.declare("FC-recurring-thing", count=2)
        self.commit("fix(scope): declared in the body only (#4243)", date="2026-07-02T00:00:00Z")
        body = self.pr_body("FC-recurring-thing")
        result = self.check("--pr-body-file", str(body))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("FC-recurring-thing", result.stderr)

    def test_one_integration_change_with_many_declarations_counts_once(self) -> None:
        self.define("FC-recurring-thing")
        squashed = "\n".join(
            ["chore(release): merge", "", *["Failure-Class: FC-recurring-thing"] * 6]
        )
        self.commit(squashed, date="2026-07-01T00:00:00Z")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_class_in_history_is_ignored(self) -> None:
        self.declare("FC-never-defined", count=9)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_history_shorter_than_the_window_skips_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            recent = Path(temporary_directory)
            git(recent, "init", "-q", "-b", "main")
            git(recent, "config", "user.email", "a@b.test")
            git(recent, "config", "user.name", "A B")
            (recent / ".github" / "failure-classes").mkdir(parents=True)
            git(recent, "commit", "-q", "--allow-empty", "-m", "chore: recent root", date=NOW)
            result = run_checker(recent)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("SKIP", result.stdout)

    def test_shallow_clone_skips_loudly(self) -> None:
        self.define("FC-recurring-thing")
        self.declare("FC-recurring-thing", count=5)
        with tempfile.TemporaryDirectory() as temporary_directory:
            shallow = Path(temporary_directory) / "shallow"
            clone = git(shallow.parent, "clone", "-q", "--depth", "1", f"file://{self.root}", str(shallow))
            self.assertEqual(clone.returncode, 0, clone.stderr)
            result = run_checker(shallow)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("SKIP", result.stdout)

    def test_repository_registry_is_green_today(self) -> None:
        """The shipped registry plus allowlist must pass in this checkout."""
        result = run_checker(REPOSITORY_ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

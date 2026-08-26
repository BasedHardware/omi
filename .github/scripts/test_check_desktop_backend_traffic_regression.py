#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("check_desktop_backend_traffic_regression.py")
SPEC = importlib.util.spec_from_file_location("desktop_backend_traffic_regression", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _ancestry(pairs: dict[tuple[str, str], bool | None]):
    def is_ancestor(ancestor: str, descendant: str) -> bool | None:
        return pairs[(ancestor, descendant)]

    return is_ancestor


class EvaluateTrafficPromotionTests(unittest.TestCase):
    def test_admits_a_candidate_built_before_main_advanced(self) -> None:
        """The regression this file exists for: a merge during the build is not staleness."""
        decision = MODULE.evaluate_traffic_promotion(
            candidate_sha="cafe1",
            serving_sha="beef0",
            is_ancestor=_ancestry({("beef0", "cafe1"): True}),
        )

        self.assertTrue(decision.allowed)
        self.assertIn("descends from serving", decision.reason)

    def test_refuses_a_candidate_the_serving_revision_already_descends_from(self) -> None:
        decision = MODULE.evaluate_traffic_promotion(
            candidate_sha="beef0",
            serving_sha="cafe1",
            is_ancestor=_ancestry({("cafe1", "beef0"): False}),
        )

        self.assertFalse(decision.allowed)
        self.assertIn("would move desktop-backend backwards", decision.reason)

    def test_refuses_a_candidate_on_a_divergent_history(self) -> None:
        decision = MODULE.evaluate_traffic_promotion(
            candidate_sha="fork1",
            serving_sha="fork2",
            is_ancestor=_ancestry({("fork2", "fork1"): False}),
        )

        self.assertFalse(decision.allowed)

    def test_admits_an_idempotent_reroute_of_the_same_commit(self) -> None:
        decision = MODULE.evaluate_traffic_promotion(
            candidate_sha="cafe1",
            serving_sha="cafe1",
            is_ancestor=_ancestry({}),
        )

        self.assertTrue(decision.allowed)
        self.assertIn("idempotent", decision.reason)

    def test_admits_when_the_serving_revision_records_no_release_sha(self) -> None:
        """Legacy revisions predate SHA stamping; refusing would deadlock the pipeline."""
        decision = MODULE.evaluate_traffic_promotion(
            candidate_sha="cafe1",
            serving_sha=None,
            is_ancestor=_ancestry({}),
        )

        self.assertTrue(decision.allowed)
        self.assertTrue(decision.reason.startswith(MODULE.UNKNOWN_LINEAGE))

    def test_admits_when_the_serving_commit_is_unreachable(self) -> None:
        decision = MODULE.evaluate_traffic_promotion(
            candidate_sha="cafe1",
            serving_sha="gone0",
            is_ancestor=_ancestry({("gone0", "cafe1"): None}),
        )

        self.assertTrue(decision.allowed)
        self.assertTrue(decision.reason.startswith(MODULE.UNKNOWN_LINEAGE))

    def test_rejects_a_missing_candidate_sha(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.evaluate_traffic_promotion(
                candidate_sha="",
                serving_sha="beef0",
                is_ancestor=_ancestry({}),
            )


class GitAncestryTests(unittest.TestCase):
    """Exercise the real git seam the workflow runs, not a stub of it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        # A pre-push/pre-flight hook exports GIT_DIR & friends for the outer
        # repository; the scratch repos below must not inherit them.
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_NAMESPACE"}
        }
        env.update(
            GIT_AUTHOR_NAME="t",
            GIT_AUTHOR_EMAIL="t@example.com",
            GIT_COMMITTER_NAME="t",
            GIT_COMMITTER_EMAIL="t@example.com",
        )

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args],
                cwd=self.repo,
                env=env,
                capture_output=True,
                check=True,
            ).stdout.decode()

        git("init", "-q", "-b", "main")
        (self.repo / "f").write_text("1")
        git("add", "f")
        git("commit", "-qm", "first")
        self.first = git("rev-parse", "HEAD").strip()
        (self.repo / "f").write_text("2")
        git("commit", "-qam", "second")
        self.second = git("rev-parse", "HEAD").strip()

        self._cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, self._cwd)

    def test_reports_ancestry_in_both_directions(self) -> None:
        self.assertTrue(MODULE._git_is_ancestor(self.first, self.second))
        self.assertFalse(MODULE._git_is_ancestor(self.second, self.first))

    def test_reports_none_for_a_commit_absent_from_the_checkout(self) -> None:
        absent = "0" * 40
        self.assertIsNone(MODULE._git_is_ancestor(absent, self.second))

    def test_cli_admits_a_descendant_and_refuses_an_ancestor(self) -> None:
        self.assertEqual(
            MODULE.main(["--candidate-sha", self.second, "--serving-release-sha", self.first]),
            0,
        )
        self.assertEqual(
            MODULE.main(["--candidate-sha", self.first, "--serving-release-sha", self.second]),
            1,
        )

    def test_cli_admits_an_empty_serving_sha(self) -> None:
        self.assertEqual(
            MODULE.main(["--candidate-sha", self.second, "--serving-release-sha", ""]),
            0,
        )


if __name__ == "__main__":
    unittest.main()

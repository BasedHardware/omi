#!/usr/bin/env python3
"""Behavioural cover for automatic development backend release admission."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github/scripts/verify_auto_backend_release_admission.py"
SPEC = importlib.util.spec_from_file_location("verify_auto_backend_release_admission", MODULE_PATH)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
# dataclasses resolves annotations through sys.modules[cls.__module__]; a
# module built by module_from_spec is absent from it until registered.
sys.modules[SPEC.name] = GUARD
SPEC.loader.exec_module(GUARD)

MERGED = "a" * 40
MAIN = "b" * 40


def identity(**overrides: object) -> object:
    base = {
        "sha": MERGED,
        "main_sha": MAIN,
        "checkout_sha": MAIN,
        "run_attempt": "1",
        "sha_is_ancestor_of_main": True,
    }
    base.update(overrides)
    return GUARD.AutomaticReleaseIdentity(**base)  # type: ignore[arg-type]


class AutomaticReleaseAdmissionTests(unittest.TestCase):
    def test_merged_commit_behind_current_main_is_admitted(self) -> None:
        """The regression this guard change exists for.

        A commit merging while Release Eligibility runs leaves the proof's SHA
        behind main. That used to fail admission and strand development.
        """
        GUARD.validate(identity())

    def test_commit_that_is_still_main_tip_is_admitted(self) -> None:
        GUARD.validate(identity(sha=MAIN))

    def test_unmerged_commit_is_rejected(self) -> None:
        with self.assertRaises(GUARD.AutomaticReleaseAdmissionError) as caught:
            GUARD.validate(identity(sha_is_ancestor_of_main=False))
        self.assertIn("merged into current main", str(caught.exception))

    def test_guard_checkout_must_be_current_main(self) -> None:
        with self.assertRaises(GUARD.AutomaticReleaseAdmissionError) as caught:
            GUARD.validate(identity(checkout_sha="c" * 40))
        self.assertIn("current-main checkout", str(caught.exception))

    def test_retried_proof_is_rejected(self) -> None:
        with self.assertRaises(GUARD.AutomaticReleaseAdmissionError):
            GUARD.validate(identity(run_attempt="2"))

    def test_short_and_zero_shas_are_rejected(self) -> None:
        for label, bad in (("short", "abc123"), ("zero", "0" * 40), ("uppercase", "A" * 40)):
            with self.subTest(label), self.assertRaises(GUARD.AutomaticReleaseAdmissionError):
                GUARD.validate(identity(sha=bad))

    def test_ancestry_flag_only_accepts_the_workflow_spelling(self) -> None:
        self.assertIs(GUARD._parse_bool("true"), True)
        self.assertIs(GUARD._parse_bool("false"), False)
        for bad in ("True", "1", "yes", ""):
            with self.subTest(bad), self.assertRaises(GUARD.AutomaticReleaseAdmissionError):
                GUARD._parse_bool(bad)


if __name__ == "__main__":
    unittest.main()

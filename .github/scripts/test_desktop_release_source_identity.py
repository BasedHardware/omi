#!/usr/bin/env python3
"""Regression tests for macOS release planner source identity evidence."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("desktop-release-source-identity.py")
SPEC = importlib.util.spec_from_file_location("desktop_release_source_identity", SCRIPT)
assert SPEC and SPEC.loader
identity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(identity)

PLANNED_SHA = "a" * 40
CANDIDATE_SHA = "b" * 40
CHANGELOG_SHA = "c" * 40
PR_URL = "https://github.com/BasedHardware/omi/pull/12345"


class DesktopReleaseSourceIdentityTests(unittest.TestCase):
    def test_merged_changelog_records_the_exact_main_candidate_sha(self) -> None:
        evidence = identity.build_evidence(
            planned_source_sha=PLANNED_SHA,
            candidate_source_sha=CANDIDATE_SHA,
            origin_main_sha=CANDIDATE_SHA,
            first_parent_sha=PLANNED_SHA,
            changelog_commit=CHANGELOG_SHA,
            changelog_pr=PR_URL,
        )

        self.assertEqual(evidence["schema"], "desktop-release-planner-source-identity/v1")
        self.assertEqual(evidence["mode"], "merged-changelog")
        self.assertEqual(evidence["candidate_source_sha"], CANDIDATE_SHA)
        self.assertEqual(evidence["origin_main_sha"], CANDIDATE_SHA)

    def test_rejects_candidate_that_is_not_the_fresh_main_tip(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly match fresh origin/main"):
            identity.build_evidence(
                planned_source_sha=PLANNED_SHA,
                candidate_source_sha=CANDIDATE_SHA,
                origin_main_sha="d" * 40,
                first_parent_sha=PLANNED_SHA,
                changelog_commit=CHANGELOG_SHA,
                changelog_pr=PR_URL,
            )

    def test_rejects_changelog_merge_when_main_drifted_from_the_gated_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "first parent must match the planner source SHA"):
            identity.build_evidence(
                planned_source_sha=PLANNED_SHA,
                candidate_source_sha=CANDIDATE_SHA,
                origin_main_sha=CANDIDATE_SHA,
                first_parent_sha="d" * 40,
                changelog_commit=CHANGELOG_SHA,
                changelog_pr=PR_URL,
            )

    def test_direct_path_allows_only_an_unchanged_planner_source(self) -> None:
        evidence = identity.build_evidence(
            planned_source_sha=PLANNED_SHA,
            candidate_source_sha=PLANNED_SHA,
            origin_main_sha=PLANNED_SHA,
        )
        self.assertEqual(evidence["mode"], "direct")

        with self.assertRaisesRegex(ValueError, "direct candidate source must match"):
            identity.build_evidence(
                planned_source_sha=PLANNED_SHA,
                candidate_source_sha=CANDIDATE_SHA,
                origin_main_sha=CANDIDATE_SHA,
            )


if __name__ == "__main__":
    unittest.main()

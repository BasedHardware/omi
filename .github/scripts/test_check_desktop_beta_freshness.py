#!/usr/bin/env python3
"""Tests for the hourly desktop beta freshness alarm."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("check-desktop-beta-freshness.py")
SPEC = importlib.util.spec_from_file_location("check_desktop_beta_freshness", SCRIPT)
assert SPEC and SPEC.loader
freshness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freshness)

REPOSITORY = "BasedHardware/omi"
TAG = "v0.12.172+12172-macos"
TAG_SHA = "a" * 40
MAIN_SHA = "b" * 40


def _appcast(build: int) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">'
        f"<item><sparkle:version>{build}</sparkle:version></item>"
        "</rss>"
    )


class FreshnessTests(unittest.TestCase):
    def test_parses_tag_and_appcast_builds(self) -> None:
        self.assertEqual(freshness.parse_tag_build(TAG), 12172)
        self.assertEqual(freshness.live_beta_build(_appcast(12170)), 12170)
        self.assertEqual(
            freshness.live_beta_build('<enclosure sparkle:version="9"/><sparkle:version>11</sparkle:version>'),
            11,
        )

    def test_healthy_when_live_beta_matches_candidate(self) -> None:
        with (
            patch.object(freshness.planner, "latest_desktop_tag", return_value=TAG),
            patch.object(freshness, "fetch_beta_appcast", return_value=_appcast(12172)),
            patch.object(freshness.planner, "tag_sha", return_value=TAG_SHA),
            patch.object(freshness.planner, "tag_age_seconds", return_value=20_000),
            patch.object(freshness, "oldest_unreleased_releasable_main_commit", return_value=(MAIN_SHA, 100)),
            patch.object(freshness, "is_ancestor", return_value=True),
        ):
            code, lines = freshness.evaluate(repository=REPOSITORY)
        self.assertEqual(code, 0)
        self.assertIn("status=healthy", lines)

    def test_promotion_lag_with_failed_codemagic_check(self) -> None:
        with (
            patch.object(freshness.planner, "latest_desktop_tag", return_value=TAG),
            patch.object(freshness, "fetch_beta_appcast", return_value=_appcast(12100)),
            patch.object(freshness.planner, "tag_sha", return_value=TAG_SHA),
            patch.object(freshness.planner, "tag_age_seconds", return_value=12_000),
            patch.object(
                freshness.planner,
                "github_check_status",
                return_value=("completed", "failure", "https://example.test/codemagic", None),
            ),
            patch.object(freshness, "oldest_unreleased_releasable_main_commit", return_value=(MAIN_SHA, 100)),
            patch.object(freshness, "is_ancestor", return_value=True),
        ):
            code, lines = freshness.evaluate(repository=REPOSITORY)
        self.assertEqual(code, 1)
        joined = "\n".join(lines)
        self.assertIn("Promotion lag", joined)
        self.assertIn("Desktop Release Recovery Required", joined)
        self.assertIn("https://example.test/codemagic", joined)

    def test_promotion_lag_success_points_at_recover_beta(self) -> None:
        with (
            patch.object(freshness.planner, "latest_desktop_tag", return_value=TAG),
            patch.object(freshness, "fetch_beta_appcast", return_value=_appcast(12100)),
            patch.object(freshness.planner, "tag_sha", return_value=TAG_SHA),
            patch.object(freshness.planner, "tag_age_seconds", return_value=12_000),
            patch.object(
                freshness.planner,
                "github_check_status",
                return_value=("completed", "success", "https://example.test/ok", None),
            ),
            patch.object(freshness, "oldest_unreleased_releasable_main_commit", return_value=(MAIN_SHA, 100)),
            patch.object(freshness, "is_ancestor", return_value=True),
        ):
            code, lines = freshness.evaluate(repository=REPOSITORY)
        self.assertEqual(code, 1)
        joined = "\n".join(lines)
        self.assertIn("desktop_recover_beta.yml", joined)
        self.assertIn(f"release_tag={TAG}", joined)

    def test_promotion_lag_absent_check_points_at_auto_release(self) -> None:
        with (
            patch.object(freshness.planner, "latest_desktop_tag", return_value=TAG),
            patch.object(freshness, "fetch_beta_appcast", return_value=_appcast(12100)),
            patch.object(freshness.planner, "tag_sha", return_value=TAG_SHA),
            patch.object(freshness.planner, "tag_age_seconds", return_value=12_000),
            patch.object(
                freshness.planner,
                "github_check_status",
                return_value=(None, None, None, None),
            ),
            patch.object(freshness, "oldest_unreleased_releasable_main_commit", return_value=(MAIN_SHA, 100)),
            patch.object(freshness, "is_ancestor", return_value=True),
        ):
            code, lines = freshness.evaluate(repository=REPOSITORY)
        self.assertEqual(code, 1)
        self.assertIn("Build Desktop Release Candidate", "\n".join(lines))

    def test_young_candidate_ahead_of_beta_is_not_lag(self) -> None:
        with (
            patch.object(freshness.planner, "latest_desktop_tag", return_value=TAG),
            patch.object(freshness, "fetch_beta_appcast", return_value=_appcast(12100)),
            patch.object(freshness.planner, "tag_sha", return_value=TAG_SHA),
            patch.object(freshness.planner, "tag_age_seconds", return_value=60),
            patch.object(freshness, "oldest_unreleased_releasable_main_commit", return_value=(MAIN_SHA, 100)),
            patch.object(freshness, "is_ancestor", return_value=True),
        ):
            code, lines = freshness.evaluate(repository=REPOSITORY)
        self.assertEqual(code, 0)
        self.assertIn("status=healthy", lines)

    def test_wedged_train_when_untagged_desktop_commit_is_old(self) -> None:
        with (
            patch.object(freshness.planner, "latest_desktop_tag", return_value=TAG),
            patch.object(freshness, "fetch_beta_appcast", return_value=_appcast(12172)),
            patch.object(freshness.planner, "tag_sha", return_value=TAG_SHA),
            patch.object(freshness.planner, "tag_age_seconds", return_value=60),
            patch.object(freshness, "oldest_unreleased_releasable_main_commit", return_value=(MAIN_SHA, 22_000)),
            patch.object(freshness, "is_ancestor", return_value=False),
            patch.object(
                freshness,
                "latest_auto_release_run_url",
                return_value="https://github.com/BasedHardware/omi/actions/runs/1",
            ),
        ):
            code, lines = freshness.evaluate(repository=REPOSITORY)
        self.assertEqual(code, 1)
        joined = "\n".join(lines)
        self.assertIn("Wedged train", joined)
        self.assertIn(MAIN_SHA, joined)
        self.assertIn("https://github.com/BasedHardware/omi/actions/runs/1", joined)

    def test_merge_churn_cannot_reset_the_oldest_unreleased_update_age(self) -> None:
        changelog_only = "1" * 40
        oldest_desktop = "2" * 40
        newest_desktop = "3" * 40

        def fake_git(args: list[str], *, check: bool = True) -> str:
            del check
            if args[:3] == ["log", "--first-parent", "--reverse"]:
                self.assertIn(f"{TAG}..HEAD", args)
                return "\n".join((changelog_only, oldest_desktop, newest_desktop))
            if args[0] == "diff-tree":
                sha = args[6]
                self.assertEqual(args[5], f"{sha}^1")
                return {
                    changelog_only: "desktop/macos/changelog/unreleased/note.json",
                    oldest_desktop: "desktop/macos/Desktop/Sources/App.swift",
                    newest_desktop: "desktop/macos/Desktop/Sources/New.swift",
                }[sha]
            self.fail(f"unexpected git call: {args}")

        with (
            patch.object(freshness.planner, "git", side_effect=fake_git),
            patch.object(freshness.planner, "commit_age_seconds", return_value=30_000) as age,
        ):
            result = freshness.oldest_unreleased_releasable_main_commit(TAG)

        self.assertEqual(result, (oldest_desktop, 30_000))
        age.assert_called_once_with(oldest_desktop)


if __name__ == "__main__":
    unittest.main()

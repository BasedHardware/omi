#!/usr/bin/env python3
"""Regression tests for macOS release planner source identity evidence."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
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
RELEASE_TAG = "v1.2.3+10203-macos"


class DesktopReleaseSourceIdentityTests(unittest.TestCase):
    def test_merged_changelog_records_the_exact_main_candidate_sha(self) -> None:
        evidence = identity.build_evidence(
            release_tag=RELEASE_TAG,
            planned_source_sha=PLANNED_SHA,
            candidate_source_sha=CANDIDATE_SHA,
            origin_main_sha=CANDIDATE_SHA,
            changelog_parent_sha=PLANNED_SHA,
            changelog_commit=CHANGELOG_SHA,
            changelog_pr=PR_URL,
        )

        self.assertEqual(evidence["schema"], "desktop-release-planner-source-identity/v2")
        self.assertEqual(evidence["release_tag"], RELEASE_TAG)
        self.assertEqual(evidence["mode"], "merged-changelog")
        self.assertEqual(evidence["candidate_source_sha"], CANDIDATE_SHA)
        self.assertEqual(evidence["origin_main_sha"], CANDIDATE_SHA)

    def test_rejects_candidate_that_is_not_the_fresh_main_tip(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly match fresh origin/main"):
            identity.build_evidence(
                release_tag=RELEASE_TAG,
                planned_source_sha=PLANNED_SHA,
                candidate_source_sha=CANDIDATE_SHA,
                origin_main_sha="d" * 40,
                changelog_parent_sha=PLANNED_SHA,
                changelog_commit=CHANGELOG_SHA,
                changelog_pr=PR_URL,
            )

    def test_direct_path_records_current_main_after_non_desktop_commits(self) -> None:
        evidence = identity.build_evidence(
            release_tag=RELEASE_TAG,
            planned_source_sha=PLANNED_SHA,
            candidate_source_sha=CANDIDATE_SHA,
            origin_main_sha=CANDIDATE_SHA,
        )
        self.assertEqual(evidence["mode"], "direct")
        self.assertEqual(evidence["candidate_source_sha"], CANDIDATE_SHA)

    def test_rejects_a_noncanonical_candidate_tag(self) -> None:
        with self.assertRaisesRegex(ValueError, "release_tag must be an exact"):
            identity.build_evidence(
                release_tag="v1.2.3-macos",
                planned_source_sha=PLANNED_SHA,
                candidate_source_sha=CANDIDATE_SHA,
                origin_main_sha=CANDIDATE_SHA,
            )

    def _git(self, repository: Path, *args: str) -> str:
        # The repository-wide pre-push hook exports GIT_* state while running
        # selected checks. Test repositories must not inherit that state from
        # their caller or their commits can target the wrong index/worktree.
        environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        ).stdout.strip()

    def _commit(self, repository: Path, path: str, contents: str, message: str) -> str:
        file_path = repository / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")
        self._git(repository, "add", path)
        self._git(repository, "commit", "-m", message)
        return self._git(repository, "rev-parse", "HEAD")

    def _repository_with_planned_source(self) -> tuple[tempfile.TemporaryDirectory[str], Path, str]:
        directory = tempfile.TemporaryDirectory()
        repository = Path(directory.name)
        self._git(repository, "init")
        self._git(repository, "config", "user.name", "Release test")
        self._git(repository, "config", "user.email", "release-test@example.com")
        planned_source_sha = self._commit(
            repository,
            "desktop/macos/Desktop/Sources/App.swift",
            "let releaseSource = true\n",
            "desktop source",
        )
        return directory, repository, planned_source_sha

    def test_non_desktop_main_commit_after_planned_source_is_valid(self) -> None:
        directory, repository, planned_source_sha = self._repository_with_planned_source()
        with directory:
            candidate_source_sha = self._commit(
                repository,
                "docs/release-note.md",
                "No desktop source change.\n",
                "docs only",
            )
            identity.ensure_candidate_history_is_safe(
                repository_root=repository,
                planned_source_sha=planned_source_sha,
                candidate_source_sha=candidate_source_sha,
            )

    def test_newer_desktop_change_after_planned_source_fails_closed(self) -> None:
        directory, repository, planned_source_sha = self._repository_with_planned_source()
        with directory:
            candidate_source_sha = self._commit(
                repository,
                "desktop/macos/Desktop/Sources/Newer.swift",
                "let newerDesktopChange = true\n",
                "newer desktop source",
            )
            with self.assertRaisesRegex(ValueError, "newer releasable desktop changes"):
                identity.ensure_candidate_history_is_safe(
                    repository_root=repository,
                    planned_source_sha=planned_source_sha,
                    candidate_source_sha=candidate_source_sha,
                )

    def test_reverted_newer_desktop_change_after_planned_source_still_fails_closed(self) -> None:
        directory, repository, planned_source_sha = self._repository_with_planned_source()
        with directory:
            self._commit(
                repository,
                "desktop/macos/Desktop/Sources/App.swift",
                "let releaseSource = false\n",
                "newer desktop source",
            )
            candidate_source_sha = self._commit(
                repository,
                "desktop/macos/Desktop/Sources/App.swift",
                "let releaseSource = true\n",
                "revert newer desktop source",
            )
            with self.assertRaisesRegex(ValueError, "newer releasable desktop changes"):
                identity.ensure_candidate_history_is_safe(
                    repository_root=repository,
                    planned_source_sha=planned_source_sha,
                    candidate_source_sha=candidate_source_sha,
                )

    def test_stale_changelog_parent_fails_closed(self) -> None:
        directory, repository, planned_source_sha = self._repository_with_planned_source()
        with directory:
            stale_parent_sha = self._commit(
                repository,
                "docs/concurrent-main.md",
                "A later non-desktop commit.\n",
                "concurrent main",
            )
            candidate_source_sha = self._commit(
                repository,
                "desktop/macos/changelog/2026-07-25.json",
                "{}\n",
                "stale changelog",
            )
            with self.assertRaisesRegex(ValueError, "changelog parent does not match"):
                identity.ensure_candidate_history_is_safe(
                    repository_root=repository,
                    planned_source_sha=planned_source_sha,
                    candidate_source_sha=candidate_source_sha,
                    changelog_commit=candidate_source_sha,
                    changelog_parent_sha=planned_source_sha,
                )
            self.assertNotEqual(stale_parent_sha, planned_source_sha)

    def test_replans_after_concurrent_desktop_change_without_losing_changelog_evidence(self) -> None:
        """Model SCA-146: a newer desktop merge races a regular changelog merge."""
        directory, repository, original_planned_source_sha = self._repository_with_planned_source()
        with directory:
            main_branch = self._git(repository, "branch", "--show-current")
            replanned_source_sha = self._commit(
                repository,
                "desktop/macos/Desktop/Sources/Newer.swift",
                "let newerDesktopChange = true\n",
                "newer desktop source",
            )
            self._git(repository, "checkout", "-b", "changelog", original_planned_source_sha)
            changelog_commit = self._commit(
                repository,
                "desktop/macos/changelog/2026-07-25.json",
                "{}\n",
                "consolidate changelog",
            )
            self._git(repository, "checkout", main_branch)
            self._git(
                repository,
                "merge",
                "--no-ff",
                "changelog",
                "-m",
                "regular changelog merge",
            )
            candidate_source_sha = self._git(repository, "rev-parse", "HEAD")

            with self.assertRaisesRegex(ValueError, "newer releasable desktop changes"):
                identity.ensure_candidate_history_is_safe(
                    repository_root=repository,
                    planned_source_sha=original_planned_source_sha,
                    candidate_source_sha=candidate_source_sha,
                    changelog_commit=changelog_commit,
                    changelog_parent_sha=original_planned_source_sha,
                )

            identity.ensure_candidate_history_is_safe(
                repository_root=repository,
                planned_source_sha=replanned_source_sha,
                candidate_source_sha=candidate_source_sha,
                changelog_commit=changelog_commit,
                changelog_parent_sha=original_planned_source_sha,
            )
            evidence = identity.build_evidence(
                release_tag=RELEASE_TAG,
                planned_source_sha=replanned_source_sha,
                candidate_source_sha=candidate_source_sha,
                origin_main_sha=candidate_source_sha,
                changelog_parent_sha=original_planned_source_sha,
                changelog_commit=changelog_commit,
                changelog_pr=PR_URL,
            )

        self.assertEqual(evidence["mode"], "replanned-changelog")
        self.assertEqual(evidence["planned_source_sha"], replanned_source_sha)
        self.assertEqual(evidence["replanned_from_source_sha"], original_planned_source_sha)
        self.assertEqual(evidence["changelog_commit"], changelog_commit)


if __name__ == "__main__":
    unittest.main()

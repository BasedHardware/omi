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
CHANGELOG_SHA = "b" * 40
MAIN_SHA = "c" * 40
PR_URL = "https://github.com/BasedHardware/omi/pull/12345"
RELEASE_TAG = "v1.2.3+10203-macos"


class DesktopReleaseSourceIdentityTests(unittest.TestCase):
    def test_direct_candidate_stays_on_green_source_when_main_advances(self) -> None:
        evidence = identity.build_evidence(
            release_tag=RELEASE_TAG,
            planned_source_sha=PLANNED_SHA,
            candidate_source_sha=PLANNED_SHA,
            origin_main_sha=MAIN_SHA,
        )

        self.assertEqual(evidence["schema"], "desktop-release-planner-source-identity/v3")
        self.assertEqual(evidence["mode"], "direct")
        self.assertEqual(evidence["candidate_source_sha"], PLANNED_SHA)
        self.assertEqual(evidence["origin_main_sha"], MAIN_SHA)

    def test_changelog_candidate_is_the_changelog_only_child(self) -> None:
        evidence = identity.build_evidence(
            release_tag=RELEASE_TAG,
            planned_source_sha=PLANNED_SHA,
            candidate_source_sha=CHANGELOG_SHA,
            origin_main_sha=MAIN_SHA,
            changelog_parent_sha=PLANNED_SHA,
            changelog_commit=CHANGELOG_SHA,
            changelog_pr=PR_URL,
        )

        self.assertEqual(evidence["mode"], "changelog-only")
        self.assertEqual(evidence["candidate_source_sha"], CHANGELOG_SHA)
        self.assertEqual(evidence["changelog_parent_sha"], PLANNED_SHA)

    def test_direct_candidate_cannot_absorb_a_later_main_tip(self) -> None:
        with self.assertRaisesRegex(ValueError, "direct candidate must exactly equal"):
            identity.build_evidence(
                release_tag=RELEASE_TAG,
                planned_source_sha=PLANNED_SHA,
                candidate_source_sha=MAIN_SHA,
                origin_main_sha=MAIN_SHA,
            )

    def test_rejects_a_noncanonical_candidate_tag(self) -> None:
        with self.assertRaisesRegex(ValueError, "release_tag must be an exact"):
            identity.build_evidence(
                release_tag="v1.2.3-macos",
                planned_source_sha=PLANNED_SHA,
                candidate_source_sha=PLANNED_SHA,
                origin_main_sha=MAIN_SHA,
            )

    def _git(self, repository: Path, *args: str) -> str:
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

    def _repository_with_planned_source(self) -> tuple[tempfile.TemporaryDirectory[str], Path, str, str]:
        directory = tempfile.TemporaryDirectory()
        repository = Path(directory.name)
        self._git(repository, "init")
        self._git(repository, "config", "user.name", "Release test")
        self._git(repository, "config", "user.email", "release-test@example.com")
        main_branch = self._git(repository, "branch", "--show-current")
        planned_source_sha = self._commit(
            repository,
            "desktop/macos/Desktop/Sources/App.swift",
            "let releaseSource = true\n",
            "desktop source",
        )
        return directory, repository, main_branch, planned_source_sha

    def test_busy_main_does_not_invalidate_the_exact_green_source(self) -> None:
        """Regression for issue #11936: later desktop merges belong to the next train."""
        directory, repository, _main_branch, planned_source_sha = self._repository_with_planned_source()
        with directory:
            main_sha = self._commit(
                repository,
                "desktop/macos/Desktop/Sources/Newer.swift",
                "let nextTrain = true\n",
                "newer desktop source",
            )
            identity.ensure_candidate_history_is_safe(
                repository_root=repository,
                planned_source_sha=planned_source_sha,
                candidate_source_sha=planned_source_sha,
                origin_main_sha=main_sha,
            )

    def test_changelog_only_child_survives_concurrent_desktop_merges(self) -> None:
        directory, repository, main_branch, planned_source_sha = self._repository_with_planned_source()
        with directory:
            self._git(repository, "checkout", "-b", "changelog", planned_source_sha)
            changelog_sha = self._commit(
                repository,
                "desktop/macos/changelog/releases/1.2.3.json",
                '{"version":"1.2.3"}\n',
                "chore: consolidate changelog for v1.2.3",
            )
            self._git(repository, "checkout", main_branch)
            self._commit(
                repository,
                "desktop/macos/Desktop/Sources/Newer.swift",
                "let nextTrain = true\n",
                "concurrent desktop source",
            )
            self._git(repository, "merge", "--no-ff", "changelog", "-m", "regular changelog merge")
            main_sha = self._git(repository, "rev-parse", "HEAD")

            identity.ensure_candidate_history_is_safe(
                repository_root=repository,
                planned_source_sha=planned_source_sha,
                candidate_source_sha=changelog_sha,
                origin_main_sha=main_sha,
                changelog_commit=changelog_sha,
                changelog_parent_sha=planned_source_sha,
            )

    def test_rejects_candidate_not_reachable_from_main(self) -> None:
        directory, repository, main_branch, planned_source_sha = self._repository_with_planned_source()
        with directory:
            self._git(repository, "checkout", "-b", "unmerged", planned_source_sha)
            changelog_sha = self._commit(
                repository,
                "desktop/macos/changelog/releases/1.2.3.json",
                '{}\n',
                "unmerged changelog",
            )
            self._git(repository, "checkout", main_branch)
            main_sha = self._git(repository, "rev-parse", "HEAD")
            with self.assertRaisesRegex(ValueError, "reachable from fresh origin/main"):
                identity.ensure_candidate_history_is_safe(
                    repository_root=repository,
                    planned_source_sha=planned_source_sha,
                    candidate_source_sha=changelog_sha,
                    origin_main_sha=main_sha,
                    changelog_commit=changelog_sha,
                    changelog_parent_sha=planned_source_sha,
                )

    def test_rejects_non_changelog_content_in_candidate_child(self) -> None:
        directory, repository, _main_branch, planned_source_sha = self._repository_with_planned_source()
        with directory:
            candidate_sha = self._commit(
                repository,
                "desktop/macos/Desktop/Sources/Ungated.swift",
                "let ungated = true\n",
                "not changelog only",
            )
            with self.assertRaisesRegex(ValueError, "non-changelog paths"):
                identity.ensure_candidate_history_is_safe(
                    repository_root=repository,
                    planned_source_sha=planned_source_sha,
                    candidate_source_sha=candidate_sha,
                    origin_main_sha=candidate_sha,
                    changelog_commit=candidate_sha,
                    changelog_parent_sha=planned_source_sha,
                )


if __name__ == "__main__":
    unittest.main()

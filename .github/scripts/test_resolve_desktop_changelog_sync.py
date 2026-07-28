#!/usr/bin/env python3
"""Regression tests for tag-release changelog sync commit resolution."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("resolve-desktop-changelog-sync.py")
SPEC = importlib.util.spec_from_file_location("resolve_desktop_changelog_sync", SCRIPT)
assert SPEC and SPEC.loader
resolve_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resolve_mod)


class ResolveDesktopChangelogSyncTests(unittest.TestCase):
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

    def _repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        directory = tempfile.TemporaryDirectory()
        repository = Path(directory.name)
        self._git(repository, "init")
        self._git(repository, "config", "user.name", "test")
        self._git(repository, "config", "user.email", "test@example.com")
        self._git(repository, "checkout", "-b", "main")
        return directory, repository

    def test_prefers_branch_tip_when_already_on_main(self) -> None:
        directory, repository = self._repo()
        with directory:
            planned = self._commit(repository, "desktop/macos/App.swift", "a\n", "feature")
            consolidate = self._commit(
                repository,
                "desktop/macos/changelog/releases/0.12.143.json",
                "{}\n",
                "chore: consolidate changelog for v0.12.143",
            )
            # simulate regular merge already done: tip is consolidate itself on main
            result = resolve_mod.resolve_changelog_sync(
                repository,
                planned_source_sha=planned,
                version="0.12.143",
                branch_tip=consolidate,
                main_ref="main",
                repository_slug="BasedHardware/omi",
            )
            self.assertEqual(result["mode"], "already-on-main")
            self.assertEqual(result["commit"], consolidate)
            self.assertTrue(result["already_on_main"])

    def test_orphan_branch_tip_recovers_main_consolidate(self) -> None:
        directory, repository = self._repo()
        with directory:
            planned = self._commit(repository, "desktop/macos/App.swift", "a\n", "feature")
            # Main-side consolidate (second parent of a real merge).
            self._git(repository, "checkout", "-b", "changelog-good", planned)
            good = self._commit(
                repository,
                "desktop/macos/changelog/releases/0.12.143.json",
                '{"v":1}\n',
                "chore: consolidate changelog for v0.12.143",
            )
            self._git(repository, "checkout", "main")
            self._git(repository, "merge", "--no-ff", "-m", "Update desktop changelog for v0.12.143 [skip ci] (#10787)", "changelog-good")
            # Orphan tip: same parent + subject, different tree/hash, not on main.
            self._git(repository, "checkout", "-b", "changelog-orphan", planned)
            orphan = self._commit(
                repository,
                "desktop/macos/changelog/releases/0.12.143.json",
                '{"v":2}\n',
                "chore: consolidate changelog for v0.12.143",
            )
            self._git(repository, "checkout", "main")

            result = resolve_mod.resolve_changelog_sync(
                repository,
                planned_source_sha=planned,
                version="0.12.143",
                branch_tip=orphan,
                main_ref="main",
                repository_slug="BasedHardware/omi",
            )
            self.assertEqual(result["commit"], good)
            self.assertTrue(result["already_on_main"])
            self.assertEqual(result["pr_url"], "https://github.com/BasedHardware/omi/pull/10787")
            self.assertTrue(result["merged_main_sha"])
            self.assertNotEqual(result["commit"], orphan)

    def test_rejects_branch_tip_with_wrong_parent(self) -> None:
        directory, repository = self._repo()
        with directory:
            planned = self._commit(repository, "desktop/macos/App.swift", "a\n", "feature")
            other = self._commit(repository, "desktop/macos/Other.swift", "b\n", "other")
            tip = self._commit(
                repository,
                "desktop/macos/changelog/releases/0.12.143.json",
                "{}\n",
                "chore: consolidate changelog for v0.12.143",
            )
            with self.assertRaisesRegex(ValueError, "first parent must equal"):
                resolve_mod.resolve_changelog_sync(
                    repository,
                    planned_source_sha=planned,
                    version="0.12.143",
                    branch_tip=tip,
                    main_ref="main",
                )
            _ = other

    def test_missing_when_no_branch_and_no_main_commit(self) -> None:
        directory, repository = self._repo()
        with directory:
            planned = self._commit(repository, "desktop/macos/App.swift", "a\n", "feature")
            result = resolve_mod.resolve_changelog_sync(
                repository,
                planned_source_sha=planned,
                version="0.12.143",
                main_ref="main",
            )
            self.assertEqual(result["mode"], "missing")
            self.assertEqual(result["commit"], "")


if __name__ == "__main__":
    unittest.main()

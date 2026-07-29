#!/usr/bin/env python3
"""Regression tests for Windows desktop release path classification."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
MODULE_PATH = SCRIPT_DIR / "windows_release_paths.py"
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/desktop_windows_release.yml"
SPEC = importlib.util.spec_from_file_location("windows_release_paths", MODULE_PATH)
assert SPEC and SPEC.loader
release_paths = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_paths)


class WindowsReleasePathTests(unittest.TestCase):
    def test_docs_are_release_neutral_but_runtime_and_changelog_are_releasable(self) -> None:
        self.assertFalse(release_paths.is_releasable_windows_path("desktop/windows/docs/release-pipeline.md"))
        self.assertTrue(release_paths.is_releasable_windows_path("desktop/windows/src/main/index.ts"))
        self.assertTrue(
            release_paths.is_releasable_windows_path("desktop/windows/changelog/unreleased/2026-07-runtime-fix.json")
        )
        self.assertFalse(release_paths.is_releasable_windows_path("desktop/macos/README.md"))

    def test_real_git_history_ignores_docs_only_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.git(root, "init", "--quiet")
            source = root / "desktop/windows/src/main/index.ts"
            docs = root / "desktop/windows/docs/release-pipeline.md"
            source.parent.mkdir(parents=True)
            docs.parent.mkdir(parents=True)
            source.write_text("export const version = 1\n", encoding="utf-8")
            docs.write_text("# Release\n", encoding="utf-8")
            self.commit_all(root, "initial")
            base = self.git(root, "rev-parse", "HEAD").stdout.strip()

            docs.write_text("# Release\n\nDocs only.\n", encoding="utf-8")
            self.commit_all(root, "docs")
            self.assertEqual(release_paths.releasable_paths(root, base), [])
            self.assertEqual(self.run_cli(root, base).stdout.strip(), "false")

            source.write_text("export const version = 2\n", encoding="utf-8")
            self.commit_all(root, "runtime")
            self.assertEqual(
                release_paths.releasable_paths(root, base),
                ["desktop/windows/src/main/index.ts"],
            )
            self.assertEqual(self.run_cli(root, base).stdout.strip(), "true")

    def test_first_release_still_requires_non_docs_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.git(root, "init", "--quiet")
            docs = root / "desktop/windows/docs/release-pipeline.md"
            docs.parent.mkdir(parents=True)
            docs.write_text("# Release\n", encoding="utf-8")
            self.commit_all(root, "docs")
            self.assertEqual(release_paths.releasable_paths(root), [])

            source = root / "desktop/windows/package.json"
            source.write_text("{}\n", encoding="utf-8")
            self.commit_all(root, "package")
            self.assertEqual(release_paths.releasable_paths(root), ["desktop/windows/package.json"])

    def test_moving_runtime_content_into_docs_is_still_releasable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.git(root, "init", "--quiet")
            source = root / "desktop/windows/src/runtime.md"
            destination = root / "desktop/windows/docs/runtime.md"
            source.parent.mkdir(parents=True)
            source.write_text("runtime content\n", encoding="utf-8")
            self.commit_all(root, "runtime")
            base = self.git(root, "rev-parse", "HEAD").stdout.strip()

            destination.parent.mkdir(parents=True)
            self.git(root, "mv", str(source.relative_to(root)), str(destination.relative_to(root)))
            self.commit_all(root, "move")

            self.assertEqual(
                release_paths.releasable_paths(root, base),
                ["desktop/windows/src/runtime.md"],
            )

    def test_manual_workflow_uses_the_tested_classifier(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("\non:\n  workflow_dispatch:\n", workflow)
        self.assertNotIn("\n  push:\n", workflow)
        self.assertIn(
            'HAS_CHANGES=$(python3 .github/scripts/windows_release_paths.py --base "$LATEST")',
            workflow,
        )
        self.assertNotIn("git diff --quiet --diff-filter=ACDMR", workflow)

    @staticmethod
    def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def commit_all(self, root: Path, message: str) -> None:
        self.git(root, "add", ".")
        self.git(
            root,
            "-c",
            "user.name=Omi release path test",
            "-c",
            "user.email=release-paths@example.invalid",
            "commit",
            "--quiet",
            "-m",
            message,
        )

    @staticmethod
    def run_cli(root: Path, base: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), "--root", str(root), "--base", base],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()

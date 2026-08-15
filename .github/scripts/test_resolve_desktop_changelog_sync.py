#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / ".github/scripts/resolve-desktop-changelog-sync.py"


def load_resolve():
    spec = importlib.util.spec_from_file_location("resolve_desktop_changelog_sync", MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["resolve_desktop_changelog_sync"] = mod
    spec.loader.exec_module(mod)
    return mod


resolve = load_resolve()


def clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_AUTHOR_NAME"] = "test"
    env["GIT_AUTHOR_EMAIL"] = "t@example.com"
    env["GIT_COMMITTER_NAME"] = "test"
    env["GIT_COMMITTER_EMAIL"] = "t@example.com"
    return env


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True, env=clean_env()).strip()


class ResolveDesktopChangelogSyncTests(unittest.TestCase):
    def _repo(self) -> Path:
        root = Path(tempfile.mkdtemp())
        git(root, "init")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "test")
        # default branch main
        git(root, "checkout", "-b", "main")
        (root / "f").write_text("a\n", encoding="utf-8")
        git(root, "add", "f")
        git(root, "commit", "-m", "base")
        return root

    def test_already_on_main_with_tip_bump_planned_source(self) -> None:
        repo = self._repo()
        base = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-b", "changelog-side")
        (repo / "c").write_text("c\n", encoding="utf-8")
        git(repo, "add", "c")
        git(repo, "commit", "-m", "chore: consolidate changelog for v0.12.143")
        cons = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "main")
        git(repo, "merge", "--no-ff", "changelog-side", "-m", "Update desktop changelog for v0.12.143 [skip ci] (#10787)")
        (repo / "t").write_text("t\n", encoding="utf-8")
        git(repo, "add", "t")
        git(repo, "commit", "-m", "tip bump")
        tip = git(repo, "rev-parse", "HEAD")
        started = time.monotonic()
        result = resolve.resolve_changelog_sync(
            repo,
            planned_source_sha=tip,
            version="0.12.143",
            main_ref="main",
            repository_slug="BasedHardware/omi",
        )
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 5.0, "must not O(n) scan main history")
        self.assertEqual(result["mode"], "already-on-main")
        self.assertTrue(result["already_on_main"])
        self.assertEqual(result["commit"], cons)
        self.assertIn("10787", str(result["pr_url"]))

    def test_parent_mismatch_rejects_when_unreleased_fragments_advance(self) -> None:
        """Codex P2: do not reuse old consolidate when planned source gained fragments."""
        repo = self._repo()
        git(repo, "checkout", "-b", "changelog-side")
        (repo / "c").write_text("c\n", encoding="utf-8")
        git(repo, "add", "c")
        git(repo, "commit", "-m", "chore: consolidate changelog for v0.12.143")
        cons = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "main")
        git(
            repo,
            "merge",
            "--no-ff",
            "changelog-side",
            "-m",
            "Update desktop changelog for v0.12.143 [skip ci] (#10787)",
        )
        frag = repo / "desktop" / "macos" / "changelog" / "unreleased" / "20260728-99.json"
        frag.parent.mkdir(parents=True, exist_ok=True)
        frag.write_text('{"change": "new fragment after consolidate"}\n', encoding="utf-8")
        git(repo, "add", str(frag.relative_to(repo)))
        git(repo, "commit", "-m", "feat: desktop change with changelog fragment")
        tip = git(repo, "rev-parse", "HEAD")
        result = resolve.resolve_changelog_sync(
            repo,
            planned_source_sha=tip,
            version="0.12.143",
            main_ref="main",
            repository_slug="BasedHardware/omi",
        )
        self.assertEqual(result["mode"], "missing")
        self.assertEqual(result["commit"], "")
        self.assertFalse(result["already_on_main"])

    def test_missing_when_no_consolidate(self) -> None:
        repo = self._repo()
        tip = git(repo, "rev-parse", "HEAD")
        result = resolve.resolve_changelog_sync(
            repo,
            planned_source_sha=tip,
            version="0.12.143",
            main_ref="main",
        )
        self.assertEqual(result["mode"], "missing")
        self.assertEqual(result["commit"], "")


if __name__ == "__main__":
    unittest.main()

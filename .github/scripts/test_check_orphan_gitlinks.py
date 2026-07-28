#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT_SRC = Path(__file__).resolve().with_name("check_orphan_gitlinks.py")


def clean_git_environment(env: dict[str, str]) -> dict[str, str]:
    """Keep hook-local Git state out of isolated fixtures."""
    cleaned = {k: v for k, v in env.items() if not k.startswith("GIT_")}
    cleaned.setdefault("GIT_AUTHOR_NAME", "test")
    cleaned.setdefault("GIT_AUTHOR_EMAIL", "test@example.com")
    cleaned.setdefault("GIT_COMMITTER_NAME", "test")
    cleaned.setdefault("GIT_COMMITTER_EMAIL", "test@example.com")
    return cleaned


def _run(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        env=clean_git_environment(dict(os.environ)),
    )


def _git(cwd: Path, *args: str) -> None:
    _run(cwd, "git", *args)


class CheckOrphanGitlinksTests(unittest.TestCase):
    def _layout(self, repo: Path) -> Path:
        tools = repo / ".github" / "scripts"
        tools.mkdir(parents=True)
        target = tools / "check_orphan_gitlinks.py"
        target.write_text(SCRIPT_SRC.read_text(encoding="utf-8"), encoding="utf-8")
        return target

    def _init_repo(self, repo: Path) -> None:
        _git(repo, "init")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "test")
        (repo / "README").write_text("x\n", encoding="utf-8")
        _git(repo, "add", "README")
        _git(repo, "commit", "-m", "init")

    def test_clean_tree_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_repo(repo)
            script = self._layout(repo)
            proc = _run(repo, "python3", str(script), check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)

    def test_orphan_gitlink_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_repo(repo)
            nested = repo / "_nested"
            nested.mkdir()
            _git(nested, "init")
            _git(nested, "config", "user.email", "test@example.com")
            _git(nested, "config", "user.name", "test")
            (nested / "f").write_text("y\n", encoding="utf-8")
            _git(nested, "add", "f")
            _git(nested, "commit", "-m", "nested")
            oid = _run(nested, "git", "rev-parse", "HEAD").stdout.strip()
            _run(
                repo,
                "git",
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{oid},vendor/dep",
            )
            _git(repo, "commit", "-m", "add orphan gitlink")
            script = self._layout(repo)
            proc = _run(repo, "python3", str(script), check=False)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("Orphan gitlink", proc.stderr)

    def test_mapped_gitlink_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_repo(repo)
            nested = repo / "_nested"
            nested.mkdir()
            _git(nested, "init")
            _git(nested, "config", "user.email", "test@example.com")
            _git(nested, "config", "user.name", "test")
            (nested / "f").write_text("y\n", encoding="utf-8")
            _git(nested, "add", "f")
            _git(nested, "commit", "-m", "nested")
            oid = _run(nested, "git", "rev-parse", "HEAD").stdout.strip()
            _run(
                repo,
                "git",
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{oid},vendor/dep",
            )
            (repo / ".gitmodules").write_text(
                '[submodule "vendor/dep"]\n\tpath = vendor/dep\n'
                "\turl = https://example.com/dep.git\n",
                encoding="utf-8",
            )
            _git(repo, "add", ".gitmodules")
            _git(repo, "commit", "-m", "mapped gitlink")
            script = self._layout(repo)
            proc = _run(repo, "python3", str(script), check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)


if __name__ == "__main__":
    unittest.main()

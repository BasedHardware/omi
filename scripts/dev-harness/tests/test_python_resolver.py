from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

HARNESS_ROOT = Path(__file__).resolve().parents[1]
RESOLVER = HARNESS_ROOT / "_resolve_python.sh"


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _resolve_python(repo: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)
    monkeypatch.delenv("PYTHON", raising=False)
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; dev_harness_python', "bash", str(resolver)],
        cwd=repo,
        env=os.environ.copy(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_resolver_prefers_repo_venvs_and_only_uses_python3_without_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    modern = repo / "backend/.venv/bin/python"
    legacy = repo / "backend/venv/bin/python"

    _make_executable(modern)
    _make_executable(legacy)
    assert _resolve_python(repo, monkeypatch) == str(modern)

    modern.unlink()
    assert _resolve_python(repo, monkeypatch) == str(legacy)

    legacy.unlink()
    assert _resolve_python(repo, monkeypatch) == "python3"


def test_resolver_honors_explicit_python_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_executable(repo / "backend/.venv/bin/python")
    monkeypatch.setenv("PYTHON", "custom-python")

    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; dev_harness_python', "bash", str(resolver)],
        cwd=repo,
        env=os.environ.copy(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "custom-python"

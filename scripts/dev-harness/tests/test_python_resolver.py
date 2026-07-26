from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

HARNESS_ROOT = Path(__file__).resolve().parents[1]
RESOLVER = HARNESS_ROOT / "_resolve_python.sh"
MAKEFILE = HARNESS_ROOT.parents[1] / "Makefile"


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


def test_make_harness_targets_run_resolved_python_from_checkout_with_spaces(tmp_path: Path) -> None:
    repo = tmp_path / "omi pr-10017 space"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    shutil.copy2(MAKEFILE, repo / "Makefile")

    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)

    calls = repo / "python calls.log"
    python = repo / "backend/.venv/bin/python"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$HARNESS_PYTHON_CALLS"\n', encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)

    # Exercise the resolver's backend/.venv fallback, so clear any inherited
    # PYTHON (e.g. `make preflight` exports it) exactly like the sibling tests.
    env = os.environ.copy()
    env.pop("PYTHON", None)
    env["HARNESS_PYTHON_CALLS"] = str(calls)
    targets = (
        ("list-memory-scenarios", []),
        ("seed-memory-scenario", ["SCENARIO=sample"]),
        ("reset-memory-scenario", ["SCENARIO=sample"]),
        ("run-canonical-promotion", ["PROMOTION_USER=alice"]),
    )
    for target, variables in targets:
        result = subprocess.run(
            ["make", "-C", str(repo), *variables, target],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    assert calls.read_text(encoding="utf-8").splitlines() == [
        "scripts/dev-harness/list-memory-scenarios.py",
        "scripts/dev-harness/seed-memory-scenario.py sample",
        "scripts/dev-harness/reset-memory-scenario.py sample",
        "scripts/dev-harness/run-canonical-promotion.py alice",
    ]


def test_make_harness_does_not_execute_checkout_name_and_resolves_python(tmp_path: Path) -> None:
    repo = tmp_path / "omi pr-10017'; touch injected-marker; #"
    marker = repo / "injected-marker"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    shutil.copy2(MAKEFILE, repo / "Makefile")

    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)

    calls = repo / "python calls.log"
    python = repo / "backend/.venv/bin/python"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$HARNESS_PYTHON_CALLS"\n', encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env.pop("PYTHON", None)
    env["HARNESS_PYTHON_CALLS"] = str(calls)
    result = subprocess.run(
        ["make", "-C", str(repo), "list-memory-scenarios"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    assert not marker.exists()
    assert result.returncode == 0, result.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == ["scripts/dev-harness/list-memory-scenarios.py"]


def test_make_harness_does_not_execute_double_quote_in_checkout_name(tmp_path: Path) -> None:
    """A double quote in the checkout root must not break recipe shell quoting.

    Recipes now use $$PYTHON (shell variable expansion) instead of $(PYTHON)
    (Make text interpolation). Shell variable expansion treats the resolved
    path as data, so quote characters cannot escape the recipe's quoting.
    """
    repo = tmp_path / 'omi "; touch double-quote-marker; #'
    marker = repo / "double-quote-marker"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    shutil.copy2(MAKEFILE, repo / "Makefile")

    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)

    calls = repo / "python calls.log"
    python = repo / "backend/.venv/bin/python"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$HARNESS_PYTHON_CALLS"\n', encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env.pop("PYTHON", None)
    env["HARNESS_PYTHON_CALLS"] = str(calls)
    result = subprocess.run(
        ["make", "-C", str(repo), "list-memory-scenarios"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    assert not marker.exists()
    assert result.returncode == 0, result.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == ["scripts/dev-harness/list-memory-scenarios.py"]

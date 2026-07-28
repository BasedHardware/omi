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


def _bash_command() -> str:
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            git_root = Path(git).resolve().parent.parent
            for relative_path in (Path("bin/bash.exe"), Path("usr/bin/bash.exe")):
                candidate = git_root / relative_path
                if candidate.is_file():
                    return str(candidate)
    else:
        bash = shutil.which("bash")
        if bash:
            return bash
    pytest.skip("Bash is required for dev-harness resolver tests")


def _make_command() -> str:
    for name in ("make", "mingw32-make"):
        executable = shutil.which(name)
        if executable:
            return executable
    pytest.skip("GNU Make is required for dev-harness Makefile tests")


def _shell_env() -> dict[str, str]:
    env = os.environ.copy()
    if os.name == "nt":
        bash = Path(_bash_command())
        path_entries = [str(bash.parent)]
        if existing := env.get("PATH"):
            path_entries.append(existing)
        env["PATH"] = os.pathsep.join(path_entries)
        env["SHELL"] = str(bash)
    return env


def _as_bash_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    result = subprocess.run(
        [_bash_command(), "-c", 'cygpath -u "$1"', "bash", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


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
        [_bash_command(), "-c", 'source "$1"; dev_harness_python', "bash", _as_bash_path(resolver)],
        cwd=repo,
        env=_shell_env(),
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
    assert _resolve_python(repo, monkeypatch) == _as_bash_path(modern)

    modern.unlink()
    assert _resolve_python(repo, monkeypatch) == _as_bash_path(legacy)

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
        [_bash_command(), "-c", 'source "$1"; dev_harness_python', "bash", _as_bash_path(resolver)],
        cwd=repo,
        env=_shell_env(),
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
    env = _shell_env()
    env.pop("PYTHON", None)
    env["HARNESS_PYTHON_CALLS"] = _as_bash_path(calls)
    targets = (
        ("list-memory-scenarios", []),
        ("seed-memory-scenario", ["SCENARIO=sample"]),
        ("reset-memory-scenario", ["SCENARIO=sample"]),
        ("run-canonical-promotion", ["PROMOTION_USER=alice"]),
    )
    for target, variables in targets:
        result = subprocess.run(
            [_make_command(), "-C", str(repo), *variables, target],
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

    env = _shell_env()
    env.pop("PYTHON", None)
    env["HARNESS_PYTHON_CALLS"] = _as_bash_path(calls)
    result = subprocess.run(
        [_make_command(), "-C", str(repo), "list-memory-scenarios"],
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


@pytest.mark.skipif(os.name == "nt", reason='Windows filenames cannot contain a double quote (")')
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

    env = _shell_env()
    env.pop("PYTHON", None)
    env["HARNESS_PYTHON_CALLS"] = _as_bash_path(calls)
    result = subprocess.run(
        [_make_command(), "-C", str(repo), "list-memory-scenarios"],
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

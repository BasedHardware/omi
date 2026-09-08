from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

HARNESS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = HARNESS_ROOT.parents[1]
DEV_INIT = HARNESS_ROOT / "dev-init.sh"
RESOLVER = HARNESS_ROOT / "_resolve_python.sh"
INSTALL_HOOKS = REPO_ROOT / "scripts/install-git-hooks.sh"
HOOK_SOURCES = ("changed-files", "pre-commit", "pre-push", "pre-push-singleflight", "pr-preflight")


def _clean_env() -> dict[str, str]:
    """Environment with Git's repository-local variables stripped.

    Git exports GIT_DIR and friends to hooks, so this module runs under them
    whenever the pre-push gate invokes it. Left in place, `git init <fixture>`
    re-opens the *caller's* repository instead of creating the fixture.
    """
    env = os.environ.copy()
    local_vars = subprocess.run(
        ["git", "rev-parse", "--local-env-vars"], text=True, stdout=subprocess.PIPE, check=True
    ).stdout.split()
    for var in local_vars:
        env.pop(var, None)
    env.pop("PYTHON", None)
    return env


def _git(*args: str) -> None:
    subprocess.run(["git", *args], env=_clean_env(), check=True, stdout=subprocess.DEVNULL)


def _bash() -> str:
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is required for dev-init tests")
    return bash


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _fixture_repo(root: Path) -> Path:
    """A checkout carrying just enough of the repo for dev-init.sh to run."""
    repo = root / "repo"
    repo.mkdir()
    _git("init", "-q", "--initial-branch=main", str(repo))

    (repo / "scripts/dev-harness").mkdir(parents=True)
    shutil.copy2(DEV_INIT, repo / "scripts/dev-harness/dev-init.sh")
    shutil.copy2(RESOLVER, repo / "scripts/dev-harness/_resolve_python.sh")
    shutil.copy2(INSTALL_HOOKS, repo / "scripts/install-git-hooks.sh")
    for name in HOOK_SOURCES:
        _write_executable(repo / "scripts" / name, "#!/usr/bin/env bash\nexit 0\n")

    (repo / "backend").mkdir()
    (repo / "backend/.env.local-dev.template").write_text("OMI_FIXTURE=1\n", encoding="utf-8")
    (repo / "backend/requirements.txt").write_text("", encoding="utf-8")
    # Stand in for the backend venv so the dependency install is a no-op and the
    # test exercises the hook step without touching the network.
    _write_executable(repo / "backend/.venv/bin/python", "#!/usr/bin/env bash\nexit 0\n")

    _git("-C", str(repo), "add", "-A")
    _git(
        "-C",
        str(repo),
        "-c",
        "user.name=omi",
        "-c",
        "user.email=omi@example.invalid",
        "commit",
        "-qm",
        "init",
    )
    return repo


def _run_dev_init(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_bash(), "scripts/dev-harness/dev-init.sh"],
        cwd=cwd,
        env=_clean_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )


def _hooks_dir(cwd: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--git-path", "hooks"],
        env=_clean_env(),
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    )
    # `--git-path` answers relative to the work tree in a main checkout and
    # absolutely in a linked worktree; joining handles both.
    return (cwd / result.stdout.strip()).resolve()


def test_dev_init_installs_hooks_from_a_linked_worktree(tmp_path: Path) -> None:
    """A linked worktree's `.git` is a file, so `.git/hooks/pre-commit` does not exist.

    dev-init.sh used to symlink that literal path and died with
    `ln: .git/hooks/pre-commit: Not a directory` — after `pip install`, so the
    failure cost a full dependency install first.
    """
    repo = _fixture_repo(tmp_path)
    worktree = tmp_path / "linked"
    _git("-C", str(repo), "worktree", "add", "-q", "-b", "work", str(worktree))
    assert (worktree / ".git").is_file()

    result = _run_dev_init(worktree)

    assert result.returncode == 0, result.stdout
    hook = _hooks_dir(worktree) / "pre-commit"
    assert hook.is_file() and os.access(hook, os.X_OK), result.stdout


def test_dev_init_installs_hooks_in_a_main_checkout(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)

    result = _run_dev_init(repo)

    assert result.returncode == 0, result.stdout
    hook = _hooks_dir(repo) / "pre-commit"
    assert hook.is_file() and os.access(hook, os.X_OK), result.stdout
    assert (repo / "backend/.env.local-dev").is_file(), result.stdout


def test_dev_init_next_steps_cover_mobile_and_desktop(tmp_path: Path) -> None:
    """The closing hint used to name only `make dev-desktop`, so anyone setting
    up the harness for mobile/iOS testing against it (which needs `make
    dev-up`, not the desktop app) was pointed at the wrong command.
    """
    repo = _fixture_repo(tmp_path)

    result = _run_dev_init(repo)

    assert result.returncode == 0, result.stdout
    assert "make dev-up" in result.stdout, result.stdout
    assert "make dev-desktop" in result.stdout, result.stdout

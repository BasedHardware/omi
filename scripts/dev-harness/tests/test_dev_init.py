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
    # test exercises the hook step without touching the network. The stub
    # reports this venv as its sys.prefix — the membership contract dev-init
    # checks before installing.
    _write_executable(
        repo / "backend/.venv/bin/python",
        "#!/usr/bin/env bash\n"
        'if [ "${1:-}" = "-c" ] && [ "${2:-}" = "import sys; print(sys.prefix)" ]; then\n'
        '  d="$(cd "$(dirname "$0")/.." && pwd -P)"\n'
        '  printf \'%s\\n\' "$d"\n'
        '  exit 0\n'
        "fi\n"
        "exit 0\n",
    )

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


def _linked_worktree_dest(tmp_path: Path) -> Path:
    """Place the linked worktree where the host Git wrapper allows it.

    The managed git wrapper refuses destinations under /tmp and ~/workspace so
    disposable trees land on scratch. Pytest's tmp_path is typically
    /private/tmp, which that guard correctly denies. Task worktrees belong
    under $OMI_WORKTREES (normally /Volumes/scratch/worktrees/omi). Do not
    bypass the guard or skip this test when that root exists.
    """
    candidates: list[Path] = []
    env_root = os.environ.get("OMI_WORKTREES", "").strip()
    if env_root:
        candidates.append(Path(env_root))
    default_root = Path("/Volumes/scratch/worktrees/omi")
    if default_root not in candidates:
        candidates.append(default_root)
    for root in candidates:
        if root.is_dir():
            return root / f".pytest-dev-init-linked-{os.getpid()}-{tmp_path.name}"
    return tmp_path / "linked"


def test_dev_init_installs_hooks_from_a_linked_worktree(tmp_path: Path) -> None:
    """A linked worktree's `.git` is a file, so `.git/hooks/pre-commit` does not exist.

    dev-init.sh used to symlink that literal path and died with
    `ln: .git/hooks/pre-commit: Not a directory` — after `pip install`, so the
    failure cost a full dependency install first.
    """
    repo = _fixture_repo(tmp_path)
    worktree = _linked_worktree_dest(tmp_path)
    try:
        _git("-C", str(repo), "worktree", "add", "-q", "-b", "work", str(worktree))
        assert (worktree / ".git").is_file()

        result = _run_dev_init(worktree)

        assert result.returncode == 0, result.stdout
        hook = _hooks_dir(worktree) / "pre-commit"
        assert hook.is_file() and os.access(hook, os.X_OK), result.stdout
    finally:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree)],
            env=_clean_env(),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        shutil.rmtree(worktree, ignore_errors=True)


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


def test_dev_init_creates_the_venv_even_with_a_floor_qualified_fallback(
    tmp_path: Path,
) -> None:
    """A floor-qualified versioned interpreter must not skip venv creation.

    dev-init used to create backend/.venv only when the resolver returned the
    literal `python3`; on a host with python3.12 on PATH but no venv, it ran
    `pip install -r requirements.txt` against the global interpreter instead
    (externally-managed Homebrew Pythons reject that; others get polluted).
    Creation now keys on the venv's absence, and the requirements install must
    run through the freshly created venv (Codex P1).
    """
    repo = _fixture_repo(tmp_path)
    (repo / "backend/.venv/bin/python").unlink()
    log = tmp_path / "python-calls.log"
    stub_bin = tmp_path / "devinit-stub-bin"
    stub_bin.mkdir()
    stub = stub_bin / "python3"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "# Fake bootstrap interpreter: `-m venv <dir>` materializes a stub venv\n"
        "# whose python logs its invocations and reports the venv as its\n"
        "# sys.prefix; every other call is logged too.\n"
        f'LOG="{log}"\n'
        'if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then\n'
        '  target="$3"\n'
        '  mkdir -p "$target/bin"\n'
        "  cat > \"$target/bin/python\" <<'INNER'\n"
        "#!/usr/bin/env bash\n"
        f'LOG="{log}"\n'
        'if [ "${1:-}" = "-c" ] && [ "${2:-}" = "import sys; print(sys.prefix)" ]; then\n'
        '  d="$(cd "$(dirname "$0")/.." && pwd -P)"\n'
        '  printf \'%s\\n\' "$d"\n'
        '  exit 0\n'
        "fi\n"
        f'printf \'VENV %s\\n\' "$*" >> "{log}"\n'
        "exit 0\n"
        "INNER\n"
        '  chmod +x "$target/bin/python"\n'
        "  exit 0\n"
        "fi\n"
        f'printf \'%s\\n\' "$*" >> "{log}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    env = _clean_env()
    env["PATH"] = os.pathsep.join((str(stub_bin), "/usr/bin", "/bin"))
    env["DEVINIT_LOG"] = str(log)
    result = subprocess.run(
        [_bash(), "scripts/dev-harness/dev-init.sh"],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    assert (repo / "backend/.venv/bin/python").is_file(), result.stdout
    assert "Created backend/.venv" in result.stdout, result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    # The requirements install (and its pip probe) must have run through the
    # freshly created venv interpreter — the P1 contract — never a bare/global
    # interpreter.
    assert any(line.startswith("VENV -m pip --version") for line in calls), calls
    assert any(line.startswith("VENV -m pip install") for line in calls), calls


def _write_logging_bootstrap_stub(directory: Path, name: str, log: Path, *, floor_ok: bool) -> None:
    """A fake interpreter whose probes are scripted and whose `venv` subcommand
    materializes a stub venv whose python logs its invocations and reports the
    venv as its sys.prefix (the membership contract dev-init checks)."""
    stub = directory / name
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'LOG="{log}"\n'
        f'FLOOR_OK="{1 if floor_ok else 0}"\n'
        'if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then\n'
        '  target="$3"\n'
        '  mkdir -p "$target/bin"\n'
        "  cat > \"$target/bin/python\" <<'INNER'\n"
        "#!/usr/bin/env bash\n"
        f'LOG="{log}"\n'
        'if [ "${1:-}" = "-c" ] && [ "${2:-}" = "import sys; print(sys.prefix)" ]; then\n'
        '  d="$(cd "$(dirname "$0")/.." && pwd -P)"\n'
        '  printf \'%s\\n\' "$d"\n'
        '  exit 0\n'
        "fi\n"
        f'printf \'VENV %s\\n\' "$*" >> "{log}"\n'
        "exit 0\n"
        "INNER\n"
        '  chmod +x "$target/bin/python"\n'
        f'printf \'%s %s\\n\' "{name}" "$*" >> "{log}"\n'
        "  exit 0\n"
        "fi\n"
        'case "$2" in\n'
        "  *version_info*) exit $((1 - FLOOR_OK)) ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
        f'printf \'%s %s\\n\' "{name}" "$*" >> "{log}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)


def test_dev_init_bootstraps_the_venv_with_a_floor_qualified_interpreter(
    tmp_path: Path,
) -> None:
    """The bootstrap interpreter is the resolver's floor-qualified pick.

    With python3.12 (floor-qualified) ahead of a 3.9 `python3` on PATH, the
    created venv must come from python3.12 — creating it from the 3.9 host
    interpreter would produce a below-floor venv that the resolver then
    rejects (Oracle follow-up on the Codex P1).
    """
    repo = _fixture_repo(tmp_path)
    (repo / "backend/.venv/bin/python").unlink()
    log = tmp_path / "bootstrap-calls.log"
    stub_bin = tmp_path / "bootstrap-stub-bin"
    stub_bin.mkdir()
    _write_logging_bootstrap_stub(stub_bin, "python3.12", log, floor_ok=True)
    _write_logging_bootstrap_stub(stub_bin, "python3", log, floor_ok=False)

    env = _clean_env()
    env["PATH"] = os.pathsep.join((str(stub_bin), "/usr/bin", "/bin"))
    result = subprocess.run(
        [_bash(), "scripts/dev-harness/dev-init.sh"],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    assert "Created backend/.venv (with python3.12)" in result.stdout, result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("python3.12 -m venv backend/.venv") for line in calls), calls
    assert any(line.startswith("VENV -m pip install") for line in calls), calls


def test_dev_init_refuses_to_install_outside_the_venv(tmp_path: Path) -> None:
    """The requirements install must never run outside backend/.venv.

    When the resolver's final pick is not the repo venv (here: an explicit
    PYTHON override, the same seam the resolver documents), dev-init must
    refuse with lane-bootstrap guidance instead of pip-installing into a
    global/foreign interpreter (Oracle follow-up on the Codex P1).
    """
    repo = _fixture_repo(tmp_path)
    log = tmp_path / "refusal-calls.log"
    stub_bin = tmp_path / "refusal-stub-bin"
    stub_bin.mkdir()
    foreign = stub_bin / "foreign-python"
    foreign.write_text(
        "#!/usr/bin/env bash\n"
        f'printf \'FOREIGN %s\\n\' "$*" >> "{log}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    foreign.chmod(foreign.stat().st_mode | stat.S_IXUSR)

    env = _clean_env()
    env["PYTHON"] = str(foreign)
    result = subprocess.run(
        [_bash(), "scripts/dev-harness/dev-init.sh"],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )

    assert result.returncode == 1, result.stdout
    assert "refusing to install requirements outside the venv" in result.stdout, result.stdout
    assert "make lane-bootstrap" in result.stdout, result.stdout
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    assert not any(line.startswith("FOREIGN -m pip") for line in calls), calls


def test_dev_init_refuses_a_foreign_checkout_venv_override(tmp_path: Path) -> None:
    """Another repo's backend/.venv must not pass the venv guard.

    The guard compares the resolved interpreter's physical path against THIS
    repo's canonical venv, so a PYTHON override whose path merely contains
    `backend/.venv` cannot pip-install this repo's requirements elsewhere
    (Oracle follow-up: substring match bypass).
    """
    repo = _fixture_repo(tmp_path)
    log = tmp_path / "foreign-venv-calls.log"
    other = tmp_path / "other-checkout"
    (other / "backend/.venv/bin").mkdir(parents=True)
    foreign = other / "backend/.venv/bin/python"
    foreign.write_text(
        "#!/usr/bin/env bash\n"
        f'printf \'FOREIGNVENV %s\\n\' "$*" >> "{log}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    foreign.chmod(foreign.stat().st_mode | stat.S_IXUSR)

    env = _clean_env()
    env["PYTHON"] = str(foreign)
    result = subprocess.run(
        [_bash(), "scripts/dev-harness/dev-init.sh"],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )

    assert result.returncode == 1, result.stdout
    assert "refusing to install requirements outside the venv" in result.stdout, result.stdout
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    assert not any(line.startswith("FOREIGNVENV -m pip") for line in calls), calls

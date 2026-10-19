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


def _write_logging_bootstrap_stub(directory: Path, name: str, log: Path, *, pinned_ok: bool) -> None:
    """A fake interpreter whose probes are scripted and whose `venv` subcommand
    materializes a stub venv whose python logs its invocations and reports the
    venv as its sys.prefix (the membership contract dev-init checks).

    `pinned_ok` scripts the version predicate: dev-init's bootstrap probe is
    the strict >=3.11,<3.12 pin, so a stub that fails it (a real 3.12 or 3.9)
    must not be selected as the pinned backend runtime.
    """
    stub = directory / name
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'LOG="{log}"\n'
        f'PINNED_OK="{1 if pinned_ok else 0}"\n'
        'if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then\n'
        '  target="$3"\n'
        '  mkdir -p "$target/bin"\n'
        "  cat > \"$target/bin/python\" <<'INNER'\n"
        "#!/usr/bin/env bash\n"
        f'LOG="{log}"\n'
        'if [ "${1:-}" = "-c" ] && [ "${2:-}" = "import sys; print(sys.prefix)" ]; then\n'
        '  d="$(cd "$(dirname "$0")/.." && pwd -P)"\n'
        "  printf '%s\\n' \"$d\"\n"
        "  exit 0\n"
        "fi\n"
        f'printf \'VENV %s\\n\' "$*" >> "{log}"\n'
        "exit 0\n"
        "INNER\n"
        '  chmod +x "$target/bin/python"\n'
        f'printf \'%s %s\\n\' "{name}" "$*" >> "{log}"\n'
        "  exit 0\n"
        "fi\n"
        'case "$2" in\n'
        "  *version_info*) exit $((1 - PINNED_OK)) ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
        f'printf \'%s %s\\n\' "{name}" "$*" >> "{log}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)


def _isolate_host_prefixes(repo: Path) -> None:
    """Neutralize the host's real Homebrew 3.11 prefixes in a fixture repo.

    `dev_harness_backend_pinned_python` probes absolute Homebrew prefixes, so on
    a macOS host with a keg-only 3.11 the fallback/absence fixtures would be
    silently rescued (Codex P2). The fixture's resolver copy gets an empty
    prefix list; only PATH/uv/PYTHON discovery remains host-dependent, and
    those tests already stub them.
    """
    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    with resolver.open("a", encoding="utf-8") as handle:
        handle.write("\ndev_harness_backend_pinned_prefixes() { :; }\n")


def test_dev_init_refuses_to_bootstrap_without_a_pinned_311(tmp_path: Path) -> None:
    """No discoverable or provisionable 3.11 means refusal — not a fallback.

    dev-init provisions the backend requirements install, and the backend
    pylock is `>=3.11,<3.12` (mobile_doctor rejects any other version), so a
    3.12/3.14 floor pick must not silently create a backend-incompatible venv
    (Codex P1 + Oracle review). With only a floor-qualified python3.12 and a
    3.9 python3 on PATH and no uv, dev-init must exit 1 with install guidance.
    """
    repo = _fixture_repo(tmp_path)
    _isolate_host_prefixes(repo)
    (repo / "backend/.venv/bin/python").unlink()
    log = tmp_path / "bootstrap-calls.log"
    stub_bin = tmp_path / "bootstrap-stub-bin"
    stub_bin.mkdir()
    _write_logging_bootstrap_stub(stub_bin, "python3.12", log, pinned_ok=False)
    _write_logging_bootstrap_stub(stub_bin, "python3", log, pinned_ok=False)

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

    assert result.returncode == 1, result.stdout
    assert "no Python 3.11 could be provisioned" in result.stdout, result.stdout
    assert "uv python install 3.11" in result.stdout, result.stdout
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    # No venv may be created from a backend-incompatible interpreter.
    assert not any(line.startswith("python3.12 -m venv") for line in calls), calls
    assert not any(line.startswith("python3 -m venv") for line in calls), calls
    assert not (repo / "backend/.venv/bin/python").exists(), result.stdout


def test_dev_installs_311_via_uv_when_not_on_path(tmp_path: Path) -> None:
    """Without a PATH python3.11, dev-init provisions it through uv.

    `uv python install 3.11` is exactly what `make lane-backend` does, so a
    uv-present host without a discoverable 3.11 must end up with the pinned
    runtime rather than a refusal (Codex P1 + Oracle review).
    """
    repo = _fixture_repo(tmp_path)
    _isolate_host_prefixes(repo)
    (repo / "backend/.venv/bin/python").unlink()
    log = tmp_path / "uv-calls.log"
    stub_bin = tmp_path / "uv-stub-bin"
    stub_bin.mkdir()
    # Only a floor-qualified python3.12 (not the pin) on PATH…
    _write_logging_bootstrap_stub(stub_bin, "python3.12", log, pinned_ok=False)
    # …and a pinned-runtime template that `uv python install 3.11` "installs"
    # onto PATH (a venv-creating, membership-reporting, pin-passing stub).
    template = tmp_path / "pinned-template"
    _write_logging_bootstrap_stub(tmp_path, "pinned-template", log, pinned_ok=True)
    # …and a uv whose `python install 3.11` materializes python3.11 on PATH.
    uv = stub_bin / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        f'LOG="{log}"\n'
        'if [ "${1:-}" = "python" ] && [ "${2:-}" = "install" ] && [ "${3:-}" = "3.11" ]; then\n'
        f'  printf \'%s %s\\n\' "uv" "$*" >> "{log}"\n'
        f'  cp "{template}" "$(dirname "$0")/python3.11"\n'
        '  chmod +x "$(dirname "$0")/python3.11"\n'
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)

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
    assert "uv-provisioned repo-pinned backend runtime" in result.stdout, result.stdout
    assert "Created backend/.venv (with python3.11)" in result.stdout, result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("uv python install 3.11") for line in calls), calls


def test_dev_init_refuses_to_install_outside_the_venv(tmp_path: Path) -> None:
    """The requirements install must never run outside backend/.venv.

    dev-init binds the install to this repo's venv python; if that interpreter
    has been replaced by (or symlinked to) a foreign one, the sys.prefix
    membership check must refuse with lane-bootstrap guidance instead of
    pip-installing elsewhere (Oracle follow-up on the Codex P1).
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
    # Replace the repo venv python with a link to the foreign interpreter: the
    # exact spoofing shape the sys.prefix check exists for.
    (repo / "backend/.venv/bin/python").unlink()
    (repo / "backend/.venv/bin/python").symlink_to(foreign)

    env = _clean_env()
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
    assert "does not belong to this repo's backend/.venv" in result.stdout, result.stdout
    assert "make lane-bootstrap" in result.stdout, result.stdout
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    assert not any(line.startswith("FOREIGN -m pip") for line in calls), calls


def test_dev_init_refuses_a_foreign_checkout_venv_override(tmp_path: Path) -> None:
    """A symlinked repo venv python pointing at another checkout must fail.

    The membership check compares sys.prefix against THIS repo's venv realpath,
    so a backend/.venv/bin/python that resolves into a foreign checkout's venv
    (different prefix) cannot pip-install this repo's requirements there.
    """
    repo = _fixture_repo(tmp_path)
    log = tmp_path / "foreign-venv-calls.log"
    other = tmp_path / "other-checkout"
    (other / "backend/.venv/bin").mkdir(parents=True)
    foreign = other / "backend/.venv/bin/python"
    foreign.write_text(
        "#!/usr/bin/env bash\n"
        f'LOG="{log}"\n'
        'if [ "${1:-}" = "-c" ] && [ "${2:-}" = "import sys; print(sys.prefix)" ]; then\n'
        '  d="$(cd "$(dirname "$0")/../.." && pwd -P)"\n'
        '  printf \'%s\\n\' "$d"\n'
        '  exit 0\n'
        "fi\n"
        f'printf \'FOREIGNVENV %s\\n\' "$*" >> "{log}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    foreign.chmod(foreign.stat().st_mode | stat.S_IXUSR)
    (repo / "backend/.venv/bin/python").unlink()
    (repo / "backend/.venv/bin/python").symlink_to(foreign)

    env = _clean_env()
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
    assert "does not belong to this repo's backend/.venv" in result.stdout, result.stdout
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    assert not any(line.startswith("FOREIGNVENV -m pip") for line in calls), calls


def test_dev_init_bootstraps_the_pinned_311_when_discoverable(tmp_path: Path) -> None:
    """Bootstrap must prefer the repo-pinned 3.11 over the floor pick.

    The backend pylock is `>=3.11,<3.12` and mobile_doctor rejects a non-3.11
    backend venv, so dev-init provisioning a 3.12/3.14 venv would create an
    environment the documented mobile flow immediately blocks (Codex P1).
    Discovery comes from the resolver's pinned-backend helper; this test pins
    the dev-init preference contract, not the helper's internals.
    """
    repo = _fixture_repo(tmp_path)
    (repo / "backend/.venv/bin/python").unlink()
    log = tmp_path / "pinned-calls.log"
    stub_bin = tmp_path / "pinned-stub-bin"
    stub_bin.mkdir()

    # A venv-creating, membership-reporting python3.11 (pin OK)…
    _write_logging_bootstrap_stub(stub_bin, "python3.11", log, pinned_ok=True)
    # …and a floor-qualified python3.12 that must NOT be preferred over it.
    _write_logging_bootstrap_stub(stub_bin, "python3.12", log, pinned_ok=False)

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
    assert "Created backend/.venv (with python3.11)" in result.stdout, result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("python3.11 -m venv backend/.venv") for line in calls), calls
    assert not any(line.startswith("python3.12 -m venv") for line in calls), calls
    assert any(line.startswith("VENV -m pip install") for line in calls), calls


def test_dev_init_refuses_an_existing_below_floor_venv(tmp_path: Path) -> None:
    """A pre-existing below-floor venv must not receive the requirements install.

    The executable-only bootstrap condition used to skip every check on a
    checkout that already had backend/.venv, so dev-init ran the full install
    under 3.9 and reported success while the resolver (and the pre-push gate)
    ignores that same venv (Codex P1). dev-init must refuse with
    lane-bootstrap guidance instead.
    """
    repo = _fixture_repo(tmp_path)
    # The fixture venv python exits 0 for everything; script it into a
    # below-floor interpreter so dev_harness_canonical_python rejects it.
    venv_python = repo / "backend/.venv/bin/python"
    venv_python.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "${1:-}" = "-c" ]; then\n'
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    venv_python.chmod(venv_python.stat().st_mode | 0o755)

    env = _clean_env()
    env["PATH"] = os.pathsep.join(("/usr/bin", "/bin"))
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
    assert "not the pinned Python 3.11 runtime" in result.stdout, result.stdout
    assert "make lane-bootstrap" in result.stdout, result.stdout
    assert "refusing to install requirements into it" in result.stdout, result.stdout


def test_dev_init_completes_an_interrupted_install_in_an_existing_venv(
    tmp_path: Path,
) -> None:
    """A floor-OK venv missing cheap-gate packages is completable, not refused.

    An interrupted first run leaves backend/.venv at exactly this shape (the
    venv was created, the requirements install did not finish). Refusing it
    would deadlock: the only tool allowed to finish the install is the one
    that refuses. dev-init must complete the install instead (Oracle review
    follow-up on the Codex P1).
    """
    repo = _fixture_repo(tmp_path)
    # Script the fixture venv python to log its non-probe calls (the pip
    # install) while still reporting its sys.prefix — floor OK, import probe
    # passes, i.e. exactly the interrupted-first-run shape. dev-init must
    # proceed to the pip install rather than refuse.
    log = tmp_path / "resume-calls.log"
    venv_python = repo / "backend/.venv/bin/python"
    venv_python.write_text(
        "#!/usr/bin/env bash\n"
        f'LOG="{log}"\n'
        'if [ "${1:-}" = "-c" ] && [ "${2:-}" = "import sys; print(sys.prefix)" ]; then\n'
        '  d="$(cd "$(dirname "$0")/.." && pwd -P)"\n'
        "  printf '%s\\n' \"$d\"\n"
        "  exit 0\n"
        "fi\n"
        "printf 'VENV %s\\n' \"$*\" >> \"$LOG\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    venv_python.chmod(venv_python.stat().st_mode | 0o755)

    env = _clean_env()
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
    assert "below the 3.10 floor" not in result.stdout, result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("VENV -m pip install") for line in calls), calls

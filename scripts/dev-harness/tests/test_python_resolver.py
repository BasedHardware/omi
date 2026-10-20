from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import runpy
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

HARNESS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = HARNESS_ROOT.parents[1]
RESOLVER = HARNESS_ROOT / "_resolve_python.sh"
PYTHON_RUNNER = HARNESS_ROOT / "run-python.sh"
MAKEFILE = REPO_ROOT / "Makefile"
PRE_PUSH_SINGLEFLIGHT = REPO_ROOT / "scripts/pre-push-singleflight"
PREFLIGHT_RUNNER = REPO_ROOT / ".github/scripts/preflight_runner.py"


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
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _git_init(repo: Path) -> None:
    """Create a fixture repository without re-opening the caller's repository.

    Git exports GIT_DIR and friends to hooks, so this module runs under them
    whenever the pre-push gate invokes it. Left in place, `git init <fixture>`
    re-inits the caller's repository instead — which sets `core.bare=true` on a
    linked-worktree parent and breaks every later `git rev-parse --show-toplevel`
    in the same push.
    """
    env = os.environ.copy()
    local_vars = subprocess.run(
        ["git", "rev-parse", "--local-env-vars"], text=True, stdout=subprocess.PIPE, check=True
    ).stdout.split()
    for var in local_vars:
        env.pop(var, None)
    subprocess.run(["git", "init", "-q", str(repo)], env=env, check=True)


# Completeness probes invoke `$python -c 'import dotenv, yaml'`. Fixture
# interpreters must pass that check without logging it as a harness call.
_LOGGED_PYTHON = """#!/usr/bin/env bash
if [ "${1:-}" = "-c" ]; then
  exit 0
fi
printf "%s\\n" "$*" >> "$HARNESS_PYTHON_CALLS"
"""


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_logged_python(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_LOGGED_PYTHON, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _resolve_python(repo: Path, monkeypatch: pytest.MonkeyPatch, path: str | None = None) -> str:
    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)
    monkeypatch.delenv("PYTHON", raising=False)
    env = _shell_env()
    if path is not None:
        env["PATH"] = path
    result = subprocess.run(
        [_bash_command(), "-c", 'source "$1"; dev_harness_python', "bash", _as_bash_path(resolver)],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _write_stub_python(directory: Path, name: str, *, meets_floor: bool) -> Path:
    """Stub a PATH interpreter whose floor probe result is scripted.

    The resolver probes each fallback candidate with
    `python -c '... sys.version_info >= (3, 10) ...'`, so a stub that exits 0
    represents a >= 3.10 interpreter and exit 1 represents a below-floor one.
    Stubbing every fallback name keeps the resolution outcome deterministic on
    any host, regardless of which real interpreters are installed.
    """
    stub = directory / name
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text("#!/bin/sh\n" f"exit {0 if meets_floor else 1}\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub


def _stubbed_path(tmp_path: Path, meets_floor: dict[str, bool]) -> str:
    directory = tmp_path / "stub-bin"
    for name, floor_ok in meets_floor.items():
        _write_stub_python(directory, name, meets_floor=floor_ok)
    return os.pathsep.join((str(directory), os.environ.get("PATH", "")))


def _assert_floor_qualified_or_documented_fallback(resolved: str) -> None:
    """Accept every documented resolver outcome when no venv exists.

    Either a PATH name (`python3`, `python3.X`) that the resolver floor-probed,
    or an absolute prefix path that was floor-probed. Anything else (a bare
    python3 name on a 3.9 Xcode CLT host when a qualified candidate exists) is
    the regression this suite guards.
    """
    if resolved == "python3":
        return
    if not resolved.startswith("/"):
        assert resolved.startswith("python3."), resolved
        return
    assert Path(resolved).is_file(), resolved
    version_probe = subprocess.run(
        [resolved, "-c", "import sys; print(sys.version_info[:2] >= (3, 10))"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert version_probe.stdout.strip() == "True", resolved


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
    # Without a repo venv the resolver probes PATH candidates and then absolute
    # install prefixes. Any floor-qualified outcome (or the documented bare
    # `python3` name) is acceptable; a below-floor pick is the regression.
    _assert_floor_qualified_or_documented_fallback(_resolve_python(repo, monkeypatch))


def test_resolver_skips_below_floor_python3_for_versioned_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bare `python3` is often macOS Xcode CLT 3.9, which cannot run the gate.

    The pre-push check scripts use PEP 604 unions at module scope, so the
    fallback chain must prefer a versioned interpreter that meets the 3.10
    floor instead of crashing at import time.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    stubbed = _stubbed_path(
        tmp_path,
        {
            "python3.14": False,
            "python3.13": False,
            "python3.12": False,
            "python3.11": True,
            "python3.10": False,
            "python3": False,
        },
    )
    assert _resolve_python(repo, monkeypatch, path=stubbed) == "python3.11"


def test_resolver_prefers_newest_meeting_floor_among_versioned_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    stubbed = _stubbed_path(
        tmp_path,
        {
            "python3.14": True,
            "python3.13": True,
            "python3.12": True,
            "python3.11": True,
            "python3.10": True,
            "python3": True,
        },
    )
    assert _resolve_python(repo, monkeypatch, path=stubbed) == "python3.14"


def test_resolver_keeps_bare_python3_when_it_meets_the_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    stubbed = _stubbed_path(
        tmp_path,
        {
            "python3.14": False,
            "python3.13": False,
            "python3.12": False,
            "python3.11": False,
            "python3.10": False,
            "python3": True,
        },
    )
    assert _resolve_python(repo, monkeypatch, path=stubbed) == "python3"


def _write_probe_stub_python(directory: Path, name: str, *, floor_ok: bool, imports_ok: bool) -> None:
    """Stub an interpreter whose floor and cheap-gate import probes are scripted.

    The resolver floor-probes with `-c 'import sys; ... version_info ...'` and
    import-probes with `-c 'import dotenv, yaml'`; `$2` carries the payload, so
    a stub can answer each probe independently.
    """
    stub = directory / name
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(
        "#!/bin/sh\n"
        'case "$2" in\n'
        "  *version_info*) exit "
        f"{0 if floor_ok else 1}"
        " ;;\n"
        "  *) exit "
        f"{0 if imports_ok else 1}"
        " ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)


def _stubbed_probe_path(tmp_path: Path, probes: dict[str, tuple[bool, bool]]) -> str:
    directory = tmp_path / "stub-probe-bin"
    for name, (floor_ok, imports_ok) in probes.items():
        _write_probe_stub_python(directory, name, floor_ok=floor_ok, imports_ok=imports_ok)
    return os.pathsep.join((str(directory), os.environ.get("PATH", "")))


def test_resolver_prefers_import_capable_python_over_newer_import_bare_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A newer interpreter without PyYAML/python-dotenv must not shadow one that has them.

    The resolver is shared by mobile-session.sh, dev-up.sh and the cheap
    pre-push gates, so among floor-qualified candidates the import-capable one
    wins even when a version-newer candidate exists.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    stubbed = _stubbed_probe_path(
        tmp_path,
        {
            # floor-passing but cannot import the cheap-gate deps
            "python3.14": (True, False),
            "python3.13": (False, False),
            "python3.12": (False, False),
            # floor-passing AND import-capable: must win over python3.14
            "python3.11": (True, True),
            "python3.10": (False, False),
            "python3": (False, False),
        },
    )
    assert _resolve_python(repo, monkeypatch, path=stubbed) == "python3.11"


def test_resolver_keeps_floor_qualified_fallback_when_no_candidate_has_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no import-capable candidate, keep the documented floor-only outcome.

    The gate then reports the missing module (actionable) instead of silently
    selecting a below-floor interpreter. An absolute prefix interpreter that is
    both floor- and import-qualified is an equally valid outcome on hosts that
    have one.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    stubbed = _stubbed_probe_path(
        tmp_path,
        {
            "python3.14": (True, False),
            "python3.13": (False, False),
            "python3.12": (False, False),
            "python3.11": (False, False),
            "python3.10": (False, False),
            "python3": (False, False),
        },
    )
    resolved = _resolve_python(repo, monkeypatch, path=stubbed)
    assert resolved != "python3", resolved
    _assert_floor_qualified_or_documented_fallback(resolved)


def test_resolver_probes_homebrew_prefix_when_path_is_stripped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hooks and cron contexts run /usr/bin:/bin PATHs with no versioned name.

    The absolute Homebrew prefix probe must still find a floor-qualified
    interpreter so the fixer push does not crash on macOS system 3.9. The probe
    list is fixed in the resolver, so assert the host-adaptive contract: the
    outcome must be a floor-qualified absolute prefix path when that prefix
    exists, or any other documented outcome (a PATH name such as `python3.12`
    on Linux hosts, or the bare `python3` fallback).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    stripped = os.pathsep.join(("/usr/bin", "/bin"))
    resolved = _resolve_python(repo, monkeypatch, path=stripped)
    # Host-adaptive contract for the absolute prefix probe: accept every
    # documented outcome (floor-qualified absolute prefix path, relative PATH
    # name such as `python3.12` on Linux, or bare `python3`) and reject only a
    # below-floor pick. Whether an import-capable candidate shadows a newer
    # prefix interpreter depends on host state the test cannot enumerate; that
    # preference contract is pinned deterministically by
    # test_resolver_prefers_import_capable_python_over_newer_import_bare_one
    # with stubbed probes.
    _assert_floor_qualified_or_documented_fallback(resolved)


def test_resolver_skips_below_floor_venv_that_can_import_cheap_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 3.9 venv with dotenv/yaml must not shadow a floor-qualified pick.

    The venv probes used to check only imports; the pre-push check scripts use
    PEP 604 syntax at module scope, so a below-floor venv crashes the gate even
    when a valid interpreter exists (Codex P2 on the venv path).
    """
    repo = tmp_path / "repo"
    below_floor = repo / "backend/.venv/bin/python"
    _write_probe_stub_python(below_floor.parent, "python", floor_ok=False, imports_ok=True)
    stubbed = _stubbed_probe_path(
        tmp_path,
        {
            # The PATH fallback the resolver must reach instead.
            "python3.14": (True, False),
            "python3.13": (True, True),
            "python3.12": (False, False),
            "python3.11": (False, False),
            "python3.10": (False, False),
            "python3": (False, False),
        },
    )
    resolved = _resolve_python(repo, monkeypatch, path=stubbed)
    assert resolved == "python3.13", resolved


def test_resolver_skips_incomplete_venv_that_cannot_import_cheap_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A .venv directory is not proof the cheap pre-push gates can import."""

    if shutil.which("uv") is None:
        pytest.skip("uv is required to mint an incomplete 3.11 venv")
    repo = tmp_path / "repo"
    repo.mkdir()
    venv_dir = repo / "backend" / ".venv"
    created = subprocess.run(
        ["uv", "venv", "--python", "3.11", str(venv_dir)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if created.returncode != 0:
        pytest.skip(created.stderr[-500:] or "uv venv failed")
    python = venv_dir / "bin" / "python"
    assert python.is_file()
    probe = subprocess.run([str(python), "-c", "import dotenv, yaml"], capture_output=True, check=False)
    assert probe.returncode != 0
    # The skipped venv must fall through to the PATH probes and then absolute
    # install prefixes: any floor-qualified outcome (or the documented bare
    # `python3` name) is acceptable; a below-floor pick is the regression.
    _assert_floor_qualified_or_documented_fallback(_resolve_python(repo, monkeypatch))


def test_resolver_finds_windows_virtualenv_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    modern = repo / "backend/.venv/Scripts/python.exe"
    legacy = repo / "backend/venv/Scripts/python.exe"

    _make_executable(modern)
    _make_executable(legacy)
    assert _resolve_python(repo, monkeypatch) == _as_bash_path(modern)

    modern.unlink()
    assert _resolve_python(repo, monkeypatch) == _as_bash_path(legacy)


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


def test_resolver_detects_windows_python_without_bash4_case_conversion(tmp_path: Path) -> None:
    resolver = tmp_path / "_resolve_python.sh"
    shutil.copy2(RESOLVER, resolver)
    result = subprocess.run(
        [_bash_command(), "-c", 'source "$1"; dev_harness_python_uses_windows_paths PYTHON.EXE', "bash", str(resolver)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.name != "nt", reason="native Windows Python path semantics")
def test_pythonpath_uses_selected_windows_interpreter_separator(tmp_path: Path) -> None:
    repo = tmp_path / "omi 路径 pythonpath"
    module = repo / "scripts/dev-harness/fixture_import.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 'imported'\n", encoding="utf-8")
    resolver = module.parent / "_resolve_python.sh"
    shutil.copy2(RESOLVER, resolver)

    env = _shell_env()
    env["PYTHON"] = _as_bash_path(Path(sys.executable))
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            _bash_command(),
            "-c",
            (
                'source "$1"; '
                'python_bin="$(dev_harness_python)"; '
                'PYTHONPATH="$(dev_harness_pythonpath "$python_bin" scripts/dev-harness backend)" '
                '"$python_bin" -c \'import os, fixture_import; '
                'print(os.environ["PYTHONPATH"]); print(fixture_import.VALUE)\''
            ),
            "bash",
            _as_bash_path(resolver),
        ],
        cwd=repo,
        env=env,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["scripts/dev-harness;backend", "imported"]


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell entrypoint regression")
def test_make_uses_git_bash_when_bare_bash_resolves_to_wsl(tmp_path: Path) -> None:
    repo = tmp_path / "omi 路径 powershell"
    repo.mkdir()
    _git_init(repo)
    shutil.copy2(MAKEFILE, repo / "Makefile")

    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)
    shutil.copy2(PYTHON_RUNNER, resolver.parent / "run-python.sh")

    calls = tmp_path / "powershell-python-calls.log"
    target = repo / "scripts/dev-harness/list-memory-scenarios.py"
    target.write_text(
        "from pathlib import Path\n"
        "import os\n"
        "Path(os.environ['HARNESS_PYTHON_CALLS']).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )

    make = Path(_make_command()).resolve()
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    env = os.environ.copy()
    inherited_paths = [
        entry
        for entry in env.get("PATH", "").split(os.pathsep)
        if entry
        and Path(entry).as_posix().lower().rstrip("/")
        not in {"c:/program files/git/bin", "c:/program files/git/usr/bin"}
    ]
    env["PATH"] = os.pathsep.join((str(make.parent), *inherited_paths))
    bare_bash = shutil.which("bash", path=env["PATH"])
    assert bare_bash and Path(bare_bash).samefile(system32 / "bash.exe")
    env["OS"] = "Windows_NT"
    env["PYTHON"] = _as_bash_path(Path(sys.executable))
    env.pop("SHELL", None)
    env["HARNESS_PYTHON_CALLS"] = str(calls)
    result = subprocess.run(
        [str(make), "-C", str(repo), "list-memory-scenarios"],
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert calls.read_text(encoding="utf-8") == "ran"
    assert "WSL" not in result.stdout + result.stderr


@pytest.mark.skipif(os.name != "nt", reason="native Windows hook entrypoint regression")
def test_pre_push_singleflight_runs_shell_child_with_native_windows_python(tmp_path: Path) -> None:
    repo = tmp_path / "omi 路径 hook"
    repo.mkdir()
    _git_init(repo)

    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True)
    shutil.copy2(RESOLVER, resolver)
    wrapper = repo / "scripts/pre-push-singleflight"
    shutil.copy2(PRE_PUSH_SINGLEFLIGHT, wrapper)
    runner = repo / ".github/scripts/preflight_runner.py"
    runner.parent.mkdir(parents=True)
    shutil.copy2(PREFLIGHT_RUNNER, runner)
    pre_push = repo / "scripts/pre-push"
    pre_push.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf 'hook-output: 路径🚀\\n'\n"
        'printf "args: %s | %s\\n" "${1:-}" "${2:-}"\n',
        encoding="utf-8",
    )
    pre_push.chmod(pre_push.stat().st_mode | stat.S_IXUSR)

    state_root = tmp_path / "preflight-state"
    env = _shell_env()
    env["PYTHON"] = _as_bash_path(Path(sys.executable))
    env["OMI_PREFLIGHT_STATE_DIR"] = str(state_root)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [_bash_command(), _as_bash_path(wrapper), "fork", "https://example.invalid/repo.git"],
        cwd=repo,
        env=env,
        input="",
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    assert "hook-output: 路径🚀" in result.stdout
    assert "args: fork | https://example.invalid/repo.git" in result.stdout
    log = (state_root / "pre-push" / "preflight.log").read_text(encoding="utf-8")
    assert "hook-output: 路径🚀" in log


def test_make_harness_targets_run_resolved_python_from_checkout_with_unicode_and_spaces(tmp_path: Path) -> None:
    repo = tmp_path / "omi 路径 pr-10017 space"
    repo.mkdir()
    _git_init(repo)
    shutil.copy2(MAKEFILE, repo / "Makefile")

    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)
    shutil.copy2(PYTHON_RUNNER, resolver.parent / "run-python.sh")

    calls = tmp_path / "python calls.log"
    python = repo / "backend/.venv/bin/python"
    _write_logged_python(python)

    # Exercise the resolver's backend/.venv fallback, so clear any inherited
    # PYTHON (e.g. `make preflight` exports it) exactly like the sibling tests.
    env = _shell_env()
    env.pop("PYTHON", None)
    env["HARNESS_PYTHON_CALLS"] = _as_bash_path(calls)
    targets = (
        ("preflight", []),
        ("list-memory-scenarios", []),
        ("seed-memory-scenario", ["SCENARIO=sample"]),
        ("reset-memory-scenario", ["SCENARIO=sample"]),
        ("run-canonical-maintenance", ["MAINTENANCE_USER=alice"]),
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
        ".github/scripts/pr_preflight.py --lane local --base origin/main",
        "scripts/dev-harness/list-memory-scenarios.py",
        "scripts/dev-harness/seed-memory-scenario.py sample",
        "scripts/dev-harness/reset-memory-scenario.py sample",
        "scripts/dev-harness/run-canonical-maintenance.py alice",
    ]


def test_canonical_maintenance_harness_accepts_any_synthetic_uid_only_in_emulator(monkeypatch) -> None:
    module = runpy.run_path(
        str(REPO_ROOT / "scripts/dev-harness/run-canonical-maintenance.py"),
        run_name="run_canonical_maintenance_test",
    )
    from utils.memory import memory_authority

    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:18080")
    monkeypatch.setenv("ENVIRONMENT", "local-dev-harness")
    module["_configure_local_universal_memory"]("synthetic-alice")

    assert memory_authority.resolve_memory_system("synthetic-alice") == memory_authority.MemorySystem.CANONICAL
    assert memory_authority.resolve_memory_system("someone-else") == memory_authority.MemorySystem.CANONICAL


def test_canonical_maintenance_harness_replaces_ambient_environment(monkeypatch) -> None:
    module = runpy.run_path(
        str(REPO_ROOT / "scripts/dev-harness/run-canonical-maintenance.py"),
        run_name="run_canonical_maintenance_env_test",
    )
    original_env = os.environ.copy()
    child_env = {
        "ENVIRONMENT": "local-dev-harness",
        "FIRESTORE_EMULATOR_HOST": "127.0.0.1:18080",
        "PATH": original_env.get("PATH", ""),
    }
    monkeypatch.setattr(module["config"], "child_env_for", lambda _cfg: child_env)
    try:
        os.environ["PINECONE_API_KEY"] = "ambient-production-secret"
        os.environ["PINECONE_INDEX_NAME"] = "ambient-production-index"

        module["_apply_harness_env"](object())

        assert dict(os.environ) == child_env
        assert "PINECONE_API_KEY" not in os.environ
        assert "PINECONE_INDEX_NAME" not in os.environ
    finally:
        os.environ.clear()
        os.environ.update(original_env)


def test_canonical_maintenance_harness_serializes_recurrence_signals() -> None:
    pytest.importorskip("pydantic")
    module = runpy.run_path(
        str(REPO_ROOT / "scripts/dev-harness/run-canonical-maintenance.py"),
        run_name="run_canonical_maintenance_serialization_test",
    )
    from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
    from models.memory_recurrence import CanonicalRecurrenceSignal

    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    signal = CanonicalRecurrenceSignal(
        signal_id="loop-investor-update",
        title="Investor update",
        objective="Send the revised investor update",
        anchor_task_description="Prepare the investor email",
        occurrence_count=2,
        distinct_day_count=2,
        unresolved=True,
        confidence=0.9,
        first_seen_at=now - timedelta(days=1),
        last_seen_at=now,
        evidence_refs=[
            EvidenceRef(
                kind=EvidenceKind.memory_item,
                id="mem-investor-update",
                scope=EvidenceScope.canonical,
            )
        ],
    )

    @dataclass
    class _Report:
        recurrence_signals: list[CanonicalRecurrenceSignal]

    payload = module["_jsonable"](_Report(recurrence_signals=[signal]))

    assert json.loads(json.dumps(payload))["recurrence_signals"][0]["signal_id"] == signal.signal_id


def test_canonical_maintenance_harness_fails_on_outbox_delivery_errors(monkeypatch, capsys) -> None:
    module = runpy.run_path(
        str(REPO_ROOT / "scripts/dev-harness/run-canonical-maintenance.py"),
        run_name="run_canonical_maintenance_outbox_test",
    )
    main_globals = module["main"].__globals__
    monkeypatch.setattr(main_globals["config"], "load_config", lambda *_args, **_kwargs: object())
    monkeypatch.setitem(main_globals, "_apply_harness_env", lambda _cfg: None)
    monkeypatch.setitem(main_globals, "_resolve_uid", lambda _cfg, _user: "synthetic-alice")
    monkeypatch.setitem(main_globals, "_configure_local_universal_memory", lambda _uid: None)

    @dataclass
    class _MaintenanceReport:
        uid: str
        outbox: dict[str, object]
        skipped_reason: str | None = None
        promoted_count: int = 0

    report = _MaintenanceReport(
        uid="synthetic-alice",
        outbox={
            "retryable_failure_count": 2,
            "dead_letter_count": 1,
            "ack_failed_count": 3,
            "errors": [{"detail": "private provider response must not reach stderr"}],
        },
    )
    maintenance_module = ModuleType("utils.memory.short_term_promotion")
    maintenance_module.run_canonical_short_term_maintenance = lambda *_args, **_kwargs: report
    monkeypatch.setitem(sys.modules, maintenance_module.__name__, maintenance_module)

    assert module["main"](["alice", "--run-id", "outbox-failure"]) == 2

    captured = capsys.readouterr()
    assert ("canonical maintenance outbox delivery failed: " "retryable=2 dead_letter=1 ack=3 errors=1") in captured.err
    assert "private provider response" not in captured.err


def test_make_harness_does_not_execute_checkout_name_and_resolves_python(tmp_path: Path) -> None:
    repo = tmp_path / "omi pr-10017'; touch injected-marker; #"
    marker = repo / "injected-marker"
    repo.mkdir()
    _git_init(repo)
    shutil.copy2(MAKEFILE, repo / "Makefile")

    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)
    shutil.copy2(PYTHON_RUNNER, resolver.parent / "run-python.sh")

    calls = repo / "python calls.log"
    python = repo / "backend/.venv/bin/python"
    _write_logged_python(python)

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

    Recipes invoke a relative Bash runner, which resolves the checkout-local
    interpreter without interpolating the checkout root into recipe text.
    """
    repo = tmp_path / 'omi "; touch double-quote-marker; #'
    marker = repo / "double-quote-marker"
    repo.mkdir()
    _git_init(repo)
    shutil.copy2(MAKEFILE, repo / "Makefile")

    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)
    shutil.copy2(PYTHON_RUNNER, resolver.parent / "run-python.sh")

    calls = repo / "python calls.log"
    python = repo / "backend/.venv/bin/python"
    _write_logged_python(python)

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


def _run_resolver_function(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    function: str,
    path: str | None = None,
    extra_env: dict[str, str] | None = None,
    preamble: str = "",
) -> subprocess.CompletedProcess[str]:
    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)
    monkeypatch.delenv("PYTHON", raising=False)
    env = _shell_env()
    if path is not None:
        env["PATH"] = path
    for key, value in (extra_env or {}).items():
        env[key] = value
    return subprocess.run(
        [
            _bash_command(),
            "-c",
            f'source "$1"; {preamble}{function}',
            "bash",
            _as_bash_path(resolver),
        ],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )


def test_backend_pinned_python_prefers_path_311_over_uv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pinned-backend helper prefers a PATH python3.11 over uv discovery.

    Both sources are the same runtime family; the PATH name is the cheaper
    probe, so it must win when it exists. `uv` is absent from the stubbed PATH
    here, proving the PATH branch answers alone.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = tmp_path / "pinned-calls.log"
    stub_bin = tmp_path / "pinned-stub-bin"
    stub_bin.mkdir()
    stub = stub_bin / "python3.11"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\\\n" "$*" >> "{calls}"\n'
        'if [ "${1:-}" = "-c" ]; then\n'
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    result = _run_resolver_function(
        repo,
        monkeypatch,
        "dev_harness_backend_pinned_python",
        path=os.pathsep.join((str(stub_bin), "/usr/bin", "/bin")),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "python3.11"
    # The floor probe ran against the PATH name; no uv discovery was needed.
    assert any("version_info" in line for line in calls.read_text(encoding="utf-8").splitlines()), calls


def test_backend_pinned_python_falls_back_to_uv_managed_311(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a PATH python3.11, the helper discovers the uv-managed 3.11.

    This is the provisioning contract the Codex P1 asks for: dev-init must be
    able to bootstrap the pinned backend runtime from the same toolchain
    `make lane-backend` uses, without requiring an install first.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    uv_managed = tmp_path / "uv" / "python3.11"
    uv_managed.parent.mkdir(parents=True)
    uv_managed.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    uv_managed.chmod(uv_managed.stat().st_mode | stat.S_IXUSR)
    stub_bin = tmp_path / "uv-stub-bin"
    stub_bin.mkdir()
    uv = stub_bin / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "${1:-}" = "python" ] && [ "${2:-}" = "find" ] && [ "${3:-}" = "3.11" ]; then\n'
        f'  printf "%s\\\\n" "{uv_managed}"\n'
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)

    result = _run_resolver_function(
        repo,
        monkeypatch,
        "dev_harness_backend_pinned_python",
        path=os.pathsep.join((str(stub_bin), "/usr/bin", "/bin")),
        # A host with a real keg-only Homebrew 3.11 would otherwise satisfy
        # discovery before the fixture's uv is consulted (Codex P2): point the
        # prefix list at nothing.
        preamble="dev_harness_backend_pinned_prefixes() { :; }\n",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(uv_managed)


def test_backend_pinned_python_fails_without_any_311(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No usable 3.11 anywhere means failure — callers fall back.

    dev-init keys its advisory path on this failure, so the helper must return
    non-zero instead of printing an unqualified interpreter. Stubs make this
    deterministic: a PATH python3.11 that fails the floor probe is skipped,
    and a uv that cannot find 3.11 ends the discovery.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    stub_bin = tmp_path / "nopin-stub-bin"
    stub_bin.mkdir()
    below_floor = stub_bin / "python3.11"
    below_floor.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "${1:-}" = "-c" ]; then\n'
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    below_floor.chmod(below_floor.stat().st_mode | stat.S_IXUSR)
    uv = stub_bin / "uv"
    uv.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)

    result = _run_resolver_function(
        repo,
        monkeypatch,
        "dev_harness_backend_pinned_python",
        path=os.pathsep.join((str(stub_bin), "/usr/bin", "/bin")),
        # Host isolation: a real keg-only prefix must not rescue this fixture.
        preamble="dev_harness_backend_pinned_prefixes() { :; }\n",
    )

    assert result.returncode != 0
    assert result.stdout.strip() == ""


def test_backend_pinned_python_honors_python_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit PYTHON= selection passing the pin is the bootstrap pick.

    The resolver-level PYTHON override is a supported caller choice; when it
    points at a pinned 3.11 (e.g. a bare-named python3.11 without a python3.11
    on PATH), the helper must accept it instead of reporting failure (Codex P1).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    selected = tmp_path / "selected-python"
    selected.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    selected.chmod(selected.stat().st_mode | 0o755)

    result = _run_resolver_function(
        repo,
        monkeypatch,
        "dev_harness_backend_pinned_python",
        path=os.pathsep.join(("/usr/bin", "/bin")),
        extra_env={"PYTHON": str(selected)},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(selected)


def test_backend_pinned_python_rejects_below_pin_python_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PYTHON= override that fails the pin is not accepted."""
    repo = tmp_path / "repo"
    repo.mkdir()
    below = tmp_path / "below-pin-python"
    below.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "${1:-}" = "-c" ]; then\n'
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    below.chmod(below.stat().st_mode | 0o755)

    result = _run_resolver_function(
        repo,
        monkeypatch,
        "dev_harness_backend_pinned_python",
        path=os.pathsep.join(("/usr/bin", "/bin")),
        extra_env={"PYTHON": str(below)},
        # Host isolation: a real keg-only Homebrew 3.11 would legitimately
        # answer after the override is rejected (Codex P2).
        preamble="dev_harness_backend_pinned_prefixes() { :; }\n",
    )

    assert result.returncode != 0
    assert result.stdout.strip() == ""


def test_backend_pinned_python_probes_keg_only_homebrew_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The advertised brew remedy must satisfy discovery without uv.

    `brew install python@3.11` is keg-only when a newer python3 shadows it: no
    `python3.11` on PATH, but a real interpreter at the Homebrew prefix. The
    helper must probe those absolute prefixes before requiring uv (Codex P1).
    The prefix list and the pin predicate are stubbed AFTER the source (the
    resolver's definitions win otherwise) to point at a fixture keg path —
    creating real /opt/homebrew paths in a test is not possible without root.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    keg = tmp_path / "keg" / "bin" / "python3.11"
    keg.parent.mkdir(parents=True)
    keg.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    keg.chmod(keg.stat().st_mode | 0o755)

    resolver = repo / "scripts/dev-harness/_resolve_python.sh"
    resolver.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RESOLVER, resolver)
    monkeypatch.delenv("PYTHON", raising=False)
    env = _shell_env()
    env["PATH"] = os.pathsep.join(("/usr/bin", "/bin"))
    stubs = (
        "dev_harness_backend_pinned_prefixes() { printf '%s\\n' \"" + str(keg) + "\"; }\n"
        "dev_harness_venv_python_is_pinned_311() { [ \"$1\" = \"" + str(keg) + "\" ]; }\n"
    )
    result = subprocess.run(
        [
            _bash_command(),
            "-c",
            'source "$1"; '
            + stubs
            + "dev_harness_backend_pinned_python",
            "bash",
            _as_bash_path(resolver),
        ],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(keg)

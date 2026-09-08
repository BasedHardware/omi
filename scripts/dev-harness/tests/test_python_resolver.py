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
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$HARNESS_PYTHON_CALLS"\n', encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)

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

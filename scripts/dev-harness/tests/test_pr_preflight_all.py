"""Hermetic contract tests for the keep-going PR preflight orchestrator.

``scripts/pr_preflight_all.py`` is selected by ``scripts/pr-preflight --all``
(or ``OMI_PREFLIGHT_ALL=1`` for the hook path). These tests pin the contract
the mode exists for: a failing gate does not stop the run, the passing gate
after it still executes, one summary reports the failing gate's name, first
error line, log path, and repro command, and the exit code is nonzero.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR = REPO_ROOT / "scripts" / "pr_preflight_all.py"
WRAPPER = REPO_ROOT / "scripts" / "pr-preflight"

FAIL_FIRST_MANIFEST = """checks:
  - id: always-fail
    command: ["python3", "fail_gate.py"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "fixture gate that always fails"
  - id: always-pass
    command: ["python3", "pass_gate.py"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "fixture gate that always passes, ordered after the failing gate"
"""

PASS_ONLY_MANIFEST = """checks:
  - id: always-pass
    command: ["python3", "pass_gate.py"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "fixture gate that always passes"
"""

SLOW_THEN_PASS_MANIFEST = """checks:
  - id: slow
    command: ["python3", "slow_gate.py"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "fixture gate that exceeds the wall budget"
  - id: after-slow
    command: ["python3", "pass_gate.py"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "fixture gate after the over-budget gate"
"""


def _git(repo: Path, *args: str) -> str:
    # Temporary test identities go through `git -c`, never user configuration.
    result = subprocess.run(
        ["git", "-c", "user.name=Preflight Test", "-c", "user.email=preflight-test@example.com", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _build_repo(base: Path, manifest: str, *, backend_change: bool) -> tuple[Path, str]:
    repo = base / "repo"
    (repo / ".github").mkdir(parents=True)
    (repo / "fail_gate.py").write_text('print("FAIL: fixture gate one is broken")\nraise SystemExit(1)\n')
    (repo / "pass_gate.py").write_text('print("fixture gate two passed")\n')
    (repo / ".github" / "checks-manifest.yaml").write_text(manifest)
    _git(repo, "init")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text("change\n")
    if backend_change:
        (repo / "backend").mkdir()
        (repo / "backend" / "app.py").write_text("x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "head")
    return repo, base_sha


def _build_slow_repo(base: Path) -> tuple[Path, str]:
    repo, base_sha = _build_repo(base, SLOW_THEN_PASS_MANIFEST, backend_change=False)
    (repo / "slow_gate.py").write_text("import time\ntime.sleep(5)\n")
    _git(repo, "add", "slow_gate.py")
    _git(repo, "commit", "-m", "add slow fixture")
    return repo, base_sha


def _gate_env(**extra: str) -> dict[str, str]:
    # The outer harness may export GIT_* (hooks) and OMI_PREFLIGHT_* knobs; a
    # fixture repository must run without either leaking in (#11183 class).
    env = {key: value for key, value in os.environ.items() if not key.startswith(("GIT_", "OMI_PREFLIGHT_"))}
    env["OMI_PREFLIGHT_BACKGROUND"] = "0"
    env.update(extra)
    return env


def _run_orchestrator(
    repo: Path, base_sha: str, *args: str, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(ORCHESTRATOR),
            "--lane",
            "local",
            "--base",
            base_sha,
            "--head",
            "HEAD",
            "--root",
            str(repo),
            *args,
        ],
        cwd=repo,
        env=_gate_env(**(env_extra or {})),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
        check=False,
    )


@pytest.fixture()
def failing_then_passing_repo(tmp_path: Path) -> tuple[Path, str]:
    return _build_repo(tmp_path, FAIL_FIRST_MANIFEST, backend_change=False)


def test_failing_gate_then_passing_gate_reported_with_nonzero_exit(failing_then_passing_repo) -> None:
    repo, base_sha = failing_then_passing_repo
    body = repo / "pr-body.md"
    body.write_text("test body\n")
    result = _run_orchestrator(repo, base_sha, "--pr-body-file", str(body))

    assert result.returncode == 1
    out = result.stdout
    # Keep-going: execution reached the gate ordered after the failure.
    assert out.index("==> always-fail") < out.index("==> always-pass")
    assert "<== FAIL always-fail" in out
    assert "<== PASS always-pass" in out
    # One summary reports the failing gate with name, first error line, log path, repro.
    assert "FAILED always-fail" in out
    assert "error: FAIL: fixture gate one is broken" in out
    log_line = next(line for line in out.splitlines() if line.strip().startswith("log:"))
    log_path = Path(log_line.split("log:", 1)[1].strip())
    assert log_path.name == "always-fail.log"
    assert log_path.is_file()
    assert "FAIL: fixture gate one is broken" in log_path.read_text(encoding="utf-8")
    repro_line = next(line for line in out.splitlines() if line.strip().startswith("repro:"))
    assert "fail_gate.py" in repro_line
    assert str(repo) in repro_line
    assert "PR preflight --all failed" in out


def test_all_gates_passing_exits_zero(tmp_path: Path) -> None:
    repo, base_sha = _build_repo(tmp_path, PASS_ONLY_MANIFEST, backend_change=False)
    body = repo / "pr-body.md"
    body.write_text("test body\n")
    # --pr-body-file keeps gh discovery (and its network timeout) out of the run.
    result = _run_orchestrator(repo, base_sha, "--pr-body-file", str(body))

    assert result.returncode == 0
    assert "<== PASS always-pass" in result.stdout
    assert "FAILED" not in result.stdout
    assert "PR preflight --all passed: 1 gate(s)" in result.stdout


def test_exhausted_budget_reports_skipped_gates_instead_of_passing(failing_then_passing_repo) -> None:
    repo, base_sha = failing_then_passing_repo
    body = repo / "pr-body.md"
    body.write_text("test body\n")
    result = _run_orchestrator(
        repo, base_sha, "--pr-body-file", str(body), env_extra={"OMI_PREFLIGHT_ALL_BUDGET_SECONDS": "0"}
    )

    assert result.returncode == 1
    out = result.stdout
    assert "SKIPPED-FOR-TIME always-fail" in out
    assert "SKIPPED-FOR-TIME always-pass" in out
    assert "0 failed, 2 skipped for time" in out
    assert "did not certify the whole selection" in out


def test_gate_that_runs_past_budget_is_stopped_and_following_gate_is_reported(tmp_path: Path) -> None:
    repo, base_sha = _build_slow_repo(tmp_path)
    body = repo / "pr-body.md"
    body.write_text("test body\n")
    result = _run_orchestrator(
        repo,
        base_sha,
        "--pr-body-file",
        str(body),
        env_extra={"OMI_PREFLIGHT_ALL_BUDGET_SECONDS": "2"},
    )

    assert result.returncode == 1
    assert "<== SKIPPED-FOR-TIME slow" in result.stdout
    assert "SKIPPED-FOR-TIME after-slow" in result.stdout
    assert "0 failed, 2 skipped for time" in result.stdout


def test_ratchet_gate_selected_only_when_backend_files_change(tmp_path: Path) -> None:
    backend_repo, backend_base = _build_repo(tmp_path / "backend", FAIL_FIRST_MANIFEST, backend_change=True)
    docs_repo, docs_base = _build_repo(tmp_path / "docs-only", FAIL_FIRST_MANIFEST, backend_change=False)

    backend_out = _run_orchestrator(backend_repo, backend_base, "--list").stdout
    assert "SELECTED always-fail" in backend_out
    assert "SELECTED backend-ratchet-preflight" in backend_out

    docs_out = _run_orchestrator(docs_repo, docs_base, "--list").stdout
    assert "SELECTED always-fail" in docs_out
    assert "backend-ratchet-preflight" not in docs_out

    makefile_repo, makefile_base = _build_repo(tmp_path / "makefile-only", FAIL_FIRST_MANIFEST, backend_change=False)
    (makefile_repo / "Makefile").write_text("all:\n\t@true\n")
    makefile_out = _run_orchestrator(makefile_repo, makefile_base, "--list").stdout
    assert "backend-ratchet-preflight" not in makefile_out


def test_bad_budget_fails_closed(failing_then_passing_repo) -> None:
    repo, base_sha = failing_then_passing_repo
    result = _run_orchestrator(repo, base_sha, env_extra={"OMI_PREFLIGHT_ALL_BUDGET_SECONDS": "soon"})

    assert result.returncode == 2
    assert "OMI_PREFLIGHT_ALL_BUDGET_SECONDS" in result.stdout


def test_metadata_failure_is_summarized_and_does_not_stop_selected_gates(failing_then_passing_repo) -> None:
    repo, base_sha = failing_then_passing_repo
    result = _run_orchestrator(repo, base_sha, "--pr-body-file", str(repo / "missing-body.md"))

    assert result.returncode == 1
    assert "==> always-fail" in result.stdout
    assert "==> always-pass" in result.stdout
    assert "FAILED pr-metadata" in result.stdout
    assert "PR body file not found" in result.stdout


def _bash() -> str:
    if os.name == "nt":
        pytest.skip("wrapper dispatch tests run the Bash wrapper")
    return "bash"


def test_wrapper_all_flag_dispatches_to_keep_going(tmp_path: Path) -> None:
    repo, base_sha = _build_repo(tmp_path / "w", FAIL_FIRST_MANIFEST, backend_change=True)
    result = subprocess.run(
        [
            _bash(),
            str(WRAPPER),
            "--all",
            "--list",
            "--lane",
            "local",
            "--base",
            base_sha,
            "--head",
            "HEAD",
            "--root",
            str(repo),
        ],
        cwd=REPO_ROOT,
        env=_gate_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
        check=False,
    )

    assert result.returncode == 0
    assert "keep-going" in result.stdout
    assert "SELECTED backend-ratchet-preflight" in result.stdout


@pytest.mark.parametrize("flag_name", ["OMI_PREFLIGHT_ALL", "PRE_PUSH_PREFLIGHT_ALL"])
def test_wrapper_env_flag_dispatches_to_keep_going(tmp_path: Path, flag_name: str) -> None:
    repo, base_sha = _build_repo(tmp_path / "env", FAIL_FIRST_MANIFEST, backend_change=True)
    result = subprocess.run(
        [_bash(), str(WRAPPER), "--list", "--lane", "local", "--base", base_sha, "--head", "HEAD", "--root", str(repo)],
        cwd=REPO_ROOT,
        env=_gate_env(**{flag_name: "True"}),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
        check=False,
    )

    assert result.returncode == 0
    assert "keep-going" in result.stdout


def test_wrapper_without_all_keeps_fail_fast_default(tmp_path: Path) -> None:
    repo, base_sha = _build_repo(tmp_path / "legacy", FAIL_FIRST_MANIFEST, backend_change=True)
    result = subprocess.run(
        [_bash(), str(WRAPPER), "--list", "--lane", "local", "--base", base_sha, "--head", "HEAD", "--root", str(repo)],
        cwd=REPO_ROOT,
        env=_gate_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
        check=False,
    )

    assert result.returncode == 0
    assert "keep-going" not in result.stdout
    # The legacy fail-fast preflight still owns the default path.
    assert result.stdout.startswith("PR preflight: lane=local")


def test_wrapper_all_flag_is_removed_when_delegating_metadata_only(tmp_path: Path) -> None:
    repo, base_sha = _build_repo(tmp_path / "metadata", FAIL_FIRST_MANIFEST, backend_change=False)
    result = subprocess.run(
        [
            _bash(),
            str(WRAPPER),
            "--all",
            "--metadata-only",
            "--list",
            "--lane",
            "local",
            "--base",
            base_sha,
            "--head",
            "HEAD",
            "--root",
            str(repo),
        ],
        cwd=REPO_ROOT,
        env=_gate_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.startswith("PR preflight: lane=local")

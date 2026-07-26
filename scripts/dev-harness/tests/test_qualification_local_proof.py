from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import qualification, safety


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_NAMES = (
    "qualification-local-proof.sh",
    "qualification-lease-command.sh",
    "release-keyvalue.py",
    "omi-fault-inject.sh",
)
RELEASE_TAG = "v0.0.1+1-macos"
INHERITED_GIT_CONTEXT = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_QUARANTINE_PATH",
    "GIT_WORK_TREE",
)


def _run(*args: str | Path, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    process_env = dict(os.environ if env is None else env)
    for key in INHERITED_GIT_CONTEXT:
        process_env.pop(key, None)
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        env=process_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


@pytest.fixture
def proof_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "canonical-repo"
    scripts = repo / "desktop" / "macos" / "scripts"
    scripts.mkdir(parents=True)
    for name in SCRIPT_NAMES:
        shutil.copy2(REPO_ROOT / "desktop" / "macos" / "scripts" / name, scripts / name)
    shutil.copytree(REPO_ROOT / "scripts" / "dev-harness" / "dev_harness", repo / "scripts" / "dev-harness" / "dev_harness")
    backend = repo / "backend"
    backend.mkdir()
    (backend / ".venv").symlink_to(REPO_ROOT / "backend" / ".venv", target_is_directory=True)

    commands = (
        ("git", "init", "--quiet"),
        ("git", "config", "user.email", "qualification-proof@example.invalid"),
        ("git", "config", "user.name", "Qualification Proof Test"),
        ("git", "add", "."),
        ("git", "-c", "core.hooksPath=/dev/null", "commit", "--quiet", "-m", "qualification proof fixture"),
        ("git", "tag", RELEASE_TAG),
    )
    for command in commands:
        completed = _run(*command, cwd=repo)
        assert completed.returncode == 0, completed.stderr
    return repo


def _proof_env(tmp_path: Path) -> dict[str, str]:
    temporary = tmp_path / "tmp"
    temporary.mkdir(exist_ok=True)
    return {
        **os.environ,
        "OMI_QUALIFICATION_LEASE_ROOT": str(tmp_path / "qualification"),
        "TMPDIR": str(temporary),
    }


def _run_proof(repo: Path, tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    result = tmp_path / "evidence" / "local-qualification-proof.json"
    completed = _run(
        repo / "desktop" / "macos" / "scripts" / "qualification-local-proof.sh",
        "--offline",
        "--fast",
        "--result",
        result,
        RELEASE_TAG,
        cwd=repo,
        env=_proof_env(tmp_path),
    )
    return completed, result


def _free_port() -> int:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = int(listener.getsockname()[1])
    listener.close()
    return port


def _start_owned_fault(repo: Path, state: Path, token: str, port: int, env: dict[str, str]) -> int:
    completed = _run(
        repo / "desktop" / "macos" / "scripts" / "omi-fault-inject.sh",
        "start",
        "error",
        "--port",
        str(port),
        cwd=repo,
        env={
            **env,
            "OMI_FAULT_STATE_DIR": str(state),
            "OMI_FAULT_OWNERSHIP_TOKEN": token,
        },
    )
    assert completed.returncode == 0, completed.stderr
    return int((state / "pid").read_text(encoding="utf-8"))


def _wait_until(predicate: Callable[[], bool], timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert predicate()


@pytest.mark.skipif(sys.platform != "darwin", reason="the local proof is an M1/macOS lifecycle command")
def test_local_qualification_proof_completes_every_offline_boundary(proof_repo: Path, tmp_path: Path) -> None:
    completed, result_path = _run_proof(proof_repo, tmp_path)

    assert completed.returncode == 0, completed.stderr
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "passed"
    assert result["mode"] == "offline-fast"
    assert result["cleanup_status"] == "released"
    assert result["source_sha"] == _run("git", "rev-parse", "HEAD", cwd=proof_repo).stdout.strip()
    assert result["completed_boundaries"] == [
        "release-tag-validation",
        "lease-provenance-acquisition",
        "disposable-fault-listener-start",
        "runner-hygiene-preflight",
        "cleanup-finalization",
    ]
    assert result["fault_listener_result"]["status"] == "passed"
    assert stat.S_IMODE(result_path.stat().st_mode) == 0o600
    assert not (tmp_path / "qualification" / "qualification-lease.json").exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="the local proof is an M1/macOS lifecycle command")
def test_local_qualification_proof_refuses_foreign_stale_listener(
    monkeypatch: pytest.MonkeyPatch, proof_repo: Path, tmp_path: Path
) -> None:
    env = _proof_env(tmp_path)
    lease_root = Path(env["OMI_QUALIFICATION_LEASE_ROOT"])
    lease_id = "qualification-stale-proof"
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(lease_root))
    acquired = qualification.acquire(
        repo_root=proof_repo,
        lease_id=lease_id,
        owner_pid=os.getpid(),
        port_offset=1000,
    )
    state = lease_root / "state" / lease_id / qualification.FAULT_STATE_DIRNAME
    state.mkdir(mode=0o700)
    port = _free_port()
    owned_pid = _start_owned_fault(proof_repo, state, str(acquired["token"]), port, env)
    os.killpg(owned_pid, signal.SIGTERM)
    _wait_until(lambda: not safety.process_exists(owned_pid))

    foreign = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import socket,time; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); "
            "s.bind(('127.0.0.1',int(__import__('sys').argv[1]))); s.listen(); time.sleep(60)",
            str(port),
        ],
        start_new_session=True,
    )
    try:
        _wait_until(lambda: foreign.pid in safety.listening_pids(port))
        lease_path = lease_root / "qualification-lease.json"
        stale = json.loads(lease_path.read_text(encoding="utf-8"))
        stale["owner_pid"] = 999999
        lease_path.write_text(json.dumps(stale), encoding="utf-8")

        completed, result_path = _run_proof(proof_repo, tmp_path)

        assert completed.returncode != 0
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result["status"] == "failed"
        assert result["failure_reason"] == "unproven-stale-listener"
        assert result["cleanup_status"] == "not-acquired"
        assert result["completed_boundaries"] == ["release-tag-validation"]
        assert foreign.poll() is None
        assert lease_path.is_file()
        assert (state / "pid").is_file()
        assert (state / "meta").is_file()
    finally:
        if foreign.poll() is None:
            foreign.terminate()
            foreign.wait(timeout=10)
        qualification.release(repo_root=proof_repo, lease_id=lease_id, token=str(acquired["token"]))

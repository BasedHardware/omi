from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import qualification, safety


REPO_ROOT = Path(__file__).resolve().parents[3]


def _stale_lease(root: Path, lease_id: str, pid: int, port: int) -> None:
    state = root / "state" / lease_id
    lease_path = root / "qualification-lease.json"
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    marker = f"omi-dev-harness:{lease_id}:backend:{lease['token']}"
    state.joinpath("manifests", "processes.json").write_text(
        json.dumps({"processes": [{"service": "backend", "pid": pid, "process_group": pid, "port": port, "ownership_marker": marker}]}),
        encoding="utf-8",
    )
    state.joinpath("manifests", "ports.json").write_text(
        json.dumps({"ports": [{"service": "backend", "pid": pid, "port": port}]}), encoding="utf-8"
    )
    lease["owner_pid"] = 999999
    lease_path.write_text(json.dumps(lease), encoding="utf-8")


def test_active_lease_serializes_qualification_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "qualification"
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(root))
    first = qualification.acquire(repo_root=REPO_ROOT, lease_id="qualification-one", owner_pid=os.getpid(), port_offset=1000)

    with pytest.raises(qualification.QualificationLeaseError, match="refusing concurrent stack use"):
        qualification.acquire(repo_root=REPO_ROOT, lease_id="qualification-two", owner_pid=os.getpid(), port_offset=1001)

    qualification.release(repo_root=REPO_ROOT, lease_id="qualification-one", token=str(first["token"]))


def test_stale_owned_stack_is_reclaimed_without_touching_foreign_listener(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "qualification"
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(root))
    old_id = "qualification-owned"
    qualification.acquire(repo_root=REPO_ROOT, lease_id=old_id, owner_pid=os.getpid(), port_offset=1000)
    marker = f"omi-dev-harness:{old_id}:backend:{json.loads((root / 'qualification-lease.json').read_text(encoding='utf-8'))['token']}"
    owned_pid, stopped, signalled = 42424, set(), []
    foreign = subprocess.Popen(
        [sys.executable, "-c", "import socket,time; s=socket.socket(); s.bind(('127.0.0.1', 49199)); s.listen(); time.sleep(60)"],
        start_new_session=True,
    )
    try:
        original_exists = safety.process_exists
        monkeypatch.setattr(safety, "process_exists", lambda pid: pid == owned_pid and pid not in stopped or original_exists(pid))
        monkeypatch.setattr(safety, "command_line_for_pid", lambda pid: marker if pid == owned_pid else "")
        monkeypatch.setattr(qualification.os, "getpgid", lambda pid: pid)
        monkeypatch.setattr(qualification.os, "killpg", lambda pid, sig: (signalled.append((pid, sig)), stopped.add(pid)))
        _stale_lease(root, old_id, owned_pid, 49198)
        replacement = qualification.acquire(
            repo_root=REPO_ROOT, lease_id="qualification-replacement", owner_pid=os.getpid(), port_offset=1001
        )
        assert signalled and signalled[0][0] == owned_pid
        assert foreign.poll() is None
        qualification.release(
            repo_root=REPO_ROOT, lease_id="qualification-replacement", token=str(replacement["token"])
        )
    finally:
        for proc in (foreign,):
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)


def test_retention_prunes_only_completed_sentinel_proven_qualification_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "qualification"
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(root))
    completed = qualification.acquire(repo_root=REPO_ROOT, lease_id="qualification-completed", owner_pid=os.getpid(), port_offset=1000)
    qualification.release(repo_root=REPO_ROOT, lease_id="qualification-completed", token=str(completed["token"]))
    completion = root / "state" / "qualification-completed" / qualification.COMPLETION_FILENAME
    payload = json.loads(completion.read_text(encoding="utf-8"))
    payload["completed_at"] = 1
    completion.write_text(json.dumps(payload), encoding="utf-8")
    active = qualification.acquire(repo_root=REPO_ROOT, lease_id="qualification-active", owner_pid=os.getpid(), port_offset=1001)
    foreign = root / "state" / "foreign"
    foreign.mkdir(parents=True)
    qualification._prune(root, keep_lease_ids={"qualification-active"}, retained_runs=3, retention_age_seconds=1)
    assert not (root / "state" / "qualification-completed").exists()
    assert (root / "state" / "qualification-active").exists()
    assert foreign.exists()
    qualification.release(repo_root=REPO_ROOT, lease_id="qualification-active", token=str(active["token"]))


def test_supervisor_dead_with_recorded_port_still_open_retains_incomplete_lease(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "qualification"
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(root))
    lease_id = "qualification-port-still-open"
    monkeypatch.setattr(
        qualification,
        "STOP_PHASES",
        ((qualification.signal.SIGINT, 0), (qualification.signal.SIGTERM, 0), (qualification.signal.SIGKILL, 0)),
    )
    acquired = qualification.acquire(repo_root=REPO_ROOT, lease_id=lease_id, owner_pid=os.getpid(), port_offset=1000)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    try:
        _stale_lease(root, lease_id, pid=42424, port=port)
        with pytest.raises(qualification.QualificationLeaseError, match="port.*still open"):
            qualification.release(repo_root=REPO_ROOT, lease_id=lease_id, token=str(acquired["token"]))
        assert listener.fileno() >= 0
        assert (root / "qualification-lease.json").exists()
        assert not (root / "state" / lease_id / qualification.COMPLETION_FILENAME).exists()
    finally:
        listener.close()

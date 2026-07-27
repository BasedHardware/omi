from __future__ import annotations

import json
import os
import signal
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import qualification, safety


REPO_ROOT = Path(__file__).resolve().parents[3]
FAULT_INJECTOR = REPO_ROOT / "desktop" / "macos" / "scripts" / "omi-fault-inject.sh"


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


def _free_port() -> int:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = int(listener.getsockname()[1])
    listener.close()
    return port


def _start_fault_injector(state: Path, token: str, port: int) -> int:
    env = {
        **os.environ,
        "OMI_FAULT_STATE_DIR": str(state),
        "OMI_FAULT_OWNERSHIP_TOKEN": token,
    }
    subprocess.run(
        ["bash", str(FAULT_INJECTOR), "start", "error", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return int((state / "pid").read_text(encoding="utf-8"))


def test_active_lease_serializes_qualification_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "qualification"
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(root))
    first = qualification.acquire(repo_root=REPO_ROOT, lease_id="qualification-one", owner_pid=os.getpid(), port_offset=1000)

    with pytest.raises(qualification.QualificationLeaseError, match="refusing concurrent stack use"):
        qualification.acquire(repo_root=REPO_ROOT, lease_id="qualification-two", owner_pid=os.getpid(), port_offset=1001)

    qualification.release(repo_root=REPO_ROOT, lease_id="qualification-one", token=str(first["token"]))


def test_release_stops_the_exact_lease_owned_fault_inject_listener(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "qualification"
    lease_id = "qualification-owned-fault"
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(root))
    monkeypatch.setattr(qualification, "STOP_PHASES", ((signal.SIGTERM, 2), (signal.SIGKILL, 1)))
    acquired = qualification.acquire(repo_root=REPO_ROOT, lease_id=lease_id, owner_pid=os.getpid(), port_offset=1000)
    state = root / "state" / lease_id / qualification.FAULT_STATE_DIRNAME
    state.mkdir(mode=0o700)
    port = _free_port()
    pid = _start_fault_injector(state, str(acquired["token"]), port)

    qualification.release(repo_root=REPO_ROOT, lease_id=lease_id, token=str(acquired["token"]))

    assert not safety.listening_pids(port)
    deadline = time.monotonic() + 2
    while safety.process_exists(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not safety.process_exists(pid)
    assert not (root / "qualification-lease.json").exists()
    assert (root / "state" / lease_id / qualification.COMPLETION_FILENAME).is_file()


def test_fault_listener_preflight_proves_cleanup_before_retaining_the_active_lease(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "qualification"
    lease_id = "qualification-owned-fault-preflight"
    report_path = tmp_path / "fault-listener-preflight.json"
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(root))
    monkeypatch.setattr(qualification, "STOP_PHASES", ((signal.SIGTERM, 2), (signal.SIGKILL, 1)))
    acquired = qualification.acquire(
        repo_root=REPO_ROOT,
        lease_id=lease_id,
        owner_pid=os.getpid(),
        port_offset=1000,
    )
    state = root / "state" / lease_id / qualification.FAULT_STATE_DIRNAME
    state.mkdir(mode=0o700)
    port = _free_port()
    pid = _start_fault_injector(state, str(acquired["token"]), port)

    report = qualification.preflight_fault_cleanup(
        repo_root=REPO_ROOT,
        lease_id=lease_id,
        token=str(acquired["token"]),
        result_path=report_path,
    )

    assert report["status"] == "passed"
    assert report["port"] == port
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    assert not safety.listening_pids(port)
    deadline = time.monotonic() + 2
    while safety.process_exists(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not safety.process_exists(pid)
    assert not (state / "pid").exists()
    assert not (state / "meta").exists()
    assert (root / "qualification-lease.json").is_file()

    qualification.release(repo_root=REPO_ROOT, lease_id=lease_id, token=str(acquired["token"]))


def test_fault_listener_preflight_retains_replaced_listener_and_reports_host_prerequisite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "qualification"
    lease_id = "qualification-foreign-fault-preflight"
    report_path = tmp_path / "fault-listener-preflight.json"
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(root))
    acquired = qualification.acquire(
        repo_root=REPO_ROOT,
        lease_id=lease_id,
        owner_pid=os.getpid(),
        port_offset=1000,
    )
    state = root / "state" / lease_id / qualification.FAULT_STATE_DIRNAME
    state.mkdir(mode=0o700)
    port = _free_port()
    owned_pid = _start_fault_injector(state, str(acquired["token"]), port)
    os.killpg(owned_pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while safety.process_exists(owned_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
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
        deadline = time.monotonic() + 5
        while foreign.pid not in safety.listening_pids(port) and time.monotonic() < deadline:
            time.sleep(0.05)
        with pytest.raises(qualification.QualificationLeaseError, match="lease lineage is unproven"):
            qualification.preflight_fault_cleanup(
                repo_root=REPO_ROOT,
                lease_id=lease_id,
                token=str(acquired["token"]),
                result_path=report_path,
            )

        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["status"] == "failed"
        assert report["failure_reason"] == "unproven-listener-lineage"
        assert report["classification"] == "runner-hygiene-cleanup"
        assert foreign.poll() is None
        assert (root / "qualification-lease.json").is_file()
        assert (state / "pid").is_file()
        assert (state / "meta").is_file()
        assert not (root / "state" / lease_id / qualification.COMPLETION_FILENAME).exists()
    finally:
        if foreign.poll() is None:
            foreign.terminate()
            foreign.wait(timeout=10)


def test_release_refuses_and_retains_an_unproven_listener_on_the_recorded_fault_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "qualification"
    lease_id = "qualification-foreign-fault"
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(root))
    acquired = qualification.acquire(repo_root=REPO_ROOT, lease_id=lease_id, owner_pid=os.getpid(), port_offset=1000)
    state = root / "state" / lease_id / qualification.FAULT_STATE_DIRNAME
    state.mkdir(mode=0o700)
    port = _free_port()
    owned_pid = _start_fault_injector(state, str(acquired["token"]), port)
    os.killpg(owned_pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while safety.process_exists(owned_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
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
        deadline = time.monotonic() + 5
        while foreign.pid not in safety.listening_pids(port) and time.monotonic() < deadline:
            time.sleep(0.05)
        with pytest.raises(qualification.QualificationLeaseError, match="lease lineage is unproven"):
            qualification.release(repo_root=REPO_ROOT, lease_id=lease_id, token=str(acquired["token"]))
        assert foreign.poll() is None
        assert (root / "qualification-lease.json").is_file()
        assert (state / "meta").is_file()
        assert not (root / "state" / lease_id / qualification.COMPLETION_FILENAME).exists()
    finally:
        if foreign.poll() is None:
            foreign.terminate()
            foreign.wait(timeout=10)


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


def test_dead_lease_with_missing_sentinel_is_quarantined_before_a_fresh_lease_acquires(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "qualification"
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(root))
    stale_id = "qualification-missing-sentinel"
    qualification.acquire(repo_root=REPO_ROOT, lease_id=stale_id, owner_pid=os.getpid(), port_offset=1000)
    stale_pointer = json.loads((root / "qualification-lease.json").read_text(encoding="utf-8"))
    stale_state = root / "state" / stale_id
    (stale_state / safety.HARNESS_SENTINEL_FILENAME).unlink()
    stale_pointer["owner_pid"] = 999999
    (root / "qualification-lease.json").write_text(json.dumps(stale_pointer), encoding="utf-8")

    replacement = qualification.acquire(
        repo_root=REPO_ROOT, lease_id="qualification-replacement", owner_pid=os.getpid(), port_offset=1001
    )

    quarantined = list((root / qualification.QUARANTINE_DIRNAME).glob("*.json"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text(encoding="utf-8")) == stale_pointer
    assert stale_state.exists()
    assert not (stale_state / safety.HARNESS_SENTINEL_FILENAME).exists()
    assert json.loads((root / "qualification-lease.json").read_text(encoding="utf-8"))["lease_id"] == "qualification-replacement"

    qualification.release(repo_root=REPO_ROOT, lease_id="qualification-replacement", token=str(replacement["token"]))


def test_dead_lease_with_unproven_listener_is_quarantined_without_signalling_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "qualification"
    lease_id, recorded_pid = "qualification-unproven-listener", 42424
    monkeypatch.setenv("OMI_QUALIFICATION_LEASE_ROOT", str(root))
    qualification.acquire(repo_root=REPO_ROOT, lease_id=lease_id, owner_pid=os.getpid(), port_offset=1000)
    stale_pointer = json.loads((root / "qualification-lease.json").read_text(encoding="utf-8"))
    marker = f"omi-dev-harness:{lease_id}:backend:{stale_pointer['token']}"
    port = _free_port()
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
    signals: list[tuple[int, signal.Signals]] = []
    try:
        deadline = time.monotonic() + 5
        while foreign.pid not in safety.listening_pids(port) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert foreign.pid in safety.listening_pids(port)
        _stale_lease(root, lease_id, pid=recorded_pid, port=port)
        stale_pointer = json.loads((root / "qualification-lease.json").read_text(encoding="utf-8"))
        original_exists = safety.process_exists
        original_getpgid = qualification.os.getpgid
        monkeypatch.setattr(
            safety, "process_exists", lambda pid: pid == recorded_pid or original_exists(pid)
        )
        monkeypatch.setattr(safety, "command_line_for_pid", lambda pid: marker if pid == recorded_pid else "")
        monkeypatch.setattr(
            qualification.os, "getpgid", lambda pid: recorded_pid if pid == recorded_pid else original_getpgid(pid)
        )
        monkeypatch.setattr(qualification.os, "killpg", lambda pid, sig: signals.append((pid, sig)))

        replacement = qualification.acquire(
            repo_root=REPO_ROOT, lease_id="qualification-replacement", owner_pid=os.getpid(), port_offset=1001
        )

        quarantined = list((root / qualification.QUARANTINE_DIRNAME).glob("*.json"))
        assert len(quarantined) == 1
        assert json.loads(quarantined[0].read_text(encoding="utf-8")) == stale_pointer
        assert (root / "state" / lease_id).exists()
        assert foreign.poll() is None
        assert signals == []
        qualification.release(
            repo_root=REPO_ROOT, lease_id="qualification-replacement", token=str(replacement["token"])
        )
    finally:
        if foreign.poll() is None:
            foreign.terminate()
            foreign.wait(timeout=10)


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


def test_docker_typesense_proxy_listener_is_reclaimed_only_with_exact_container_binding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Docker owns the host listener outside the supervisor's process group."""
    lease_id, supervisor_pid, proxy_pid, port = "qualification-typesense", 42424, 51515, 49199
    container = f"omi-dev-harness-{lease_id}-typesense"
    record = {
        "service": "typesense",
        "pid": supervisor_pid,
        "process_group": supervisor_pid,
        "port": port,
        "command": [
            "docker",
            "run",
            "--rm",
            "--name",
            container,
            "-p",
            f"127.0.0.1:{port}:8108",
        ],
    }
    signalled: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(safety, "validate_owned_pid", lambda *args, **kwargs: None)
    monkeypatch.setattr(safety, "validate_port_owner", lambda *args, **kwargs: None)
    monkeypatch.setattr(safety, "listening_pids", lambda observed_port: (proxy_pid,) if observed_port == port else ())
    monkeypatch.setattr(safety, "is_descendant_of", lambda child, parent: False)
    monkeypatch.setattr(qualification.os, "getpgid", lambda pid: supervisor_pid if pid == supervisor_pid else proxy_pid)
    monkeypatch.setattr(qualification.os, "killpg", lambda pid, sig: signalled.append((pid, sig)))
    monkeypatch.setattr(
        qualification.subprocess,
        "run",
        lambda _args, **kwargs: subprocess.CompletedProcess(
            ["docker", "inspect"],
            0,
            stdout=json.dumps(
                {
                    "Name": f"/{container}",
                    "State": {"Running": True},
                    "NetworkSettings": {
                        "Ports": {"8108/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(port)}]}
                    },
                }
            ),
        ),
    )

    qualification._validated_signal(
        record, tmp_path / "processes.json", tmp_path / "ports.json", signal.SIGTERM, lease_id
    )

    assert signalled == [(supervisor_pid, signal.SIGTERM)]


def test_external_typesense_listener_without_exact_docker_binding_is_not_signalled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lease_id, supervisor_pid, proxy_pid, port = "qualification-typesense", 42424, 51515, 49199
    record = {
        "service": "typesense",
        "pid": supervisor_pid,
        "process_group": supervisor_pid,
        "port": port,
        "command": [
            "docker",
            "run",
            "--name",
            f"omi-dev-harness-{lease_id}-typesense",
            "-p",
            f"127.0.0.1:{port}:8108",
        ],
    }
    signalled: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(safety, "validate_owned_pid", lambda *args, **kwargs: None)
    monkeypatch.setattr(safety, "validate_port_owner", lambda *args, **kwargs: None)
    monkeypatch.setattr(safety, "listening_pids", lambda observed_port: (proxy_pid,) if observed_port == port else ())
    monkeypatch.setattr(safety, "is_descendant_of", lambda child, parent: False)
    monkeypatch.setattr(qualification.os, "getpgid", lambda pid: supervisor_pid if pid == supervisor_pid else proxy_pid)
    monkeypatch.setattr(qualification.os, "killpg", lambda pid, sig: signalled.append((pid, sig)))

    with pytest.raises(qualification.QualificationLeaseError, match="lease lineage is unproven"):
        qualification._validated_signal(
            record, tmp_path / "processes.json", tmp_path / "ports.json", signal.SIGTERM, lease_id
        )

    assert signalled == []

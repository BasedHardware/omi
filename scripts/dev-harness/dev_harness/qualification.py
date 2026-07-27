"""Ownership-safe lifecycle primitives for macOS qualification stacks."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import secrets
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, TextIO

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from . import config, safety

LEASE_SCHEMA_VERSION = 1
LEASE_OWNER = "omi-desktop-qualification"
DEFAULT_RETAINED_RUNS = 3
DEFAULT_RETENTION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
COMPLETION_FILENAME = "qualification-completed.json"
QUARANTINE_DIRNAME = "quarantined-lease-pointers"
FAULT_STATE_DIRNAME = "fault"
STOP_PHASES: tuple[tuple[signal.Signals, float], ...] = tuple(
    (signal.Signals(value), wait_seconds)
    for name, wait_seconds in (("SIGINT", 8), ("SIGTERM", 5), ("SIGKILL", 2))
    if (value := getattr(signal, name, None)) is not None
)


class QualificationLeaseError(RuntimeError):
    """A lease is active or cannot be proven safe to reclaim."""


def _real(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def lease_root_from_env(env: dict[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    configured = source.get("OMI_QUALIFICATION_LEASE_ROOT", "").strip()
    return _real(Path(configured)) if configured else _real(Path(tempfile.gettempdir()) / LEASE_OWNER)


def _validate_root(root: Path, repo_root: Path) -> Path:
    resolved = _real(root)
    if resolved in {Path(resolved.anchor), _real(Path.home()), _real(repo_root)}:
        raise QualificationLeaseError(f"Unsafe qualification lease root: {resolved}")
    if resolved in _real(repo_root).parents:
        raise QualificationLeaseError(f"Qualification lease root cannot parent the source worktree: {resolved}")
    return resolved


def _acquire_file_lock(lock_file: TextIO) -> None:
    if os.name != "nt":
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        return

    while True:
        lock_file.seek(0)
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            time.sleep(0.05)


def _release_file_lock(lock_file: TextIO) -> None:
    if os.name != "nt":
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return

    lock_file.seek(0)
    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def _locked(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".qualification-lease.lock").open("a+", encoding="utf-8") as lock_file:
        _acquire_file_lock(lock_file)
        try:
            yield
        finally:
            _release_file_lock(lock_file)


def _lease_path(root: Path) -> Path:
    return root / "qualification-lease.json"


def _read_lease(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QualificationLeaseError(f"Invalid qualification lease at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise QualificationLeaseError(f"Invalid qualification lease at {path}")
    return payload


def _write_lease(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _quarantine_stale_lease_pointer(path: Path, root: Path, lease: dict[str, object]) -> Path:
    """Retire only a dead lease pointer when its state cannot prove safe cleanup.

    The active pointer is moved under the root lock to preserve its exact diagnostic
    contents. The associated state and logs remain untouched: without a valid
    ownership sentinel, neither deletion nor process signalling is authorized.
    """

    lease_id = safety.validate_instance_name(str(lease["lease_id"]))
    token_digest = hashlib.sha256(str(lease["token"]).encode("utf-8")).hexdigest()
    quarantine = root / QUARANTINE_DIRNAME
    quarantine.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = quarantine / f"{lease_id}-{int(time.time_ns())}-{token_digest}.json"
    if destination.exists():
        raise QualificationLeaseError(f"Refusing to overwrite quarantined qualification lease evidence: {destination}")
    path.replace(destination)
    destination.chmod(0o400)
    return destination


def _lease_provenance(lease: dict[str, object], root: Path) -> tuple[str, Path, Path, int, str]:
    if lease.get("schema_version") != LEASE_SCHEMA_VERSION or lease.get("owner") != LEASE_OWNER:
        raise QualificationLeaseError("Existing lease is not owned by the qualification harness")
    lease_id = safety.validate_instance_name(str(lease.get("lease_id", "")))
    state_root = _real(Path(str(lease.get("state_root", ""))))
    if state_root != _real(root / "state" / lease_id):
        raise QualificationLeaseError("Qualification lease state root does not match its recorded lease ID")
    repo_root = _real(Path(str(lease.get("repo_root", ""))))
    if not repo_root.is_dir():
        raise QualificationLeaseError("Qualification lease source worktree no longer exists")
    try:
        owner_pid = int(lease.get("owner_pid", -1))
    except (TypeError, ValueError) as exc:
        raise QualificationLeaseError("Qualification lease has an invalid owner PID") from exc
    token = str(lease.get("token", ""))
    if len(token) < 32:
        raise QualificationLeaseError("Qualification lease has an invalid ownership token")
    return lease_id, state_root, repo_root, owner_pid, token


def _load_records(path: Path, key: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationLeaseError(f"Cannot validate recorded qualification {key}: {exc}") from exc
    records = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise QualificationLeaseError(f"Invalid qualification {key} manifest")
    return records


def _posix_process_group_api() -> tuple[
    Callable[[int], int],
    Callable[[int, signal.Signals], None],
]:
    getpgid = getattr(os, "getpgid", None)
    killpg = getattr(os, "killpg", None)
    if not callable(getpgid) or not callable(killpg):
        raise QualificationLeaseError(
            "Qualification process-manifest cleanup requires POSIX process provenance; retaining lease state"
        )
    return getpgid, killpg


def _validated_owned_records(
    state_root: Path, repo_root: Path, lease_id: str, ownership_token: str
) -> tuple[list[dict[str, object]], Path, Path]:
    safety.read_and_validate_sentinel(state_root, repo_root=repo_root, instance=lease_id)
    process_manifest = state_root / "manifests" / "processes.json"
    port_manifest = state_root / "manifests" / "ports.json"
    if not process_manifest.exists() and not port_manifest.exists():
        # A cancellation can land immediately after acquire, before dev-up has
        # created any process records. There is no process to signal in that
        # state, and the sentinel still proves the directory is ours.
        return [], process_manifest, port_manifest
    if not process_manifest.is_file() or not port_manifest.is_file():
        raise QualificationLeaseError("Qualification lease is missing process or port provenance")
    records = _load_records(process_manifest, "processes")
    ports = _load_records(port_manifest, "ports")
    by_service = {(str(record.get("service")), int(record.get("pid", -1))): record for record in ports}
    validated: list[dict[str, object]] = []
    for record in records:
        service = str(record.get("service", ""))
        pid = int(record.get("pid", -1))
        marker = str(record.get("ownership_marker", ""))
        process_group = int(record.get("process_group", -1))
        expected_marker = f"omi-dev-harness:{lease_id}:{service}:{ownership_token}"
        if not service or marker != expected_marker:
            raise QualificationLeaseError("Qualification process marker does not match the recorded lease")
        if process_group != pid:
            raise QualificationLeaseError("Qualification process group does not match its recorded leader")
        port_record = by_service.get((service, pid))
        if port_record is None or int(port_record.get("port", -1)) != int(record.get("port", -2)):
            raise QualificationLeaseError("Qualification process has no matching recorded port provenance")
        if safety.process_exists(pid):
            getpgid, _killpg = _posix_process_group_api()
            safety.validate_owned_pid(pid, process_manifest=process_manifest, service=service)
            if getpgid(pid) != process_group:
                raise QualificationLeaseError("Qualification process is no longer in its recorded process group")
            safety.validate_port_owner(
                int(record["port"]),
                pid=pid,
                port_manifest=port_manifest,
                process_manifest=process_manifest,
                service=service,
            )
        validated.append(record)
    return validated, process_manifest, port_manifest


def _read_fault_metadata(path: Path) -> dict[str, str]:
    try:
        file_stat = path.stat()
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise QualificationLeaseError(f"Cannot validate qualification fault-inject state: {exc}") from exc
    if path.is_symlink() or not path.is_file() or file_stat.st_uid != os.getuid():
        raise QualificationLeaseError("Qualification fault-inject state is not an owner-controlled regular file")
    if stat.S_IMODE(file_stat.st_mode) & 0o077:
        raise QualificationLeaseError("Qualification fault-inject state is not owner-only")
    fields: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            raise QualificationLeaseError("Qualification fault-inject state is malformed")
        key, value = line.split("=", 1)
        if not key or key in fields:
            raise QualificationLeaseError("Qualification fault-inject state is malformed")
        fields[key] = value
    return fields


def _validated_fault_record(state_root: Path, ownership_token: str) -> dict[str, object] | None:
    """Authenticate the optional fault listener rooted inside this exact lease."""

    fault_state = state_root / FAULT_STATE_DIRNAME
    if not fault_state.exists():
        return None
    if os.name == "nt":
        raise QualificationLeaseError(
            "Qualification fault-inject cleanup requires POSIX process provenance; retaining lease state"
        )
    if (
        fault_state.is_symlink()
        or not fault_state.is_dir()
        or _real(fault_state) != _real(state_root) / FAULT_STATE_DIRNAME
    ):
        raise QualificationLeaseError("Qualification fault-inject state escaped its recorded lease root")
    try:
        directory_stat = fault_state.stat()
    except OSError as exc:
        raise QualificationLeaseError(f"Cannot validate qualification fault-inject state: {exc}") from exc
    if directory_stat.st_uid != os.getuid() or stat.S_IMODE(directory_stat.st_mode) & 0o077:
        raise QualificationLeaseError("Qualification fault-inject state directory is not owner-only")

    pid_path, meta_path = fault_state / "pid", fault_state / "meta"
    if not pid_path.exists() and not meta_path.exists():
        return None
    if not pid_path.is_file() or not meta_path.is_file():
        raise QualificationLeaseError("Qualification fault-inject state is incomplete")
    fields = _read_fault_metadata(meta_path)
    try:
        pid_stat = pid_path.stat()
        pid_text = pid_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise QualificationLeaseError(f"Cannot validate qualification fault-inject PID: {exc}") from exc
    if pid_path.is_symlink() or pid_stat.st_uid != os.getuid() or stat.S_IMODE(pid_stat.st_mode) & 0o077:
        raise QualificationLeaseError("Qualification fault-inject PID is not owner-only")
    try:
        pid = int(pid_text)
        recorded_pid = int(fields.get("pid", "-1"))
        process_group = int(fields.get("pgid", "-1"))
        port = int(fields.get("port", "-1"))
    except ValueError as exc:
        raise QualificationLeaseError("Qualification fault-inject state has invalid numeric provenance") from exc
    if pid <= 0 or recorded_pid != pid or process_group != pid:
        raise QualificationLeaseError("Qualification fault-inject process lineage is invalid")
    if not 1 <= port <= 65535:
        raise QualificationLeaseError("Qualification fault-inject port is invalid")
    if fields.get("token") != ownership_token:
        raise QualificationLeaseError("Qualification fault-inject token does not match the active lease")
    if fields.get("url") != f"http://127.0.0.1:{port}":
        raise QualificationLeaseError("Qualification fault-inject endpoint is not the recorded loopback port")

    record: dict[str, object] = {
        "service": "fault-inject",
        "pid": pid,
        "process_group": process_group,
        "port": port,
        "ownership_marker": f"omi-fault-inject:{ownership_token}",
    }
    _validate_fault_process(record)
    return record


def _validate_fault_process(record: dict[str, object]) -> tuple[bool, tuple[int, ...]]:
    """Re-prove the exact token-bound fault process and its current listener."""

    pid = int(record["pid"])
    process_group = int(record["process_group"])
    port = int(record["port"])
    marker = str(record["ownership_marker"])
    listeners = safety.listening_pids(port)
    alive = safety.process_exists(pid)
    if listeners and listeners != (pid,):
        raise QualificationLeaseError(
            "Refusing to signal a qualification fault-inject listener whose lease lineage is unproven"
        )
    if alive:
        if marker not in safety.command_line_for_pid(pid) or os.getpgid(pid) != process_group or process_group != pid:
            raise QualificationLeaseError(
                "Refusing to signal a qualification fault-inject process whose lease lineage is unproven"
            )
    elif listeners:
        raise QualificationLeaseError(
            "Refusing to signal a qualification fault-inject listener whose lease lineage is unproven"
        )
    return alive, listeners


def _stop_owned_fault_record(record: dict[str, object] | None) -> None:
    if record is None:
        return
    process_group = int(record["process_group"])
    service, port = str(record["service"]), int(record["port"])
    for sig, wait_seconds in STOP_PHASES:
        alive, listeners = _validate_fault_process(record)
        if not alive and not listeners:
            return
        if alive:
            try:
                os.killpg(process_group, sig)
            except (ProcessLookupError, PermissionError) as exc:
                raise QualificationLeaseError(
                    f"Cannot signal recorded qualification fault-inject group: {exc}"
                ) from exc
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            alive, listeners = _validate_fault_process(record)
            if not alive and not listeners:
                return
            time.sleep(0.2)
    alive, listeners = _validate_fault_process(record)
    if listeners:
        raise QualificationLeaseError(
            f"Qualification fault-inject port still open after cleanup; retaining incomplete lease state: "
            f"{service}:{port} (listeners {','.join(map(str, listeners))})"
        )
    if alive:
        raise QualificationLeaseError(
            f"Qualification fault-inject process still running after cleanup; retaining incomplete lease state: "
            f"{service} pid={record['pid']}"
        )


def _write_fault_preflight_report(
    path: Path,
    *,
    lease_id: str,
    status: str,
    port: int | None,
    failure_reason: str | None = None,
    detail: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "gate": "fault-listener-provenance-cleanup",
        "classification": "runner-hygiene-cleanup",
        "lease_id": lease_id,
        "status": status,
        "port": port,
        "failure_reason": failure_reason,
    }
    if detail:
        payload["detail"] = detail
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _write_lease(path, payload)
    path.chmod(0o600)


def _fault_preflight_failure_reason(exc: Exception) -> str:
    detail = str(exc).lower()
    if "lineage is unproven" in detail or "ownership changed" in detail:
        return "unproven-listener-lineage"
    if "token" in detail:
        return "lease-token-mismatch"
    if "port still open" in detail or "process still running" in detail:
        return "owned-listener-cleanup-incomplete"
    if "state" in detail or "pid" in detail:
        return "invalid-listener-provenance"
    return "host-prerequisite-unmet"


def preflight_fault_cleanup(*, repo_root: Path, lease_id: str, token: str, result_path: Path) -> dict[str, object]:
    """Prove and reclaim a disposable listener before expensive qualification."""

    root = _validate_root(lease_root_from_env(), repo_root)
    observed_port: int | None = None
    try:
        with _locked(root):
            path = _lease_path(root)
            lease = _read_lease(path)
            if lease is None:
                raise QualificationLeaseError("Qualification fault-listener preflight requires an active lease")
            recorded_id, state_root, recorded_repo, _owner_pid, recorded_token = _lease_provenance(lease, root)
            if recorded_id != lease_id or recorded_token != token:
                raise QualificationLeaseError("Qualification lease token does not match the active lease")
            if recorded_repo != _real(repo_root):
                raise QualificationLeaseError("Qualification lease belongs to a different source worktree")
            fault_record = _validated_fault_record(state_root, recorded_token)
            if fault_record is None:
                raise QualificationLeaseError("Qualification fault-listener preflight found no recorded listener")
            observed_port = int(fault_record["port"])
            _stop_owned_fault_record(fault_record)
            alive, listeners = _validate_fault_process(fault_record)
            if alive or listeners:
                raise QualificationLeaseError(
                    "Qualification fault-listener preflight could not prove cleanup completion"
                )
            fault_state = state_root / FAULT_STATE_DIRNAME
            for evidence in (fault_state / "pid", fault_state / "meta"):
                evidence.unlink()
            report = {
                "schema_version": 1,
                "gate": "fault-listener-provenance-cleanup",
                "classification": "runner-hygiene-cleanup",
                "lease_id": lease_id,
                "status": "passed",
                "port": observed_port,
                "failure_reason": None,
            }
            _write_fault_preflight_report(
                result_path,
                lease_id=lease_id,
                status="passed",
                port=observed_port,
            )
            return report
    except (QualificationLeaseError, safety.SafetyError) as exc:
        _write_fault_preflight_report(
            result_path,
            lease_id=lease_id,
            status="failed",
            port=observed_port,
            failure_reason=_fault_preflight_failure_reason(exc),
            detail=str(exc),
        )
        raise


def _is_exact_typesense_docker_proxy(record: dict[str, object], lease_id: str | None) -> bool:
    """Prove Docker's external port proxy belongs to this exact lease container."""

    if lease_id is None or str(record.get("service", "")) != "typesense":
        return False
    port = int(str(record["port"]))
    container = f"omi-dev-harness-{lease_id}-typesense"
    expected_prefix = [
        "docker",
        "run",
        "--rm",
        "--name",
        container,
        "-p",
        f"127.0.0.1:{port}:{config.TYPESENSE_CONTAINER_PORT}",
    ]
    command = record.get("command")
    if not isinstance(command, list) or command[: len(expected_prefix)] != expected_prefix:
        return False
    try:
        inspected = subprocess.run(
            ["docker", "inspect", "--format", "{{json .}}", container],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            check=False,
        )
        payload = json.loads(inspected.stdout) if inspected.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or payload.get("Name") != f"/{container}":
        return False
    if not isinstance(payload.get("State"), dict) or payload["State"].get("Running") is not True:
        return False
    network = payload.get("NetworkSettings")
    ports = network.get("Ports") if isinstance(network, dict) else None
    bindings = ports.get(f"{config.TYPESENSE_CONTAINER_PORT}/tcp") if isinstance(ports, dict) else None
    return isinstance(bindings, list) and any(
        isinstance(binding, dict)
        and binding.get("HostIp") == "127.0.0.1"
        and binding.get("HostPort") == str(port)
        for binding in bindings
    )


def _validated_signal(
    record: dict[str, object], process_manifest: Path, port_manifest: Path, sig: signal.Signals, lease_id: str | None = None
) -> None:
    """Signal only a current supervisor whose listener children still prove lease lineage."""

    pid = int(record["pid"])
    service = str(record["service"])
    process_group = int(record["process_group"])
    port = int(record["port"])
    getpgid, killpg = _posix_process_group_api()
    safety.validate_owned_pid(pid, process_manifest=process_manifest, service=service)
    if getpgid(pid) != process_group or process_group != pid:
        raise QualificationLeaseError("Refusing to signal a qualification process group whose ownership changed")
    safety.validate_port_owner(
        port, pid=pid, port_manifest=port_manifest, process_manifest=None, service=service
    )
    listeners = safety.listening_pids(port)
    if listeners and not _is_exact_typesense_docker_proxy(record, lease_id):
        for listener_pid in listeners:
            if getpgid(listener_pid) != process_group or not safety.is_descendant_of(listener_pid, pid):
                raise QualificationLeaseError("Refusing to signal a qualification listener whose lease lineage is unproven")
    try:
        killpg(process_group, sig)
    except (ProcessLookupError, PermissionError) as exc:
        raise QualificationLeaseError(f"Cannot signal recorded qualification process group: {exc}") from exc


def _open_recorded_ports(records: list[dict[str, object]]) -> list[tuple[str, int, tuple[int, ...]]]:
    """Re-read every lease port from the OS, never infer closure from supervisor exit."""

    open_ports: list[tuple[str, int, tuple[int, ...]]] = []
    for record in records:
        service, port = str(record["service"]), int(record["port"])
        listeners = safety.listening_pids(port)
        if listeners:
            open_ports.append((service, port, listeners))
    return open_ports


def _wait_for_ports_to_close(records: list[dict[str, object]], seconds: float) -> list[tuple[str, int, tuple[int, ...]]]:
    deadline = time.monotonic() + seconds
    open_ports = _open_recorded_ports(records)
    while open_ports and time.monotonic() < deadline:
        time.sleep(0.2)
        open_ports = _open_recorded_ports(records)
    return open_ports


def _stop_owned_records(
    records: list[dict[str, object]], process_manifest: Path, port_manifest: Path, lease_id: str
) -> None:
    for sig, wait_seconds in STOP_PHASES:
        for record in records:
            pid = int(record["pid"])
            if safety.process_exists(pid):
                _validated_signal(record, process_manifest, port_manifest, sig, lease_id)
        open_ports = _wait_for_ports_to_close(records, wait_seconds)
        if not open_ports:
            return
    details = ", ".join(f"{service}:{port} (listeners {','.join(map(str, pids))})" for service, port, pids in open_ports)
    raise QualificationLeaseError(f"Qualification port still open after cleanup; retaining incomplete lease state: {details}")


def _safe_remove_state(state_root: Path, repo_root: Path, lease_id: str) -> None:
    safety.read_and_validate_sentinel(state_root, repo_root=repo_root, instance=lease_id)
    safety.validate_destructive_target(state_root, state_root=state_root, repo_root=repo_root)
    shutil.rmtree(state_root)


def _completion_path(state_root: Path) -> Path:
    return state_root / COMPLETION_FILENAME


def _mark_completed(state_root: Path, repo_root: Path, lease_id: str, token: str) -> None:
    safety.read_and_validate_sentinel(state_root, repo_root=repo_root, instance=lease_id)
    _write_lease(
        _completion_path(state_root),
        {
            "schema_version": LEASE_SCHEMA_VERSION,
            "owner": LEASE_OWNER,
            "lease_id": lease_id,
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "completed_at": int(time.time()),
        },
    )


def _completed_at(state_root: Path, lease_id: str) -> int | None:
    completion = _read_lease(_completion_path(state_root))
    if completion is None:
        return None
    try:
        completed_at = int(completion.get("completed_at", -1))
    except (TypeError, ValueError):
        return None
    if (
        completion.get("schema_version") != LEASE_SCHEMA_VERSION
        or completion.get("owner") != LEASE_OWNER
        or completion.get("lease_id") != lease_id
        or completed_at <= 0
    ):
        return None
    return completed_at


def _prune(root: Path, *, keep_lease_ids: set[str], retained_runs: int, retention_age_seconds: int) -> None:
    if retained_runs < 0:
        raise QualificationLeaseError("Qualification retention must be non-negative")
    if retention_age_seconds < 0:
        raise QualificationLeaseError("Qualification retention age must be non-negative")
    state_base, logs_base = root / "state", root / "logs"
    entries = [entry for entry in state_base.iterdir() if entry.is_dir()] if state_base.is_dir() else []
    eligible: list[tuple[float, str, Path, Path]] = []
    for state_root in entries:
        lease_id = state_root.name
        try:
            sentinel = safety.read_and_validate_sentinel(state_root, instance=lease_id)
            repo_root = _real(Path(str(sentinel.get("repo_root", ""))))
            completed_at = _completed_at(state_root, lease_id)
        except safety.SafetyError:
            continue
        if completed_at is not None:
            eligible.append((float(completed_at), lease_id, state_root, repo_root))
    eligible.sort(reverse=True)
    kept = 0
    now = time.time()
    for completed_at, lease_id, state_root, repo_root in eligible:
        if lease_id in keep_lease_ids:
            continue
        if now - completed_at <= retention_age_seconds and kept < retained_runs:
            kept += 1
            continue
        _safe_remove_state(state_root, repo_root, lease_id)
        log_dir = logs_base / lease_id
        if log_dir.is_dir():
            shutil.rmtree(log_dir)


def acquire(
    *, repo_root: Path, lease_id: str, owner_pid: int, port_offset: int, retained_runs: int = DEFAULT_RETAINED_RUNS,
    retention_age_seconds: int = DEFAULT_RETENTION_MAX_AGE_SECONDS,
) -> dict[str, object]:
    root = _validate_root(lease_root_from_env(), repo_root)
    lease_id = safety.validate_instance_name(lease_id)
    if owner_pid <= 0 or not safety.process_exists(owner_pid):
        raise QualificationLeaseError(f"Qualification lease owner PID is not running: {owner_pid}")
    if port_offset < 0:
        raise QualificationLeaseError("Qualification port offset must be non-negative")
    with _locked(root):
        path = _lease_path(root)
        existing = _read_lease(path)
        if existing is not None:
            old_id, old_state, old_repo, old_owner, old_token = _lease_provenance(existing, root)
            if safety.process_exists(old_owner):
                raise QualificationLeaseError(
                    f"Qualification lease {old_id!r} is held by live PID {old_owner}; refusing concurrent stack use"
                )
            try:
                records, process_manifest, port_manifest = _validated_owned_records(old_state, old_repo, old_id, old_token)
                fault_record = _validated_fault_record(old_state, old_token)
                _stop_owned_fault_record(fault_record)
                _stop_owned_records(records, process_manifest, port_manifest, old_id)
                _safe_remove_state(old_state, old_repo, old_id)
            except (safety.SafetyError, QualificationLeaseError):
                # A dead owner cannot keep the admission pointer indefinitely.
                # If any provenance or listener-lineage check fails, preserve the
                # state/log evidence and retire only the pointer. In particular,
                # do not retry or broaden process cleanup after a refused signal.
                _quarantine_stale_lease_pointer(path, root, existing)
            else:
                old_logs = root / "logs" / old_id
                if old_logs.is_dir():
                    shutil.rmtree(old_logs)
                path.unlink(missing_ok=True)

        state_root = _real(root / "state" / lease_id)
        if state_root.exists():
            try:
                sentinel = safety.read_and_validate_sentinel(state_root, instance=lease_id)
                previous_repo = _real(Path(str(sentinel.get("repo_root", ""))))
                _safe_remove_state(state_root, previous_repo, lease_id)
            except safety.SafetyError as exc:
                raise QualificationLeaseError(f"Refusing to replace unproven qualification state {state_root}: {exc}") from exc
        safety.create_state_layout(repo_root, lease_id, {"OMI_LOCAL_STATE_ROOT": str(root / "state")})
        log_dir = root / "logs" / lease_id
        log_dir.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(24)
        lease = {
            "schema_version": LEASE_SCHEMA_VERSION,
            "owner": LEASE_OWNER,
            "lease_id": lease_id,
            "owner_pid": owner_pid,
            "repo_root": str(_real(repo_root)),
            "state_root": str(state_root),
            "port_offset": port_offset,
            "token": token,
            "created_at": int(time.time()),
        }
        _write_lease(path, lease)
        _prune(
            root,
            keep_lease_ids={lease_id},
            retained_runs=retained_runs,
            retention_age_seconds=retention_age_seconds,
        )
        return {**lease, "lease_root": str(root), "log_dir": str(log_dir)}


def release(
    *, repo_root: Path, lease_id: str, token: str, retained_runs: int = DEFAULT_RETAINED_RUNS,
    retention_age_seconds: int = DEFAULT_RETENTION_MAX_AGE_SECONDS,
) -> None:
    root = _validate_root(lease_root_from_env(), repo_root)
    with _locked(root):
        path = _lease_path(root)
        lease = _read_lease(path)
        if lease is None:
            return
        recorded_id, state_root, recorded_repo, _owner_pid, recorded_token = _lease_provenance(lease, root)
        if recorded_id != lease_id or str(lease.get("token", "")) != token:
            raise QualificationLeaseError("Qualification lease token does not match the active lease")
        if recorded_repo != _real(repo_root):
            raise QualificationLeaseError("Qualification lease belongs to a different source worktree")
        records, process_manifest, port_manifest = _validated_owned_records(
            state_root, recorded_repo, recorded_id, recorded_token
        )
        fault_record = _validated_fault_record(state_root, recorded_token)
        _stop_owned_fault_record(fault_record)
        _stop_owned_records(records, process_manifest, port_manifest, recorded_id)
        path.unlink(missing_ok=True)
        _mark_completed(state_root, recorded_repo, recorded_id, recorded_token)
        _prune(
            root,
            keep_lease_ids=set(),
            retained_runs=retained_runs,
            retention_age_seconds=retention_age_seconds,
        )

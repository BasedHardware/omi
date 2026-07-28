# Post-#10764 source bump: keep this file on the releasable desktop path after changelog exemption.
#!/usr/bin/env python3
"""Ownership-scoped self-clean and capacity gate for the trusted M1 runner."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import plistlib
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
DEV_HARNESS_ROOT = REPO_ROOT / "scripts" / "dev-harness"
sys.path.insert(0, str(DEV_HARNESS_ROOT))

from dev_harness import qualification, safety  # noqa: E402

RUN_STAGE_RE = re.compile(r"^[0-9]+-[1-9][0-9]*$")
SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FAULT_TEMP_RE = re.compile(r"^omi-fault-owned-app\.[A-Za-z0-9]+$")
FAULT_BUNDLE_RE = re.compile(r"^omi-fault-[a-z0-9][a-z0-9-]{0,79}$")
RUN_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
FAULT_RECORD = "fault-app.json"
KNOWN_PROCESS_MARKERS = (
    "omi-fault-",
    "desktop-core-harness.sh --fault-suite",
    "qualify-desktop-beta.sh",
    "pre-tag-readiness.sh",
)


class HygieneError(RuntimeError):
    """Runner residue cannot be classified safely."""


@dataclass(frozen=True)
class ProcessRecord:
    pid: int
    process_group: int
    process_start: str
    command: str


@dataclass(frozen=True)
class FaultAppTarget:
    record_path: Path
    pid: int
    process_start: str
    command_sha256: str
    run_token: str
    bundle: str
    bundle_id: str
    app_path: Path
    executable_path: Path
    automation_port: int


def _load_cache_module() -> ModuleType:
    path = SCRIPT_DIR / "qualification-cache-reclaim.py"
    spec = importlib.util.spec_from_file_location("qualification_cache_reclaim_for_runner_hygiene", path)
    if spec is None or spec.loader is None:
        raise HygieneError("qualification cache reclaim authority cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CACHE = _load_cache_module()


def _owned_directory(path: Path, *, private: bool) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise HygieneError(f"cannot inspect owned directory {path}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise HygieneError(f"runner hygiene root is not a real directory: {path}")
    if info.st_uid != os.getuid():
        raise HygieneError(f"runner hygiene root is owned by another user: {path}")
    if private and stat.S_IMODE(info.st_mode) & 0o077:
        raise HygieneError(f"runner hygiene root is not owner-only: {path}")
    return info


def _trusted_temp_directory(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise HygieneError(f"cannot inspect temporary search root {path}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise HygieneError(f"temporary search root is not a real directory: {path}")
    if info.st_uid == os.getuid():
        return info
    if info.st_uid == 0 and stat.S_IMODE(info.st_mode) & stat.S_ISVTX:
        return info
    raise HygieneError(f"temporary search root is neither user-owned nor root-owned sticky: {path}")


def _owned_json(path: Path) -> dict[str, object]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise HygieneError(f"cannot inspect ownership record {path}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise HygieneError(f"ownership record is not an owned regular file: {path}")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise HygieneError(f"ownership record is not owner-only: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HygieneError(f"ownership record is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise HygieneError(f"ownership record is not a JSON object: {path}")
    return payload


def process_snapshot() -> list[ProcessRecord]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,pgid=,lstart=,command="],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HygieneError("cannot inspect runner processes") from exc
    records: list[ProcessRecord] = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 7)
        if len(fields) != 8 or not fields[0].isdigit() or not fields[1].isdigit():
            continue
        records.append(
            ProcessRecord(
                pid=int(fields[0]),
                process_group=int(fields[1]),
                process_start=" ".join(fields[2:7]),
                command=fields[7],
            )
        )
    return records


def _known_process_count(processes: Iterable[ProcessRecord]) -> int:
    return sum(
        1
        for process in processes
        if process.pid != os.getpid()
        and "qualification-runner-self-clean.py" not in process.command
        and any(marker in process.command for marker in KNOWN_PROCESS_MARKERS)
    )


def _validate_fault_app_target(
    record_path: Path,
    processes: dict[int, ProcessRecord],
) -> tuple[FaultAppTarget, ProcessRecord | None]:
    payload = _owned_json(record_path)
    bundle = payload.get("bundle")
    run_token = payload.get("run_token")
    bundle_id = payload.get("bundle_id")
    app_path_value = payload.get("app_path")
    executable_value = payload.get("executable_path")
    process_start = payload.get("process_start")
    command_sha256 = payload.get("command_sha256")
    try:
        pid = int(payload.get("launch_pid", -1))
        automation_port = int(payload.get("automation_port", -1))
    except (TypeError, ValueError) as exc:
        raise HygieneError(f"fault app record has invalid numeric provenance: {record_path}") from exc
    if (
        payload.get("schema_version") != 2
        or not isinstance(bundle, str)
        or not FAULT_BUNDLE_RE.fullmatch(bundle)
        or not isinstance(run_token, str)
        or not RUN_TOKEN_RE.fullmatch(run_token)
        or bundle_id != f"com.omi.{bundle}"
        or app_path_value != f"/Applications/{bundle}.app"
        or executable_value != f"/Applications/{bundle}.app/Contents/MacOS/Omi Computer"
        or not isinstance(process_start, str)
        or not process_start
        or not isinstance(command_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", command_sha256)
        or pid <= 0
        or not 1 <= automation_port <= 65535
        or payload.get("launch_transport") not in {"open", "direct"}
    ):
        raise HygieneError(f"fault app record does not prove a disposable bundle: {record_path}")
    target = FaultAppTarget(
        record_path=record_path,
        pid=pid,
        process_start=process_start,
        command_sha256=command_sha256,
        run_token=run_token,
        bundle=bundle,
        bundle_id=str(bundle_id),
        app_path=Path(str(app_path_value)),
        executable_path=Path(str(executable_value)),
        automation_port=automation_port,
    )
    process = processes.get(pid)
    if process is None:
        return target, None
    token_argument = f"--omi-launch-token={run_token}"
    if (
        process.process_start != process_start
        or str(target.executable_path) not in process.command
        or token_argument not in process.command
        or hashlib.sha256(process.command.encode()).hexdigest() != command_sha256
    ):
        raise HygieneError(f"fault app PID no longer matches its launch capability: {record_path}")
    return target, process


def _iter_fault_records_under(root: Path, *, max_depth: int) -> Iterable[Path]:
    if not root.exists():
        return
    _owned_directory(root, private=False)
    root_depth = len(root.parts)
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        safe_directories: list[str] = []
        for name in directories:
            candidate = current_path / name
            try:
                info = candidate.lstat()
            except OSError:
                continue
            if not stat.S_ISLNK(info.st_mode) and stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid():
                safe_directories.append(name)
        directories[:] = safe_directories if depth < max_depth else []
        if FAULT_RECORD in files:
            yield current_path / FAULT_RECORD


def discover_fault_records(cache_root: Path, stage_root: Path, fault_temp_root: Path) -> list[Path]:
    roots: list[Path] = []
    if cache_root.exists():
        _owned_directory(cache_root, private=False)
        for entry in cache_root.iterdir():
            if SOURCE_SHA_RE.fullmatch(entry.name) and entry.is_dir() and not entry.is_symlink():
                roots.append(entry / "source" / "desktop" / "macos" / ".harness" / "desktop-core")
    if stage_root.exists():
        _owned_directory(stage_root, private=False)
        for entry in stage_root.iterdir():
            if RUN_STAGE_RE.fullmatch(entry.name) and entry.is_dir() and not entry.is_symlink():
                roots.append(entry / "source" / "desktop" / "macos" / ".harness" / "desktop-core")
    if fault_temp_root.exists():
        _trusted_temp_directory(fault_temp_root)
        for entry in fault_temp_root.iterdir():
            if FAULT_TEMP_RE.fullmatch(entry.name) and entry.is_dir() and not entry.is_symlink():
                roots.append(entry)
    records: set[Path] = set()
    for root in roots:
        records.update(_iter_fault_records_under(root, max_depth=6))
    return sorted(records)


def _signal_fault_app(
    target: FaultAppTarget,
    *,
    snapshot: Callable[[], list[ProcessRecord]] = process_snapshot,
) -> None:
    for sig, timeout_seconds in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 2.0)):
        processes = {process.pid: process for process in snapshot()}
        _target, process = _validate_fault_app_target(target.record_path, processes)
        if process is None:
            return
        try:
            os.kill(target.pid, sig)
        except (ProcessLookupError, PermissionError) as exc:
            raise HygieneError(f"cannot signal exact recorded fault app PID {target.pid}: {exc}") from exc
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            processes = {candidate.pid: candidate for candidate in snapshot()}
            _target, process = _validate_fault_app_target(target.record_path, processes)
            if process is None:
                return
            time.sleep(0.1)
    raise HygieneError(f"recorded fault app PID {target.pid} did not stop")


def _remove_fault_bundle(target: FaultAppTarget, processes: Iterable[ProcessRecord]) -> str:
    app = target.app_path
    if not app.exists():
        return "absent"
    info = _owned_directory(app, private=False)
    if info.st_uid != os.getuid() or app.parent != Path("/Applications"):
        raise HygieneError(f"fault app bundle escaped the disposable Applications boundary: {app}")
    plist_path = app / "Contents" / "Info.plist"
    executable = target.executable_path
    try:
        with plist_path.open("rb") as handle:
            plist = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise HygieneError(f"cannot validate disposable fault app bundle metadata: {app}") from exc
    if plist.get("CFBundleIdentifier") != target.bundle_id or not executable.is_file():
        raise HygieneError(f"fault app bundle identity does not match its launch record: {app}")
    if any(str(app) in process.command for process in processes):
        return "preserved-live-reference"
    shutil.rmtree(app)
    return "removed"


def clean_fault_apps(
    record_paths: Iterable[Path],
    *,
    dry_run: bool,
    snapshot: Callable[[], list[ProcessRecord]] = process_snapshot,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    seen_pids: dict[int, FaultAppTarget] = {}
    for record_path in record_paths:
        processes = {process.pid: process for process in snapshot()}
        target, process = _validate_fault_app_target(record_path, processes)
        previous = seen_pids.get(target.pid)
        if previous is not None and previous != target:
            raise HygieneError(f"conflicting fault app records claim PID {target.pid}")
        seen_pids[target.pid] = target
        action = "already-exited" if process is None else ("would-stop" if dry_run else "stopped")
        if process is not None and not dry_run:
            _signal_fault_app(target, snapshot=snapshot)
        bundle_action = "would-validate" if dry_run else _remove_fault_bundle(target, snapshot())
        results.append(
            {
                "record": str(record_path),
                "pid": target.pid,
                "bundle": target.bundle,
                "process_action": action,
                "bundle_action": bundle_action,
            }
        )
    return results


def clean_stages(
    stage_root: Path,
    *,
    current_run_id: str,
    processes: Iterable[ProcessRecord],
    dry_run: bool,
) -> list[dict[str, str]]:
    if not stage_root.exists():
        return []
    if stage_root.name != "desktop-beta-qualification":
        raise HygieneError(f"qualification stage root has an unexpected name: {stage_root}")
    _owned_directory(stage_root, private=False)
    results: list[dict[str, str]] = []
    commands = [process.command for process in processes]
    for entry in sorted(stage_root.iterdir(), key=lambda path: path.name):
        if not RUN_STAGE_RE.fullmatch(entry.name):
            continue
        _owned_directory(entry, private=True)
        if entry.name == current_run_id:
            results.append({"run_id": entry.name, "action": "preserved-current"})
            continue
        if any(str(entry) in command for command in commands):
            raise HygieneError(f"abandoned qualification stage still has a live process reference: {entry.name}")
        if not dry_run:
            shutil.rmtree(entry)
        results.append({"run_id": entry.name, "action": "would-remove" if dry_run else "removed"})
    return results


def _capacity_snapshot(path: Path) -> dict[str, int]:
    capacity = CACHE._capacity(path)
    return {
        "available_kib": capacity.available_kib,
        "available_inodes": capacity.available_inodes,
    }


def _dry_run_capacity(
    cache_root: Path,
    capacity_path: Path,
    *,
    minimum_free_kib: int,
    minimum_free_inodes: int,
    minimum_age_seconds: int,
    max_entries: int,
    max_reclaim_kib: int,
) -> dict[str, object]:
    cache_root_permissions = "absent"
    if cache_root.exists():
        info = _owned_directory(cache_root, private=False)
        cache_root_permissions = "would-tighten-to-0700" if stat.S_IMODE(info.st_mode) & 0o077 else "owner-only"
        CACHE._inventory(cache_root.expanduser().absolute())
    capacity = _capacity_snapshot(capacity_path)
    failures: list[str] = []
    if capacity["available_kib"] < minimum_free_kib:
        failures.append("insufficient-free-kib")
    if capacity["available_inodes"] < minimum_free_inodes:
        failures.append("insufficient-free-inodes")
    return {
        "schema_version": 2,
        "guard": "runner-capacity-preflight",
        "status": "failed" if failures else "passed",
        "failure_reasons": failures,
        "minimum_free_kib": minimum_free_kib,
        "minimum_free_inodes": minimum_free_inodes,
        **capacity,
        "before_reclaim_available_kib": capacity["available_kib"],
        "before_reclaim_available_inodes": capacity["available_inodes"],
        "reclaim": {
            "policy": "oldest-idle-capacity-first-v2",
            "mode": "dry-run",
            "cache_root_permissions": cache_root_permissions,
            "minimum_age_seconds": minimum_age_seconds,
            "max_entries": max_entries,
            "max_reclaim_kib": max_reclaim_kib,
            "deleted_entries": [],
            "dead_leases_removed": [],
            "reclaimed_kib": 0,
        },
    }


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temporary.replace(path)


def run(args: argparse.Namespace) -> dict[str, object]:
    before_processes = process_snapshot()
    before_capacity = _capacity_snapshot(args.capacity_path)
    errors: list[str] = []
    lease_result: dict[str, object] = {"status": "not-run"}
    fault_results: list[dict[str, object]] = []
    stage_results: list[dict[str, str]] = []
    capacity_result: dict[str, object] = {
        "status": "not-run",
        "failure_reasons": ["runner-hygiene-aborted"],
    }
    try:
        lease_result = qualification.reclaim_abandoned(
            lease_root=args.qualification_lease_root,
            repo_root=args.repo_root,
            dry_run=args.dry_run,
        )
        if lease_result["status"] == "active":
            raise HygieneError(
                f"qualification lease {lease_result['lease_id']} still has a live owner; refusing concurrent cleanup"
            )
        records = discover_fault_records(args.cache_root, args.stage_root, args.fault_temp_root)
        fault_results = clean_fault_apps(records, dry_run=args.dry_run)
        stage_results = clean_stages(
            args.stage_root,
            current_run_id=args.current_run_id,
            processes=process_snapshot(),
            dry_run=args.dry_run,
        )
        if args.dry_run:
            capacity_result = _dry_run_capacity(
                args.cache_root,
                args.capacity_path,
                minimum_free_kib=args.minimum_free_kib,
                minimum_free_inodes=args.minimum_free_inodes,
                minimum_age_seconds=args.minimum_age_seconds,
                max_entries=args.max_entries,
                max_reclaim_kib=args.max_reclaim_kib,
            )
        else:
            capacity_result = CACHE.reclaim(
                args.cache_root,
                qualification_lease_root=args.qualification_lease_root,
                capacity_path=args.capacity_path,
                minimum_free_kib=args.minimum_free_kib,
                minimum_free_inodes=args.minimum_free_inodes,
                minimum_age_seconds=args.minimum_age_seconds,
                max_entries=args.max_entries,
                max_reclaim_kib=args.max_reclaim_kib,
                process_probe=lambda: [
                    process
                    for process in CACHE._process_snapshot()
                    if "qualification-runner-self-clean.py" not in process.command
                    and "qualification-watchdog.py" not in process.command
                ],
            )
        if capacity_result["status"] != "passed":
            errors.extend(str(reason) for reason in capacity_result.get("failure_reasons", []))
    except (HygieneError, qualification.QualificationLeaseError, safety.SafetyError, CACHE.CacheSafetyError) as exc:
        errors.append(str(exc)[:500])
    after_processes = process_snapshot()
    after_capacity = _capacity_snapshot(args.capacity_path)
    report = {
        "schema_version": 1,
        "guard": "qualification-runner-self-clean",
        "mode": "dry-run" if args.dry_run else "clean",
        "status": "failed" if errors else "passed",
        "current_run_id": args.current_run_id,
        "production_bundles_touched": False,
        "before": {
            **before_capacity,
            "known_disposable_process_count": _known_process_count(before_processes),
        },
        "after": {
            **after_capacity,
            "known_disposable_process_count": _known_process_count(after_processes),
        },
        "cleanup": {
            "abandoned_lease": lease_result,
            "fault_apps": fault_results,
            "stages": stage_results,
        },
        "capacity": capacity_result,
        "errors": errors,
    }
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path.home() / "Library/Caches/OmiDesktop/qualification-swiftpm-v2",
    )
    parser.add_argument(
        "--qualification-lease-root",
        type=Path,
        default=Path(
            os.environ.get(
                "OMI_QUALIFICATION_LEASE_ROOT", f"{os.environ.get('TMPDIR', '/tmp')}/omi-desktop-qualification"
            )
        ),
    )
    parser.add_argument(
        "--stage-root",
        type=Path,
        default=Path(os.environ.get("RUNNER_TEMP", os.environ.get("TMPDIR", "/tmp"))) / "desktop-beta-qualification",
    )
    parser.add_argument(
        "--fault-temp-root",
        type=Path,
        default=Path(os.environ.get("TMPDIR", "/tmp")),
    )
    parser.add_argument(
        "--capacity-path",
        type=Path,
        default=Path(os.environ.get("RUNNER_TEMP", os.environ.get("TMPDIR", "/tmp"))),
    )
    parser.add_argument(
        "--current-run-id",
        default=f"{os.environ.get('GITHUB_RUN_ID', 'local')}-{os.environ.get('GITHUB_RUN_ATTEMPT', 'attempt')}",
    )
    parser.add_argument(
        "--minimum-free-kib",
        type=int,
        default=int(os.environ.get("OMI_QUALIFICATION_MINIMUM_FREE_KIB", "33554432")),
    )
    parser.add_argument(
        "--minimum-free-inodes",
        type=int,
        default=int(os.environ.get("OMI_QUALIFICATION_MINIMUM_FREE_INODES", "65536")),
    )
    parser.add_argument("--minimum-age-seconds", type=int, default=60 * 60)
    parser.add_argument("--max-entries", type=int, default=16)
    parser.add_argument("--max-reclaim-kib", type=int, default=128 * 1024 * 1024)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = run(args)
    _write_report(args.report, report)
    before = report["before"]
    after = report["after"]
    print(
        "qualification runner self-clean "
        f"{report['status']} mode={report['mode']} "
        f"processes={before['known_disposable_process_count']}->{after['known_disposable_process_count']} "
        f"free_kib={before['available_kib']}->{after['available_kib']} "
        f"report={args.report}"
    )
    if report["status"] != "passed":
        for error in report["errors"]:
            print(f"::error::qualification runner self-clean refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

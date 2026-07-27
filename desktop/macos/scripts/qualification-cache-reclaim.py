#!/usr/bin/env python3
"""Ownership-safe lifecycle and bounded reclaim for the M1 SwiftPM cache."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

CACHE_FORMAT = 2
CACHE_LEASE_OWNER = "omi-desktop-qualification-swiftpm"
CACHE_LEASE_SCHEMA_VERSION = 1
HARNESS_LEASE_OWNER = "omi-desktop-qualification"
HARNESS_LEASE_SCHEMA_VERSION = 1
HARNESS_SENTINEL = ".omi-dev-harness-owned.json"
RECLAIM_LOCK = ".reclaim.lock"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,95}$")
QUALIFIER_MARKER = "qualify-desktop-beta.sh"


class CacheSafetyError(RuntimeError):
    """Cache ownership or idleness could not be proven."""


@dataclass(frozen=True)
class Capacity:
    available_kib: int
    available_inodes: int


@dataclass(frozen=True)
class CacheEntry:
    source_sha: str
    path: Path
    last_used_at: int
    size_kib: int
    live_lease_owner_pids: frozenset[int]


@dataclass(frozen=True)
class ProcessRecord:
    pid: int
    command: str


def _lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as error:
        raise CacheSafetyError(f"cannot inspect {path.name}: {error}") from error


def _require_owned_directory(path: Path, *, private: bool) -> os.stat_result:
    info = _lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise CacheSafetyError(f"{path.name} is not an owned directory")
    if info.st_uid != os.getuid():
        raise CacheSafetyError(f"{path.name} is owned by a different user")
    if private and stat.S_IMODE(info.st_mode) & 0o077:
        raise CacheSafetyError(f"{path.name} is not owner-only")
    return info


def _require_owned_file(path: Path, *, private: bool) -> os.stat_result:
    info = _lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise CacheSafetyError(f"{path.name} is not an owned regular file")
    if info.st_uid != os.getuid():
        raise CacheSafetyError(f"{path.name} is owned by a different user")
    if private and stat.S_IMODE(info.st_mode) & 0o077:
        raise CacheSafetyError(f"{path.name} is not owner-only")
    return info


def _read_json(path: Path, *, private: bool = False) -> dict[str, object]:
    _require_owned_file(path, private=private)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CacheSafetyError(f"{path.name} is not valid JSON") from error
    if not isinstance(payload, dict):
        raise CacheSafetyError(f"{path.name} is not a JSON object")
    return payload


def _write_private_json(path: Path, payload: dict[str, object], *, exclusive: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
    except OSError as error:
        raise CacheSafetyError(f"cannot publish {path.name}: {error}") from error


def _validate_cache_root(cache_root: Path, *, create: bool) -> Path:
    root = cache_root.expanduser().absolute()
    if root in {Path(root.anchor), Path.home().resolve()}:
        raise CacheSafetyError("cache root is too broad")
    current = Path(root.anchor)
    for component in root.parts[1:]:
        current /= component
        if current.exists() and stat.S_ISLNK(_lstat(current).st_mode):
            raise CacheSafetyError(f"cache path has a symlinked component: {current.name}")
    if not root.exists():
        if not create:
            raise CacheSafetyError("cache root does not exist")
        root.mkdir(mode=0o700, parents=True)
    current = Path(root.anchor)
    for component in root.parts[1:]:
        current /= component
        if stat.S_ISLNK(_lstat(current).st_mode):
            raise CacheSafetyError(f"cache path has a symlinked component: {current.name}")
    _require_owned_directory(root, private=True)
    return root


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _process_snapshot() -> list[ProcessRecord]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise CacheSafetyError("cannot inspect live runner processes") from error
    records: list[ProcessRecord] = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 1)
        if not fields or not fields[0].isdigit():
            continue
        records.append(ProcessRecord(int(fields[0]), fields[1] if len(fields) == 2 else ""))
    return records


def _capacity(path: Path) -> Capacity:
    try:
        filesystem = os.statvfs(path)
    except OSError as error:
        raise CacheSafetyError("cannot inspect runner capacity") from error
    return Capacity(
        available_kib=(filesystem.f_bavail * filesystem.f_frsize) // 1024,
        available_inodes=filesystem.f_favail,
    )


def _tree_size_kib(path: Path) -> int:
    blocks = 0
    try:
        for root, directories, files in os.walk(path, topdown=True, followlinks=False):
            root_path = Path(root)
            blocks += root_path.lstat().st_blocks
            for name in directories:
                candidate = root_path / name
                blocks += candidate.lstat().st_blocks
            for name in files:
                blocks += (root_path / name).lstat().st_blocks
    except OSError as error:
        raise CacheSafetyError(f"cannot size cache entry {path.name}") from error
    return (blocks * 512 + 1023) // 1024


def _git_head(source: Path) -> str:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    try:
        result = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise CacheSafetyError(f"cannot validate source identity for {source.parent.name}") from error
    return result.stdout.strip()


def _cache_lease_records(entry: Path, source_sha: str) -> tuple[frozenset[int], set[int]]:
    lease_root = entry / ".leases"
    if not lease_root.exists():
        return frozenset(), set()
    _require_owned_directory(lease_root, private=True)
    owner_pids: set[int] = set()
    live_pids: set[int] = set()
    for lease_path in sorted(lease_root.iterdir(), key=lambda path: path.name):
        if lease_path.suffix != ".json" or not LEASE_ID_RE.fullmatch(lease_path.stem):
            raise CacheSafetyError(f"unrecognized cache lease record in {source_sha}")
        payload = _read_json(lease_path, private=True)
        required = {
            "schema_version": CACHE_LEASE_SCHEMA_VERSION,
            "owner": CACHE_LEASE_OWNER,
            "source_sha": source_sha,
            "lease_id": lease_path.stem,
        }
        if any(payload.get(key) != value for key, value in required.items()):
            raise CacheSafetyError(f"cache lease provenance mismatch in {source_sha}")
        try:
            owner_pid = int(payload.get("owner_pid", -1))
            created_at = int(payload.get("created_at", -1))
        except (TypeError, ValueError) as error:
            raise CacheSafetyError(f"cache lease has invalid numeric provenance in {source_sha}") from error
        token = payload.get("token")
        if owner_pid <= 0 or created_at <= 0 or not isinstance(token, str) or len(token) < 32:
            raise CacheSafetyError(f"cache lease is incomplete in {source_sha}")
        owner_pids.add(owner_pid)
        if _process_exists(owner_pid):
            live_pids.add(owner_pid)
    return frozenset(owner_pids), live_pids


def _validate_entry(
    entry: Path,
    *,
    git_head: Callable[[Path], str] = _git_head,
    size_probe: Callable[[Path], int] = _tree_size_kib,
) -> CacheEntry:
    source_sha = entry.name
    if not SHA_RE.fullmatch(source_sha):
        raise CacheSafetyError(f"unrecognized cache entry {source_sha}")
    entry_info = _require_owned_directory(entry, private=True)
    complete = entry / "complete"
    manifest_path = entry / "manifest.json"
    complete_info = _require_owned_file(complete, private=False)
    manifest_info = _require_owned_file(manifest_path, private=False)
    try:
        if complete.read_text(encoding="utf-8") != "complete\n":
            raise CacheSafetyError(f"incomplete cache entry {source_sha}")
    except OSError as error:
        raise CacheSafetyError(f"cannot read completion marker for {source_sha}") from error
    manifest = _read_json(manifest_path)
    if manifest.get("cache_format") != CACHE_FORMAT or manifest.get("source_sha") != source_sha:
        raise CacheSafetyError(f"cache provenance mismatch in {source_sha}")
    source = entry / "source"
    build = source / "desktop/macos/Desktop/.build"
    _require_owned_directory(source, private=True)
    _require_owned_directory(source / ".git", private=False)
    _require_owned_directory(build, private=True)
    if git_head(source) != source_sha:
        raise CacheSafetyError(f"source HEAD mismatch in {source_sha}")
    _owner_pids, live_pids = _cache_lease_records(entry, source_sha)
    last_used_at = int(max(entry_info.st_mtime, complete_info.st_mtime, manifest_info.st_mtime))
    return CacheEntry(source_sha, entry, last_used_at, size_probe(entry), frozenset(live_pids))


def _protected_harness_worktree(cache_root: Path, lease_root: Path) -> tuple[set[str], set[int]]:
    lease_root = lease_root.expanduser().resolve(strict=False)
    if not lease_root.exists():
        return set(), set()
    _require_owned_directory(lease_root, private=False)
    pointer = lease_root / "qualification-lease.json"
    if not pointer.exists():
        return set(), set()
    lease = _read_json(pointer)
    if lease.get("schema_version") != HARNESS_LEASE_SCHEMA_VERSION or lease.get("owner") != HARNESS_LEASE_OWNER:
        raise CacheSafetyError("qualification harness lease provenance is unknown")
    lease_id = lease.get("lease_id")
    repo_root_value = lease.get("repo_root")
    state_root_value = lease.get("state_root")
    token = lease.get("token")
    try:
        owner_pid = int(lease.get("owner_pid", -1))
    except (TypeError, ValueError) as error:
        raise CacheSafetyError("qualification harness lease owner PID is invalid") from error
    if (
        not isinstance(lease_id, str)
        or not LEASE_ID_RE.fullmatch(lease_id)
        or not isinstance(repo_root_value, str)
        or not isinstance(state_root_value, str)
        or not isinstance(token, str)
        or len(token) < 32
        or owner_pid <= 0
    ):
        raise CacheSafetyError("qualification harness lease is incomplete")
    state_root = Path(state_root_value).expanduser().resolve(strict=False)
    expected_state = (lease_root / "state" / lease_id).resolve(strict=False)
    if state_root != expected_state:
        raise CacheSafetyError("qualification harness state root is not lease-bound")
    _require_owned_directory(state_root, private=False)
    sentinel = _read_json(state_root / HARNESS_SENTINEL)
    repo_root = Path(repo_root_value).expanduser().resolve(strict=False)
    expected_sentinel = {
        "schema_version": 1,
        "owner": "omi-local-dev-harness",
        "instance": lease_id,
        "repo_root": str(repo_root),
    }
    if any(sentinel.get(key) != value for key, value in expected_sentinel.items()):
        raise CacheSafetyError("qualification harness sentinel does not bind its worktree")

    protected: set[str] = set()
    try:
        relative = repo_root.relative_to(cache_root)
    except ValueError:
        relative = None
    if relative is not None:
        parts = relative.parts
        if len(parts) != 2 or parts[1] != "source" or not SHA_RE.fullmatch(parts[0]):
            raise CacheSafetyError("qualification harness worktree is ambiguously rooted in the cache")
        protected.add(parts[0])
    return protected, {owner_pid}


def _inventory(cache_root: Path) -> list[CacheEntry]:
    entries: list[CacheEntry] = []
    for child in sorted(cache_root.iterdir(), key=lambda path: path.name):
        if child.name == RECLAIM_LOCK:
            continue
        if child.name.startswith(".") and child.name.endswith(".lock"):
            raise CacheSafetyError(f"cache operation lock is active: {child.name}")
        if child.name.startswith(".") and ".prepare." in child.name:
            raise CacheSafetyError(f"incomplete cache publication is present: {child.name}")
        if child.name.startswith("."):
            raise CacheSafetyError(f"unrecognized cache control state: {child.name}")
        entries.append(_validate_entry(child))
    return entries


def _process_protection(
    cache_root: Path,
    entries: Iterable[CacheEntry],
    represented_owner_pids: set[int],
    processes: Iterable[ProcessRecord],
) -> set[str]:
    protected: set[str] = set()
    current_pid = os.getpid()
    entry_paths = {entry.source_sha: str(entry.path) for entry in entries}
    cache_text = str(cache_root)
    for process in processes:
        if process.pid == current_pid:
            continue
        matched = {source_sha for source_sha, path in entry_paths.items() if path in process.command}
        if matched:
            protected.update(matched)
            represented_owner_pids.add(process.pid)
        elif cache_text in process.command:
            raise CacheSafetyError("a live process references an unrecognized cache path")
        if QUALIFIER_MARKER in process.command and process.pid not in represented_owner_pids:
            raise CacheSafetyError("a live qualifier has no authoritative cache or harness lease")
    return protected


def _lock_payload(lock: Path) -> dict[str, object]:
    payload = _read_json(lock / "owner.json", private=True)
    if payload.get("schema_version") != 1 or payload.get("owner") != CACHE_LEASE_OWNER:
        raise CacheSafetyError("cache reclaim lock provenance is unknown")
    try:
        owner_pid = int(payload.get("owner_pid", -1))
    except (TypeError, ValueError) as error:
        raise CacheSafetyError("cache reclaim lock owner PID is invalid") from error
    if owner_pid <= 0:
        raise CacheSafetyError("cache reclaim lock owner PID is invalid")
    return payload


def wait_for_reclaim(cache_root: Path, *, timeout_seconds: float) -> None:
    root = _validate_cache_root(cache_root, create=True)
    deadline = time.monotonic() + timeout_seconds
    lock = root / RECLAIM_LOCK
    while lock.exists():
        try:
            payload = _lock_payload(lock)
        except CacheSafetyError:
            if time.monotonic() < deadline and time.time() - _lstat(lock).st_mtime < 1:
                time.sleep(0.05)
                continue
            raise
        owner_pid = int(payload["owner_pid"])
        if not _process_exists(owner_pid):
            shutil.rmtree(lock)
            return
        if time.monotonic() >= deadline:
            raise CacheSafetyError("timed out waiting for active cache reclaim")
        time.sleep(0.05)


class _ReclaimLock:
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root
        self.path = cache_root / RECLAIM_LOCK
        self.acquired = False

    def __enter__(self) -> None:
        wait_for_reclaim(self.cache_root, timeout_seconds=0)
        try:
            self.path.mkdir(mode=0o700)
            self.acquired = True
            _write_private_json(
                self.path / "owner.json",
                {
                    "schema_version": 1,
                    "owner": CACHE_LEASE_OWNER,
                    "owner_pid": os.getpid(),
                    "created_at": int(time.time()),
                },
                exclusive=True,
            )
        except OSError as error:
            raise CacheSafetyError("another cache operation acquired the reclaim lock") from error

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        if self.acquired:
            shutil.rmtree(self.path)


def acquire_cache_lease(
    cache_root: Path,
    *,
    source_sha: str,
    lease_id: str,
    owner_pid: int,
    now: int | None = None,
) -> dict[str, object]:
    root = _validate_cache_root(cache_root, create=False)
    if not SHA_RE.fullmatch(source_sha) or not LEASE_ID_RE.fullmatch(lease_id):
        raise CacheSafetyError("cache lease identity is invalid")
    if not _process_exists(owner_pid):
        raise CacheSafetyError("cache lease owner PID is not running")
    entry = _validate_entry(root / source_sha)
    lease_root = entry.path / ".leases"
    if not lease_root.exists():
        lease_root.mkdir(mode=0o700)
    _require_owned_directory(lease_root, private=True)
    token = secrets.token_urlsafe(24)
    payload: dict[str, object] = {
        "schema_version": CACHE_LEASE_SCHEMA_VERSION,
        "owner": CACHE_LEASE_OWNER,
        "source_sha": source_sha,
        "lease_id": lease_id,
        "owner_pid": owner_pid,
        "created_at": int(time.time() if now is None else now),
        "token": token,
    }
    _write_private_json(lease_root / f"{lease_id}.json", payload, exclusive=True)
    os.utime(entry.path, None)
    return {**payload, "source": str(entry.path / "source")}


def release_cache_lease(
    cache_root: Path,
    *,
    source_sha: str,
    lease_id: str,
    owner_pid: int,
    token: str,
) -> None:
    root = _validate_cache_root(cache_root, create=False)
    if not SHA_RE.fullmatch(source_sha) or not LEASE_ID_RE.fullmatch(lease_id):
        raise CacheSafetyError("cache lease identity is invalid")
    entry = _validate_entry(root / source_sha)
    lease_path = entry.path / ".leases" / f"{lease_id}.json"
    if not lease_path.exists():
        return
    payload = _read_json(lease_path, private=True)
    expected = {
        "schema_version": CACHE_LEASE_SCHEMA_VERSION,
        "owner": CACHE_LEASE_OWNER,
        "source_sha": source_sha,
        "lease_id": lease_id,
        "owner_pid": owner_pid,
        "token": token,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise CacheSafetyError("cache lease release capability does not match")
    lease_path.unlink()
    os.utime(entry.path, None)


def reclaim(
    cache_root: Path,
    *,
    qualification_lease_root: Path,
    capacity_path: Path,
    minimum_free_kib: int,
    minimum_free_inodes: int,
    minimum_age_seconds: int,
    max_entries: int,
    max_reclaim_kib: int,
    now: int | None = None,
    capacity_probe: Callable[[Path], Capacity] = _capacity,
    process_probe: Callable[[], list[ProcessRecord]] = _process_snapshot,
) -> dict[str, object]:
    for name, value in (
        ("minimum_free_kib", minimum_free_kib),
        ("minimum_free_inodes", minimum_free_inodes),
        ("minimum_age_seconds", minimum_age_seconds),
        ("max_entries", max_entries),
        ("max_reclaim_kib", max_reclaim_kib),
    ):
        if value < 1:
            raise CacheSafetyError(f"{name} must be positive")
    root = _validate_cache_root(cache_root, create=True)
    observed_at = int(time.time() if now is None else now)
    before = capacity_probe(capacity_path)
    deleted: list[dict[str, object]] = []
    with _ReclaimLock(root):
        entries = _inventory(root)
        harness_shas, harness_owner_pids = _protected_harness_worktree(root, qualification_lease_root)
        represented = set(harness_owner_pids)
        protected = set(harness_shas)
        for entry in entries:
            represented.update(entry.live_lease_owner_pids)
            if entry.live_lease_owner_pids:
                protected.add(entry.source_sha)
        protected.update(_process_protection(root, entries, represented, process_probe()))

        eligible = sorted(
            (
                entry
                for entry in entries
                if entry.source_sha not in protected and observed_at - entry.last_used_at >= minimum_age_seconds
            ),
            key=lambda entry: (entry.last_used_at, entry.source_sha),
        )
        after = before
        reclaimed_kib = 0
        for entry in eligible:
            if after.available_kib >= minimum_free_kib and after.available_inodes >= minimum_free_inodes:
                break
            if len(deleted) >= max_entries or reclaimed_kib + entry.size_kib > max_reclaim_kib:
                break
            shutil.rmtree(entry.path)
            reclaimed_kib += entry.size_kib
            deleted.append(
                {
                    "source_sha": entry.source_sha,
                    "age_seconds": observed_at - entry.last_used_at,
                    "size_kib": entry.size_kib,
                }
            )
            after = capacity_probe(capacity_path)

    failures: list[str] = []
    if after.available_kib < minimum_free_kib:
        failures.append("insufficient-free-kib")
    if after.available_inodes < minimum_free_inodes:
        failures.append("insufficient-free-inodes")
    return {
        "schema_version": 2,
        "guard": "runner-capacity-preflight",
        "status": "failed" if failures else "passed",
        "failure_reasons": failures,
        "minimum_free_kib": minimum_free_kib,
        "minimum_free_inodes": minimum_free_inodes,
        "available_kib": after.available_kib,
        "available_inodes": after.available_inodes,
        "before_reclaim_available_kib": before.available_kib,
        "before_reclaim_available_inodes": before.available_inodes,
        "reclaim": {
            "policy": "oldest-idle-exact-sha-v1",
            "minimum_age_seconds": minimum_age_seconds,
            "max_entries": max_entries,
            "max_reclaim_kib": max_reclaim_kib,
            "deleted_entries": deleted,
            "reclaimed_kib": sum(int(item["size_kib"]) for item in deleted),
        },
    }


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    _write_private_json(temporary, payload, exclusive=True)
    temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)

    wait = subcommands.add_parser("wait-for-reclaim")
    wait.add_argument("--cache-root", type=Path, required=True)
    wait.add_argument("--timeout-seconds", type=float, default=60)

    acquire = subcommands.add_parser("lease-acquire")
    acquire.add_argument("--cache-root", type=Path, required=True)
    acquire.add_argument("--source-sha", required=True)
    acquire.add_argument("--lease-id", required=True)
    acquire.add_argument("--owner-pid", type=int, required=True)

    release = subcommands.add_parser("lease-release")
    release.add_argument("--cache-root", type=Path, required=True)
    release.add_argument("--source-sha", required=True)
    release.add_argument("--lease-id", required=True)
    release.add_argument("--owner-pid", type=int, required=True)
    release.add_argument("--token", required=True)

    reclaim_parser = subcommands.add_parser("reclaim")
    reclaim_parser.add_argument("--cache-root", type=Path, required=True)
    reclaim_parser.add_argument("--qualification-lease-root", type=Path, required=True)
    reclaim_parser.add_argument("--capacity-path", type=Path, required=True)
    reclaim_parser.add_argument("--minimum-free-kib", type=int, required=True)
    reclaim_parser.add_argument("--minimum-free-inodes", type=int, required=True)
    reclaim_parser.add_argument("--minimum-age-seconds", type=int, default=6 * 60 * 60)
    reclaim_parser.add_argument("--max-entries", type=int, default=8)
    reclaim_parser.add_argument("--max-reclaim-kib", type=int, default=64 * 1024 * 1024)
    reclaim_parser.add_argument("--report", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "wait-for-reclaim":
            wait_for_reclaim(args.cache_root, timeout_seconds=args.timeout_seconds)
            return 0
        if args.command == "lease-acquire":
            print(
                json.dumps(
                    acquire_cache_lease(
                        args.cache_root,
                        source_sha=args.source_sha,
                        lease_id=args.lease_id,
                        owner_pid=args.owner_pid,
                    ),
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "lease-release":
            release_cache_lease(
                args.cache_root,
                source_sha=args.source_sha,
                lease_id=args.lease_id,
                owner_pid=args.owner_pid,
                token=args.token,
            )
            return 0

        report = reclaim(
            args.cache_root,
            qualification_lease_root=args.qualification_lease_root,
            capacity_path=args.capacity_path,
            minimum_free_kib=args.minimum_free_kib,
            minimum_free_inodes=args.minimum_free_inodes,
            minimum_age_seconds=args.minimum_age_seconds,
            max_entries=args.max_entries,
            max_reclaim_kib=args.max_reclaim_kib,
        )
        _write_report(args.report, report)
        if report["status"] != "passed":
            print(
                "::error::M1 qualification runner capacity guard refused to start "
                f"(available_kib={report['available_kib']}, required_kib={report['minimum_free_kib']}, "
                f"available_inodes={report['available_inodes']}, required_inodes={report['minimum_free_inodes']})"
            )
            return 1
        print(
            "M1 qualification runner capacity guard passed "
            f"(available_kib={report['available_kib']}, reclaimed_kib={report['reclaim']['reclaimed_kib']})"
        )
        return 0
    except CacheSafetyError as error:
        if args.command == "reclaim":
            failed_report = {
                "schema_version": 2,
                "guard": "runner-capacity-preflight",
                "status": "failed",
                "failure_reasons": ["cache-reclaim-unsafe"],
                "minimum_free_kib": args.minimum_free_kib,
                "minimum_free_inodes": args.minimum_free_inodes,
                "reclaim": {
                    "policy": "oldest-idle-exact-sha-v1",
                    "status": "refused",
                    "reason": str(error)[:300],
                    "deleted_entries": [],
                    "reclaimed_kib": 0,
                },
            }
            _write_report(args.report, failed_report)
        print(f"qualification cache reclaim refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

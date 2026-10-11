"""Exclusive physical-device leases for the C5 qualification lane (SCA-491).

A device lease is the authority gate for every device-runner action: install,
launch, permission toggles, log capture and teardown all require an active
lease owned by the caller. The rules reuse the C1 session-lease ownership
model (``mobile_session``) and add a device-qualification registry so a
personal/foreign phone can never be operated on by accident:

- a device must be **registered as a dedicated test device** (explicit
  operator confirmation) before it can be leased at all;
- one exclusive lease per device id, claimed atomically (``O_EXCL``);
- a **live foreign lease is never stolen** — bounded acquisition waits and
  then fails with the holder's identity;
- cross-host or cross-user leases are never auto-recovered (operator matter);
- a stale lease (same host + same user + provably dead owner pid) is
  recovered under a concurrency guard, bumping the lease ``generation``;
- release is owner-gated and idempotent, and never touches device data:
  factory reset / wiping / unenrollment are not part of this module's
  vocabulary. Removing harness-installed *apps* is the device runner's job,
  restricted to synthetic harness app ids.

All state lives under ``<state>/mobile-sessions/device-leases`` and
``.../device-registry`` (see ``safety.default_state_base``). Everything here
is hermetic: time and process liveness are injectable for tests.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from . import safety, session_evidence
from .mobile_session import _same_host, _save_json_atomic, check_ownership, owner_identity, sessions_root

DEVICE_LEASE_SCHEMA_VERSION = "device-lease/v1"
DEVICE_QUALIFICATION_SCHEMA_VERSION = "device-qualification/v1"
LEASES_DIRNAME = "device-leases"
REGISTRY_DIRNAME = "device-registry"
PLATFORMS = ("ios", "android", "wearable")
_DEVICE_ID_RE = re.compile(r"[A-Za-z0-9._-]{4,64}")
_RECOVERY_GUARD_SUFFIX = ".recovering"


class DeviceLeaseError(RuntimeError):
    """Refusal or blocked device-lease operation (exit code 2 at the CLI)."""


def _validate_platform(platform: str) -> str:
    if platform not in PLATFORMS:
        raise DeviceLeaseError(f"platform must be one of {PLATFORMS}, got {platform!r}")
    return platform


def _validate_device_id(device_id: str) -> str:
    if not _DEVICE_ID_RE.fullmatch(device_id or ""):
        raise DeviceLeaseError(
            f"device id {device_id!r} must match {_DEVICE_ID_RE.pattern} (udid/serial form); refusing"
        )
    return device_id


def devices_root(repo_root: Path, env: Mapping[str, str] | None = None) -> Path:
    return sessions_root(repo_root, env) / LEASES_DIRNAME


def registry_root(repo_root: Path, env: Mapping[str, str] | None = None) -> Path:
    return sessions_root(repo_root, env) / REGISTRY_DIRNAME


def _device_path(base: Path, platform: str, device_id: str, suffix: str = ".json") -> Path:
    return base / _validate_platform(platform) / f"{_validate_device_id(device_id)}{suffix}"


def _load_json(path: Path, *, what: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DeviceLeaseError(f"no {what} at {path}") from exc
    except json.JSONDecodeError as exc:
        raise DeviceLeaseError(f"{what} {path} is corrupt: {exc}; inspect it manually") from exc
    if not isinstance(data, dict):
        raise DeviceLeaseError(f"{what} {path} is corrupt (not an object); inspect it manually")
    return data


# ---------------------------------------------------------------------------
# Device qualification registry (personal/foreign-device refusal)
# ---------------------------------------------------------------------------


def register_device(
    repo_root: Path,
    platform: str,
    device_id: str,
    *,
    label: str,
    os_version: str,
    confirm: bool,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Record a device as a dedicated test device.

    ``confirm`` is the explicit operator assertion that the device is a
    dedicated test device (synthetic identities/data only). Without it the
    registration refuses: this is the personal-device gate. Registration is
    idempotent for identical content and refuses to downgrade an existing
    entry silently.
    """

    record = {
        "schema_version": DEVICE_QUALIFICATION_SCHEMA_VERSION,
        "platform": _validate_platform(platform),
        "device_id": _validate_device_id(device_id),
        "label": label or device_id,
        "os_version": os_version,
        "confirmed_test_device": True,
        "registered_by": owner_identity(),
        "registered_at": session_evidence.utc_now(),
    }
    if not confirm:
        raise DeviceLeaseError(
            f"refusing to register {platform}/{device_id} as a test device without --confirm-test-device: "
            "only dedicated test devices (never a personal phone/watch) may join the qualification lane; "
            "an unregistered device is refused by acquire"
        )
    path = _device_path(registry_root(repo_root, env), platform, device_id)
    if path.exists():
        existing = _load_json(path, what="device qualification record")
        for key in ("platform", "device_id"):
            if existing.get(key) != record[key]:
                raise DeviceLeaseError(f"qualification record {path} disagrees on {key}; inspect it")
        _save_json_atomic(path, {**existing, **{k: v for k, v in record.items() if k != "registered_by"}})
        return _load_json(path, what="device qualification record")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return _load_json(path, what="device qualification record")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return record


def deregister_device(
    repo_root: Path,
    platform: str,
    device_id: str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Remove a device from the qualification registry; refuses while leased."""

    lease = _device_path(devices_root(repo_root, env), platform, device_id)
    if lease.exists():
        raise DeviceLeaseError(
            f"device {platform}/{device_id} has an active lease ({lease}); release it before deregistering"
        )
    path = _device_path(registry_root(repo_root, env), platform, device_id)
    record = _load_json(path, what="device qualification record")
    path.unlink(missing_ok=True)
    return record


def require_qualified_device(
    repo_root: Path,
    platform: str,
    device_id: str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    record = _load_json(
        _device_path(registry_root(repo_root, env), platform, device_id),
        what="device qualification record",
    )
    if record.get("schema_version") != DEVICE_QUALIFICATION_SCHEMA_VERSION:
        raise DeviceLeaseError(f"device qualification record for {platform}/{device_id} has an unsupported schema")
    if record.get("confirmed_test_device") is not True:
        raise DeviceLeaseError(f"device {platform}/{device_id} is not confirmed as a dedicated test device; refusing")
    return record


# ---------------------------------------------------------------------------
# Lease lifecycle
# ---------------------------------------------------------------------------


def _load_lease(repo_root: Path, platform: str, device_id: str, env: Mapping[str, str] | None) -> dict[str, Any]:
    lease = _load_json(_device_path(devices_root(repo_root, env), platform, device_id), what="device lease")
    if lease.get("schema_version") != DEVICE_LEASE_SCHEMA_VERSION:
        raise DeviceLeaseError(f"device lease for {platform}/{device_id} has an unsupported schema")
    return lease


def _lease_is_stale(
    lease: Mapping[str, Any],
    *,
    process_exists: Callable[[int], bool] = safety.process_exists,
) -> bool:
    """A lease is stale only when provably reclaimable: same host, same user,
    and an owner pid that no longer exists. Anything else (live pid, foreign
    host/user) is NOT stale — it is owned, and ownership wins."""

    owner = lease.get("owner")
    if not isinstance(owner, Mapping) or not _same_host(owner):
        return False
    if str(owner.get("user", "")) != owner_identity()["user"]:
        return False
    owner_pid = int(owner.get("pid", -1))
    return owner_pid > 0 and not process_exists(owner_pid)


def _refuse_live_foreign_owner(
    lease: Mapping[str, Any],
    platform: str,
    device_id: str,
    *,
    process_exists: Callable[[int], bool],
) -> None:
    """Refuse to act on a lease held by a pid that is live and not us."""

    owner_pid = int(lease.get("owner", {}).get("pid", -1))
    if owner_pid > 0 and owner_pid != owner_identity()["pid"] and process_exists(owner_pid):
        raise DeviceLeaseError(
            f"device {platform}/{device_id} is leased by live pid {owner_pid}; refusing to touch a live foreign lease"
        )


def _claim_new_lease(
    repo_root: Path,
    platform: str,
    device_id: str,
    purpose: str,
    session_id: str | None,
    env: Mapping[str, str] | None,
    *,
    generation: int,
    recovered_count: int,
) -> dict[str, Any]:
    path = _device_path(devices_root(repo_root, env), platform, device_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lease = {
        "schema_version": DEVICE_LEASE_SCHEMA_VERSION,
        "platform": platform,
        "device_id": device_id,
        "status": "leased",
        "generation": generation,
        "recovered_count": recovered_count,
        "owner": owner_identity(),
        "purpose": purpose,
        "session_id": session_id,
        "created_at": session_evidence.utc_now(),
        "heartbeat_at": session_evidence.utc_now(),
    }
    _save_json_atomic(path, lease)
    return lease


def acquire(
    repo_root: Path,
    platform: str,
    device_id: str,
    *,
    purpose: str,
    session_id: str | None = None,
    wait_timeout_s: float = 0.0,
    env: Mapping[str, str] | None = None,
    process_exists: Callable[[int], bool] = safety.process_exists,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Acquire the exclusive lease for a qualified device.

    Bounded acquisition: while the device is held by a live foreign owner,
    retry until ``wait_timeout_s`` elapses, then refuse with the holder's
    identity. A provably stale lease (same host + user + dead pid) is
    recovered atomically under a guard directory so exactly one concurrent
    acquirer wins; the generation increments on every recovery.
    """

    _validate_platform(platform)
    _validate_device_id(device_id)
    require_qualified_device(repo_root, platform, device_id, env=env)
    if session_id is not None:
        from .mobile_session import _load_lease as _load_session_lease  # avoid import cycle at module import

        session_dir = sessions_root(repo_root, env) / session_id
        try:
            _load_session_lease(session_dir / "lease.json")  # bound leases must reference a real session
        except Exception as exc:
            raise DeviceLeaseError(f"device lease session binding failed: {exc}") from exc

    path = _device_path(devices_root(repo_root, env), platform, device_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = clock() + max(0.0, wait_timeout_s)
    while True:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            lease = _load_json(path, what="device lease")
            if lease.get("schema_version") != DEVICE_LEASE_SCHEMA_VERSION:
                raise DeviceLeaseError(f"device lease {path} has an unsupported schema; refusing") from None
            _refuse_live_foreign_owner(lease, platform, device_id, process_exists=process_exists)
            try:
                check_ownership(lease, allow_dead_owner=True)
            except Exception as exc:
                # Live foreign owner, or foreign host/user: never steal.
                if clock() >= deadline:
                    raise DeviceLeaseError(
                        f"device {platform}/{device_id} is leased by another owner ({exc}); "
                        f"bounded acquisition gave up after {wait_timeout_s:.1f}s"
                    ) from exc
                sleep(0.05)
                continue
            if not _lease_is_stale(lease, process_exists=process_exists):
                # check_ownership passed but the owner is live and not us: owned.
                if clock() >= deadline:
                    raise DeviceLeaseError(
                        f"device {platform}/{device_id} is leased (owner pid {lease['owner'].get('pid')} "
                        f"is live; refusing to steal a live lease); "
                        f"bounded acquisition gave up after {wait_timeout_s:.1f}s"
                    )
                sleep(0.05)
                continue
            # Provably stale: recover exactly once under a guard, then claim
            # the post-recovery generation (the bump happened inside it).
            recovered = _recover_stale_lease(repo_root, platform, device_id, env=env, process_exists=process_exists)
            return _claim_new_lease(
                repo_root,
                platform,
                device_id,
                purpose,
                session_id,
                env,
                generation=int(recovered["generation"]),
                recovered_count=int(recovered.get("recovered_count", 0)),
            )
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write("")
        # Claimed the name atomically; publish the full record (replace).
        return _claim_new_lease(
            repo_root, platform, device_id, purpose, session_id, env, generation=1, recovered_count=0
        )


def _recover_stale_lease(
    repo_root: Path,
    platform: str,
    device_id: str,
    *,
    env: Mapping[str, str] | None,
    process_exists: Callable[[int], bool] = safety.process_exists,
) -> dict[str, Any]:
    """Take over a provably dead same-host/same-user lease under a lock guard.

    The ``.recovering`` guard directory is created with ``O_EXCL``: only one
    concurrent acquirer enters, re-verifies staleness, then bumps the
    generation and re-stamps the owner. A loser of the guard race sees a
    lease that is either fresh (owner live again) or foreign — both refuse.
    """

    path = _device_path(devices_root(repo_root, env), platform, device_id)
    guard = _device_path(devices_root(repo_root, env), platform, device_id, suffix=_RECOVERY_GUARD_SUFFIX)
    guard.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.mkdir(guard)
    except FileExistsError as exc:
        raise DeviceLeaseError(
            f"another recovery of {platform}/{device_id} is already in progress ({guard}); retry shortly"
        ) from exc
    try:
        lease = _load_json(path, what="device lease")
        owner_pid = int(lease.get("owner", {}).get("pid", -1))
        if process_exists(owner_pid):
            raise DeviceLeaseError(
                f"device {platform}/{device_id} owner pid {owner_pid} is live again; refusing to recover"
            )
        try:
            check_ownership(lease, allow_dead_owner=True)
        except Exception as exc:
            raise DeviceLeaseError(f"refusing to recover {platform}/{device_id}: {exc}") from exc
        lease = {
            **lease,
            "generation": int(lease.get("generation", 1)) + 1,
            "recovered_count": int(lease.get("recovered_count", 0)) + 1,
            "owner": owner_identity(),
            "recovered_at": session_evidence.utc_now(),
            "heartbeat_at": session_evidence.utc_now(),
        }
        _save_json_atomic(path, lease)
        return lease
    finally:
        try:
            guard.rmdir()
        except OSError:
            pass


def recover(
    repo_root: Path,
    platform: str,
    device_id: str,
    *,
    env: Mapping[str, str] | None = None,
    process_exists: Callable[[int], bool] = safety.process_exists,
) -> dict[str, Any]:
    """Explicit operator-facing recovery of a stale same-host lease."""

    _validate_platform(platform)
    _validate_device_id(device_id)
    require_qualified_device(repo_root, platform, device_id, env=env)
    path = _device_path(devices_root(repo_root, env), platform, device_id)
    lease = _load_json(path, what="device lease")
    if not _lease_is_stale(lease, process_exists=process_exists):
        owner = lease.get("owner", {})
        raise DeviceLeaseError(
            f"device {platform}/{device_id} is not recoverable here: owner {owner.get('user')}@{owner.get('host')} "
            f"pid {owner.get('pid')} — a live or foreign lease is an operator decision, never an automatic takeover"
        )
    return _recover_stale_lease(repo_root, platform, device_id, env=env, process_exists=process_exists)


def heartbeat(
    repo_root: Path,
    platform: str,
    device_id: str,
    *,
    env: Mapping[str, str] | None = None,
    process_exists: Callable[[int], bool] = safety.process_exists,
) -> dict[str, Any]:
    """Refresh the lease liveness stamp (long device runs should call this)."""

    path = _device_path(devices_root(repo_root, env), platform, device_id)
    lease = _load_json(path, what="device lease")
    _refuse_live_foreign_owner(lease, platform, device_id, process_exists=process_exists)
    check_ownership(lease, allow_dead_owner=True)
    lease = {**lease, "heartbeat_at": session_evidence.utc_now()}
    _save_json_atomic(path, lease)
    return lease


def release(
    repo_root: Path,
    platform: str,
    device_id: str,
    *,
    env: Mapping[str, str] | None = None,
    process_exists: Callable[[int], bool] = safety.process_exists,
) -> dict[str, Any]:
    """Release the caller's lease (idempotent; never touches device data)."""

    path = _device_path(devices_root(repo_root, env), platform, device_id)
    if not path.exists():
        return {"platform": platform, "device_id": device_id, "status": "released", "generation": 0}
    lease = _load_json(path, what="device lease")
    _refuse_live_foreign_owner(lease, platform, device_id, process_exists=process_exists)
    check_ownership(lease, allow_dead_owner=True)
    path.unlink()
    return {
        "platform": platform,
        "device_id": device_id,
        "status": "released",
        "generation": int(lease.get("generation", 1)),
    }


def status(
    repo_root: Path,
    platform: str | None = None,
    device_id: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Snapshot registry + lease state for one device or a whole platform."""

    base_root = devices_root(repo_root, env)
    reg_root = registry_root(repo_root, env)
    platforms = (platform,) if platform else PLATFORMS
    devices: list[dict[str, Any]] = []
    for plat in platforms:
        _validate_platform(plat)
        reg_dir = reg_root / plat
        lease_dir = base_root / plat
        ids = sorted({p.stem for p in reg_dir.glob("*.json")} | {p.stem for p in lease_dir.glob("*.json")})
        for dev in ids:
            if device_id and dev != device_id:
                continue
            entry: dict[str, Any] = {"platform": plat, "device_id": dev}
            reg = reg_dir / f"{dev}.json"
            lease = lease_dir / f"{dev}.json"
            entry["qualified"] = reg.exists()
            if reg.exists():
                record = _load_json(reg, what="device qualification record")
                entry["label"] = record.get("label")
                entry["os_version"] = record.get("os_version")
            entry["leased"] = lease.exists()
            if lease.exists():
                current = _load_json(lease, what="device lease")
                owner = current.get("owner", {})
                entry["lease"] = {
                    "generation": current.get("generation"),
                    "owner": f"{owner.get('user')}@{owner.get('host')} pid {owner.get('pid')}",
                    "purpose": current.get("purpose"),
                    "session_id": current.get("session_id"),
                    "heartbeat_at": current.get("heartbeat_at"),
                    "stale_here": _lease_is_stale(current),
                }
            devices.append(entry)
    return {"schema_version": DEVICE_LEASE_SCHEMA_VERSION, "devices": devices}

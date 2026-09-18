"""Isolated mobile session orchestration (SCA-487 C1).

One CLI owns a local mobile session end to end:

    mobile-session doctor | list
    mobile-session acquire  [--name N] [--platform P] [--fixture-version V]
    mobile-session start    <session-id>
    mobile-session seed     <session-id>
    mobile-session reset    <session-id>
    mobile-session status   <session-id>
    mobile-session evidence <session-id> [--artifact PATH] [--state S]
    mobile-session stop     <session-id>
    mobile-session recover  <session-id>
    mobile-session release  <session-id>

A session is a uniquely owned harness instance (its own state root, ports,
backend, Firebase emulators, Redis namespace and logs) plus a device lease and
a session-evidence-v1 receipt. Ownership is fail-closed:

- leases are created atomically (``O_EXCL``) and record owner host/user/pid;
- a live foreign owner is never reclaimed — recover only takes over a lease
  whose owner is provably dead on this host, bumping the generation;
- ports are claimed by actual port number (including cross-role intersections)
  and refused (never killed) when a foreign process already listens;
- stop/release/reset only touch processes and state recorded under the
  session's own manifests (the harness's own ownership guards apply).

Services start/stop reuse the existing dev-harness lifecycle in-process, so a
session is exactly a harness instance + offset — no second orchestration
stack.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import random
import re
import shutil
import string
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import config, mobile_doctor, mobile_fixtures, safety, session_evidence
from .session_evidence import EvidenceError

CLI_VERSION = "0.1.0"
SESSIONS_DIRNAME = "mobile-sessions"
SESSION_ID_PREFIX = "oms-"
LEASE_FILENAME = "lease.json"
EVIDENCE_FILENAME = "evidence.json"
SEED_FILENAME = "seed.json"
PORTS_DIRNAME = "ports"
LEASE_SCHEMA_VERSION = 1

PORT_OFFSET_MIN = 100
PORT_OFFSET_STEP = 100
PORT_OFFSET_MAX = 5000
MAX_OFFSET_ATTEMPTS = 48

PLATFORMS = ("android", "ios-simulator")
DEFAULT_APP_IDS = {
    "android": "com.friend.ios.dev",
    "ios-simulator": "com.friend-app-with-wearable.ios12.development",
}
DEFAULT_PROFILE = "local_dev"
DEFAULT_FLAVOR = "dev"


class SessionError(RuntimeError):
    """Raised for ownership/safety violations and fail-closed refusals."""


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


# Lease lifecycle statuses that differ from the evidence-state vocabulary
# (contracts/session/session-evidence-v1.schema.json): after seeding the
# session is ready for journeys; after reset it is ready for a fresh seed.
_EVIDENCE_STATE_FOR_LEASE = {
    "creating": "creating",
    "running": "running",
    "seeded": "ready",
    "reset": "ready",
    "blocked": "blocked",
    "failed": "failed",
}


def sessions_root(repo_root: Path, env: Mapping[str, str] | None = None) -> Path:
    return safety.default_state_base(Path(repo_root), env) / SESSIONS_DIRNAME


def session_dir(repo_root: Path, session_id: str, env: Mapping[str, str] | None = None) -> Path:
    _validate_session_id(session_id)
    return sessions_root(repo_root, env) / session_id


def _validate_session_id(session_id: str) -> str:
    if not re.fullmatch(rf"{SESSION_ID_PREFIX}[a-z0-9][a-z0-9-]{{0,63}}", session_id or ""):
        raise SessionError(f"session id {session_id!r} must match {SESSION_ID_PREFIX}<lowercase-alnum-dash>")
    return session_id


def new_session_id() -> str:
    import time as _time

    stamp = _time.strftime("%Y%m%d%H%M%S", _time.gmtime())
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{SESSION_ID_PREFIX}{stamp}-{suffix}"


def owner_identity() -> dict[str, Any]:
    return {
        "host": platform.node(),
        "user": getpass.getuser(),
        "pid": os.getpid(),
    }


def _same_host(owner: Mapping[str, Any]) -> bool:
    return str(owner.get("host", "")) == platform.node()


def _load_lease(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SessionError(f"no session lease at {path}: acquire it first, or list sessions") from exc
    except json.JSONDecodeError as exc:
        raise SessionError(f"session lease {path} is corrupt: {exc}; use recover after inspecting it") from exc
    if not isinstance(data, dict) or data.get("schema_version") != LEASE_SCHEMA_VERSION:
        raise SessionError(f"session lease {path} has an unsupported schema")
    return data


def _save_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(target.parent), prefix=target.name, suffix=".tmp", delete=False
    )
    try:
        with handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(handle.name, target)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


# ---------------------------------------------------------------------------
# Ownership guards
# ---------------------------------------------------------------------------


def check_ownership(lease: Mapping[str, Any], *, allow_dead_owner: bool = True) -> None:
    """Refuse to act on a lease this caller does not own.

    CLI invocations are separate processes, so a recorded owner pid being dead
    is the normal state between commands, not evidence of a crash. The rules
    that actually protect a session are:

    - different host: operator matter (shared filesystem) — refuse;
    - different local user: refuse (someone else's session, even orphaned);
    - live owner pid that is not us: refuse (never touch a live foreign session);
    - same host + same user + dead/own pid: allowed — an orphaned session
      continues under its lease; `recover` exists to bump the generation and
      re-stamp the owner explicitly.
    """

    owner = lease.get("owner")
    if not isinstance(owner, Mapping):
        raise SessionError("lease has no owner record; refusing to act — inspect it manually")
    if not _same_host(owner):
        raise SessionError(
            f"session is owned by {owner.get('user')}@{owner.get('host')} (this host is {platform.node()}); "
            "cross-host takeover is an operator decision, not an automatic one"
        )
    if str(owner.get("user", "")) != getpass.getuser():
        raise SessionError(
            f"session is owned by local user {owner.get('user')!r} (you are {getpass.getuser()!r}); "
            "refusing to operate on another user's session"
        )
    owner_pid = int(owner.get("pid", -1))
    if owner_pid == os.getpid():
        return
    if safety.process_exists(owner_pid):
        raise SessionError(
            f"session is owned by live pid {owner_pid} ({owner.get('user')}@{owner.get('host')}); "
            "refusing to touch a live foreign session"
        )
    if not allow_dead_owner:
        raise SessionError(
            f"session owner pid {owner_pid} is dead; run 'mobile-session recover {lease.get('session_id')}' "
            "to take it over (same host only)"
        )


def _port_claim_path(ports_dir: Path, port: int) -> Path:
    return ports_dir / f"port-{port}.json"


def _write_exclusive_claim(path: Path, payload: Mapping[str, Any]) -> None:
    handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _rollback_claims(paths: Sequence[Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _claim_port_offset(
    root: Path,
    session_id: str,
    *,
    requested_offset: int | None = None,
    listeners: Callable[[int], tuple[int, ...]] = safety.listening_pids,
) -> tuple[int, dict[str, int]]:
    """Atomically claim an isolated port set, refusing foreign listeners.

    Exclusive claims are the derived port numbers (including cross-role
    intersections). The offset file is session metadata, not the isolation
    boundary: offsets 1000 and 3700 both derive port 10080.
    """

    ports_dir = root / PORTS_DIRNAME
    ports_dir.mkdir(parents=True, exist_ok=True)
    if requested_offset is not None:
        if not PORT_OFFSET_MIN <= requested_offset <= PORT_OFFSET_MAX:
            raise SessionError(
                f"requested port offset {requested_offset} outside [{PORT_OFFSET_MIN}, {PORT_OFFSET_MAX}]"
            )
        if requested_offset % PORT_OFFSET_STEP != 0:
            raise SessionError(f"requested port offset {requested_offset} must be a multiple of {PORT_OFFSET_STEP}")
        candidates: Sequence[int] = (requested_offset,)
    else:
        shuffled = list(range(PORT_OFFSET_MIN, PORT_OFFSET_MAX + 1, PORT_OFFSET_STEP))
        random.shuffle(shuffled)
        candidates = shuffled[:MAX_OFFSET_ATTEMPTS]

    refusals: list[str] = []
    for offset in candidates:
        claim_path = ports_dir / f"{offset}.json"
        ports = config.harness_ports_from_env({config.PORT_OFFSET_ENV: str(offset)})
        for port in sorted(set(ports.values())):
            try:
                pids = listeners(port)
            except safety.SafetyError as exc:
                raise SessionError(
                    f"cannot verify ownership of port {port}: {exc}; refusing to allocate ports blindly"
                ) from exc
            if pids:
                refusals.append(f"port {port} held by pid(s) {list(pids)} — refused, not killed")
        if refusals and requested_offset is not None:
            raise SessionError("; ".join(refusals))
        if refusals:
            refusals = []
            continue
        acquired: list[Path] = []
        claimed_at = session_evidence.utc_now()
        try:
            _write_exclusive_claim(
                claim_path,
                {
                    "schema_version": 1,
                    "session_id": session_id,
                    "port_offset": offset,
                    "claimed_at": claimed_at,
                },
            )
            acquired.append(claim_path)
            for port in sorted(set(ports.values())):
                port_path = _port_claim_path(ports_dir, port)
                _write_exclusive_claim(
                    port_path,
                    {
                        "schema_version": 1,
                        "session_id": session_id,
                        "port": port,
                        "port_offset": offset,
                        "claimed_at": claimed_at,
                    },
                )
                acquired.append(port_path)
        except FileExistsError as exc:
            _rollback_claims(acquired)
            if requested_offset is not None:
                raise SessionError(
                    f"port set for offset {offset} is already claimed ({exc.filename or claim_path})"
                ) from exc
            continue
        return offset, dict(ports)
    raise SessionError(
        f"no free port offset in [{PORT_OFFSET_MIN}, {PORT_OFFSET_MAX}] after {MAX_OFFSET_ATTEMPTS} attempts; "
        "last refusals: " + ("; ".join(refusals) or "all offsets claimed")
    )


def _release_port_offset(root: Path, offset: int, session_id: str) -> None:
    ports_dir = root / PORTS_DIRNAME
    claim_path = ports_dir / f"{offset}.json"
    try:
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        claim = None
    except json.JSONDecodeError:
        raise SessionError(f"port claim {claim_path} is corrupt; inspect before deleting it") from None
    if claim is not None and claim.get("session_id") != session_id:
        raise SessionError(
            f"port offset {offset} is claimed by session {claim.get('session_id')!r}, not {session_id!r}; refusing"
        )
    ports = config.harness_ports_from_env({config.PORT_OFFSET_ENV: str(offset)})
    for port in sorted(set(ports.values())):
        port_path = _port_claim_path(ports_dir, port)
        try:
            payload = json.loads(port_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except json.JSONDecodeError:
            raise SessionError(f"port claim {port_path} is corrupt; inspect before deleting it") from None
        if payload.get("session_id") != session_id:
            raise SessionError(
                f"port {port} is claimed by session {payload.get('session_id')!r}, not {session_id!r}; refusing"
            )
        port_path.unlink()
    if claim is not None:
        claim_path.unlink()


# ---------------------------------------------------------------------------
# Device lease
# ---------------------------------------------------------------------------


class DeviceController:
    """Owns the simulator/emulator lifecycle for a session. Injectable."""

    def __init__(self, runner: Callable[[Sequence[str]], tuple[int, str]] | None = None) -> None:
        self._runner = runner or self._default_runner

    @staticmethod
    def _default_runner(command: Sequence[str]) -> tuple[int, str]:
        # A missing binary (e.g. xcrun on a host without Xcode) must surface as
        # exit 127 + message so callers fail closed with a remedy; an escaping
        # FileNotFoundError would also break stop()/release() idempotency.
        try:
            completed = subprocess.run(list(command), capture_output=True, text=True, check=False, timeout=120)
        except OSError as exc:
            return 127, f"{command[0]} not available: {exc}"
        return completed.returncode, (completed.stdout or "") + (completed.stderr or "")

    def android_ready(self, android_home: str) -> tuple[bool, str]:
        home = Path(android_home or "")
        emulator = home / "emulator" / "emulator"
        if not emulator.exists():
            return False, f"emulator engine missing at {emulator} (sdkmanager 'emulator' 'cmdline-tools;latest')"
        sdkmanager = home / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
        list_code: int | None = None
        list_output = ""
        if sdkmanager.exists():
            list_code, list_output = self._runner([str(sdkmanager), "--list_installed"])
        image = mobile_doctor.installed_android_system_image(home, list_output=list_output)
        if image:
            return True, f"android emulator engine present ({image})"
        disk = home.joinpath(*mobile_doctor.PREFERRED_ANDROID_IMAGE_DIR)
        if list_code is None:
            return False, (
                f"cannot determine Android system image: sdkmanager missing at {sdkmanager} "
                f"and no on-disk image at {disk}; this is not a finding that the emulator engine is absent"
            )
        if list_code != 0:
            snippet = " ".join(list_output.split())[:180]
            return False, (
                f"cannot determine Android system image: sdkmanager --list_installed exited {list_code}"
                + (f" ({snippet})" if snippet else "")
                + "; this is not a finding that the emulator engine is absent"
            )
        return False, f"no Android system image installed (sdkmanager '{mobile_doctor.PREFERRED_ANDROID_IMAGE}')"

    def attach_ios_simulator(self, session_id: str, device_type: str, runtime: str) -> tuple[str, str]:
        name = f"omi-session-{session_id}"
        code, out = self._runner(["xcrun", "simctl", "create", name, device_type, runtime])
        udid = out.strip().splitlines()[0].strip() if out.strip() else ""
        if code != 0 or not re.fullmatch(r"[0-9A-Fa-f-]{16,}", udid or ""):
            raise SessionError(f"simctl create failed for session simulator: {out.strip() or code}")
        code, out = self._runner(["xcrun", "simctl", "boot", udid])
        if code != 0 and "already booted" not in out.lower():
            self._runner(["xcrun", "simctl", "delete", udid])
            raise SessionError(f"simctl boot failed for {udid}: {out.strip()}")
        return udid, f"{device_type} ({runtime})"

    def detach(self, platform_name: str, device_id: str) -> None:
        if platform_name == "ios-simulator":
            self._runner(["xcrun", "simctl", "shutdown", device_id])
            self._runner(["xcrun", "simctl", "delete", device_id])
        # android: AVD-based emulators stop with the session services; the AVD
        # template stays for reuse and is owned by the session's lease record.


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def acquire(
    repo_root: Path,
    env: Mapping[str, str] | None = None,
    *,
    name: str | None = None,
    platform_name: str = "android",
    fixture_version: str = mobile_fixtures.CURRENT_FIXTURE_VERSION,
    offset: int | None = None,
    listeners: Callable[[int], tuple[int, ...]] = safety.listening_pids,
) -> dict[str, Any]:
    root = sessions_root(repo_root, env)
    session_id = _validate_session_id(f"{SESSION_ID_PREFIX}{name}" if name else new_session_id())
    if platform_name not in PLATFORMS:
        raise SessionError(f"platform must be one of {PLATFORMS}, got {platform_name!r}")
    fixture = mobile_fixtures.load_fixture(fixture_version)  # fail fast on unknown fixture
    directory = root / session_id
    directory.mkdir(parents=True, exist_ok=True)
    lease_path = directory / LEASE_FILENAME

    try:
        handle = os.open(lease_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        existing = _load_lease(lease_path)
        owner = existing.get("owner", {})
        hint = (
            "its owner is live — do not take it over"
            if safety.process_exists(int(owner.get("pid", -1)))
            else "its owner is dead — run recover"
        )
        raise SessionError(
            f"session {session_id} already exists ({hint}); pick another --name or release it first"
        ) from None
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write("")

    try:
        port_offset, ports = _claim_port_offset(root, session_id, requested_offset=offset, listeners=listeners)
    except BaseException:
        # A half-acquired session (empty lease file, no port claim) must not
        # poison the name for the next attempt.
        lease_path.unlink(missing_ok=True)
        raise
    source = session_evidence.source_identity(Path(repo_root))
    lease = {
        "schema_version": LEASE_SCHEMA_VERSION,
        "session_id": session_id,
        "harness_instance": session_id.removeprefix(SESSION_ID_PREFIX) or session_id,
        "platform": platform_name,
        "status": "creating",
        "generation": 1,
        "owner": owner_identity(),
        "created_at": session_evidence.utc_now(),
        "port_offset": port_offset,
        "ports": {key: value for key, value in sorted(ports.items())},
        "fixture_version": fixture.version,
        "default_auth_uid": fixture.default_user.uid,
        "app_id": DEFAULT_APP_IDS[platform_name],
        "flavor": DEFAULT_FLAVOR,
        "profile": DEFAULT_PROFILE,
        "source_at_acquire": source,
        "device": None,
    }
    _save_json_atomic(lease_path, lease)
    # Harness-standard ownership sentinel so destructive release can prove
    # this directory belongs to this repo's harness layer (safety.validate_destructive_target).
    sentinel = {
        "schema_version": safety.SENTINEL_SCHEMA_VERSION,
        "owner": "omi-local-dev-harness",
        "project_id": safety.DEFAULT_LOCAL_FIREBASE_PROJECT_ID,
        "database_id": safety.DEFAULT_FIRESTORE_DATABASE_ID,
        "instance": lease["harness_instance"],
        "repo_root": str(Path(repo_root)),
    }
    _save_json_atomic(directory / safety.HARNESS_SENTINEL_FILENAME, sentinel)
    return lease


def recover(repo_root: Path, session_id: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    directory = session_dir(repo_root, session_id, env)
    lease = _load_lease(directory / LEASE_FILENAME)
    check_ownership(lease, allow_dead_owner=True)
    lease = {**lease, "generation": int(lease.get("generation", 1)) + 1, "owner": owner_identity()}
    lease["recovered_at"] = session_evidence.utc_now()
    _save_json_atomic(directory / LEASE_FILENAME, lease)
    return lease


def _session_env(lease: Mapping[str, Any]) -> dict[str, str]:
    env = dict(os.environ)
    env["OMI_LOCAL_INSTANCE"] = str(lease["harness_instance"])
    env[config.PORT_OFFSET_ENV] = str(lease["port_offset"])
    # Isolated mobile sessions are the synthetic local lane. Pin offline
    # providers unless the caller already set a mode — never inherit a
    # production-family PROVIDER_MODE=real from the parent shell.
    env.setdefault("PROVIDER_MODE", "offline")
    return env


def _harness_call(lease: Mapping[str, Any], command: Callable[[argparse.Namespace], int]) -> int:
    """Run a dev-harness CLI command against the session's instance/offset."""

    saved = dict(os.environ)
    try:
        os.environ.update(_session_env(lease))
        return command(argparse.Namespace())
    finally:
        os.environ.clear()
        os.environ.update(saved)


def start(
    repo_root: Path,
    session_id: str,
    env: Mapping[str, str] | None = None,
    *,
    devices: DeviceController | None = None,
    attach_device: bool = True,
) -> dict[str, Any]:
    from . import cli as harness_cli

    directory = session_dir(repo_root, session_id, env)
    lease = _load_lease(directory / LEASE_FILENAME)
    check_ownership(lease)

    if attach_device:
        devices = devices or DeviceController()
        if lease["platform"] == "android":
            android_home = (env or os.environ).get("ANDROID_HOME", "").strip() or os.environ.get("ANDROID_HOME", "")
            ready, detail = devices.android_ready(android_home)
            if not ready:
                lease = {**lease, "status": "blocked", "blocked_reason": detail}
                _save_json_atomic(directory / LEASE_FILENAME, lease)
                raise SessionError(
                    f"android device lane not ready: {detail} — run 'mobile-session doctor --platform android'"
                )
        else:  # ios-simulator
            device_type = "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro"
            runtime = "com.apple.CoreSimulator.SimRuntime.iOS-26-5"
            udid, label = devices.attach_ios_simulator(session_id, device_type, runtime)
            lease = {**lease, "device": {"kind": "simulator", "udid": udid, "label": label, "owner": "session"}}

    code = _harness_call(lease, harness_cli.cmd_up)
    if code != 0:
        lease = {**lease, "status": "failed", "blocked_reason": "harness services failed to start (see logs)"}
        _save_json_atomic(directory / LEASE_FILENAME, lease)
        raise SessionError(f"session harness services failed to start (exit {code}); see session status/logs")
    lease = {**lease, "status": "running", "started_at": session_evidence.utc_now()}
    lease.pop("blocked_reason", None)
    _save_json_atomic(directory / LEASE_FILENAME, lease)
    return lease


def backend_base_url(lease: Mapping[str, Any]) -> str:
    return f"http://127.0.0.1:{lease['ports']['backend']}/"


def _probe_backend(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status < 500, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return exc.code < 500, f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        return False, str(exc)


def seed(
    repo_root: Path,
    session_id: str,
    env: Mapping[str, str] | None = None,
    *,
    probe: Callable[[str], tuple[bool, str]] = _probe_backend,
    post: Callable[[str, Mapping[str, str]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    directory = session_dir(repo_root, session_id, env)
    lease = _load_lease(directory / LEASE_FILENAME)
    check_ownership(lease)
    fixture = mobile_fixtures.load_fixture(str(lease.get("fixture_version")))

    base_url = backend_base_url(lease)
    healthy, detail = probe(base_url)
    if not healthy:
        lease = {**lease, "status": "blocked", "blocked_reason": f"session backend unreachable: {detail}"}
        _save_json_atomic(directory / LEASE_FILENAME, lease)
        raise SessionError(f"session backend at {base_url} is unreachable ({detail}); start the session before seeding")

    receipt = mobile_fixtures.seed_synthetic_user(base_url, fixture, post=post)
    mobile_fixtures.write_seed_receipt(directory / SEED_FILENAME, receipt)
    lease = {**lease, "status": "seeded", "seeded_at": receipt["seeded_at"], "default_auth_uid": receipt["uid"]}
    lease.pop("blocked_reason", None)
    _save_json_atomic(directory / LEASE_FILENAME, lease)
    return receipt


def reset(
    repo_root: Path,
    session_id: str,
    env: Mapping[str, str] | None = None,
    *,
    harness_reset: Callable[[argparse.Namespace], int] | None = None,
) -> dict[str, Any]:
    """Idempotent reset of ONLY the owning session's synthetic state."""

    from . import cli as harness_cli

    directory = session_dir(repo_root, session_id, env)
    lease = _load_lease(directory / LEASE_FILENAME)
    check_ownership(lease)
    # The harness reset validates the instance sentinel itself, so the blast
    # radius is exactly this session's instance state root.
    code = _harness_call(lease, harness_reset or harness_cli.cmd_reset)
    if code != 0:
        raise SessionError(f"session harness reset failed (exit {code}); nothing was re-seeded")
    seed_path = directory / SEED_FILENAME
    if seed_path.exists():
        seed_path.unlink()
    lease = {**lease, "status": "reset", "reset_at": session_evidence.utc_now()}
    lease.pop("seeded_at", None)
    _save_json_atomic(directory / LEASE_FILENAME, lease)
    return lease


def stop(
    repo_root: Path,
    session_id: str,
    env: Mapping[str, str] | None = None,
    *,
    devices: DeviceController | None = None,
) -> dict[str, Any]:
    """Idempotent stop of the session's own services/device."""

    from . import cli as harness_cli

    directory = session_dir(repo_root, session_id, env)
    lease = _load_lease(directory / LEASE_FILENAME)
    check_ownership(lease, allow_dead_owner=True)

    device = lease.get("device")
    if isinstance(device, Mapping) and device.get("kind") == "simulator" and device.get("udid"):
        (devices or DeviceController()).detach(str(lease["platform"]), str(device["udid"]))

    code = _harness_call(lease, harness_cli.cmd_down)
    if code != 0:
        raise SessionError(f"session harness down failed (exit {code}); session services may still run")
    lease = {**lease, "status": "stopped", "stopped_at": session_evidence.utc_now(), "device": None}
    _save_json_atomic(directory / LEASE_FILENAME, lease)
    return lease


def release(
    repo_root: Path,
    session_id: str,
    env: Mapping[str, str] | None = None,
    *,
    devices: DeviceController | None = None,
    stop_services: Callable[[Path, str, Mapping[str, str] | None], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = sessions_root(repo_root, env)
    directory = session_dir(repo_root, session_id, env)
    lease_path = directory / LEASE_FILENAME
    if not lease_path.exists():
        return {"session_id": session_id, "released": True, "already_absent": True}
    lease = _load_lease(lease_path)
    check_ownership(lease, allow_dead_owner=True)
    stopper = stop_services or (lambda root, sid, session_env: stop(root, sid, session_env, devices=devices))
    stopper(repo_root, session_id, env)
    _release_port_offset(root, int(lease["port_offset"]), session_id)
    # The session directory carries its own harness sentinel (written at
    # acquire), so the destructive check proves ownership of exactly this dir.
    target = safety.validate_destructive_target(directory, state_root=directory, repo_root=Path(repo_root))
    shutil.rmtree(target)
    return {"session_id": session_id, "released": True, "already_absent": False}


def list_sessions(repo_root: Path, env: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    root = sessions_root(repo_root, env)
    if not root.is_dir():
        return []
    sessions = []
    for lease_path in sorted(root.glob(f"*/{LEASE_FILENAME}")):
        try:
            lease = _load_lease(lease_path)
        except SessionError:
            continue
        sessions.append(
            {
                "session_id": lease.get("session_id"),
                "platform": lease.get("platform"),
                "status": lease.get("status"),
                "port_offset": lease.get("port_offset"),
                "owner": lease.get("owner"),
                "created_at": lease.get("created_at"),
            }
        )
    return sessions


def status(repo_root: Path, session_id: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    directory = session_dir(repo_root, session_id, env)
    lease = _load_lease(directory / LEASE_FILENAME)
    result: dict[str, Any] = {"lease": lease}
    seed_path = directory / SEED_FILENAME
    if seed_path.exists():
        result["seed"] = mobile_fixtures.read_seed_receipt(seed_path)
    evidence_path = directory / EVIDENCE_FILENAME
    if evidence_path.exists():
        result["evidence"] = json.loads(evidence_path.read_text(encoding="utf-8"))
    return result


def build_session_evidence(
    repo_root: Path,
    lease: Mapping[str, Any],
    *,
    artifact_path: Path | None = None,
    state: str | None = None,
    counts: Mapping[str, int] | None = None,
    artifact_files: Mapping[str, Sequence[str]] | None = None,
    source: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble (and validate) the session-evidence-v1 receipt for a lease."""

    root = Path(repo_root)
    live_source = dict(source or session_evidence.source_identity(root))
    acquired = lease.get("source_at_acquire") or {}
    # Lease lifecycle statuses (seeded/reset) are not evidence states; map
    # them onto the vocabulary the v1 receipt accepts.
    resolved_state = state or _EVIDENCE_STATE_FOR_LEASE.get(
        str(lease.get("status", "creating")), str(lease.get("status", "creating"))
    )
    if resolved_state in ("ready", "running") and acquired.get("git_sha") not in ("", None):
        if live_source["git_sha"] != acquired.get("git_sha"):
            raise EvidenceError(
                "source moved since acquire "
                f"(acquired {acquired.get('git_sha')}, now {live_source['git_sha']}): "
                "re-acquire the session or rebuild; a stale source cannot be reported ready"
            )

    ports = lease["ports"]
    artifact: dict[str, Any] | None = None
    if artifact_path is not None:
        artifact_path = Path(artifact_path)
        artifact = {
            "kind": "apk" if artifact_path.suffix == ".apk" else "ios-app-bundle",
            "sha256": session_evidence.file_sha256(artifact_path),
            "git_sha": live_source["git_sha"],
            "path": artifact_path.name,
            "flavor": lease.get("flavor", DEFAULT_FLAVOR),
            "built_from_source": live_source["git_sha"] == acquired.get("git_sha"),
        }

    pin = mobile_doctor.flutter_pin(root)
    runners = {"mobile-session": CLI_VERSION}
    if pin:
        runners["flutter"] = pin

    document = session_evidence.build_evidence(
        session_id=str(lease["session_id"]),
        source=live_source,
        target={
            "platform": lease["platform"],
            "device": (lease.get("device") or {}).get("label") if isinstance(lease.get("device"), Mapping) else None,
            "os": None,
            "app_id": lease.get("app_id", DEFAULT_APP_IDS.get(str(lease["platform"]), "unknown")),
            "flavor": lease.get("flavor", DEFAULT_FLAVOR),
            "profile": lease.get("profile", DEFAULT_PROFILE),
        },
        endpoints={
            "api_base_url": f"http://127.0.0.1:{ports['backend']}/",
            "auth_emulator_host": f"127.0.0.1:{ports['auth']}",
            "firestore_emulator_host": f"127.0.0.1:{ports['firestore']}",
            "redis_url": f"redis://127.0.0.1:{ports['redis']}/0?omi_instance={lease['harness_instance']}",
            "egress_policy": session_evidence.EGRESS_POLICY,
        },
        fixtures={
            "fixture_version": str(lease.get("fixture_version", mobile_fixtures.CURRENT_FIXTURE_VERSION)),
            "auth_uid": lease.get("default_auth_uid"),
        },
        runners=runners,
        status=(
            {"state": resolved_state}
            if resolved_state != "blocked"
            else {
                "state": "blocked",
                "blocked_reason": str(lease.get("blocked_reason", "blocked")),
            }
        ),
        timestamps={
            "created_at": str(lease.get("created_at", session_evidence.utc_now())),
            **({"started_at": str(lease["started_at"])} if lease.get("started_at") else {}),
            **({"ended_at": str(lease["stopped_at"])} if lease.get("stopped_at") else {}),
        },
        artifact=artifact,
        counts=dict(counts) if counts else None,
        artifacts=artifact_files,
    )
    return document


def evidence(
    repo_root: Path,
    session_id: str,
    env: Mapping[str, str] | None = None,
    *,
    artifact_path: Path | None = None,
    state: str | None = None,
    counts: Mapping[str, int] | None = None,
    artifact_files: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    directory = session_dir(repo_root, session_id, env)
    lease = _load_lease(directory / LEASE_FILENAME)
    document = build_session_evidence(
        repo_root,
        lease,
        artifact_path=artifact_path,
        state=state,
        counts=counts,
        artifact_files=artifact_files,
    )
    session_evidence.write_evidence(directory / EVIDENCE_FILENAME, document)
    return document


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit(payload: Mapping[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    elif isinstance(payload, Mapping):
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                print(f"{key}: {json.dumps(value, indent=2, sort_keys=True, default=str)}")
            else:
                print(f"{key}: {value}")
    else:
        print(payload)


def _repo_root_from_cwd() -> Path:
    return config.repo_root_from(Path.cwd())


def build_parser() -> argparse.ArgumentParser:
    from . import device_lease  # lazy: device_lease builds on this module's primitives

    parser = argparse.ArgumentParser(prog="mobile-session", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"mobile-session {CLI_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="structured readiness report")
    doctor.add_argument("--platform", action="append", choices=[mobile_doctor.LANE_ANDROID, mobile_doctor.LANE_IOS])
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--min-free-gb", type=float, default=mobile_doctor.MIN_FREE_GB_EMULATOR_LANES)
    doctor.add_argument("--skip-capacity", action="store_true")

    listing = sub.add_parser("list", help="list sessions")
    listing.add_argument("--json", action="store_true")

    acq = sub.add_parser("acquire", help="atomically acquire an isolated session lease")
    acq.add_argument("--name", help="session name suffix (default: generated)")
    acq.add_argument("--platform", default="android", choices=list(PLATFORMS))
    acq.add_argument("--fixture-version", default=mobile_fixtures.CURRENT_FIXTURE_VERSION)
    acq.add_argument("--offset", type=int, default=None, help="explicit port offset (default: auto)")
    acq.add_argument("--json", action="store_true")

    for name, help_text in (
        ("start", "start session-owned services (and device lease)"),
        ("seed", "seed the synthetic auth fixture user"),
        ("reset", "reset only this session's synthetic state (idempotent)"),
        ("status", "lease + seed + evidence snapshot"),
        ("stop", "stop session-owned services/device (idempotent)"),
        ("recover", "take over a lease whose owner is dead on this host"),
        ("release", "stop, free the port claim, remove session state (idempotent)"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("session_id")
        command.add_argument("--json", action="store_true")
        if name == "start":
            command.add_argument("--no-device", action="store_true", help="services only; skip the device lease")

    live = sub.add_parser("live", help="V1 live Flutter broker (pending implementation)")
    live.add_argument(
        "operation", choices=("start", "reload", "restart", "screenshot", "logs", "controls", "status", "stop")
    )
    live.add_argument("session_id")
    live.add_argument("--params", type=json.loads, default={}, help="operation-specific JSON object")
    live.add_argument("--json", action="store_true")

    ev = sub.add_parser("evidence", help="emit/refresh the session-evidence-v1 receipt")
    ev.add_argument("session_id")
    ev.add_argument("--artifact", type=Path, default=None, help="built app (apk/bundle) to bind")
    ev.add_argument("--state", default=None, choices=list(session_evidence.STATES))
    ev.add_argument("--json", action="store_true")
    device = sub.add_parser("device", help="C5 physical-device lane: leases + qualification runner")
    device.add_argument("--json", action="store_true")
    device_sub = device.add_subparsers(dest="device_command", required=True)

    dev_doctor = device_sub.add_parser("doctor", help="read-only physical-device readiness report")
    # Sibling of `mobile-session doctor --json`: accept the flag after the
    # subcommand as well as `device --json doctor`.
    dev_doctor.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    dev_doctor.add_argument("--platform", action="append", choices=list(device_lease.PLATFORMS))

    dev_register = device_sub.add_parser(
        "register", help="register a dedicated test device (personal devices are refused)"
    )
    dev_register.add_argument("--platform", required=True, choices=list(device_lease.PLATFORMS))
    dev_register.add_argument("--device-id", required=True)
    dev_register.add_argument("--label", default="")
    dev_register.add_argument("--os-version", default="")
    dev_register.add_argument("--confirm-test-device", action="store_true")

    dev_deregister = device_sub.add_parser("deregister", help="remove a device from the qualification registry")
    dev_deregister.add_argument("--platform", required=True, choices=list(device_lease.PLATFORMS))
    dev_deregister.add_argument("--device-id", required=True)

    dev_list = device_sub.add_parser("list", help="registry + lease status")
    dev_list.add_argument("--platform", choices=list(device_lease.PLATFORMS))
    dev_list.add_argument("--device-id", default=None)

    dev_acquire = device_sub.add_parser("acquire", help="acquire the exclusive device lease")
    dev_acquire.add_argument("--platform", required=True, choices=list(device_lease.PLATFORMS))
    dev_acquire.add_argument("--device-id", required=True)
    dev_acquire.add_argument("--purpose", required=True)
    dev_acquire.add_argument("--session", default=None, help="bind to a C1 mobile session id")
    dev_acquire.add_argument("--wait-timeout", type=float, default=0.0, dest="wait_timeout_s")

    for name, help_text in (
        ("release", "release the caller's device lease (idempotent)"),
        ("recover", "take over a provably stale same-host device lease"),
        ("status", "one device's registry + lease state"),
        ("heartbeat", "refresh the caller's device lease liveness (call during long runs)"),
    ):
        command = device_sub.add_parser(name, help=help_text)
        command.add_argument("--platform", required=True, choices=list(device_lease.PLATFORMS))
        command.add_argument("--device-id", required=True)

    dev_run = device_sub.add_parser("run", help="automatable part of a qualification run against a leased device")
    dev_run.add_argument("--session", required=True, help="C1 mobile session id (manifest: ports/fixture/app id)")
    dev_run.add_argument("--platform", required=True, choices=list(device_lease.PLATFORMS))
    dev_run.add_argument("--device-id", required=True)
    dev_run.add_argument("--artifact", type=Path, required=True, help="built apk/ipa to install")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    repo_root = _repo_root_from_cwd()
    try:
        if args.command == "live":
            from . import live_session

            if not isinstance(args.params, dict):
                raise SessionError("live --params must be a JSON object")
            try:
                result = live_session.dispatch(repo_root, args.session_id, args.operation, args.params)
            except live_session.SessionError as exc:
                # `python -m` loads this module as __main__; the broker imports
                # its canonical module identity. Normalize across that boundary.
                raise SessionError(str(exc)) from None
            _emit(result, as_json=args.json)
            return {"ok": 0, "rejected": 1, "restart-required": 2, "blocked": 2}.get(result.get("outcome"), 2)
        if args.command == "doctor":
            report = mobile_doctor.run_doctor(
                repo_root,
                platforms=tuple(args.platform or ()),
                min_free_gb=args.min_free_gb,
                skip_capacity=args.skip_capacity,
            )
            if args.json:
                _emit(report.as_dict(), as_json=True)
            else:
                print(mobile_doctor.format_report_text(report))
            return {"ready": 0, "degraded": 1, "blocked": 2}[report.overall]
        if args.command == "list":
            _emit({"sessions": list_sessions(repo_root)}, as_json=args.json)
            return 0
        if args.command == "acquire":
            lease = acquire(
                repo_root,
                name=args.name,
                platform_name=args.platform,
                fixture_version=args.fixture_version,
                offset=args.offset,
            )
            _emit(lease, as_json=args.json)
            return 0
        if args.command == "start":
            lease = start(repo_root, args.session_id, attach_device=not args.no_device)
            _emit(lease, as_json=args.json)
            return 0
        if args.command == "seed":
            _emit(seed(repo_root, args.session_id), as_json=args.json)
            return 0
        if args.command == "reset":
            _emit(reset(repo_root, args.session_id), as_json=args.json)
            return 0
        if args.command == "status":
            _emit(status(repo_root, args.session_id), as_json=args.json)
            return 0
        if args.command == "evidence":
            _emit(
                evidence(repo_root, args.session_id, artifact_path=args.artifact, state=args.state), as_json=args.json
            )
            return 0
        if args.command == "stop":
            _emit(stop(repo_root, args.session_id), as_json=args.json)
            return 0
        if args.command == "recover":
            _emit(recover(repo_root, args.session_id), as_json=args.json)
            return 0
        if args.command == "release":
            _emit(release(repo_root, args.session_id), as_json=args.json)
            return 0
        if args.command == "device":
            return _dispatch_device(args, repo_root)
    except (SessionError, safety.SafetyError, EvidenceError, mobile_fixtures.FixtureError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled command {args.command!r}")


def _default_device_runner(command: Sequence[str]) -> tuple[int, str]:
    # Default device-tooling seam (adb / xcrun devicectl): a missing binary is
    # exit 127 + message so doctor/run classify it as a remediable failure —
    # DeviceRunnerError from the tooling shims — instead of a raw traceback.
    try:
        completed = subprocess.run(list(command), capture_output=True, text=True, check=False, timeout=180)
    except OSError as exc:
        return 127, f"{command[0]} not available: {exc}"
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def _dispatch_device(args: argparse.Namespace, repo_root: Path) -> int:
    """C5 physical-device lane (SCA-491). Imported lazily: device_lease and
    device_runner build on this module's ownership primitives, so a module-
    level import would be circular."""

    from . import device_lease, device_runner

    try:
        if args.device_command == "doctor":
            platforms = args.platform or ["android", "ios"]
            report = device_runner.device_doctor(
                repo_root,
                android=device_runner.AndroidTooling(_default_device_runner) if "android" in platforms else None,
                ios=device_runner.IosTooling(_default_device_runner) if "ios" in platforms else None,
            )
            _emit(report, as_json=args.json)
            statuses = {check["status"] for check in report["checks"]}
            if "operator-action-needed" in statuses or "agent-remediable" in statuses:
                return 2
            return 0
        if args.device_command == "register":
            _emit(
                device_lease.register_device(
                    repo_root,
                    args.platform,
                    args.device_id,
                    label=args.label,
                    os_version=args.os_version,
                    confirm=args.confirm_test_device,
                ),
                as_json=args.json,
            )
            return 0
        if args.device_command == "deregister":
            _emit(device_lease.deregister_device(repo_root, args.platform, args.device_id), as_json=args.json)
            return 0
        if args.device_command == "list":
            _emit(device_lease.status(repo_root, platform=args.platform, device_id=args.device_id), as_json=args.json)
            return 0
        if args.device_command == "acquire":
            _emit(
                device_lease.acquire(
                    repo_root,
                    args.platform,
                    args.device_id,
                    purpose=args.purpose,
                    session_id=args.session,
                    wait_timeout_s=args.wait_timeout_s,
                ),
                as_json=args.json,
            )
            return 0
        if args.device_command == "release":
            _emit(device_lease.release(repo_root, args.platform, args.device_id), as_json=args.json)
            return 0
        if args.device_command == "recover":
            _emit(device_lease.recover(repo_root, args.platform, args.device_id), as_json=args.json)
            return 0
        if args.device_command == "heartbeat":
            _emit(device_lease.heartbeat(repo_root, args.platform, args.device_id), as_json=args.json)
            return 0
        if args.device_command == "status":
            _emit(device_lease.status(repo_root, platform=args.platform, device_id=args.device_id), as_json=args.json)
            return 0
        if args.device_command == "run":
            tooling = (
                device_runner.AndroidTooling(_default_device_runner)
                if args.platform == "android"
                else device_runner.IosTooling(_default_device_runner)
            )
            receipt = device_runner.run(
                repo_root,
                args.session,
                args.platform,
                args.device_id,
                artifact=args.artifact,
                **({"android": tooling} if args.platform == "android" else {"ios": tooling}),
            )
            _emit(receipt, as_json=args.json)
            return 0
    except (device_lease.DeviceLeaseError, device_runner.DeviceRunnerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled device command {args.device_command!r}")


if __name__ == "__main__":
    raise SystemExit(main())

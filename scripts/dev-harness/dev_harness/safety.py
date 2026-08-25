"""Fail-closed safety guards for the local dev harness.

This module is intentionally side-effect light: it validates local-only Firebase
emulator configuration, builds sanitized child environments, owns state under a
sentinel-protected root, and verifies process/port ownership from manifests.
It does not start emulators or desktop apps.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _SYNCHRONIZE = 0x00100000
    _WAIT_OBJECT_0 = 0
    _WAIT_TIMEOUT = 258
    _WAIT_FAILED = 0xFFFFFFFF
    _ERROR_ACCESS_DENIED = 5
    _ERROR_INVALID_PARAMETER = 87

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _open_process = _kernel32.OpenProcess
    _open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _open_process.restype = wintypes.HANDLE
    _wait_for_single_object = _kernel32.WaitForSingleObject
    _wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    _wait_for_single_object.restype = wintypes.DWORD
    _close_handle = _kernel32.CloseHandle
    _close_handle.argtypes = (wintypes.HANDLE,)
    _close_handle.restype = wintypes.BOOL
    _get_system_directory = _kernel32.GetSystemDirectoryW
    _get_system_directory.argtypes = (wintypes.LPWSTR, wintypes.UINT)
    _get_system_directory.restype = wintypes.UINT

    def _windows_powershell_executable() -> Path:
        buffer = ctypes.create_unicode_buffer(32768)
        length = _get_system_directory(buffer, len(buffer))
        if length == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        if length >= len(buffer):
            raise OSError("Windows system directory exceeds the supported path length")
        return Path(buffer.value) / "WindowsPowerShell" / "v1.0" / "powershell.exe"


DEFAULT_LOCAL_FIREBASE_PROJECT_ID = "demo-omi-local"
DEFAULT_FIRESTORE_DATABASE_ID = "(default)"
DEFAULT_INSTANCE_NAME = "default"
HARNESS_SENTINEL_FILENAME = ".omi-dev-harness-owned.json"
SENTINEL_SCHEMA_VERSION = 1

_STATE_SUBDIRECTORIES = (
    "manifests",
    "logs",
    "reports",
    "services",
    "services/firestore",
    "services/auth",
    "services/redis",
    "services/typesense",
    "files",
)

_ALLOWED_INSTANCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_ALLOWED_ENV_KEYS = {
    "CI",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOGNAME",
    "NODE_ENV",
    "PATH",
    "PWD",
    "PYTHONPATH",
    "SHELL",
    "TMPDIR",
    "USER",
    "VIRTUAL_ENV",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
}
_STRIPPED_EXACT_ENV_KEYS = {
    "CLOUDSDK_CONFIG",
    "CLOUDSDK_CORE_PROJECT",
    "FIREBASE_CONFIG",
    "FIREBASE_PROJECT",
    "FIREBASE_TOKEN",
    "GCP_PROJECT",
    "GCLOUD_PROJECT",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_APPLICATION_CREDENTIALS_JSON",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_QUOTA_PROJECT",
    "GOOGLE_PROJECT_ID",
}
_STRIPPED_ENV_PREFIXES = (
    "GOOGLE_SERVICE_ACCOUNT",
    "SERVICE_ACCOUNT",
    "FIREBASE_ADMIN",
)
_LOCAL_BACKEND_SECRET_KEYS = {
    "ENCRYPTION_SECRET",
    "ADMIN_KEY",
    "TYPESENSE_API_KEY",
    "FIREBASE_API_KEY",
    # Harness-local HMAC key for internal screen-frame approval tokens. Matches
    # _PROVIDER_SECRET_RE on "SECRET" but is not a provider credential, so offline
    # mode must pass it through rather than refuse it.
    "SCREEN_FRAME_SIGNING_SECRET",
}
_OFFLINE_PROVIDER_PLACEHOLDERS = {
    "OPENAI_API_KEY": "sk-omi-local-harness-offline-not-real",
    "DEEPGRAM_API_KEY": "omi-local-harness-offline-deepgram-not-real",
    "GEMINI_API_KEY": "omi-local-harness-offline-gemini-not-real",
    "ANTHROPIC_API_KEY": "omi-local-harness-offline-anthropic-not-real",
}
_PROVIDER_SECRET_RE = re.compile(
    r"(API_KEY|ACCESS_TOKEN|AUTH_TOKEN|SECRET|DEEPGRAM|OPENAI|ANTHROPIC|GROQ|ELEVENLABS)", re.IGNORECASE
)
_LOOPBACK_NAMES = {"localhost"}
_DANGEROUS_NAMES = {"", ".", ".."}


class SafetyError(RuntimeError):
    """Raised when the local harness would cross a safety boundary."""


@dataclass(frozen=True)
class HarnessLayout:
    repo_root: Path
    state_root: Path
    instance: str
    sentinel_path: Path
    process_manifest: Path
    port_manifest: Path
    config_digest_path: Path
    logs_dir: Path
    reports_dir: Path
    services_dir: Path


def _real(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def validate_project_id(project_id: str, *, require_canonical: bool = False) -> str:
    value = (project_id or "").strip()
    if not value:
        raise SafetyError("Firebase project ID is required")
    if not value.startswith("demo-"):
        raise SafetyError(f"Refusing non-demo Firebase project ID: {value!r}")
    if require_canonical and value != DEFAULT_LOCAL_FIREBASE_PROJECT_ID:
        raise SafetyError(f"Local harness project must be {DEFAULT_LOCAL_FIREBASE_PROJECT_ID!r}, got {value!r}")
    return value


def validate_database_id(database_id: str) -> str:
    value = (database_id or "").strip()
    if value != DEFAULT_FIRESTORE_DATABASE_ID:
        raise SafetyError(f"Local harness Firestore database must be {DEFAULT_FIRESTORE_DATABASE_ID!r}, got {value!r}")
    return value


def _host_from_emulator_value(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise SafetyError("Emulator host is required")
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = parsed.hostname
    if not host:
        raise SafetyError(f"Invalid emulator host {value!r}")
    return host.strip("[]").lower()


def is_loopback_host(value: str) -> bool:
    host = _host_from_emulator_value(value)
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_loopback_emulator_host(value: str, *, name: str = "emulator") -> str:
    if not is_loopback_host(value):
        raise SafetyError(f"{name} host must point to loopback, got {value!r}")
    return value.strip()


# Private ranges a LAN- or tailnet-reachable dev harness may bind to. Distinct
# from the loopback-only guard above, which protects a different boundary: the
# backend's own connection to its co-located emulators, which must never leave
# loopback regardless of this setting. RFC 1918 covers ordinary LAN addresses;
# 100.64.0.0/10 (RFC 6598 carrier-grade NAT) covers Tailscale, whose tailnet
# addresses fall in that range and are the documented way a physical device
# reaches this harness (see #11730/#11652).
_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
)


def is_private_dev_host(value: str) -> bool:
    """True for loopback or a non-public (LAN/CGNAT) address, never a public one."""

    if is_loopback_host(value):
        return True
    host = _host_from_emulator_value(value)
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(addr in network for network in _PRIVATE_NETWORKS)


def validate_dev_bind_host(value: str, *, name: str = "dev bind host") -> str:
    """Fail closed unless the requested bind host is loopback or a private range.

    Distinct from ``validate_loopback_emulator_host``: this guards what the
    harness's own HTTP services and Firebase emulators may bind to when a
    developer opts into LAN/tailnet reachability, never a publicly routable
    address.
    """

    if not is_private_dev_host(value):
        raise SafetyError(f"{name} must be loopback or a private (LAN/CGNAT) address, got {value!r}")
    return value.strip()


def validate_harness_runtime_config(
    *,
    project_id: str,
    database_id: str,
    emulator_hosts: Mapping[str, str],
    require_canonical_project: bool = True,
) -> None:
    validate_project_id(project_id, require_canonical=require_canonical_project)
    validate_database_id(database_id)
    for name, host in emulator_hosts.items():
        validate_loopback_emulator_host(host, name=name)


def offline_provider_placeholders() -> dict[str, str]:
    """Non-secret placeholders so backend modules can import under PROVIDER_MODE=offline."""

    return dict(_OFFLINE_PROVIDER_PLACEHOLDERS)


def build_child_env(
    parent: Mapping[str, str] | None = None,
    *,
    extra: Mapping[str, str] | None = None,
    provider_mode: str = "real",
) -> dict[str, str]:
    """Return an allowlisted child environment with cloud defaults stripped.

    ``extra`` is explicit and may set harness-local values. It may not re-add ADC,
    service-account, production Firebase, or gcloud default variables.
    """

    source = dict(os.environ if parent is None else parent)
    child: dict[str, str] = {}
    for key, value in source.items():
        if key in _STRIPPED_EXACT_ENV_KEYS or key.startswith(_STRIPPED_ENV_PREFIXES):
            continue
        if provider_mode == "offline" and _PROVIDER_SECRET_RE.search(key):
            continue
        if key in _ALLOWED_ENV_KEYS or key.startswith("OMI_"):
            child[key] = value

    child.update(
        {
            "FIREBASE_PROJECT_ID": DEFAULT_LOCAL_FIREBASE_PROJECT_ID,
            "FIRESTORE_DATABASE_ID": DEFAULT_FIRESTORE_DATABASE_ID,
            "PROVIDER_MODE": provider_mode,
        }
    )

    for key, value in (extra or {}).items():
        if key in _STRIPPED_EXACT_ENV_KEYS or key.startswith(_STRIPPED_ENV_PREFIXES):
            raise SafetyError(f"Refusing to pass unsafe child environment variable {key}")
        if provider_mode == "offline" and key not in _LOCAL_BACKEND_SECRET_KEYS and _PROVIDER_SECRET_RE.search(key):
            raise SafetyError(f"Refusing provider credential {key} in offline provider mode")
        child[key] = value

    return child


def validate_instance_name(instance: str) -> str:
    value = (instance or DEFAULT_INSTANCE_NAME).strip()
    if not _ALLOWED_INSTANCE_RE.fullmatch(value) or value in _DANGEROUS_NAMES:
        raise SafetyError(f"Invalid local harness instance name: {instance!r}")
    return value


def default_state_base(repo_root: Path, env: Mapping[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    configured = source.get("OMI_LOCAL_STATE_ROOT")
    return _real(Path(configured)) if configured else _real(Path(repo_root) / ".local" / "dev-harness")


def state_root_for_instance(
    repo_root: Path, instance: str = DEFAULT_INSTANCE_NAME, env: Mapping[str, str] | None = None
) -> Path:
    name = validate_instance_name(instance)
    base = default_state_base(repo_root, env)
    root = _real(base / name)
    if (
        root == _real(Path(repo_root))
        or _real(Path(repo_root)) in {root, *root.parents}
        and root == _real(Path(repo_root))
    ):
        raise SafetyError("Harness state root cannot be the repository root")
    return root


def layout_for_instance(
    repo_root: Path, instance: str = DEFAULT_INSTANCE_NAME, env: Mapping[str, str] | None = None
) -> HarnessLayout:
    repo = _real(Path(repo_root))
    state_root = state_root_for_instance(repo, instance, env)
    return HarnessLayout(
        repo_root=repo,
        state_root=state_root,
        instance=validate_instance_name(instance),
        sentinel_path=state_root / HARNESS_SENTINEL_FILENAME,
        process_manifest=state_root / "manifests" / "processes.json",
        port_manifest=state_root / "manifests" / "ports.json",
        config_digest_path=state_root / "config-digest.json",
        logs_dir=state_root / "logs",
        reports_dir=state_root / "reports",
        services_dir=state_root / "services",
    )


def create_state_layout(
    repo_root: Path, instance: str = DEFAULT_INSTANCE_NAME, env: Mapping[str, str] | None = None
) -> HarnessLayout:
    layout = layout_for_instance(repo_root, instance, env)
    validate_safe_state_root(layout.state_root, layout.repo_root)
    layout.state_root.mkdir(parents=True, exist_ok=True)
    for relative in _STATE_SUBDIRECTORIES:
        (layout.state_root / relative).mkdir(parents=True, exist_ok=True)
    sentinel = {
        "schema_version": SENTINEL_SCHEMA_VERSION,
        "owner": "omi-local-dev-harness",
        "project_id": DEFAULT_LOCAL_FIREBASE_PROJECT_ID,
        "database_id": DEFAULT_FIRESTORE_DATABASE_ID,
        "instance": layout.instance,
        "repo_root": str(layout.repo_root),
    }
    layout.sentinel_path.write_text(json.dumps(sentinel, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return layout


def read_and_validate_sentinel(
    state_root: Path, *, repo_root: Path | None = None, instance: str | None = None
) -> dict[str, object]:
    root = _real(Path(state_root))
    sentinel_path = root / HARNESS_SENTINEL_FILENAME
    if not sentinel_path.is_file():
        raise SafetyError(f"Missing harness ownership sentinel at {sentinel_path}")
    try:
        data = json.loads(sentinel_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SafetyError(f"Invalid harness ownership sentinel: {exc}") from exc
    expected = {
        "schema_version": SENTINEL_SCHEMA_VERSION,
        "owner": "omi-local-dev-harness",
        "project_id": DEFAULT_LOCAL_FIREBASE_PROJECT_ID,
        "database_id": DEFAULT_FIRESTORE_DATABASE_ID,
    }
    for key, expected_value in expected.items():
        if data.get(key) != expected_value:
            raise SafetyError(f"Invalid harness sentinel {key}: {data.get(key)!r}")
    if instance is not None and data.get("instance") != validate_instance_name(instance):
        raise SafetyError(f"Harness sentinel belongs to instance {data.get('instance')!r}, not {instance!r}")
    if repo_root is not None and _real(Path(str(data.get("repo_root", "")))) != _real(Path(repo_root)):
        raise SafetyError("Harness sentinel belongs to a different repository root")
    return data


def validate_safe_state_root(state_root: Path, repo_root: Path) -> Path:
    root = _real(Path(state_root))
    repo = _real(Path(repo_root))
    home = _real(Path.home())
    if str(root) in _DANGEROUS_NAMES:
        raise SafetyError("Harness state root is empty or relative-dangerous")
    if root == Path(root.anchor) or root == home or root == repo:
        raise SafetyError(f"Refusing unsafe harness state root {root}")
    if root in repo.parents:
        raise SafetyError(f"Harness state root cannot be a parent of the repository: {root}")
    return root


def validate_destructive_target(target: Path, *, state_root: Path, repo_root: Path | None = None) -> Path:
    raw = str(target)
    if not raw or raw in _DANGEROUS_NAMES:
        raise SafetyError(f"Refusing dangerous destructive target {raw!r}")
    resolved = _real(Path(target))
    state = _real(Path(state_root))
    home = _real(Path.home())
    repo = _real(Path(repo_root)) if repo_root is not None else None
    if resolved == Path(resolved.anchor) or resolved == home or (repo is not None and resolved == repo):
        raise SafetyError(f"Refusing dangerous destructive target {resolved}")
    if resolved != state and state not in resolved.parents:
        raise SafetyError(f"Destructive target {resolved} is outside harness state root {state}")
    read_and_validate_sentinel(state, repo_root=repo_root)
    return resolved


def load_json_file(path: Path) -> object:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        handle = _open_process(_SYNCHRONIZE, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == _ERROR_INVALID_PARAMETER:
                return False
            if error == _ERROR_ACCESS_DENIED:
                return True
            raise ctypes.WinError(error)
        try:
            wait_result = _wait_for_single_object(handle, 0)
            if wait_result == _WAIT_TIMEOUT:
                return True
            if wait_result == _WAIT_OBJECT_0:
                return False
            if wait_result == _WAIT_FAILED:
                raise ctypes.WinError(ctypes.get_last_error())
            raise SafetyError(f"Unexpected Windows process wait result for PID {pid}: {wait_result}")
        finally:
            if not _close_handle(handle) and sys.exc_info()[0] is None:
                raise ctypes.WinError(ctypes.get_last_error())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def command_line_for_pid(pid: int) -> str:
    if os.name == "nt":
        if pid <= 0:
            return ""
        command = (
            "$ErrorActionPreference = 'Stop'; "
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
            f"$process = Get-CimInstance Win32_Process -Filter 'ProcessId = {int(pid)}'; "
            "if ($null -eq $process) { exit 1 }; "
            "[Console]::Out.Write($process.CommandLine)"
        )
        try:
            result = subprocess.run(
                [
                    str(_windows_powershell_executable()),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    command,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""

    proc_cmdline = Path("/proc") / str(pid) / "cmdline"
    if proc_cmdline.exists():
        return proc_cmdline.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except OSError:
        return ""


def listening_pids(port: int) -> tuple[int, ...]:
    """Return the current loopback listener PIDs or fail closed when discovery is unavailable."""

    if not 1 <= int(port) <= 65535:
        raise SafetyError(f"Invalid port {port}")
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-t"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise SafetyError(f"Cannot inspect listener ownership for port {port}") from exc
    if result.returncode not in {0, 1}:
        raise SafetyError(f"Cannot inspect listener ownership for port {port}")
    try:
        pids = tuple(sorted({int(line) for line in result.stdout.splitlines() if line.strip()}))
    except ValueError as exc:
        raise SafetyError(f"Invalid listener PID output for port {port}") from exc
    if any(pid <= 0 for pid in pids):
        raise SafetyError(f"Invalid listener PID output for port {port}")
    return pids


def is_descendant_of(pid: int, ancestor_pid: int) -> bool:
    """Prove a live child belongs to a recorded supervisor without command matching."""

    current = int(pid)
    ancestor = int(ancestor_pid)
    seen: set[int] = set()
    while current > 1 and current not in seen:
        if current == ancestor:
            return True
        seen.add(current)
        try:
            result = subprocess.run(
                ["ps", "-p", str(current), "-o", "ppid="],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            parent = int(result.stdout.strip()) if result.returncode == 0 else -1
        except (OSError, ValueError):
            return False
        current = parent
    return current == ancestor


def descendant_pids(ancestor_pid: int) -> tuple[int, ...]:
    """Snapshot the live descendants of a supervised PID before it is signalled.

    Emulator CLIs spawn their heavyweight children detached (`firebase
    emulators:start` gives the Firestore JVM its own session), so a process
    group signal never reaches them. Once the supervisor dies the survivors are
    reparented to init and the tree is unrecoverable, so teardown has to capture
    it first.
    """

    ancestor = int(ancestor_pid)
    if ancestor <= 1:
        return ()
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return ()
    if result.returncode != 0:
        return ()
    children: dict[int, list[int]] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            pid, parent = int(fields[0]), int(fields[1])
        except ValueError:
            continue
        children.setdefault(parent, []).append(pid)
    found: set[int] = set()
    queue = list(children.get(ancestor, ()))
    while queue:
        pid = queue.pop()
        if pid in found or pid == ancestor:
            continue
        found.add(pid)
        queue.extend(children.get(pid, ()))
    return tuple(sorted(found))


def validate_owned_pid(pid: int, *, process_manifest: Path, service: str | None = None) -> dict[str, object]:
    manifest = load_json_file(process_manifest)
    records = manifest.get("processes") if isinstance(manifest, dict) else None
    if not isinstance(records, list):
        raise SafetyError(f"Invalid process manifest {process_manifest}")
    for record in records:
        if not isinstance(record, dict) or int(record.get("pid", -1)) != int(pid):
            continue
        if service is not None and record.get("service") != service:
            raise SafetyError(f"PID {pid} is owned by service {record.get('service')!r}, not {service!r}")
        if not process_exists(pid):
            raise SafetyError(f"Recorded PID {pid} is not running")
        marker = str(record.get("ownership_marker", ""))
        if marker and marker not in command_line_for_pid(pid):
            raise SafetyError(f"PID {pid} command line does not contain harness ownership marker")
        return record
    raise SafetyError(f"Refusing foreign PID {pid}; not present in harness process manifest")


def terminate_owned_pid(
    pid: int, *, process_manifest: Path, service: str | None = None, sig: signal.Signals = signal.SIGTERM
) -> None:
    validate_owned_pid(pid, process_manifest=process_manifest, service=service)
    os.kill(pid, sig)


def validate_port_owner(
    port: int,
    *,
    pid: int | None,
    port_manifest: Path,
    process_manifest: Path | None = None,
    service: str | None = None,
) -> dict[str, object]:
    if int(port) <= 0 or int(port) > 65535:
        raise SafetyError(f"Invalid port {port}")
    manifest = load_json_file(port_manifest)
    records = manifest.get("ports") if isinstance(manifest, dict) else None
    if not isinstance(records, list):
        raise SafetyError(f"Invalid port manifest {port_manifest}")
    for record in records:
        if not isinstance(record, dict) or int(record.get("port", -1)) != int(port):
            continue
        recorded_pid = int(record.get("pid", -1))
        if pid is not None and recorded_pid != int(pid):
            raise SafetyError(f"Foreign process owns port {port}: expected PID {recorded_pid}, got PID {pid}")
        if service is not None and record.get("service") != service:
            raise SafetyError(f"Port {port} is owned by service {record.get('service')!r}, not {service!r}")
        if process_manifest is not None:
            validate_owned_pid(recorded_pid, process_manifest=process_manifest, service=record.get("service"))
        return record
    raise SafetyError(f"Foreign or unrecorded process owns port {port}; harness will not kill or hop ports")


def validate_redis_reset_target(redis_url: str, *, state_root: Path, expected_instance: str) -> str:
    """Refuse Redis resets unless the URL is loopback and namespaced per instance.

    Shared Redis URLs such as redis://localhost:6379/0 are rejected. Harness
    callers should use a URL with query parameter ``omi_instance=<instance>`` or
    a loopback Unix socket path under the harness state root.
    """

    raw = (redis_url or "").strip()
    if not raw:
        raise SafetyError("Redis URL is required before reset")
    parsed = urlparse(raw)
    if parsed.scheme in {"redis", "rediss"}:
        host = parsed.hostname or ""
        validate_loopback_emulator_host(host, name="Redis")
        query = dict(part.split("=", 1) for part in parsed.query.split("&") if "=" in part)
        if query.get("omi_instance") != validate_instance_name(expected_instance):
            raise SafetyError("Refusing to reset shared Redis without matching omi_instance namespace")
        return raw
    if parsed.scheme == "unix":
        path = _real(Path(parsed.path))
        state = _real(Path(state_root))
        if path != state and state not in path.parents:
            raise SafetyError("Redis Unix socket is outside harness state root")
        return raw
    raise SafetyError(f"Unsupported Redis URL for harness reset: {redis_url!r}")

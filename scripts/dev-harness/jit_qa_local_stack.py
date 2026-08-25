"""Fail-closed local backend stack for the ``omi-jit-qa`` bundle.

This is deliberately a separate entry point from the general offline harness.
It is a hybrid stack: Firebase ID tokens are verified against the configured
Firebase Auth project and Vertex uses development ADC, while all Firestore
traffic is forced to an owned emulator and Redis is forced to an owned
loopback instance.  No production API or shared Firestore path is accepted.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MAIN_PORT = 18080
DESKTOP_PORT = 18081
FIRESTORE_PORT = 18082
REDIS_PORT = 18083
VERTEX_GATEWAY_PORT = 18084
LOCAL_FIREBASE_PROJECT = "demo-omi-jit-qa"
DEV_GCP_PROJECT = "based-hardware-dev"
DEFAULT_AUTH_PROJECT = "based-hardware"
STATE_DIR_NAME = "jit-qa-local-dev-gcp"
OWNERSHIP_PREFIX = "omi-jit-qa-local"
HEALTH_TIMEOUT_SECONDS = 180
CLOUD_READINESS_TIMEOUT_SECONDS = 30.0
OWNED_SERVICES = frozenset({"firestore", "redis", "vertex-gateway", "main", "desktop"})


class SafetyError(RuntimeError):
    """The hybrid contract cannot be proved without crossing a boundary."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _state_root(repo_root: Path) -> Path:
    raw = os.environ.get("OMI_JIT_QA_LOCAL_STATE_ROOT", "").strip()
    root = Path(raw).expanduser() if raw else repo_root / ".dev" / STATE_DIR_NAME
    root = root.resolve()
    # The default is deliberately narrow.  An override is useful for a parallel
    # local run, but it must still be a clearly named harness directory.
    if root.name != STATE_DIR_NAME and not root.name.startswith(f"{STATE_DIR_NAME}-"):
        raise SafetyError(f"state root must end in {STATE_DIR_NAME!r}, got {root}")
    if root != repo_root and root.parent == (repo_root / ".dev").resolve():
        return root
    if os.environ.get("JIT_QA_TEST_MODE") == "1" and root.parent in {
        Path("/tmp").resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }:
        return root
    raise SafetyError("state root must be under this checkout's .dev directory")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _single_link_regular_file(path: Path, *, label: str) -> os.stat_result:
    """Return lstat data only for a regular file owned by this one pathname."""

    try:
        details = path.lstat()
    except OSError as exc:
        raise SafetyError(f"could not inspect {label}: {path}") from exc
    if not stat.S_ISREG(details.st_mode):
        raise SafetyError(f"refusing non-regular {label}: {path}")
    if details.st_nlink != 1:
        raise SafetyError(f"refusing hardlinked {label}: {path}")
    return details


def _read_json(path: Path, default: Any) -> Any:
    if path.is_symlink():
        raise SafetyError(f"refusing symlinked state file: {path}")
    if not path.exists():
        return default
    _single_link_regular_file(path, label="JSON state file")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SafetyError(f"refusing unreadable or malformed JSON state: {path}") from exc


def _write_private(path: Path, data: str | bytes) -> None:
    if path.is_symlink():
        raise SafetyError(f"refusing symlinked state file: {path}")
    if path.exists():
        _single_link_regular_file(path, label="state file")
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink():
            raise SafetyError(f"refusing symlinked state file: {path}")
        os.replace(temporary, path)
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary.exists():
            temporary.unlink()


def _ensure_private_dir(path: Path) -> None:
    if path.is_symlink():
        raise SafetyError(f"refusing symlinked state directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _harden_state_tree(state: Path) -> None:
    """Make every owned artifact private and reject links before traversal."""

    if state.is_symlink():
        raise SafetyError(f"refusing symlinked state root: {state}")
    if not state.exists():
        return
    for root, directory_names, file_names in os.walk(state, followlinks=False):
        root_path = Path(root)
        os.chmod(root_path, 0o700)
        for name in directory_names:
            child = root_path / name
            if child.is_symlink():
                raise SafetyError(f"refusing symlinked state directory: {child}")
            os.chmod(child, 0o700)
        for name in file_names:
            child = root_path / name
            if child.is_symlink():
                raise SafetyError(f"refusing symlinked state file: {child}")
            _single_link_regular_file(child, label="state file")
            os.chmod(child, 0o600)


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _http(
    url: str,
    timeout: float = 1.0,
    *,
    expected_text: str | None = None,
    expected_json: dict[str, Any] | None = None,
) -> tuple[bool, int | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(16_384).decode("utf-8", errors="replace")
            if response.status != 200:
                return False, response.status
            if expected_text is not None and body.strip() != expected_text:
                return False, response.status
            if expected_json is not None:
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    return False, response.status
                if not isinstance(payload, dict) or any(
                    payload.get(key) != value for key, value in expected_json.items()
                ):
                    return False, response.status
            return True, response.status
    except urllib.error.HTTPError as exc:
        return False, exc.code
    except (OSError, urllib.error.URLError):
        return False, None


def _file_mode_is_private(path: Path) -> bool:
    try:
        return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    except OSError:
        return False


def _validate_gcp_identity(auth_project: str) -> list[str]:
    """Return redacted diagnostics; never print credentials or tokens."""

    errors: list[str] = []
    if auth_project not in {"based-hardware", DEV_GCP_PROJECT}:
        errors.append("JIT_QA_FIREBASE_AUTH_PROJECT_ID must be based-hardware or based-hardware-dev")
    if auth_project == LOCAL_FIREBASE_PROJECT:
        errors.append("Firebase Auth project may not be the local emulator project")

    configured_project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if configured_project != DEV_GCP_PROJECT:
        errors.append(f"GOOGLE_CLOUD_PROJECT must be {DEV_GCP_PROJECT}")

    # Use the host's Application Default Credentials only. Explicit service
    # account files/JSON are deliberately rejected: they are long-lived,
    # powerful material and can silently retarget a child process even when
    # GOOGLE_CLOUD_PROJECT still says "dev".
    for name in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "FIREBASE_AUTH_CREDENTIALS_PATH",
        "SERVICE_ACCOUNT_JSON",
    ):
        if os.environ.get(name, "").strip():
            errors.append(f"{name} is not allowed; use development ADC")

    if os.environ.get("JIT_QA_TEST_MODE") == "1":
        return errors

    # Refreshing ADC proves that the local process can obtain a development
    # token without exposing it.  The project is checked both in env and in the
    # credential object so a configured dev label cannot mask a prod identity.
    try:
        import google.auth  # type: ignore[import-not-found]
        from google.auth.transport.requests import Request  # type: ignore[import-not-found]

        credentials, detected_project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if detected_project != DEV_GCP_PROJECT:
            errors.append("ADC resolved to a non-dev project")
        if getattr(credentials, "quota_project_id", None) != DEV_GCP_PROJECT:
            errors.append(f"ADC quota project must be {DEV_GCP_PROJECT}")
        credentials.refresh(Request())
    except Exception as exc:  # noqa: BLE001 - report only a class, never detail/token
        errors.append(f"development ADC could not be refreshed ({type(exc).__name__})")
    return errors


def _validate_contract(repo_root: Path) -> dict[str, str]:
    if os.environ.get("OMI_JIT_QA_TARGET", "local-dev-gcp") != "local-dev-gcp":
        raise SafetyError("local stack is only valid for OMI_JIT_QA_TARGET=local-dev-gcp")
    if os.environ.get("OMI_PYTHON_API_URL", "http://127.0.0.1:18080") != "http://127.0.0.1:18080":
        raise SafetyError("OMI_PYTHON_API_URL must be http://127.0.0.1:18080")
    if os.environ.get("OMI_DESKTOP_API_URL", "http://127.0.0.1:18081") != "http://127.0.0.1:18081":
        raise SafetyError("OMI_DESKTOP_API_URL must be http://127.0.0.1:18081")
    for name in ("BASE_API_URL", "API_BASE_URL"):
        if os.environ.get(name, "").strip() and os.environ[name].strip() not in {
            "http://127.0.0.1:18080",
            "http://localhost:18080",
        }:
            raise SafetyError(f"{name} must remain loopback-only")
    inherited_data_hosts = {
        "FIRESTORE_EMULATOR_HOST": f"127.0.0.1:{FIRESTORE_PORT}",
        "REDIS_DB_HOST": "127.0.0.1",
    }
    for name, expected in inherited_data_hosts.items():
        value = os.environ.get(name, "").strip()
        if value and value != expected:
            raise SafetyError(f"{name} must be unset or the owned loopback value {expected}")
    inherited_redis_port = os.environ.get("REDIS_DB_PORT", "").strip()
    if inherited_redis_port and inherited_redis_port != str(REDIS_PORT):
        raise SafetyError(f"REDIS_DB_PORT must be unset or the owned loopback port {REDIS_PORT}")
    for name, expected in {
        "FIRESTORE_DATABASE_ID": "(default)",
        "OMI_ENV_STAGE": "dev",
        "PROVIDER_MODE": "real",
    }.items():
        value = os.environ.get(name, "").strip()
        if value and value != expected:
            raise SafetyError(f"{name} must be unset or {expected}")
    if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "").strip():
        raise SafetyError("FIREBASE_AUTH_EMULATOR_HOST is not allowed: local-dev-gcp verifies real dev Auth tokens")
    forbidden = ("api.omi.me", "api.omiapi.com", ".a.run.app")
    for name, value in os.environ.items():
        if name.endswith(("URL", "URI", "HOST")) and any(host in value.lower() for host in forbidden):
            raise SafetyError(f"{name} contains a prohibited shared endpoint")
    if not (repo_root / "firebase.json").is_file() or not (repo_root / "firestore.rules").is_file():
        raise SafetyError("repository Firebase emulator configuration is incomplete")
    auth_project = os.environ.get("JIT_QA_FIREBASE_AUTH_PROJECT_ID", DEFAULT_AUTH_PROJECT).strip()
    errors = _validate_gcp_identity(auth_project)
    if errors:
        raise SafetyError("; ".join(errors))
    return {"auth_project": auth_project, "gcp_project": DEV_GCP_PROJECT}


def _metadata_path(state: Path) -> Path:
    return state / "run.json"


def _load_metadata(state: Path) -> dict[str, Any]:
    path = _metadata_path(state)
    if not path.exists():
        return {"schema_version": 1, "updated_at": _now(), "services": []}
    data = _read_json(path, None)
    if not isinstance(data, dict):
        raise SafetyError(f"run metadata must be a JSON object: {path}")
    if data.get("schema_version") != 1:
        raise SafetyError(f"run metadata has an unsupported schema version: {path}")
    if not isinstance(data.get("services"), list):
        raise SafetyError(f"run metadata services must be a list: {path}")
    return data


def _save_metadata(state: Path, data: dict[str, Any]) -> None:
    _write_private(_metadata_path(state), json.dumps(data, indent=2, sort_keys=True) + "\n")


@contextmanager
def _state_lock(state: Path):
    _ensure_private_dir(state)
    path = state / ".operation.lock"
    if path.is_symlink():
        raise SafetyError(f"refusing symlinked state lock: {path}")
    if path.exists():
        _single_link_regular_file(path, label="state lock")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise SafetyError(f"refusing linked or non-regular state lock: {path}")
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _make_firebase_config(repo_root: Path, state: Path) -> Path:
    config = {
        "firestore": {
            "rules": str(repo_root / "firestore.rules"),
            "indexes": str(repo_root / "firestore.indexes.json"),
        },
        "emulators": {
            "firestore": {"host": "127.0.0.1", "port": FIRESTORE_PORT},
            "ui": {"enabled": False},
            "hub": {"host": "127.0.0.1", "port": 18440},
        },
    }
    path = state / "firebase.json"
    _write_private(path, json.dumps(config, indent=2, sort_keys=True) + "\n")
    return path


def _firebase_cli(repo_root: Path) -> Path:
    package = _read_json(repo_root / "package.json", {})
    pinned = (package.get("devDependencies") or {}).get("firebase-tools") if isinstance(package, dict) else None
    executable = repo_root / "node_modules" / ".bin" / "firebase"
    if not isinstance(pinned, str) or not pinned or any(marker in pinned for marker in ("^", "~", "*", ">", "<")):
        raise SafetyError("package.json must pin an exact firebase-tools version")
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise SafetyError("locked firebase-tools is missing; run npm ci at the repository root")
    try:
        actual = subprocess.check_output([str(executable), "--version"], text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise SafetyError("locked firebase-tools version could not be verified") from exc
    if actual != pinned:
        raise SafetyError(f"firebase-tools version mismatch: expected {pinned}, got {actual}")
    return executable


def _local_secret(state: Path, name: str) -> str:
    path = state / f"{name.lower()}.secret"
    if path.is_symlink():
        raise SafetyError(f"refusing symlinked secret file: {path}")
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if len(value) >= 32 and _file_mode_is_private(path):
            return value
    value = secrets.token_urlsafe(48)
    _write_private(path, value + "\n")
    return value


def _child_env(state: Path, identity: dict[str, str], service: str) -> dict[str, str]:
    # Start from a small host-runtime allowlist. OMI_HARNESS_INSTANCE makes the
    # backend skip every dotenv file, and omitting provider/service credentials
    # prevents a local QA action from reaching PostHog, storage, payment,
    # third-party LLM, or other shared systems. Only the narrow Vertex broker
    # receives development ADC; general backend children get private HOME/XDG
    # roots and cannot discover the host's gcloud credentials.
    host_runtime_keys = {
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "NO_PROXY",
        "PATH",
        "REQUESTS_CA_BUNDLE",
        "SHELL",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TMPDIR",
        "USER",
        "VIRTUAL_ENV",
    }
    env = {key: value for key, value in os.environ.items() if key in host_runtime_keys}
    env.update(
        {
            "OMI_HARNESS_INSTANCE": OWNERSHIP_PREFIX,
            "OMI_HARNESS_STATE_ROOT": str(state),
            "OMI_HARNESS_PRIVATE_UMASK": "077",
            "PYTHONUNBUFFERED": "1",
        }
    )
    if service in {"firestore", "redis"}:
        private_home = state / f"{service}-home"
        _ensure_private_dir(private_home)
        env["HOME"] = str(private_home)
        return env

    if service == "vertex-gateway":
        for key in ("HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
            if value := os.environ.get(key):
                env[key] = value
        env.update(
            {
                "OMI_JIT_QA_VERTEX_GATEWAY": "1",
                "GOOGLE_CLOUD_PROJECT": DEV_GCP_PROJECT,
                "GCP_LOCATION": "us-central1",
                "OMI_JIT_QA_VERTEX_MODEL": "gemini-2.5-flash",
                "OMI_LLM_GATEWAY_SERVICE_TOKEN": _local_secret(state, "llm-gateway"),
                "PORT": str(VERTEX_GATEWAY_PORT),
            }
        )
        return env

    private_home = state / f"{service}-home"
    _ensure_private_dir(private_home)
    env.update(
        {
            "HOME": str(private_home),
            "XDG_CACHE_HOME": str(private_home / ".cache"),
            "XDG_CONFIG_HOME": str(private_home / ".config"),
            "XDG_DATA_HOME": str(private_home / ".local" / "share"),
            "GOOGLE_AUTH_DISABLE_GCE_CHECK": "true",
            "GCE_METADATA_HOST": "127.0.0.1:9",
        }
    )
    env.update(
        {
            "OMI_JIT_QA_LOCAL_STACK": "1",
            "OMI_JIT_QA_LOCAL_DATA_MODE": "firestore-emulator",
            "OMI_ENV_STAGE": "dev",
            "ENVIRONMENT": "development",
            "PROVIDER_MODE": "real",
            "FIRESTORE_EMULATOR_HOST": f"127.0.0.1:{FIRESTORE_PORT}",
            "FIRESTORE_DATABASE_ID": "(default)",
            "FIREBASE_PROJECT_ID": LOCAL_FIREBASE_PROJECT,
            "FIREBASE_AUTH_PROJECT_ID": identity["auth_project"],
            "GOOGLE_CLOUD_PROJECT": LOCAL_FIREBASE_PROJECT,
            "REDIS_DB_HOST": "127.0.0.1",
            "REDIS_DB_PORT": str(REDIS_PORT),
            "REDIS_DB_PASSWORD": "",
            "BASE_API_URL": "http://127.0.0.1:18080",
            "API_BASE_URL": "http://127.0.0.1:18080",
            "OMI_PYTHON_API_URL": "http://127.0.0.1:18080",
            "OMI_DESKTOP_API_URL": "http://127.0.0.1:18081",
            "OMI_AUTH_API_URL": "http://127.0.0.1:18080",
            "OMI_LLM_GATEWAY_URL": f"http://127.0.0.1:{VERTEX_GATEWAY_PORT}",
            "OMI_LLM_GATEWAY_SERVICE_TOKEN": _local_secret(state, "llm-gateway"),
            "OMI_LLM_GATEWAY_FEATURE_MODE": "gateway",
            "OMI_LLM_CHAT_AGENT_ROUTE": "gateway",
            "OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION": "false",
            "ENCRYPTION_SECRET": _local_secret(state, "encryption"),
            "ADMIN_KEY": _local_secret(state, "admin"),
        }
    )
    env.pop("FIREBASE_AUTH_EMULATOR_HOST", None)
    if service == "desktop":
        env["PORT"] = str(DESKTOP_PORT)
    else:
        env["PORT"] = str(MAIN_PORT)
    return env


def _command(repo_root: Path, state: Path, identity: dict[str, str], service: str) -> tuple[list[str], Path, str, int]:
    if service == "firestore":
        command = [
            str(_firebase_cli(repo_root)),
            "emulators:start",
            "--only",
            "firestore",
            "--config",
            str(_make_firebase_config(repo_root, state)),
            "--project",
            LOCAL_FIREBASE_PROJECT,
            "--import",
            str(state / "firestore-export"),
            "--export-on-exit",
            str(state / "firestore-export"),
            "--non-interactive",
        ]
        return command, state, "firestore.log", FIRESTORE_PORT
    if service == "redis":
        redis = shutil.which("redis-server")
        if not redis:
            raise SafetyError("redis-server is required for the local JIT QA stack")
        _ensure_private_dir(state / "redis")
        command = [
            redis,
            "--bind",
            "127.0.0.1",
            "--port",
            str(REDIS_PORT),
            "--dir",
            str(state / "redis"),
            "--save",
            "",
            "--appendonly",
            "no",
        ]
        return command, repo_root, "redis.log", REDIS_PORT
    if service == "vertex-gateway":
        return (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "dev_harness.jit_vertex_gateway:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(VERTEX_GATEWAY_PORT),
            ],
            repo_root,
            "vertex-gateway.log",
            VERTEX_GATEWAY_PORT,
        )
    python = sys.executable
    module = "main:app" if service == "main" else "desktop_backend:app"
    port = MAIN_PORT if service == "main" else DESKTOP_PORT
    return (
        [python, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port)],
        repo_root / "backend",
        f"{service}.log",
        port,
    )


def _valid_marker(service: str, marker: str) -> bool:
    prefix = f"{OWNERSHIP_PREFIX}:{service}:"
    suffix = marker.removeprefix(prefix) if marker.startswith(prefix) else ""
    return len(suffix) == 32 and all(character in "0123456789abcdef" for character in suffix)


def _owned_marker_process_count(process_group: int, marker: str) -> int:
    if process_group <= 0 or not any(_valid_marker(service, marker) for service in OWNED_SERVICES):
        return 0
    try:
        output = subprocess.check_output(
            ["ps", "-ww", "-g", str(process_group), "-o", "command="],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return 0
    return sum(marker in line for line in output.splitlines())


def _owned_process_group(process_group: int, marker: str) -> bool:
    return _owned_marker_process_count(process_group, marker) > 0


def _validated_record(record: Any) -> tuple[str, int, int, str] | None:
    if not isinstance(record, dict):
        return None
    service = str(record.get("service", ""))
    marker = str(record.get("marker", ""))
    if service not in OWNED_SERVICES or not _valid_marker(service, marker):
        return None
    try:
        pid = int(record.get("pid", -1))
        process_group = int(record.get("process_group", -1))
    except (TypeError, ValueError):
        return None
    if pid <= 0 or process_group <= 0 or process_group != pid:
        return None
    return service, pid, process_group, marker


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate_unrecorded_process_group(process: subprocess.Popen[Any], service: str) -> None:
    """Stop and reap a just-created group which never reached durable metadata."""

    for stop_signal, timeout in (
        (signal.SIGINT, 20),
        (signal.SIGTERM, 5),
        (signal.SIGKILL, 5),
    ):
        try:
            os.killpg(process.pid, stop_signal)
        except ProcessLookupError:
            break
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and _process_group_exists(process.pid):
            process.poll()  # Reap the supervisor so a zombie cannot keep the group visible.
            time.sleep(0.05)
        if not _process_group_exists(process.pid):
            break
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    if _process_group_exists(process.pid) or process.poll() is None:
        raise SafetyError(
            f"metadata persistence failed and unrecorded {service} process group {process.pid} survived cleanup"
        )


def _start_service(repo_root: Path, state: Path, identity: dict[str, str], service: str) -> dict[str, Any]:
    metadata = _load_metadata(state)
    for record in metadata.get("services", []):
        parsed = _validated_record(record)
        if parsed is None:
            raise SafetyError("run metadata contains a malformed ownership record")
        if parsed[0] == service:
            if _owned_process_group(parsed[2], parsed[3]):
                return record
            if _process_group_exists(parsed[2]):
                raise SafetyError(f"recorded {service} process group still exists without its ownership marker")
    command, cwd, log_name, port = _command(repo_root, state, identity, service)
    if _port_open(port):
        raise SafetyError(f"loopback port {port} for {service} is already held by an unowned process")
    marker = f"{OWNERSHIP_PREFIX}:{service}:{secrets.token_hex(16)}"
    log_path = state / "logs" / log_name
    _ensure_private_dir(log_path.parent)
    env = _child_env(state, identity, service)
    python_paths = [str(repo_root / "scripts" / "dev-harness")]
    if service in {"main", "desktop", "vertex-gateway"}:
        python_paths.append(str(repo_root / "backend"))
    env["PYTHONPATH"] = os.pathsep.join(python_paths)
    supervisor = [
        sys.executable,
        "-m",
        "dev_harness.supervise",
        "--marker",
        marker,
        "--service",
        service,
        "--",
        *command,
    ]
    if log_path.is_symlink():
        raise SafetyError(f"refusing symlinked log file: {log_path}")
    if log_path.exists():
        _single_link_regular_file(log_path, label="service log")
    log_fd = os.open(
        log_path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(log_fd, "ab") as log:
        details = os.fstat(log.fileno())
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise SafetyError(f"refusing linked or non-regular service log: {log_path}")
        os.fchmod(log.fileno(), 0o600)
        process = subprocess.Popen(
            supervisor,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    guardian_deadline = time.monotonic() + 5
    while time.monotonic() < guardian_deadline:
        if process.poll() is not None:
            break
        if _owned_marker_process_count(process.pid, marker) >= 2:
            break
        time.sleep(0.05)
    if process.poll() is not None or _owned_marker_process_count(process.pid, marker) < 2:
        _terminate_unrecorded_process_group(process, service)
        raise SafetyError(f"{service} ownership guardian did not become ready")
    try:
        record = {
            "service": service,
            "pid": process.pid,
            "process_group": process.pid,
            "port": port,
            "endpoint": f"http://127.0.0.1:{port}",
            "log": str(log_path),
            "marker": marker,
            "started_at": _now(),
            "command": command,
        }
        services = [item for item in metadata.get("services", []) if item.get("service") != service]
        services.append(record)
        _save_metadata(state, {"schema_version": 1, "updated_at": _now(), "services": services})
    except Exception:
        # This child has not become durable ownership state yet. Terminate the
        # exact process group created above so the outer rollback cannot miss
        # an unrecorded service when metadata persistence fails.
        _terminate_unrecorded_process_group(process, service)
        raise
    return record


def _health(service: str) -> tuple[bool, str]:
    if service == "firestore":
        ok, status = _http(f"http://127.0.0.1:{FIRESTORE_PORT}/", expected_text="Ok")
        return ok, f"HTTP {status}" if status else "unreachable"
    if service == "redis":
        try:
            with socket.create_connection(("127.0.0.1", REDIS_PORT), timeout=0.5) as client:
                client.sendall(b"*1\r\n$4\r\nPING\r\n")
                response = client.recv(64)
            return response == b"+PONG\r\n", ("PONG" if response == b"+PONG\r\n" else "unexpected-response")
        except OSError:
            return False, "unreachable"
    if service == "main":
        ok, status = _http(f"http://127.0.0.1:{MAIN_PORT}/v1/health", expected_json={"status": "ok"})
        return ok, f"HTTP {status}" if status else "unreachable"
    if service == "vertex-gateway":
        ok, status = _http(
            f"http://127.0.0.1:{VERTEX_GATEWAY_PORT}/health",
            expected_json={
                "status": "healthy",
                "service": "omi-jit-qa-vertex-gateway",
            },
        )
        if not ok:
            return False, f"HTTP {status}" if status else "unreachable"
        ready, ready_status = _http(
            f"http://127.0.0.1:{VERTEX_GATEWAY_PORT}/ready",
            timeout=CLOUD_READINESS_TIMEOUT_SECONDS,
            expected_json={
                "status": "ready",
                "service": "omi-jit-qa-vertex-gateway",
            },
        )
        return ready, (f"health HTTP {status}; ready HTTP {ready_status}" if ready_status else "ready unavailable")
    ok, status = _http(
        f"http://127.0.0.1:{DESKTOP_PORT}/health",
        expected_json={"status": "healthy", "service": "omi-desktop-backend"},
    )
    if not ok:
        return False, f"HTTP {status}" if status else "unreachable"
    ready, ready_status = _http(
        f"http://127.0.0.1:{DESKTOP_PORT}/ready",
        expected_json={"status": "ready", "service": "omi-desktop-backend"},
    )
    return ready, (f"health HTTP {status}; ready HTTP {ready_status}" if ready_status else "ready unavailable")


def _wait_for_health(services: list[str], timeout: float = HEALTH_TIMEOUT_SECONDS) -> list[str]:
    pending = set(services)
    deadline = time.monotonic() + timeout
    last: dict[str, str] = {}
    while pending and time.monotonic() < deadline:
        for service in list(pending):
            ok, detail = _health(service)
            last[service] = detail
            if ok:
                pending.remove(service)
        if pending:
            time.sleep(0.5)
    return [f"{service}: {last.get(service, 'timeout')}" for service in sorted(pending)]


def _stop(state: Path) -> int:
    metadata = _load_metadata(state)
    services = metadata.get("services", [])
    if not isinstance(services, list):
        print("ERROR: malformed service metadata", file=sys.stderr)
        return 1
    failures: list[str] = []
    valid: list[tuple[dict[str, Any], str, int, int, str]] = []
    ambiguous: list[dict[str, Any]] = []
    for record in services:
        parsed = _validated_record(record)
        if parsed is None:
            failures.append("malformed ownership record")
            continue
        service, pid, process_group, marker = parsed
        if not _owned_process_group(process_group, marker):
            if _process_group_exists(process_group):
                failures.append(f"{service}: ownership marker missing while process group exists")
                ambiguous.append(record)
            continue
        valid.append((record, service, pid, process_group, marker))
        try:
            os.killpg(process_group, signal.SIGINT)
        except (ProcessLookupError, PermissionError) as exc:
            failures.append(f"{service}: {type(exc).__name__}")

    def survivors() -> list[tuple[dict[str, Any], str, int, int, str]]:
        return [item for item in valid if _owned_process_group(item[3], item[4])]

    def wait_for_exit(timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and survivors():
            time.sleep(0.25)

    wait_for_exit(20)
    for _record, service, _pid, process_group, marker in survivors():
        if _owned_process_group(process_group, marker):
            try:
                os.killpg(process_group, signal.SIGTERM)
            except (ProcessLookupError, PermissionError) as exc:
                failures.append(f"{service}: {type(exc).__name__}")
    wait_for_exit(5)
    for _record, service, _pid, process_group, marker in survivors():
        if _owned_process_group(process_group, marker):
            try:
                os.killpg(process_group, signal.SIGKILL)
            except (ProcessLookupError, PermissionError) as exc:
                failures.append(f"{service}: {type(exc).__name__}")
    wait_for_exit(5)
    remaining = survivors()
    if remaining:
        failures.extend(f"{service}: still running" for _record, service, _pid, _process_group, _marker in remaining)
    retained = [record for record in services if _validated_record(record) is None]
    retained.extend(ambiguous)
    retained.extend(record for record, _service, _pid, _process_group, _marker in remaining)
    _save_metadata(state, {"schema_version": 1, "updated_at": _now(), "services": retained})
    _harden_state_tree(state)
    if failures:
        print("ERROR: teardown incomplete: " + ", ".join(failures), file=sys.stderr)
        return 1
    print("JIT QA local stack stopped")
    return 0


def _check(repo_root: Path) -> int:
    identity = _validate_contract(repo_root)
    _firebase_cli(repo_root)
    required = ["redis-server"]
    missing = [name for name in required if shutil.which(name) is None]
    if shutil.which("java") is None:
        missing.append("java")
    if missing:
        raise SafetyError("missing local prerequisites: " + ", ".join(missing))
    print("JIT QA local stack contract: safe")
    print(f"  main: http://127.0.0.1:{MAIN_PORT}")
    print(f"  desktop: http://127.0.0.1:{DESKTOP_PORT}")
    print(f"  firestore: emulator-only 127.0.0.1:{FIRESTORE_PORT}")
    print(f"  redis: owned loopback 127.0.0.1:{REDIS_PORT}")
    print(f"  vertex_gateway: ADC-isolated loopback 127.0.0.1:{VERTEX_GATEWAY_PORT}")
    print(f"  firebase_auth_project: {identity['auth_project']}")
    print(f"  vertex_project: {identity['gcp_project']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jit-qa-local-backend")
    parser.add_argument("command", choices=("check", "up", "status", "health", "down"))
    args = parser.parse_args(argv)
    if args.command == "up" and os.environ.get("JIT_QA_TEST_MODE") == "1":
        raise SafetyError("JIT_QA_TEST_MODE is contract-check-only and cannot start services")
    repo_root = _repo_root()
    state = _state_root(repo_root)
    if args.command == "check":
        return _check(repo_root)
    # Teardown and observation must keep working when ADC expires or the shell
    # has acquired unsafe inherited values since startup. Ownership validation,
    # not cloud authentication, is the authority for these commands.
    with _state_lock(state):
        _harden_state_tree(state)
        if args.command == "down":
            return _stop(state)
        if args.command == "status":
            metadata = _load_metadata(state)
            malformed = False
            for record in metadata.get("services", []):
                parsed = _validated_record(record)
                if parsed is None:
                    print("malformed ownership record: healthy=false", file=sys.stderr)
                    malformed = True
                    continue
                service, pid, process_group, marker = parsed
                alive = _owned_process_group(process_group, marker)
                if not alive and _process_group_exists(process_group):
                    print(
                        f"{service}: pid={pid} alive=unknown healthy=false ownership-marker-missing",
                        file=sys.stderr,
                    )
                    malformed = True
                    continue
                healthy, detail = _health(service) if alive else (False, "stopped")
                print(f"{service}: pid={pid} alive={str(alive).lower()} healthy={str(healthy).lower()} {detail}")
            if not metadata.get("services"):
                print("JIT QA local stack: stopped")
            return 1 if malformed else 0
        if args.command == "health":
            metadata = _load_metadata(state)
            owned: set[str] = set()
            for record in metadata.get("services", []):
                parsed = _validated_record(record)
                if parsed is not None and _owned_process_group(parsed[2], parsed[3]):
                    owned.add(parsed[0])
            if owned != set(OWNED_SERVICES):
                print("owned local stack is incomplete", file=sys.stderr)
                return 1
            failures = _wait_for_health(sorted(OWNED_SERVICES), timeout=1)
            if failures:
                for failure in failures:
                    print(failure, file=sys.stderr)
                return 1
            print("JIT QA local stack: healthy")
            return 0
        identity = _validate_contract(repo_root)
        _ensure_private_dir(state / "logs")
        try:
            _start_service(repo_root, state, identity, "firestore")
            _start_service(repo_root, state, identity, "redis")
            _start_service(repo_root, state, identity, "vertex-gateway")
            failures = _wait_for_health(["firestore", "redis", "vertex-gateway"], timeout=45)
            if failures:
                raise SafetyError("dependencies did not become healthy: " + "; ".join(failures))
            _start_service(repo_root, state, identity, "main")
            _start_service(repo_root, state, identity, "desktop")
            failures = _wait_for_health(["main", "desktop"], timeout=HEALTH_TIMEOUT_SECONDS)
            if failures:
                raise SafetyError("application services did not become healthy: " + "; ".join(failures))
        except Exception:
            _stop(state)
            raise
        print("JIT QA local stack is up")
        print("  launch the bundle with: desktop/macos/scripts/omi-jit-qa local-dev-gcp --fast-only")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

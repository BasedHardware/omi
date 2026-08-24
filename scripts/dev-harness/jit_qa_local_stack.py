"""Fail-closed local backend stack for the ``omi-jit-qa`` bundle.

This is deliberately a separate entry point from the general offline harness.
It is a hybrid stack: Firebase ID tokens are verified against the configured
development Auth project and Vertex uses development ADC, while all Firestore
traffic is forced to an owned emulator and Redis is forced to an owned
loopback instance.  No production API or shared Firestore path is accepted.
"""

from __future__ import annotations

import argparse
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
LOCAL_FIREBASE_PROJECT = "demo-omi-jit-qa"
DEV_GCP_PROJECT = "based-hardware-dev"
DEFAULT_AUTH_PROJECT = "based-hardware"
STATE_DIR_NAME = "jit-qa-local-dev-gcp"
OWNERSHIP_PREFIX = "omi-jit-qa-local"
HEALTH_TIMEOUT_SECONDS = 180


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
    if root == repo_root or repo_root in root.parents and root.parent.name == ".dev":
        return root
    if os.environ.get("JIT_QA_TEST_MODE") == "1" and root.parent in {
        Path("/tmp").resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }:
        return root
    raise SafetyError("state root must be under this checkout's .dev directory")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
    except (OSError, json.JSONDecodeError):
        return default


def _write_private(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.stat().st_mode if path.exists() else None
    if isinstance(data, str):
        data = data.encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(data)
    finally:
        if fd >= 0:
            os.close(fd)
    if previous is not None and stat.S_IMODE(path.stat().st_mode) != 0o600:
        os.chmod(path, 0o600)


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _http(url: str, timeout: float = 1.0) -> tuple[bool, int | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status < 500, response.status
    except urllib.error.HTTPError as exc:
        return exc.code < 500, exc.code
    except (OSError, urllib.error.URLError):
        return False, None


def _file_mode_is_private(path: Path) -> bool:
    try:
        return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    except OSError:
        return False


def _credential_project(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    project = payload.get("project_id") if isinstance(payload, dict) else None
    return project.strip() if isinstance(project, str) else None


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

    credential_paths: list[Path] = []
    for name in ("GOOGLE_APPLICATION_CREDENTIALS", "FIREBASE_AUTH_CREDENTIALS_PATH"):
        raw = os.environ.get(name, "").strip()
        if raw:
            path = Path(raw).expanduser()
            credential_paths.append(path)
            if not path.is_file():
                errors.append(f"{name} points to a missing file")
            elif not _file_mode_is_private(path):
                errors.append(f"{name} must be owner-readable only (mode 0600 or stricter)")

    service_json = os.environ.get("SERVICE_ACCOUNT_JSON", "").strip()
    if service_json:
        try:
            payload = json.loads(service_json)
        except json.JSONDecodeError:
            errors.append("SERVICE_ACCOUNT_JSON is not valid JSON")
        else:
            project = payload.get("project_id") if isinstance(payload, dict) else None
            if project != DEV_GCP_PROJECT:
                errors.append("SERVICE_ACCOUNT_JSON must belong to based-hardware-dev")

    if credential_paths:
        projects = {_credential_project(path) for path in credential_paths if path.is_file()}
        projects.discard(None)
        if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ and projects and DEV_GCP_PROJECT not in projects:
            errors.append("Google ADC credential file must belong to based-hardware-dev")

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
        "USE_VERTEX_AI": "true",
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
    data = _read_json(_metadata_path(state), {})
    return data if isinstance(data, dict) else {}


def _save_metadata(state: Path, data: dict[str, Any]) -> None:
    _write_private(_metadata_path(state), json.dumps(data, indent=2, sort_keys=True) + "\n")


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


def _local_secret(state: Path, name: str) -> str:
    path = state / f"{name.lower()}.secret"
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if len(value) >= 32 and _file_mode_is_private(path):
            return value
    value = secrets.token_urlsafe(48)
    _write_private(path, value + "\n")
    return value


def _child_env(state: Path, identity: dict[str, str], service: str) -> dict[str, str]:
    env = dict(os.environ)
    # Do not let backend load backend/.env or a stage file that could restore a
    # remote Firestore/Redis endpoint.  The explicit values below are the only
    # data-plane authority for this stack.
    for key in list(env):
        if key.startswith(("BUCKET_", "TYPESENSE_", "PINECONE_", "POSTHOG_", "SENTRY_", "LANGSMITH_")):
            env.pop(key, None)
    for key in (
        "FIREBASE_API_KEY",
        "OMI_PARITY_PACK_GCS_URI",
        "OMI_PARITY_PACK_GCS_BUCKET",
        "OMI_PARITY_PACK_GCS_PREFIX",
        "OMI_LLM_GATEWAY_URL",
        "OMI_LLM_GATEWAY_SERVICE_TOKEN",
        "OMI_LLM_GATEWAY_FEATURE_MODE",
    ):
        env.pop(key, None)
    env.update(
        {
            "OMI_HARNESS_INSTANCE": OWNERSHIP_PREFIX,
            "OMI_HARNESS_STATE_ROOT": str(state),
            "OMI_JIT_QA_LOCAL_STACK": "1",
            "OMI_JIT_QA_LOCAL_DATA_MODE": "firestore-emulator",
            "OMI_ENV_STAGE": "dev",
            "ENVIRONMENT": "development",
            "PROVIDER_MODE": "real",
            "FIRESTORE_EMULATOR_HOST": f"127.0.0.1:{FIRESTORE_PORT}",
            "FIRESTORE_DATABASE_ID": "(default)",
            "FIREBASE_PROJECT_ID": LOCAL_FIREBASE_PROJECT,
            "FIREBASE_AUTH_PROJECT_ID": identity["auth_project"],
            "GOOGLE_CLOUD_PROJECT": DEV_GCP_PROJECT,
            "USE_VERTEX_AI": "true",
            "REDIS_DB_HOST": "127.0.0.1",
            "REDIS_DB_PORT": str(REDIS_PORT),
            "REDIS_DB_PASSWORD": "",
            "BASE_API_URL": "http://127.0.0.1:18080",
            "API_BASE_URL": "http://127.0.0.1:18080",
            "OMI_PYTHON_API_URL": "http://127.0.0.1:18080",
            "OMI_DESKTOP_API_URL": "http://127.0.0.1:18081",
            "OMI_AUTH_API_URL": "http://127.0.0.1:18080",
            "OMI_LLM_GATEWAY_FEATURE_MODE": "off",
            "OMI_LLM_CHAT_AGENT_ROUTE": "direct",
            "ENCRYPTION_SECRET": _local_secret(state, "encryption"),
            "ADMIN_KEY": _local_secret(state, "admin"),
            "PYTHONUNBUFFERED": "1",
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
        firebase = shutil.which("firebase")
        base = [firebase] if firebase else [shutil.which("npx") or "npx", "--yes", "firebase-tools"]
        command = [
            *base,
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
        return command, repo_root, "firestore.log", FIRESTORE_PORT
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
    python = sys.executable
    module = "main:app" if service == "main" else "desktop_backend:app"
    port = MAIN_PORT if service == "main" else DESKTOP_PORT
    return (
        [python, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port)],
        repo_root / "backend",
        f"{service}.log",
        port,
    )


def _owned_pid(pid: int, marker: str) -> bool:
    try:
        output = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return False
    return marker in output


def _start_service(repo_root: Path, state: Path, identity: dict[str, str], service: str) -> dict[str, Any]:
    metadata = _load_metadata(state)
    for record in metadata.get("services", []):
        if record.get("service") == service and _owned_pid(int(record.get("pid", -1)), str(record.get("marker", ""))):
            return record
    command, cwd, log_name, port = _command(repo_root, state, identity, service)
    if _port_open(port):
        raise SafetyError(f"loopback port {port} for {service} is already held by an unowned process")
    marker = f"{OWNERSHIP_PREFIX}:{service}"
    log_path = state / "logs" / log_name
    _ensure_private_dir(log_path.parent)
    env = _child_env(state, identity, service)
    if service in {"main", "desktop"}:
        env["PYTHONPATH"] = os.pathsep.join(
            [str(repo_root / "scripts" / "dev-harness"), str(repo_root / "backend"), env.get("PYTHONPATH", "")]
        )
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
    with log_path.open("ab") as log:
        os.chmod(log_path, 0o600)
        process = subprocess.Popen(
            supervisor, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
    record = {
        "service": service,
        "pid": process.pid,
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
    return record


def _health(service: str) -> tuple[bool, str]:
    if service == "firestore":
        ok, status = _http(f"http://127.0.0.1:{FIRESTORE_PORT}/")
        return ok, f"HTTP {status}" if status else "unreachable"
    if service == "redis":
        return _port_open(REDIS_PORT), "port-open" if _port_open(REDIS_PORT) else "port-closed"
    if service == "main":
        ok, status = _http(f"http://127.0.0.1:{MAIN_PORT}/v1/health")
        return ok, f"HTTP {status}" if status else "unreachable"
    ok, status = _http(f"http://127.0.0.1:{DESKTOP_PORT}/health")
    if not ok:
        return False, f"HTTP {status}" if status else "unreachable"
    ready, ready_status = _http(f"http://127.0.0.1:{DESKTOP_PORT}/ready")
    return ready, f"health HTTP {status}; ready HTTP {ready_status}" if ready_status else "ready unavailable"


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
        return 0
    failures: list[str] = []
    for record in services:
        try:
            pid = int(record.get("pid", -1))
        except (TypeError, ValueError):
            continue
        marker = str(record.get("marker", ""))
        if pid <= 0 or not _owned_pid(pid, marker):
            continue
        try:
            os.killpg(pid, signal.SIGINT)
        except (ProcessLookupError, PermissionError) as exc:
            failures.append(f"{record.get('service', 'unknown')}: {type(exc).__name__}")
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline and any(
        _owned_pid(int(item.get("pid", -1)), str(item.get("marker", ""))) for item in services if item.get("pid")
    ):
        time.sleep(0.25)
    for record in services:
        pid = int(record.get("pid", -1)) if str(record.get("pid", "")).isdigit() else -1
        marker = str(record.get("marker", ""))
        if pid > 0 and _owned_pid(pid, marker):
            try:
                os.killpg(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
    _save_metadata(state, {"schema_version": 1, "updated_at": _now(), "services": []})
    if failures:
        print("teardown warnings: " + ", ".join(failures), file=sys.stderr)
    print("JIT QA local stack stopped")
    return 0


def _check(repo_root: Path) -> int:
    identity = _validate_contract(repo_root)
    required = ["node", "npx", "redis-server"]
    missing = [name for name in required if shutil.which(name) is None]
    if shutil.which("firebase") is None and shutil.which("npx") is None:
        missing.append("firebase-tools or npx")
    if shutil.which("java") is None:
        missing.append("java")
    if missing:
        raise SafetyError("missing local prerequisites: " + ", ".join(missing))
    print("JIT QA local stack contract: safe")
    print(f"  main: http://127.0.0.1:{MAIN_PORT}")
    print(f"  desktop: http://127.0.0.1:{DESKTOP_PORT}")
    print(f"  firestore: emulator-only 127.0.0.1:{FIRESTORE_PORT}")
    print(f"  redis: owned loopback 127.0.0.1:{REDIS_PORT}")
    print(f"  firebase_auth_project: {identity['auth_project']}")
    print(f"  vertex_project: {identity['gcp_project']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jit-qa-local-backend")
    parser.add_argument("command", choices=("check", "up", "status", "health", "down"))
    args = parser.parse_args(argv)
    repo_root = _repo_root()
    state = _state_root(repo_root)
    if args.command == "check":
        return _check(repo_root)
    identity = _validate_contract(repo_root)
    if args.command == "down":
        return _stop(state)
    if args.command == "status":
        metadata = _load_metadata(state)
        for record in metadata.get("services", []):
            service = record.get("service", "unknown")
            alive = _owned_pid(int(record.get("pid", -1)), str(record.get("marker", "")))
            healthy, detail = _health(str(service)) if alive else (False, "stopped")
            print(
                f"{service}: pid={record.get('pid')} alive={str(alive).lower()} healthy={str(healthy).lower()} {detail}"
            )
        if not metadata.get("services"):
            print("JIT QA local stack: stopped")
        return 0
    if args.command == "health":
        failures = _wait_for_health(["firestore", "redis", "main", "desktop"], timeout=1)
        if failures:
            for failure in failures:
                print(failure, file=sys.stderr)
            return 1
        print("JIT QA local stack: healthy")
        return 0
    _ensure_private_dir(state)
    _ensure_private_dir(state / "logs")
    try:
        _start_service(repo_root, state, identity, "firestore")
        _start_service(repo_root, state, identity, "redis")
        failures = _wait_for_health(["firestore", "redis"], timeout=45)
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
    print("  launch the bundle with: scripts/omi-jit-qa local-dev-gcp --fast-only")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

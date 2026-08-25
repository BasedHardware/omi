"""Hermetic PostHog decide/control fixture for the JIT QA local stack.

The fixture is deliberately a tiny loopback HTTP server rather than a product
provider. The real ``posthog==3.5.2`` SDK sends its normal ``POST
/decide/?v=3`` request here, so the backend's production
``PostHogJITFlagProvider`` remains the code under test. Only the authenticated
control endpoints mutate the fixture's private state; decide requests are
read-only and never leave the process.
"""

from __future__ import annotations

import argparse
import hmac
import http.server
import json
import os
from pathlib import Path
import secrets
import socketserver
import threading
import time
from typing import Any
from urllib.parse import urlparse

CONTROL_PORT = 18085
CONTROL_HOST = "127.0.0.1"
DUMMY_PROJECT_KEY = "omi-jit-qa-demo-project-key"
CONTROL_TOKEN_ENV = "OMI_JIT_QA_POSTHOG_CONTROL_TOKEN"
STATE_FILE_ENV = "OMI_JIT_QA_POSTHOG_STATE_FILE"
PROJECT_KEY_ENV = "OMI_JIT_QA_POSTHOG_PROJECT_KEY"
STATE_ROOT_PREFIX = "jit-qa-local-dev-gcp"
MAX_BODY_BYTES = 64 * 1024
SCHEMA_VERSION = 1
FLAG_ROLLOUT = "jit-processing-v1"
FLAG_KILL_SWITCH = "jit-processing-kill-switch-v1"
_STATES = frozenset({"unknown", "disabled", "enabled"})


class ControlError(RuntimeError):
    """Raised when the local fixture cannot prove its safety contract."""


def _is_state(value: Any) -> bool:
    return isinstance(value, str) and value in _STATES


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _default_state() -> dict[str, Any]:
    # Rollout is unknown by default; the kill switch is explicitly off. This
    # evaluates to fail-closed ``unknown`` in the production authority while
    # keeping the fixture's safety state visible to its operator.
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "rollout": "unknown",
        "kill_switch": "disabled",
        "decide_requests": 0,
    }


def _state_path() -> Path:
    raw = os.environ.get(STATE_FILE_ENV, "").strip()
    if not raw:
        raise ControlError(f"{STATE_FILE_ENV} is required")
    path = Path(raw).expanduser().resolve()
    root_raw = os.environ.get("OMI_HARNESS_STATE_ROOT", "").strip()
    if not root_raw:
        raise ControlError("OMI_HARNESS_STATE_ROOT is required")
    state_root = Path(root_raw).expanduser().resolve()
    if not state_root.name.startswith(STATE_ROOT_PREFIX):
        raise ControlError("PostHog fixture state root is not a managed JIT QA root")
    if state_root not in path.parents:
        raise ControlError("PostHog fixture state must remain under the managed harness root")
    if path.name != "posthog-flags.json":
        raise ControlError("PostHog fixture state must use posthog-flags.json")
    return path


def _private_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.is_symlink():
        raise ControlError(f"refusing symlinked PostHog fixture state file: {path}")
    if path.exists():
        details = path.lstat()
        if path.is_symlink() or not path.is_file() or details.st_nlink != 1:
            raise ControlError(f"refusing unsafe PostHog fixture state file: {path}")
        os.chmod(path, 0o600)


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        state = _default_state()
        _write_state(path, state)
        return state
    _private_file(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlError("PostHog fixture state is unreadable or malformed") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ControlError("PostHog fixture state has an unsupported schema")
    if not _is_state(value.get("rollout")) or not _is_state(value.get("kill_switch")):
        raise ControlError("PostHog fixture state contains an invalid flag state")
    return value


def _write_state(path: Path, state: dict[str, Any]) -> None:
    _private_file(path)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(json.dumps(state, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary.exists():
            temporary.unlink()


def _flag_payload(state: dict[str, Any]) -> dict[str, bool]:
    payload: dict[str, bool] = {}
    if state["rollout"] != "unknown":
        payload[FLAG_ROLLOUT] = state["rollout"] == "enabled"
    if state["kill_switch"] != "unknown":
        payload[FLAG_KILL_SWITCH] = state["kill_switch"] == "enabled"
    return payload


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


class _FixtureState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.RLock()
        self.value = _read_state(path)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.value)

    def decide(self) -> dict[str, bool]:
        with self.lock:
            self.value["decide_requests"] = int(self.value.get("decide_requests", 0)) + 1
            _write_state(self.path, self.value)
            return _flag_payload(self.value)

    def update(self, rollout: str | None, kill_switch: str | None) -> dict[str, Any]:
        with self.lock:
            if rollout is not None:
                self.value["rollout"] = rollout
            if kill_switch is not None:
                self.value["kill_switch"] = kill_switch
            self.value["updated_at"] = _now()
            _write_state(self.path, self.value)
            return dict(self.value)


def _token() -> str:
    token = os.environ.get(CONTROL_TOKEN_ENV, "").strip()
    if len(token) < 32:
        raise ControlError("local PostHog control token is not configured")
    return token


def _project_key() -> str:
    project_key = os.environ.get(PROJECT_KEY_ENV, DUMMY_PROJECT_KEY).strip()
    if project_key != DUMMY_PROJECT_KEY:
        raise ControlError("local PostHog fixture requires the fixed demo project key")
    return project_key


class _Handler(http.server.BaseHTTPRequestHandler):
    server: "_Server"

    def log_message(self, _format: str, *_args: Any) -> None:
        # Do not log distinct IDs, request bodies, or auth headers.
        return

    def _send(self, status: int, value: Any) -> None:
        body = _json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(400, {"error": "invalid content length"})
            return None
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send(413, {"error": "body is empty or too large"})
            return None
        try:
            value = json.loads(self.rfile.read(length))
        except (OSError, json.JSONDecodeError):
            self._send(400, {"error": "body must be JSON"})
            return None
        if not isinstance(value, dict):
            self._send(400, {"error": "body must be an object"})
            return None
        return value

    def _authorized_control(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        try:
            expected = f"Bearer {_token()}"
        except ControlError:
            self._send(503, {"error": "control authentication is unavailable"})
            return False
        if not hmac.compare_digest(supplied, expected):
            self._send(401, {"error": "invalid control authentication"})
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        if path == "/health":
            self._send(200, {"status": "healthy", "service": "omi-jit-qa-posthog"})
            return
        if path == "/ready":
            try:
                _project_key()
                _token()
                self.server.fixture.snapshot()
            except ControlError as exc:
                self._send(503, {"status": "not_ready", "error": str(exc)})
                return
            self._send(200, {"status": "ready", "service": "omi-jit-qa-posthog"})
            return
        if path == "/control/flags":
            if self._authorized_control():
                self._send(200, self.server.fixture.snapshot())
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path.rstrip("/")
        if path == "/decide":
            body = self._body()
            if body is None:
                return
            try:
                project_key = _project_key()
            except ControlError as exc:
                self._send(503, {"error": str(exc)})
                return
            if body.get("api_key") != project_key or not isinstance(body.get("distinct_id"), str):
                self._send(401, {"error": "invalid demo project request"})
                return
            if not body["distinct_id"].strip():
                self._send(400, {"error": "distinct_id is required"})
                return
            self._send(
                200,
                {
                    "featureFlags": self.server.fixture.decide(),
                    "featureFlagPayloads": {},
                },
            )
            return
        if path == "/control/flags":
            if not self._authorized_control():
                return
            body = self._body()
            if body is None:
                return
            rollout = body.get("rollout")
            kill_switch = body.get("kill_switch")
            if rollout is not None and not _is_state(rollout):
                self._send(400, {"error": "rollout must be unknown, disabled, or enabled"})
                return
            if kill_switch is not None and not _is_state(kill_switch):
                self._send(400, {"error": "kill_switch must be unknown, disabled, or enabled"})
                return
            if rollout is None and kill_switch is None:
                self._send(400, {"error": "at least one flag state is required"})
                return
            self._send(200, self.server.fixture.update(rollout, kill_switch))
            return
        self._send(404, {"error": "not found"})


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, fixture: _FixtureState, *, host: str = CONTROL_HOST, port: int = CONTROL_PORT) -> None:
        if host != CONTROL_HOST:
            raise ControlError("PostHog fixture may bind only to loopback")
        super().__init__((host, port), _Handler)
        self.fixture = fixture


def run_server() -> None:
    if os.environ.get("OMI_JIT_QA_LOCAL_STACK") != "1":
        raise ControlError("PostHog fixture may only run inside the managed JIT QA stack")
    if os.environ.get("OMI_JIT_QA_TARGET", "local-dev-gcp") != "local-dev-gcp":
        raise ControlError("PostHog fixture requires OMI_JIT_QA_TARGET=local-dev-gcp")
    path = _state_path()
    _project_key()
    _token()
    fixture = _FixtureState(path)
    server = _Server(fixture)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jit-posthog-control")
    parser.parse_args(argv)
    run_server()
    return 0


__all__ = [
    "CONTROL_HOST",
    "CONTROL_PORT",
    "DUMMY_PROJECT_KEY",
    "FLAG_KILL_SWITCH",
    "FLAG_ROLLOUT",
    "_default_state",
    "_flag_payload",
    "_FixtureState",
    "run_server",
]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ControlError as exc:
        raise SystemExit(f"ERROR: {exc}")

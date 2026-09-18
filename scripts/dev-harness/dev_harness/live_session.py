"""V1 live Flutter broker. Contract: ../LIVE_SESSIONS.md.

PR1 is fake-backed: tests inject a MachineProcess factory. This PR adds no new
live-process adapter; the CLI does not spawn `flutter run` on a device.
stop/reset/recover still reach real service and device lifecycle commands.
"""

from __future__ import annotations

import getpass
import json
import os
import platform
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import urlparse

from . import session_evidence as se
from .mobile_session import DEFAULT_APP_IDS, LEASE_FILENAME, SessionError, session_dir

OPERATIONS = ("start", "reload", "restart", "screenshot", "logs", "controls", "status", "stop")
CONTROL_METHODS = ("capabilities", "state", "wait_ready", "navigate", "fault")
READY_PROFILE = "local_dev"
CONTRACT_VERSION = "semantic-controls/v1"
REQUEST_VERSION = "live-session/v1"
MAX_REQUEST_BYTES = 1024 * 1024
MAX_LOG_ENTRIES = 256
REQUIRED_CAPABILITIES = frozenset({"capabilities", "state", "wait_ready"})
_URL_RE = re.compile(r"(?i)\b(?:https?|wss?)://[^\s'\"<>]+")
# Complete authorization values, not the first whitespace token (`Authorization:
# Bearer <token>` must not become `Authorization=<redacted> <token>`).
_AUTHORIZATION_VALUE_RE = re.compile(r"(?i)\b(authorization)(?:\s*[:=]\s*|\s+)\S.*")
_BEARER_TOKEN_RE = re.compile(r"(?i)\bbearer\s+\S+")
_CREDENTIAL_ASSIGN_RE = re.compile(r"(?i)\b(api[_-]?key|auth(?:enticat\w*)?|password|secret|token)\s*[:=]\s*\S+")
WORKTREE_LOCK = ".omi-live-worktree.lock"
LIVE_FILENAME = "live.json"
EMPTY_PARAM_OPS = frozenset({"reload", "restart", "screenshot", "status", "stop"})
DECODE_OPS = frozenset({"reload", "restart", "screenshot", "logs", "controls", "status", "stop", "verify"})
SAFE_FLAVORS = frozenset({"dev"})
SAFE_PROFILES = frozenset({"local_dev"})
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1", ""})
_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9-]{1,80}$")


class LiveNotImplemented(SessionError, NotImplementedError):
    """Explicit exit-2 refusal while a live capability is out of this PR."""


class LiveError(SessionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SourceStamp:
    git_sha: str
    dirty_digest: str
    inputs_sha256: str
    restart_sha256: str


@dataclass(frozen=True)
class LaunchSpec:
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    build_dir: Path
    device_id: str


@dataclass(frozen=True)
class BrokerIdentity:
    host: str
    user: str
    boot_id: str
    pid: int
    process_start: str
    ownership_marker: str
    generation: int
    worktree: str
    session_id: str


class MachineProcess(Protocol):
    def send(self, line: str) -> None: ...
    def receive(self, timeout_s: float) -> str | None: ...
    def close(self) -> None: ...


def _stamp_source(stamp: SourceStamp) -> dict[str, str]:
    return {"git_sha": stamp.git_sha, "dirty_digest": stamp.dirty_digest, "inputs_sha256": stamp.inputs_sha256}


def _parse_machine(line: str) -> dict[str, Any]:
    payload = json.loads(line)
    if isinstance(payload, list):
        if len(payload) != 1 or not isinstance(payload[0], dict):
            raise LiveError("malformed-response", "machine line must be a one-element object array")
        return payload[0]
    if isinstance(payload, dict):
        return payload
    raise LiveError("malformed-response", "machine line must be a JSON object")


def _env_api_base(repo_root: Path) -> str | None:
    path = Path(repo_root) / "app" / ".dev.env"
    if not path.is_file():
        return ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "API_BASE_URL":
            return value.strip().strip("'\"")
    return ""


def _as_rfc3339_utc(stamp: str) -> str:
    """Keep live timestamps on the evidence regex even if a test clock is fractional."""

    if se.RFC3339_UTC_RE.fullmatch(stamp):
        return stamp
    if stamp.endswith("Z") and "T" in stamp:
        candidate = stamp[:-1].split(".", 1)[0] + "Z"
        if se.RFC3339_UTC_RE.fullmatch(candidate):
            return candidate
    return stamp


def sanitize_log_text(text: str) -> str:
    """Redact URL and credential *shapes* before logs are stored or returned."""

    if not isinstance(text, str):
        text = str(text)

    def _url(match: re.Match[str]) -> str:
        parsed = urlparse(match.group(0))
        host = parsed.hostname or "redacted"
        scheme = parsed.scheme or "https"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{scheme}://{host}{port}/<redacted>"

    text = _URL_RE.sub(_url, text)
    text = _AUTHORIZATION_VALUE_RE.sub(r"\1=<redacted>", text)
    text = _BEARER_TOKEN_RE.sub("Bearer <redacted>", text)
    return _CREDENTIAL_ASSIGN_RE.sub(r"\1=<redacted>", text)


def _loopback_or_empty(url: str) -> bool:
    if not url:
        return True
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip("[]").lower()
    if parsed.scheme and parsed.scheme != "http":
        return False
    return host in LOOPBACK


def stop_owned_broker(
    recorded: BrokerIdentity,
    observed: BrokerIdentity | None,
    terminate: Callable[[int], None],
) -> None:
    if not recorded.ownership_marker:
        raise LiveError("unsafe-config", "live identity is missing an ownership marker")
    if observed is None:
        return
    if observed != recorded:
        raise LiveError(
            "unsafe-config",
            "live process identity does not match the recorded broker/child; refusing to signal",
        )
    terminate(recorded.pid)


def decode_request(line: bytes, *, session_id: str, generation: int) -> Mapping[str, Any]:
    if len(line) > MAX_REQUEST_BYTES:
        raise LiveError("unsafe-config", "broker request exceeds 1 MiB")
    try:
        text = line.decode("utf-8")
        payload = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveError("malformed-response", f"broker request is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise LiveError("unsafe-config", "broker request must be a JSON object")
    allowed = {"version", "id", "session_id", "generation", "operation", "params", "timeout_ms"}
    extra = set(payload) - allowed
    if extra:
        raise LiveError("unsafe-config", f"broker request has unknown fields {sorted(extra)}")
    missing = allowed - set(payload)
    if missing:
        raise LiveError("unsafe-config", f"broker request missing {sorted(missing)}")
    if payload.get("version") != REQUEST_VERSION:
        raise LiveError("unsafe-config", f"unsupported live-session version {payload.get('version')!r}")
    if payload.get("session_id") != session_id:
        raise LiveError("stale-session", "request session_id does not match the lease")
    if payload.get("generation") != generation:
        raise LiveError("stale-session", "request generation does not match the lease")
    request_id = payload.get("id")
    if not isinstance(request_id, str) or not _REQUEST_ID_RE.fullmatch(request_id):
        raise LiveError("unsafe-config", f"invalid request id {request_id!r}")
    operation = payload.get("operation")
    if operation not in DECODE_OPS:
        raise LiveError("unsupported-operation", f"unsupported broker operation {operation!r}")
    timeout_ms = payload.get("timeout_ms")
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or not 1 <= timeout_ms <= 300000:
        raise LiveError("unsafe-config", f"timeout_ms out of range: {timeout_ms!r}")
    params = payload.get("params")
    if not isinstance(params, dict):
        raise LiveError("unsafe-config", "params must be an object")
    if operation in EMPTY_PARAM_OPS and params:
        raise LiveError("unsafe-config", f"{operation} takes no params")
    if operation == "logs" and set(params) - {"cursor", "limit"}:
        raise LiveError("unsafe-config", "logs params are cursor/limit only")
    if operation == "controls" and set(params) - {"method", "params"}:
        raise LiveError("unsafe-config", "controls params are method/params only")
    return payload


def validate_live_evidence(document: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    live = document.get("live")
    if not isinstance(live, Mapping):
        return ["live: required object"]
    required = (
        "generation",
        "operation_id",
        "operation",
        "outcome",
        "requested_source",
        "loaded_source",
        "loaded_sequence",
        "restart_sha256",
        "started_at",
        "finished_at",
        "elapsed_ms",
    )
    allowed = set(required) | {"daemon_code", "screenshot"}
    extra = set(live) - allowed
    if extra:
        errors.append(f"live has unknown fields {sorted(extra)}")
    generation = live.get("generation")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        errors.append(f"live.generation must be >= 1, got {generation!r}")
    outcome = live.get("outcome")
    if outcome not in ("ok", "rejected", "restart-required", "blocked"):
        errors.append(f"live.outcome invalid: {outcome!r}")
    operation = live.get("operation")
    if operation not in DECODE_OPS | {"start"}:
        errors.append(f"live.operation invalid: {operation!r}")
    op_id = live.get("operation_id")
    if not isinstance(op_id, str) or not _REQUEST_ID_RE.fullmatch(op_id):
        errors.append(f"live.operation_id invalid: {op_id!r}")
    restart = live.get("restart_sha256")
    if not isinstance(restart, str) or not se.SHA256_RE.fullmatch(restart):
        errors.append("live.restart_sha256 must be 64-char hex")
    loaded_seq = live.get("loaded_sequence")
    if not isinstance(loaded_seq, int) or isinstance(loaded_seq, bool) or loaded_seq < 0:
        errors.append(f"live.loaded_sequence must be >= 0, got {loaded_seq!r}")
    elapsed = live.get("elapsed_ms")
    if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or elapsed < 0:
        errors.append(f"live.elapsed_ms must be >= 0, got {elapsed!r}")
    started = live.get("started_at")
    finished = live.get("finished_at")
    for key, value in (("started_at", started), ("finished_at", finished)):
        if not isinstance(value, str) or not se.RFC3339_UTC_RE.fullmatch(value):
            errors.append(f"live.{key} must be RFC3339 UTC")
    if isinstance(started, str) and isinstance(finished, str) and finished < started:
        errors.append("live.finished_at must not precede started_at")
    requested = live.get("requested_source")
    loaded = live.get("loaded_source")
    for name, source in (("requested_source", requested),):
        errors.extend(_validate_live_source(source, f"live.{name}"))
    if loaded is None:
        if outcome == "ok":
            errors.append("live.loaded_source is required on success")
    else:
        errors.extend(_validate_live_source(loaded, "live.loaded_source"))
        if outcome == "ok" and loaded != requested:
            errors.append("live.loaded_source must equal live.requested_source on success")
    daemon_code = live.get("daemon_code")
    if daemon_code is not None and (not isinstance(daemon_code, int) or isinstance(daemon_code, bool)):
        errors.append(f"live.daemon_code must be an integer, got {daemon_code!r}")
    if outcome == "ok" and daemon_code not in (0, None):
        errors.append(f"successful live outcome cannot carry daemon_code {daemon_code!r}")
    screenshot = live.get("screenshot")
    if screenshot is not None:
        if not isinstance(screenshot, Mapping):
            errors.append("live.screenshot must be an object")
        else:
            path = screenshot.get("path")
            digest = screenshot.get("sha256")
            se._validate_relative(path, "live.screenshot.path", errors)
            if not isinstance(digest, str) or not se.SHA256_RE.fullmatch(digest):
                errors.append("live.screenshot.sha256 must be 64-char hex")
    target = document.get("target")
    if isinstance(target, Mapping):
        if target.get("flavor") != "dev":
            errors.append("live receipts require target.flavor=dev")
        if target.get("profile") != "local_dev":
            errors.append("live receipts require target.profile=local_dev")
    return errors


def _validate_live_source(source: Any, path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(source, Mapping):
        return [f"{path}: required object"]
    extra = set(source) - {"git_sha", "dirty_digest", "inputs_sha256"}
    if extra:
        errors.append(f"{path} has unknown fields {sorted(extra)}")
    git_sha = source.get("git_sha")
    if not isinstance(git_sha, str) or not se.GIT_SHA_RE.fullmatch(git_sha):
        errors.append(f"{path}.git_sha must be 40-char hex")
    dirty = source.get("dirty_digest")
    if not isinstance(dirty, str) or not se.DIRTY_DIGEST_RE.fullmatch(dirty):
        errors.append(f"{path}.dirty_digest is invalid")
    digest = source.get("inputs_sha256")
    if not isinstance(digest, str) or not se.SHA256_RE.fullmatch(digest):
        errors.append(f"{path}.inputs_sha256 must be 64-char hex")
    return errors


def admit_attachment(
    lease: Mapping[str, Any],
    receipt: Mapping[str, Any],
    source: SourceStamp,
    *,
    ready: bool,
    supported: Sequence[str],
    selected: Sequence[str],
) -> None:
    if int(lease.get("generation", 0)) != int((receipt.get("live") or {}).get("generation", -1)):
        raise LiveError("stale-session", "live receipt generation does not match the lease")
    live = receipt.get("live") or {}
    loaded = live.get("loaded_source") or {}
    if loaded.get("inputs_sha256") != source.inputs_sha256:
        raise LiveError("stale-build", "loaded inputs do not match the current worktree")
    if not receipt.get("artifact"):
        raise LiveError("stale-build", "live attach requires a cold artifact")
    if lease.get("profile") not in SAFE_PROFILES or lease.get("flavor") not in SAFE_FLAVORS:
        raise LiveError("unsafe-config", "live attach requires dev/local_dev")
    if not ready:
        raise LiveError("unready", "live session is not ready")
    if not selected:
        raise LiveError("unsupported-operation", "no journeys selected")
    missing = [name for name in selected if name not in set(supported)]
    if missing:
        raise LiveError("unsupported-operation", f"unsupported live journeys {missing}")


class LiveSession:
    def __init__(
        self,
        repo_root: Path,
        directory: Path,
        *,
        load_lease: Callable[[], Mapping[str, Any]],
        source: Callable[[], SourceStamp],
        factory: Callable[[LaunchSpec], MachineProcess],
        screenshot: Callable[[str, Path], None],
        startup_timeout_s: float = 900,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        if not 1 <= float(startup_timeout_s) <= 1800:
            raise LiveError("unsafe-config", "startup_timeout_s must be between 1 and 1800")
        self.repo_root = Path(repo_root)
        self.directory = Path(directory)
        self._load_lease = load_lease
        self._source = source
        self._factory = factory
        self._screenshot = screenshot
        self._startup_timeout_s = float(startup_timeout_s)
        self._monotonic = monotonic or time.monotonic
        self._child: MachineProcess | None = None
        self._child_generation: int | None = None
        self._lock = threading.Lock()
        self._state = "stopped"
        self._app_id: str | None = None
        self._rpc_id = 0
        self._logs: list[dict[str, Any]] = []
        self._loaded: SourceStamp | None = None
        self._loaded_sequence = 0
        self._claimed_worktree = False
        self._closed = False

    def start(self) -> Mapping[str, Any]:
        lease = self._load_lease()
        self._assert_safe_lease(lease)
        self._assert_seed(lease)
        generation = int(lease.get("generation") or 0)
        requested = self._source()
        self._claim_worktree(str(lease.get("session_id")))
        self._child_generation = generation
        device = (lease.get("device") or {}).get("udid") or ""
        spec = LaunchSpec(
            argv=(
                "flutter",
                "run",
                "--machine",
                "--debug",
                "--flavor",
                "dev",
                "--dart-define=OMI_APP_PROFILE=local_dev",
                "--dart-define=OMI_DEV_CONTROLS=1",
                "--host-vmservice-port=0",
                "--no-dds",
            ),
            cwd=self.repo_root,
            env={},
            build_dir=self.repo_root / "build",
            device_id=str(device),
        )
        started_at = se.utc_now()
        started_mono = self._monotonic()
        try:
            self._child = self._factory(spec)
        except Exception:
            self._child_generation = None
            self._release_worktree()
            raise
        self._state = "starting"
        try:
            if not self._source_matches(requested):
                self._state = "blocked"
                return self._finish(
                    "start",
                    "blocked",
                    requested,
                    None,
                    None,
                    generation=generation,
                    started_at=started_at,
                    started_mono=started_mono,
                    error_code="stale-build",
                )
            deadline = self._deadline(self._startup_timeout_s)
            self._drain_until_started(deadline)
            if not self._source_matches(requested):
                self._state = "blocked"
                return self._finish(
                    "start",
                    "blocked",
                    requested,
                    None,
                    None,
                    generation=generation,
                    started_at=started_at,
                    started_mono=started_mono,
                    error_code="stale-build",
                )
            ready, _ = self._refresh_readiness(deadline, wait=True)
            if not self._source_matches(requested):
                self._state = "blocked"
                return self._finish(
                    "start",
                    "blocked",
                    requested,
                    None,
                    None,
                    generation=generation,
                    started_at=started_at,
                    started_mono=started_mono,
                    error_code="stale-build",
                )
            if not ready:
                self._state = "blocked"
                return self._finish(
                    "start",
                    "blocked",
                    requested,
                    None,
                    None,
                    generation=generation,
                    started_at=started_at,
                    started_mono=started_mono,
                    error_code="unready",
                )
            # Source was rechecked above. Publication still requires the pinned
            # lease and child generation — a source-hash match is not that check.
            if not self._generation_current(generation):
                return self._publication_blocked(
                    "start",
                    requested,
                    None,
                    generation=generation,
                    started_at=started_at,
                    started_mono=started_mono,
                )
            self._loaded = requested
            self._loaded_sequence = 1
            self._state = "ready"
            return self._finish(
                "start",
                "ok",
                requested,
                requested,
                0,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
            )
        except TimeoutError:
            self._state = "blocked"
            return self._finish(
                "start",
                "blocked",
                requested,
                self._loaded,
                None,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="deadline",
            )
        except LiveError as exc:
            self._state = "blocked"
            return self._finish(
                "start",
                "blocked",
                requested,
                self._loaded,
                None,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code=exc.code,
            )

    def request(
        self,
        operation: str,
        *,
        generation: int,
        params: Mapping[str, Any] | None = None,
        timeout_s: float = 30,
    ) -> Mapping[str, Any]:
        params = dict(params or {})
        self._assert_generation(generation)
        started_at = se.utc_now()
        started_mono = self._monotonic()
        if operation in ("status", "logs"):
            if operation == "status":
                return self._status(generation=generation, started_at=started_at, started_mono=started_mono)
            return self._logs_reply(params, generation=generation, started_at=started_at, started_mono=started_mono)
        if not self._lock.acquire(blocking=False):
            raise LiveError("busy", "a live mutation is already in progress")
        previous = self._state
        self._state = "busy"
        try:
            return self._request_locked(
                operation,
                generation=generation,
                params=params,
                timeout_s=timeout_s,
                started_at=started_at,
                started_mono=started_mono,
            )
        finally:
            if self._state == "busy":
                self._state = previous
            self._lock.release()

    def close(self) -> None:
        if self._closed:
            return
        child = self._child
        if child is not None and self._app_id:
            try:
                self._rpc("app.stop", {"appId": self._app_id}, deadline=self._monotonic() + 5)
            except (LiveError, TimeoutError, OSError):
                pass
        if child is not None:
            child.close()
        self._child = None
        self._app_id = None
        self._state = "stopped"
        self._closed = True
        self._release_worktree()

    def _request_locked(
        self,
        operation: str,
        *,
        generation: int,
        params: Mapping[str, Any],
        timeout_s: float,
        started_at: str,
        started_mono: float,
    ) -> Mapping[str, Any]:
        self._assert_generation(generation)
        if operation == "stop":
            self.close()
            stamp = self._loaded or self._source()
            return self._finish(
                "stop",
                "ok",
                stamp,
                self._loaded,
                0,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
            )
        if operation == "controls":
            return self._controls(
                params,
                timeout_s,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
            )
        if operation == "screenshot":
            return self._take_screenshot(generation=generation, started_at=started_at, started_mono=started_mono)
        if operation in ("reload", "restart"):
            return self._reload(
                full_restart=operation == "restart",
                timeout_s=timeout_s,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
            )
        raise LiveError("unsupported-operation", f"unsupported live operation {operation!r}")

    def _assert_generation(self, generation: int) -> None:
        if not self._generation_current(generation):
            raise LiveError("stale-session", "lease generation moved")

    def _generation_current(self, generation: int) -> bool:
        lease = self._load_lease()
        current = int(lease.get("generation", 0))
        if int(generation) != current:
            return False
        if self._child_generation is not None and int(generation) != int(self._child_generation):
            return False
        return True

    def _publication_blocked(
        self,
        operation: str,
        requested: SourceStamp,
        loaded: SourceStamp | None,
        *,
        generation: int,
        started_at: str,
        started_mono: float,
        daemon_code: int | None = None,
    ) -> Mapping[str, Any]:
        """Fence a completion whose lease/child generation moved during async work."""

        self._state = "blocked"
        return self._finish(
            operation,
            "blocked",
            requested,
            loaded,
            daemon_code,
            generation=generation,
            started_at=started_at,
            started_mono=started_mono,
            error_code="stale-session",
        )

    def _source_matches(self, requested: SourceStamp) -> bool:
        return self._source().inputs_sha256 == requested.inputs_sha256

    def _deadline(self, timeout_s: float) -> float:
        return self._monotonic() + float(timeout_s)

    def _remaining(self, deadline: float) -> float:
        left = deadline - self._monotonic()
        if left <= 0:
            raise TimeoutError("machine deadline")
        return left

    def _assert_safe_lease(self, lease: Mapping[str, Any]) -> None:
        owner = lease.get("owner") or {}
        if owner.get("host") != platform.node() or owner.get("user") != getpass.getuser():
            raise LiveError("unsafe-config", "lease owner is not this host/user")
        if lease.get("flavor") not in SAFE_FLAVORS or lease.get("profile") not in SAFE_PROFILES:
            raise LiveError("unsafe-config", "live start requires flavor=dev and profile=local_dev")
        if lease.get("app_id") not in DEFAULT_APP_IDS.values():
            raise LiveError("unsafe-config", f"live start refuses app_id {lease.get('app_id')!r}")
        api = _env_api_base(self.repo_root)
        if api is None or not _loopback_or_empty(api):
            raise LiveError("unsafe-config", "app/.dev.env API_BASE_URL must be empty or loopback")

    def _assert_seed(self, lease: Mapping[str, Any]) -> None:
        path = self.directory / "seed.json"
        if not path.is_file():
            raise LiveError("unsafe-config", "seed.json is required before live start")
        seed = json.loads(path.read_text(encoding="utf-8"))
        if seed.get("uid") != lease.get("default_auth_uid"):
            raise LiveError("unsafe-config", "seed uid does not match lease.default_auth_uid")
        if seed.get("fixture_version") != lease.get("fixture_version"):
            raise LiveError("unsafe-config", "seed fixture_version does not match the lease")
        if lease.get("status") != "seeded":
            raise LiveError("unsafe-config", "lease status must be seeded before live start")

    def _claim_worktree(self, session_id: str) -> None:
        path = self.repo_root / WORKTREE_LOCK
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError as exc:
            raise LiveError("worktree-busy", f"worktree already has a live session ({path})") from exc
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(session_id + "\n")
        self._claimed_worktree = True

    def _release_worktree(self) -> None:
        if not self._claimed_worktree:
            return
        path = self.repo_root / WORKTREE_LOCK
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        self._claimed_worktree = False

    def _drain_until_started(self, deadline: float) -> None:
        events = []
        while True:
            message = self._read(deadline)
            if message is None:
                raise LiveError("daemon-exited", "flutter daemon exited before app.started")
            name = message.get("event")
            if name:
                events.append(name)
                if name == "app.start":
                    self._app_id = str((message.get("params") or {}).get("appId") or "")
                if name == "app.started":
                    if "daemon.connected" not in events or "app.start" not in events:
                        raise LiveError("malformed-response", "app.started without app.start")
                    return

    def _read(self, deadline: float) -> dict[str, Any] | None:
        if self._child is None:
            raise LiveError("unready", "no live child")
        line = self._child.receive(self._remaining(deadline))
        if line is None:
            return None
        message = _parse_machine(line)
        if message.get("event") == "app.log":
            self._record_log(message)
        return message

    def _record_log(self, message: Mapping[str, Any]) -> None:
        params = message.get("params") or {}
        self._logs.append(
            {"message": sanitize_log_text(str(params.get("log", ""))), "error": bool(params.get("error"))}
        )
        if len(self._logs) > MAX_LOG_ENTRIES:
            self._logs = self._logs[-MAX_LOG_ENTRIES:]

    def _rpc(self, method: str, params: Mapping[str, Any], *, deadline: float) -> dict[str, Any]:
        if self._child is None:
            raise LiveError("unready", "no live child")
        self._rpc_id += 1
        rpc_id = self._rpc_id
        self._child.send(json.dumps([{"id": rpc_id, "method": method, "params": dict(params)}]) + "\n")
        while True:
            message = self._read(deadline)
            if message is None:
                raise LiveError("daemon-exited", "flutter daemon exited during an operation")
            if message.get("id") == rpc_id:
                return message

    def _rpc_result_object(self, reply: Mapping[str, Any], *, what: str) -> dict[str, Any]:
        if "error" in reply:
            raise LiveError("malformed-response", f"{what} negotiation failed")
        result = reply.get("result")
        if not isinstance(result, dict):
            raise LiveError("malformed-response", f"{what} result must be an object")
        return result

    def _validate_capabilities(self, reply: Mapping[str, Any]) -> None:
        result = self._rpc_result_object(reply, what="capabilities")
        if result.get("contract_version") != CONTRACT_VERSION:
            raise LiveError("malformed-response", "unsupported controls contract version")
        capabilities = result.get("capabilities")
        if not isinstance(capabilities, list):
            raise LiveError("malformed-response", "capabilities must be a list")
        missing = REQUIRED_CAPABILITIES.difference(capabilities)
        if missing:
            raise LiveError("malformed-response", f"missing required capabilities {sorted(missing)}")

    def _refresh_readiness(self, deadline: float, *, wait: bool) -> tuple[bool, dict[str, Any]]:
        cap = self._rpc(
            "app.callServiceExtension",
            {"appId": self._app_id, "methodName": "ext.omi.controls.capabilities", "params": {}},
            deadline=deadline,
        )
        self._validate_capabilities(cap)
        state_reply = self._rpc(
            "app.callServiceExtension",
            {"appId": self._app_id, "methodName": "ext.omi.controls.state", "params": {}},
            deadline=deadline,
        )
        state = self._rpc_result_object(state_reply, what="state")
        if wait and not self._is_ready(state):
            waited = self._rpc(
                "app.callServiceExtension",
                {
                    "appId": self._app_id,
                    "methodName": "ext.omi.controls.wait_ready",
                    "params": {"condition": "signedIn", "deadline_ms": "15000"},
                },
                deadline=deadline,
            )
            result = self._rpc_result_object(waited, what="wait_ready")
            nested = result.get("state")
            state = nested if isinstance(nested, Mapping) else result
        if not isinstance(state, Mapping):
            raise LiveError("malformed-response", "state result must be an object")
        return self._is_ready(state), dict(state)

    def _is_ready(self, state: Mapping[str, Any]) -> bool:
        lease = self._load_lease()
        seed_path = self.directory / "seed.json"
        seed = json.loads(seed_path.read_text(encoding="utf-8")) if seed_path.is_file() else {}
        if state.get("profile") != READY_PROFILE:
            return False
        if state.get("contract_version") != CONTRACT_VERSION:
            return False
        readiness = state.get("readiness")
        if not isinstance(readiness, Mapping):
            return False
        # A present-but-non-boolean flag is a malformed response, not a
        # not-ready state: strings such as "false" must fail closed here
        # rather than fall through to the wait_ready recovery path.
        for key in ("signedIn", "routed", "captureIdle"):
            if key not in readiness:
                return False
            value = readiness[key]
            if not isinstance(value, bool):
                raise LiveError(
                    "malformed-response", f"readiness.{key} must be boolean, got {value!r}"
                )
        if not all(readiness[key] for key in ("signedIn", "routed", "captureIdle")):
            return False
        principal = state.get("principal")
        if not isinstance(principal, Mapping):
            return False
        uid = principal.get("uid")
        return uid == lease.get("default_auth_uid") == seed.get("uid")

    def _reload(
        self,
        *,
        full_restart: bool,
        timeout_s: float,
        generation: int,
        started_at: str,
        started_mono: float,
    ) -> Mapping[str, Any]:
        requested = self._source()
        loaded = self._loaded
        op = "restart" if full_restart else "reload"
        if loaded is not None and requested.restart_sha256 != loaded.restart_sha256:
            return self._finish(
                "reload",
                "restart-required",
                requested,
                loaded,
                None,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="restart-required",
            )
        deadline = self._deadline(timeout_s)
        try:
            reply = self._rpc(
                "app.restart",
                {"appId": self._app_id, "fullRestart": full_restart, "pause": False},
                deadline=deadline,
            )
        except LiveError as exc:
            self._state = "blocked"
            return self._finish(
                op,
                "blocked",
                requested,
                loaded,
                None,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="daemon-exited" if exc.code == "daemon-exited" else exc.code,
            )
        except TimeoutError:
            self._state = "blocked"
            return self._finish(
                op,
                "blocked",
                requested,
                loaded,
                None,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="deadline",
            )
        if not self._source_matches(requested):
            self._state = "blocked"
            daemon_code = reply.get("result", {}).get("code") if isinstance(reply.get("result"), dict) else None
            return self._finish(
                op,
                "blocked",
                requested,
                loaded,
                daemon_code,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="stale-build",
            )
        if "error" in reply:
            self._state = "blocked"
            return self._finish(
                op,
                "blocked",
                requested,
                loaded,
                None,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="malformed-response",
            )
        result = reply.get("result")
        if not isinstance(result, dict) or "code" not in result:
            return self._finish(
                op,
                "blocked",
                requested,
                loaded,
                None,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="malformed-response",
            )
        code = result.get("code")
        if code != 0:
            return self._finish(
                op,
                "rejected",
                requested,
                loaded,
                code,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="reload-rejected",
            )
        try:
            ready, _ = self._refresh_readiness(deadline, wait=True)
        except TimeoutError:
            self._state = "blocked"
            return self._finish(
                op,
                "blocked",
                requested,
                loaded,
                code,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="deadline",
            )
        except LiveError as exc:
            self._state = "blocked"
            return self._finish(
                op,
                "blocked",
                requested,
                loaded,
                code,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code=exc.code,
            )
        if not self._source_matches(requested):
            self._state = "blocked"
            return self._finish(
                op,
                "blocked",
                requested,
                loaded,
                code,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="stale-build",
            )
        if not ready:
            self._state = "blocked"
            return self._finish(
                op,
                "blocked",
                requested,
                loaded,
                code,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="unready",
            )
        if not self._generation_current(generation):
            return self._publication_blocked(
                op,
                requested,
                loaded,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                daemon_code=code,
            )
        self._loaded = requested
        self._loaded_sequence += 1
        self._state = "ready"
        return self._finish(
            op,
            "ok",
            requested,
            requested,
            code,
            generation=generation,
            started_at=started_at,
            started_mono=started_mono,
        )

    def _controls(
        self,
        params: Mapping[str, Any],
        timeout_s: float,
        *,
        generation: int,
        started_at: str,
        started_mono: float,
    ) -> Mapping[str, Any]:
        method = params.get("method")
        if method not in CONTROL_METHODS:
            raise LiveError("unsupported-operation", f"unsupported control {method!r}")
        inner = dict(params.get("params") or {})
        reply = self._rpc(
            "app.callServiceExtension",
            {"appId": self._app_id, "methodName": f"ext.omi.controls.{method}", "params": inner},
            deadline=self._deadline(timeout_s),
        )
        stamp = self._loaded or self._source()
        if not self._generation_current(generation):
            return self._publication_blocked(
                "controls",
                stamp,
                self._loaded,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
            )
        if "error" in reply:
            return self._finish(
                "controls",
                "rejected",
                stamp,
                self._loaded,
                None,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="unsupported-operation",
                result=reply.get("error"),
            )
        return self._finish(
            "controls",
            "ok",
            stamp,
            self._loaded,
            0,
            generation=generation,
            started_at=started_at,
            started_mono=started_mono,
            result=reply.get("result") or {},
        )

    def _take_screenshot(self, *, generation: int, started_at: str, started_mono: float) -> Mapping[str, Any]:
        stamp = self._source()
        if self._loaded is None or stamp.inputs_sha256 != self._loaded.inputs_sha256:
            return self._finish(
                "screenshot",
                "blocked",
                stamp,
                self._loaded,
                None,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
                error_code="stale-build",
            )
        relative = Path("screenshots") / f"{uuid.uuid4().hex}.png"
        path = self.directory / relative
        lease = self._load_lease()
        device = str((lease.get("device") or {}).get("udid") or "")
        self._screenshot(device, path)
        if not self._generation_current(generation):
            return self._publication_blocked(
                "screenshot",
                stamp,
                self._loaded,
                generation=generation,
                started_at=started_at,
                started_mono=started_mono,
            )
        shot = {"path": str(relative), "sha256": se.file_sha256(path)}
        return self._finish(
            "screenshot",
            "ok",
            stamp,
            self._loaded,
            0,
            generation=generation,
            started_at=started_at,
            started_mono=started_mono,
            screenshot=shot,
        )

    def _status(self, *, generation: int, started_at: str, started_mono: float) -> Mapping[str, Any]:
        stamp = self._loaded or self._source()
        return self._finish(
            "status",
            "ok",
            stamp,
            self._loaded,
            0,
            generation=generation,
            started_at=started_at,
            started_mono=started_mono,
            result={"state": self._state},
        )

    def _logs_reply(
        self,
        params: Mapping[str, Any],
        *,
        generation: int,
        started_at: str,
        started_mono: float,
    ) -> Mapping[str, Any]:
        cursor = int(params.get("cursor") or 0)
        limit = int(params.get("limit") or 50)
        if cursor < 0:
            cursor = 0
        if limit < 0:
            limit = 0
        entries = self._logs[cursor : cursor + min(limit, MAX_LOG_ENTRIES)]
        stamp = self._loaded or self._source()
        return self._finish(
            "logs",
            "ok",
            stamp,
            self._loaded,
            0,
            generation=generation,
            started_at=started_at,
            started_mono=started_mono,
            result={"entries": entries, "next_cursor": cursor + len(entries)},
        )

    def _finish(
        self,
        operation: str,
        outcome: str,
        requested: SourceStamp,
        loaded: SourceStamp | None,
        daemon_code: int | None,
        *,
        generation: int,
        started_at: str,
        started_mono: float,
        error_code: str | None = None,
        result: Mapping[str, Any] | None = None,
        screenshot: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        finished_at = _as_rfc3339_utc(se.utc_now())
        elapsed_ms = max(0, round((self._monotonic() - started_mono) * 1000))
        operation_id = f"op-{uuid.uuid4().hex[:12]}"
        live: dict[str, Any] = {
            "generation": int(generation),
            "operation_id": operation_id,
            "operation": operation,
            "outcome": outcome,
            "requested_source": _stamp_source(requested),
            "loaded_source": None if loaded is None else _stamp_source(loaded),
            "loaded_sequence": self._loaded_sequence,
            "restart_sha256": (loaded or requested).restart_sha256,
            "started_at": _as_rfc3339_utc(started_at),
            "finished_at": finished_at,
            "elapsed_ms": elapsed_ms,
        }
        if daemon_code is not None:
            live["daemon_code"] = daemon_code
        if screenshot is not None:
            live["screenshot"] = screenshot
        document = self._attach_live(live)
        op_path = self.directory / "operations" / operation_id / "evidence.json"
        se.write_evidence(op_path, document)
        se.write_evidence(self.directory / "evidence.json", document)
        return {
            "outcome": outcome,
            "result": dict(result or ({"state": self._state} if operation == "status" else {})),
            "evidence": document,
            "error_code": error_code,
        }

    def _attach_live(self, live: Mapping[str, Any]) -> dict[str, Any]:
        path = self.directory / "evidence.json"
        if path.is_file():
            document = json.loads(path.read_text(encoding="utf-8"))
        else:
            document = {}
        document = dict(document)
        document["live"] = dict(live)
        return document


def dispatch(
    repo_root: Path, session_id: str, operation: str, params: Mapping[str, Any] | None = None
) -> Mapping[str, Any]:
    del params
    from .mobile_session import _load_lease

    directory = session_dir(repo_root, session_id)
    _load_lease(directory / LEASE_FILENAME)
    if operation == "start":
        raise LiveNotImplemented(
            "V1 PR1 adds no new live-process adapter; LiveSession is fake-backed in tests "
            "and does not spawn flutter run on a device"
        )
    raise LiveNotImplemented(
        f"no live broker is running for {operation!r} on {session_id}; "
        "V1 PR1 adds no new live-process adapter and does not spawn flutter run"
    )


def verify_live(repo_root: Path, args: Any) -> int:
    from . import mobile_verify as verify

    discovered = verify.discover_journeys(repo_root)
    if getattr(args, "filter", None):
        selected = tuple(name for name in discovered if args.filter in name)
        if not selected:
            print(f"selection drift: filter '{args.filter}' matched no journey", file=sys.stderr)
            return verify.EXIT_SELECTION_DRIFT
    elif getattr(args, "all", False):
        selected = discovered
    else:
        selection = verify.select_journeys(repo_root, verify._collect_paths(args))
        if selection.drift:
            for line in selection.drift:
                print(f"selection drift: {line}", file=sys.stderr)
            return verify.EXIT_SELECTION_DRIFT
        selected = selection.selected
        if not selected:
            return verify.EXIT_OK
    dispatch(repo_root, args.session, "status")
    print(
        f"blocked: live journeys {list(selected)} have no adapter in V1 PR1",
        file=sys.stderr,
    )
    return verify.EXIT_BLOCKED


def teardown(
    repo_root: Path,
    session_id: str,
    env: Mapping[str, str] | None = None,
    *,
    probe: Callable[[BrokerIdentity], BrokerIdentity | None] | None = None,
    terminate: Callable[[int], None] | None = None,
) -> None:
    directory = session_dir(repo_root, session_id, env)
    path = directory / LIVE_FILENAME
    if not path.is_file():
        return
    if probe is None or terminate is None:
        raise LiveError("unsafe-config", "live teardown cannot prove process identity without probe/terminate")
    payload = json.loads(path.read_text(encoding="utf-8"))
    identities = []
    for key in ("broker", "child"):
        raw = payload.get(key)
        if not isinstance(raw, dict):
            raise LiveError("unsafe-config", f"live.json missing {key} identity")
        identities.append(BrokerIdentity(**raw))
    signaled: set[int] = set()

    def terminate_once(pid: int) -> None:
        if pid in signaled:
            return
        signaled.add(pid)
        terminate(pid)

    for identity in identities:
        observed = probe(identity)
        stop_owned_broker(identity, observed, terminate_once)
        if observed is not None and probe(identity) is not None:
            raise LiveError("unsafe-config", f"live pid {identity.pid} still alive after teardown signal")
    try:
        path.unlink()
    except FileNotFoundError:
        pass

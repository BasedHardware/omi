"""V1 skeleton. Builder: Harness V1. Contract: ../LIVE_SESSIONS.md.

No runtime is started by this module yet. Dependency seams are constructor
inputs, never CLI flags that could replace production safety checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from .mobile_session import SessionError

OPERATIONS = ("start", "reload", "restart", "screenshot", "logs", "controls", "status", "stop")


class LiveNotImplemented(SessionError, NotImplementedError):
    """Explicit exit-2 refusal while the V1 builder has not implemented this."""


class LiveError(SessionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SourceStamp:
    git_sha: str
    dirty_digest: str
    inputs_sha256: str  # includes untracked input contents, unlike legacy dirty_digest
    restart_sha256: str  # native/assets/pubspec/generated config/SDK inputs


@dataclass(frozen=True)
class LaunchSpec:
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    build_dir: Path
    device_id: str


class MachineProcess(Protocol):
    """Line I/O around a real child. EOF returns None; deadline raises TimeoutError."""
    def send(self, line: str) -> None: ...
    def receive(self, timeout_s: float) -> str | None: ...
    def close(self) -> None: ...


class LiveSession:
    """Broker engine; production and subprocess contract fixture use this class.

    load_lease/source re-read before AND after operations; screenshot writes
    PNG bytes for the exact lease device to the broker-assigned relative path.
    factory only supplies child line I/O; it must not implement the protocol.
    """
    def __init__(
        self, repo_root: Path, directory: Path, *,
        load_lease: Callable[[], Mapping[str, Any]],
        source: Callable[[], SourceStamp],
        factory: Callable[[LaunchSpec], MachineProcess],
        screenshot: Callable[[str, Path], None],
        startup_timeout_s: float = 900,
    ) -> None:
        raise LiveNotImplemented("V1 live-session engine is not implemented; Harness V1 owns this package")

    def start(self) -> Mapping[str, Any]:
        raise LiveNotImplemented("V1 live start is not implemented")

    def request(self, operation: str, *, generation: int, params: Mapping[str, Any] | None = None,
                timeout_s: float = 30) -> Mapping[str, Any]:
        """Return {outcome, result, evidence}; accepted and refused attempts have receipts.

        outcome: ok|rejected|restart-required|blocked; error_code distinguishes
        daemon-exited, deadline, reload-rejected, malformed-response. Rejections of the request
        boundary itself raise LiveError with stable code. No retry on mutation.
        """
        raise LiveNotImplemented(f"V1 live {operation} is not implemented")

    def close(self) -> None:
        raise LiveNotImplemented("V1 live stop is not implemented")


def dispatch(repo_root: Path, session_id: str, operation: str,
             params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Short-lived socket client; start spawns the broker, never Flutter directly."""
    raise LiveNotImplemented(f"V1 live {operation} is not implemented; builder package: Harness V1")


def verify_live(repo_root: Path, args: Any) -> int:
    """Attach selected journeys to the broker. Never silently invoke a cold runner."""
    raise LiveNotImplemented("V1 mobile-verify fast --session is not implemented; builder package: Harness V1")


def validate_live_evidence(document: Mapping[str, Any]) -> list[str]:
    """V1 validates frozen schema plus runtime attribution; no live fields ignored."""
    raise LiveNotImplemented("V1 live evidence validation is not implemented")


def teardown(repo_root: Path, session_id: str, env: Mapping[str, str] | None = None, *,
             probe: Callable[[BrokerIdentity], BrokerIdentity | None] | None = None,
             terminate: Callable[[int], None] | None = None) -> None:
    """live.json has broker and child objects encoded as BrokerIdentity fields.

    Production probes full identity; injected callbacks only exercise teardown.
    Builder wires stop/reset/recover here before services/device/generation edits.

    No live manifest: no-op. Present manifest: bounded stop of proven owned
    process group; unverifiable ownership raises LiveError without cleanup.
    """
    raise LiveNotImplemented("V1 live lifecycle teardown is not implemented")


def admit_attachment(lease: Mapping[str, Any], receipt: Mapping[str, Any], source: SourceStamp,
                     *, ready: bool, supported: Sequence[str], selected: Sequence[str]) -> None:
    """Shared verify admission; refuse with LiveError before invoking any journey."""
    raise LiveNotImplemented("V1 live verification admission is not implemented")


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


def stop_owned_broker(recorded: BrokerIdentity, observed: BrokerIdentity | None,
                      terminate: Callable[[int], None]) -> None:
    """Teardown primitive: matching identity signals once; provably dead is no-op.

    observed=None means an authoritative process probe proved death, never a
    failed probe. Unreadable probes must raise before calling this function.
    Different boot with no process is dead; a living reused PID is foreign.
    """
    raise LiveNotImplemented("V1 owned broker teardown is not implemented")


def decode_request(line: bytes, *, session_id: str, generation: int) -> Mapping[str, Any]:
    """Broker admission: frozen wire schema, size bound, exact lease binding."""
    raise LiveNotImplemented("V1 broker wire admission is not implemented")

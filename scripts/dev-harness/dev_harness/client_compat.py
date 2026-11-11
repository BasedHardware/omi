"""C10 replay skeleton. App core supplies frozen decoders; CI/release wires backend E2E.

No imports of the backend, device services or network clients at module load.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    query: tuple[tuple[str, str], ...] = ()
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes = b''


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class Case:
    release: str
    platform: str
    id: str
    request: Request
    decoder: str
    observations: Mapping[str, Any]
    status: int = 200


@dataclass(frozen=True)
class Issue:
    release: str
    platform: str
    case: str
    pointer: str
    reason: str


@dataclass(frozen=True)
class ReplayResult:
    executed: int
    issues: tuple[Issue, ...]


def replay(cases: Sequence[Case], *, send: Callable[[Request], Response],
           decode: Callable[[str, Response], Mapping[str, Any]]) -> ReplayResult:
    """Send each exact request once, check status, decode current bytes, compare observations.

    A decoder rejects missing/null/type/enum changes via ValueError with a JSON
    pointer. Timeout, transport, malformed/empty response and zero cases cannot pass.
    Never retry a rejected request. Report all cases, not just the first mismatch.
    """
    raise NotImplementedError('C10 replay engine: App core builder')


def registered_cases(root: Path, *, supported_only: bool = True) -> Sequence[Case]:
    raise NotImplementedError('C10 released fixture loader: App core builder')


def decode_released(root: Path, decoder: str, response: Response, *,
                    execute: Callable[[Sequence[str], bytes], bytes] | None = None) -> Mapping[str, Any]:
    """Resolve decoder path in catalog, verify hash, then invoke pinned Dart.

    execute is a process seam only; default subprocess uses the pinned SDK.
    stdin JSON: status, headers, body_base64; stdout: observation object.
    Reject unregistered/tampered paths before invoking any process. The decoder
    is a frozen standalone entrypoint, never a current app model import.
    """
    raise NotImplementedError('C10 standalone frozen decoder runner: App core builder')


def seed_backend(fake_firestore: Any, uid: str) -> None:
    """Synthetic sentinel records for the real backend E2E app, no network."""
    raise NotImplementedError('C10 synthetic backend data: App core builder')


def run_registered_replay(root: Path, *, send: Callable[[Request], Response]) -> ReplayResult:
    """Same engine used by E2E acceptance and release replay command."""
    raise NotImplementedError('C10 registered backend replay: CI/release builder')

"""Dev-only capture boundary for local parity-pack cassettes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time
from typing import Any, Callable, Mapping

from .schema import CassetteIdentity, RequestFingerprint
from .whitelist import CaptureWhitelist


@dataclass(frozen=True)
class CassetteEvent:
    direction: str
    dt_ms: int
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.direction not in {"client", "outbound", "inbound"}:
            raise ValueError("direction must be client, outbound, or inbound")
        if self.dt_ms < 0:
            raise ValueError("dt_ms must be non-negative")


class CaptureTap:
    """Persists restricted local cassettes only after the dev whitelist allows it."""

    def __init__(self, root: Path, whitelist: CaptureWhitelist, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.root, self.whitelist, self._clock = root, whitelist, clock
        self.denied_metadata: list[dict[str, str]] = []

    def start(
        self, principal_id: str | None, identity: CassetteIdentity, request: Mapping[str, Any]
    ) -> "CaptureInvocation | None":
        if not self.whitelist.allows(principal_id):
            self.denied_metadata.append({"provider_lane": identity.provider_lane, "reason": "whitelist_miss"})
            del self.denied_metadata[:-100]
            return None
        return CaptureInvocation(self.root, identity, RequestFingerprint.from_request(request), self._clock)


class CaptureInvocation:
    def __init__(
        self, root: Path, identity: CassetteIdentity, fingerprint: RequestFingerprint, clock: Callable[[], float]
    ) -> None:
        self.root, self.identity, self.fingerprint, self._clock = root, identity, fingerprint, clock
        self._started_at = clock()
        self._events: list[CassetteEvent] = []

    def observe(self, direction: str, payload: Mapping[str, Any]) -> None:
        self._events.append(CassetteEvent(direction, round((self._clock() - self._started_at) * 1000), dict(payload)))

    def persist(self) -> Path:
        path = self.root / "cassettes" / f"{self.identity.key()}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": 1,
            "identity": self.identity.as_dict(),
            "request_fingerprint": self.fingerprint.as_dict(),
            "events": [asdict(event) for event in self._events],
        }
        path.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        return path

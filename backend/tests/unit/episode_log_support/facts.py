"""In-memory append-only fact log with unique event keys (step-C prototype).

The event key is (uid, cid, kind, payload_hash) — the arch-data schema. A
repeat delivery of the same fact carries the same key and appends nothing.
A changed span (growth) is a different payload, hence a new fact; the
projector folds consecutive span facts for one cid into a min/max envelope.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Fact:
    seq: int
    uid: str
    cid: str
    kind: str  # span_recorded | conversation_merged | conversation_discarded
    payload: dict
    key: str


class FactLog:
    """Append-only; duplicate keys are rejected (the paid-once/idempotency key)."""

    def __init__(self) -> None:
        self._facts: list[Fact] = []
        self._keys: set[str] = set()

    def append(self, uid: str, cid: str, kind: str, payload: dict) -> bool:
        key = f"{uid}:{cid}:{kind}:{payload_hash(payload)}"
        if key in self._keys:
            return False
        self._facts.append(Fact(len(self._facts) + 1, uid, cid, kind, dict(payload), key))
        self._keys.add(key)
        return True

    def span(self, uid: str, cid: str, start, end, source: str | None) -> bool:
        return self.append(
            uid, cid, 'span_recorded', {'start': start.isoformat(), 'end': end.isoformat(), 'source': source}
        )

    def merged(self, uid: str, donor: str, survivor: str) -> bool:
        return self.append(uid, donor, 'conversation_merged', {'survivor': survivor})

    def discarded(self, uid: str, cid: str) -> bool:
        return self.append(uid, cid, 'conversation_discarded', {})

    def facts(self, uid: str | None = None) -> list[Fact]:
        return [f for f in self._facts if uid is None or f.uid == uid]

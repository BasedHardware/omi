"""Process-local privacy decision reuse, bounded at 60 seconds.

The 60s bound limits cache lifetime; it never certifies authorization. ALLOW
callers must validate the cached durable token/server revision AND generation
against a fresh authority read before reuse. Uncertified,
legacy or mismatched entries fall through to live authority reads.

- entries expire 60s after the authoritative read STARTED;
- this generic LRU does not certify values: privacy_negative_cache and
  batch_pipeline_privacy own per-use certification;
- blocked, deleted and unavailable outcomes are not stored by those callers.

Runtime kill switch (no deploy needed): the data-plane document
``ops_kill_switches/privacy_decision_cache`` with ``disabled: true`` turns every
cache in this module off within ``KILL_POLL_SECONDS`` in every process. The
document is polled at most once per process per poll interval; an unreadable
switch counts as disabled (fail closed to live reads).
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Hashable

MAX_SECONDS = 60.0
_MAX_ENTRIES = 50_000
_MISSING = object()
KILL_COLLECTION = 'ops_kill_switches'
KILL_DOCUMENT = 'privacy_decision_cache'
KILL_POLL_SECONDS = 30.0


def ttl_seconds() -> float:
    """The reuse window. Fixed by ruling; deliberately not configurable upward."""
    return MAX_SECONDS


class BoundedTTLCache:
    """Thread-safe LRU of (expires_at, value); expired entries are never returned."""

    def __init__(self, max_entries: int = _MAX_ENTRIES, clock: Callable[[], float] = time.monotonic):
        self._entries: OrderedDict[Hashable, tuple[float, float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._max = max_entries
        self.clock = clock

    def get(self, key: Hashable) -> tuple[Any, float | None]:
        """Return (value, age_seconds) or (_MISSING, None)."""
        now = self.clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return _MISSING, None
            expires_at, started, value = entry
            if now >= expires_at:
                self._entries.pop(key, None)
                return _MISSING, None
            self._entries.move_to_end(key)
            return value, now - started

    def put(self, key: Hashable, value: Any, *, started: float) -> bool:
        """Store a value whose authoritative read started at ``started``."""
        expires_at = started + ttl_seconds()
        if self.clock() >= expires_at:
            return False
        with self._lock:
            self._entries[key] = (expires_at, started, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)
        return True

    def forget(self, key: Hashable) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


# One cache per process for token-certified nontransactional decisions.
DECISIONS = BoundedTTLCache()


_kill_lock = threading.Lock()
_kill_state: list = []  # [(next_poll_at, disabled)]


def _read_kill_flag() -> bool:
    # The data plane (where account_deletions lives) via the bare client seam: importing
    # account_deletion_marker here would pull fsr_read_cache/Redis into the GPU batch image.
    from database._client import get_data_plane_firestore_client

    snapshot = get_data_plane_firestore_client().collection(KILL_COLLECTION).document(KILL_DOCUMENT).get()
    return bool(snapshot.exists and (snapshot.to_dict() or {}).get('disabled') is True)


def disabled() -> bool:
    """True when the runtime kill switch is set or cannot be read (fail closed)."""
    now = time.monotonic()
    with _kill_lock:
        if _kill_state and _kill_state[0][0] > now:
            return _kill_state[0][1]
    try:
        off = _read_kill_flag()
    except Exception:
        off = True
    with _kill_lock:
        _kill_state[:] = [(now + KILL_POLL_SECONDS, off)]
    if off:
        DECISIONS.clear()
    try:
        from database import privacy_check_metrics as metrics

        metrics.ttl_kill_state(off)
    except Exception:
        pass
    return off


def enabled(lever: str, uid: str) -> bool:
    """Lever on for this uid AND the runtime kill switch is clear."""
    from config.firestore_read_levers import lever_enabled

    return lever_enabled(lever, uid) and not disabled()


def is_missing(value: Any) -> bool:
    return value is _MISSING


def reset_for_tests() -> None:
    DECISIONS.clear()
    with _kill_lock:
        _kill_state.clear()

"""In-memory store for per-user weight overrides (v3).

Process-local. Resets on restart. v4 may move to Firestore (the same
Firestore where user profiles already live).

Thread-safe: all reads/writes go through a `threading.Lock`. This is
the same pattern used elsewhere in the codebase (e.g., the upstream
`_cache_lock` in `backend/routers/auto_model.py:31`).

Why in-memory for v3:
    - Per-user prefs are not on the critical path of audio streaming
      (a slow pref lookup would not stall audio). A Firestore round-trip
      per pick would add 10-50ms latency.
    - The store is small: ~100 bytes per user × 1000 users = 100KB.
    - v4 can swap in Firestore without changing the API or the caller
      (the store interface is the boundary).

Side-effect-free aside from the in-memory dict.
"""

from dataclasses import dataclass
import threading
import time
from typing import Dict, Optional

from utils.auto_router.user_prefs import UserPrefs


@dataclass(frozen=True)
class StoredPrefs:
    """A user's stored prefs + the timestamp of the last write.

    `updated_at` is epoch seconds (UTC). The endpoint surfaces it as
    ISO 8601 in the JSON response.
    """

    prefs: UserPrefs
    updated_at: float


class UserPrefsStore:
    """Thread-safe in-memory store of `StoredPrefs` keyed by uid.

    UID is whatever the auth dependency returned (Firebase uid for
    production; test uid for unit tests). Empty string is allowed (for
    "anonymous" prefs), but the test suite uses non-empty uids.

    Interface:
        get(uid) -> StoredPrefs       # never raises; returns empty prefs if missing
        set(uid, UserPrefs) -> StoredPrefs   # stores + returns the new entry
        clear(uid) -> None            # removes the entry; next get returns empty
        reset_for_testing() -> None   # clears all entries (test helper)
    """

    def __init__(self) -> None:
        self._store: Dict[str, StoredPrefs] = {}
        self._lock = threading.Lock()

    def get(self, uid: str) -> StoredPrefs:
        """Return the user's stored prefs, or empty prefs if no entry.

        Never raises — callers can safely treat a missing entry as
        "user has no overrides" and merge with task defaults.
        """
        with self._lock:
            entry = self._store.get(uid)
            if entry is None:
                return StoredPrefs(prefs=UserPrefs.empty(), updated_at=0.0)
            return entry

    def set(self, uid: str, prefs: UserPrefs) -> StoredPrefs:
        """Store the user's prefs and return the new entry with timestamp.

        Replaces any existing entry for the same uid. Sets `updated_at`
        to the current epoch seconds.
        """
        now = time.time()
        entry = StoredPrefs(prefs=prefs, updated_at=now)
        with self._lock:
            self._store[uid] = entry
        return entry

    def clear(self, uid: str) -> None:
        """Remove the user's entry. Next `get(uid)` returns empty prefs."""
        with self._lock:
            self._store.pop(uid, None)

    def reset_for_testing(self) -> None:
        """Drop all entries. Test helper — never call in production."""
        with self._lock:
            self._store.clear()


# Module-level singleton. Matches the pattern of `MetricsCollector` in
# `utils/auto_router/metrics.py` and the `DailyRefreshCache` per-task
# singletons in `task_registry.py` / `model_registry.py`. The endpoint
# imports this directly; tests reset it via `reset_for_testing()`.
_user_prefs_store: Optional[UserPrefsStore] = None
_user_prefs_store_lock = threading.Lock()


def get_user_prefs_store() -> UserPrefsStore:
    """Return the process-wide UserPrefsStore (lazy-initialized)."""
    global _user_prefs_store
    if _user_prefs_store is None:
        with _user_prefs_store_lock:
            if _user_prefs_store is None:
                _user_prefs_store = UserPrefsStore()
    return _user_prefs_store


def reset_user_prefs_store_for_testing() -> None:
    """Drop the singleton and any entries. Test helper."""
    global _user_prefs_store
    with _user_prefs_store_lock:
        if _user_prefs_store is not None:
            _user_prefs_store.reset_for_testing()
        _user_prefs_store = None

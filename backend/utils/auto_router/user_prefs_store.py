"""In-memory store for per-user weight overrides (v3).

Process-local. Resets on restart. Used for tests + dev without
Firestore (set `AUTO_ROUTER_PREFS_BACKEND=memory`). For production,
use `FirestoreUserPrefsStore` (set `AUTO_ROUTER_PREFS_BACKEND=firestore`,
the default).

Thread-safe: all reads/writes go through a `threading.Lock`. This is
the same pattern used elsewhere in the codebase (e.g., the upstream
`_cache_lock` in `backend/routers/auto_model.py:31`).

Why in-memory is OK for tests:
    - Per-user prefs are not on the critical path of audio streaming
      (a slow pref lookup would not stall audio).
    - The store is small: ~100 bytes per user × 1000 users = 100KB.
    - Tests can use this without external dependencies (no Firestore mock).

This implementation satisfies `UserPrefsStoreProtocol` from
`user_prefs_store_protocol.py`. The factory in `prefs_store_factory.py`
picks this or `FirestoreUserPrefsStore` based on `AUTO_ROUTER_PREFS_BACKEND`.
"""

import threading
import time
from typing import Dict, Optional

from utils.auto_router.user_prefs import UserPrefs
from utils.auto_router.user_prefs_store_protocol import StoredPrefs


class UserPrefsStore:
    """Thread-safe in-memory store of `StoredPrefs` keyed by uid.

    UID is whatever the auth dependency returned (Firebase uid for
    production; test uid for unit tests). Empty string is allowed (for
    "anonymous" prefs), but the test suite uses non-empty uids.

    Implements `UserPrefsStoreProtocol`.
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
# singletons in `task_registry.py` / `model_registry.py`. The factory
# in `prefs_store_factory.py` picks this or FirestoreUserPrefsStore
# based on the AUTO_ROUTER_PREFS_BACKEND env var. The router imports
# the factory, not this singleton directly.
_user_prefs_store: Optional[UserPrefsStore] = None
_user_prefs_store_lock = threading.Lock()


def get_in_memory_user_prefs_store() -> UserPrefsStore:
    """Return the process-wide in-memory UserPrefsStore (lazy-initialized).

    This is a low-level helper used by the factory. Callers should
    import `get_user_prefs_store` from `prefs_store_factory` instead,
    which honors the `AUTO_ROUTER_PREFS_BACKEND` env var.
    """
    global _user_prefs_store
    if _user_prefs_store is None:
        with _user_prefs_store_lock:
            if _user_prefs_store is None:
                _user_prefs_store = UserPrefsStore()
    return _user_prefs_store


def reset_in_memory_user_prefs_store_for_testing() -> None:
    """Drop the in-memory singleton and any entries. Test helper."""
    global _user_prefs_store
    with _user_prefs_store_lock:
        if _user_prefs_store is not None:
            _user_prefs_store.reset_for_testing()
        _user_prefs_store = None


# Backward-compat aliases. v3 callers used these names; v4 renames for clarity
# (the new `prefs_store_factory.py` picks the implementation). The router
# still uses the old names in T-401; T-403 will switch them to the factory.
get_user_prefs_store = get_in_memory_user_prefs_store
reset_user_prefs_store_for_testing = reset_in_memory_user_prefs_store_for_testing

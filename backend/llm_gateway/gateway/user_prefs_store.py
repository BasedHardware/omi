"""Storage for per-user weight overrides (gateway user prefs).

The gateway owns the interface; concrete backends are pluggable:

- ``InMemoryUserPrefsStore``: process-local, suitable for unit tests
  and offline dev. Same pattern as the upstream v3 module.
- ``FirestoreUserPrefsStore``: production backend. Persists to
  ``users/{uid}/auto_router/prefs``.

Why a Protocol: keeps the endpoint + pick path independent of the
storage layer so the Firestore impl can be swapped in/out without
changing call sites. Also lets tests inject fakes without monkey
patching.

Why the endpoint takes ``ServiceCaller.user_uid`` rather than parsing
the uid from a request header directly: the gateway is service-only,
and the calling service (``backend`` / ``pusher``) is responsible for
forwarding the Firebase-validated uid. The store never sees a raw
header.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Protocol

from llm_gateway.gateway.user_prefs import UserPrefs

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredPrefs:
    """A user's stored prefs + the timestamp of the last write.

    ``updated_at`` is epoch seconds (UTC). The endpoint surfaces it
    as ISO 8601 in the JSON response.
    """

    prefs: UserPrefs
    updated_at: float


class UserPrefsStore(Protocol):
    """Storage interface for per-user weight overrides.

    Implementations must be safe to call from multiple async tasks and
    threads (the gateway runs uvicorn workers + FastAPI's threadpool
    executors concurrently). Errors from the backend must surface as
    ``UserPrefsStoreError`` so the endpoint can return 503 instead of
    silently returning lane defaults.
    """

    def get(self, uid: str) -> StoredPrefs:
        """Return the user's stored prefs, or empty prefs if no entry.

        Implementations must never raise on a missing entry; a missing
        uid is a normal "no overrides" state, not an error.
        """
        ...

    def set(self, uid: str, prefs: UserPrefs) -> StoredPrefs:
        """Store the user's prefs and return the new entry with timestamp.

        Replaces any existing entry for the same uid. The returned
        ``StoredPrefs`` carries the timestamp the backend recorded, not
        a wall-clock approximation from the caller.
        """
        ...

    def clear(self, uid: str) -> None:
        """Remove the user's entry. Next ``get(uid)`` returns empty prefs."""
        ...


class UserPrefsStoreError(RuntimeError):
    """Raised when the prefs backend fails (Firestore, network, etc.).

    The endpoint layer translates this to 503. Callers that can fall
    back to lane defaults (e.g., the chat executor with a
    ``weights_overridable: false`` lane) should treat a fetch failure
    as "no override" rather than a hard error.
    """


# ---------------------------------------------------------------------------
# In-memory implementation (dev / tests)
# ---------------------------------------------------------------------------


class InMemoryUserPrefsStore:
    """Thread-safe in-memory store keyed by uid.

    Matches the pattern used elsewhere in the codebase (e.g., upstream
    ``_cache_lock`` in ``backend/routers/auto_model.py``). Each ``get``
    returns a defensive copy so external mutation of the returned
    ``StoredPrefs`` cannot corrupt the store.
    """

    def __init__(self) -> None:
        self._store: dict[str, StoredPrefs] = {}
        self._lock = threading.Lock()

    def get(self, uid: str) -> StoredPrefs:
        with self._lock:
            entry = self._store.get(uid)
            if entry is None:
                return StoredPrefs(prefs=UserPrefs.empty(), updated_at=0.0)
            # Defensive copy so callers can't mutate stored prefs by reference.
            return StoredPrefs(prefs=entry.prefs, updated_at=entry.updated_at)

    def set(self, uid: str, prefs: UserPrefs) -> StoredPrefs:
        now = time.time()
        entry = StoredPrefs(prefs=prefs, updated_at=now)
        with self._lock:
            self._store[uid] = entry
        return entry

    def clear(self, uid: str) -> None:
        with self._lock:
            self._store.pop(uid, None)


# ---------------------------------------------------------------------------
# Firestore implementation (production)
# ---------------------------------------------------------------------------


class FirestoreUserPrefsStore:
    """Firestore-backed per-user prefs store.

    Persists to ``users/{uid}/auto_router/prefs`` with this shape::

        {
            "prefs": {"<lane_id>": {"quality": ..., "latency": ..., "cost": ...}, ...},
            "updated_at": <epoch_seconds>,
        }

    Construct with an injected Firestore client (per backend AGENTS.md:
    never construct Firestore clients at import time, and tests should
    inject a fake client).

    Failure mode: any backend error is wrapped in ``UserPrefsStoreError``
    so the endpoint layer can return 503. We do NOT silently fall back
    to lane defaults — silent fallback would hide outages and let stale
    prefs drive routing decisions the user thought they had cleared.
    """

    PREFS_SUBCOLLECTION = 'auto_router'
    PREFS_DOCUMENT_ID = 'prefs'

    def __init__(self, firestore_client) -> None:
        self._db = firestore_client

    def _doc_ref(self, uid: str):
        return (
            self._db.collection('users')
            .document(uid)
            .collection(self.PREFS_SUBCOLLECTION)
            .document(self.PREFS_DOCUMENT_ID)
        )

    def get(self, uid: str) -> StoredPrefs:
        try:
            snapshot = self._doc_ref(uid).get()
        except Exception as exc:
            raise UserPrefsStoreError(f"firestore get failed for uid={uid}: {exc}") from exc
        if not snapshot.exists:
            return StoredPrefs(prefs=UserPrefs.empty(), updated_at=0.0)
        data = snapshot.to_dict() or {}
        prefs = UserPrefs.from_dict(data.get('prefs') or {})
        updated_at = float(data.get('updated_at') or 0.0)
        return StoredPrefs(prefs=prefs, updated_at=updated_at)

    def set(self, uid: str, prefs: UserPrefs) -> StoredPrefs:
        now = time.time()
        payload = {'prefs': prefs.to_dict(), 'updated_at': now}
        try:
            self._doc_ref(uid).set(payload)
        except Exception as exc:
            raise UserPrefsStoreError(f"firestore set failed for uid={uid}: {exc}") from exc
        return StoredPrefs(prefs=prefs, updated_at=now)

    def clear(self, uid: str) -> None:
        try:
            self._doc_ref(uid).delete()
        except Exception as exc:
            raise UserPrefsStoreError(f"firestore delete failed for uid={uid}: {exc}") from exc


# ---------------------------------------------------------------------------
# Module-level singleton + reset (matches the pattern in
# ``llm_gateway/routers/dependencies.py``)
# ---------------------------------------------------------------------------


_user_prefs_store: Optional[UserPrefsStore] = None
_user_prefs_store_lock = threading.Lock()


def set_user_prefs_store(store: UserPrefsStore) -> None:
    """Install a backend. Tests use this to inject a fake; main.py
    uses this once at startup with the configured backend.
    """
    global _user_prefs_store
    with _user_prefs_store_lock:
        _user_prefs_store = store


def get_user_prefs_store() -> UserPrefsStore:
    """Return the process-wide UserPrefsStore.

    If no backend has been installed (e.g., during early tests),
    installs the in-memory backend so the endpoint is usable. The
    gateway's ``main.py`` overrides this at startup via
    ``set_user_prefs_store(...)``.
    """
    global _user_prefs_store
    if _user_prefs_store is None:
        with _user_prefs_store_lock:
            if _user_prefs_store is None:
                logger.info('llm_gateway: no UserPrefsStore installed; ' 'defaulting to in-memory (dev/test only).')
                _user_prefs_store = InMemoryUserPrefsStore()
    return _user_prefs_store


def reset_user_prefs_store_for_testing() -> None:
    """Drop the singleton. Test helper — never call in production."""
    global _user_prefs_store
    with _user_prefs_store_lock:
        _user_prefs_store = None


__all__ = [
    'StoredPrefs',
    'UserPrefsStore',
    'UserPrefsStoreError',
    'InMemoryUserPrefsStore',
    'FirestoreUserPrefsStore',
    'get_user_prefs_store',
    'set_user_prefs_store',
    'reset_user_prefs_store_for_testing',
]

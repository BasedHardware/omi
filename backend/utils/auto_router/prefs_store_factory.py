"""Factory for the per-user prefs storage backend (v4).

Picks the backend implementation based on the `AUTO_ROUTER_PREFS_BACKEND`
env var:
  - `firestore` (default): persistent, survives restarts, used in production
  - `memory`: process-local, lost on restart, used in tests + dev without Firestore

Invalid values fall back to `firestore` (the safe default) with a WARNING
log. This prevents a typo in the env var from silently breaking persistence.

The factory is a thin wrapper around the two backend implementations. Both
implement `UserPrefsStoreProtocol`, so the router doesn't need to know which
backend it's using.

Module-level singleton (matches the pattern of `MetricsCollector` and
`BenchmarksFetcher`):
  - First call to `get_user_prefs_store()` lazily creates the store.
  - Subsequent calls return the cached instance.
  - `reset_user_prefs_store_for_testing()` drops the singleton (test helper).
"""

import logging
import os
from typing import Optional

from utils.auto_router.user_prefs_store import (
    UserPrefsStore,
    get_in_memory_user_prefs_store,
    reset_in_memory_user_prefs_store_for_testing,
)
from utils.auto_router.user_prefs_store_protocol import UserPrefsStoreProtocol

logger = logging.getLogger(__name__)

# Env var name (documented in README)
ENV_VAR = "AUTO_ROUTER_PREFS_BACKEND"

# Valid values
BACKEND_FIRESTORE = "firestore"
BACKEND_MEMORY = "memory"
DEFAULT_BACKEND = BACKEND_FIRESTORE
VALID_BACKENDS = frozenset({BACKEND_FIRESTORE, BACKEND_MEMORY})


def get_user_prefs_store() -> UserPrefsStoreProtocol:
    """Return the process-wide prefs store, picking the backend by env var.

    Lazy-initializes the singleton on first call. Subsequent calls return
    the cached instance.

    Reads `AUTO_ROUTER_PREFS_BACKEND` on first call only (subsequent calls
    reuse the same backend). To switch backends at runtime, reset the
    singleton via `reset_user_prefs_store_for_testing()`.

    Default backend is `firestore` (production). Use `memory` for tests +
    dev without Firestore credentials.
    """
    global _user_prefs_store_singleton
    if _user_prefs_store_singleton is None:
        backend = os.environ.get(ENV_VAR, DEFAULT_BACKEND).strip().lower()
        if backend not in VALID_BACKENDS:
            logger.warning(
                "prefs_store_factory: invalid %s=%r, falling back to %s. " "Valid values: %s",
                ENV_VAR,
                backend,
                DEFAULT_BACKEND,
                sorted(VALID_BACKENDS),
            )
            backend = DEFAULT_BACKEND
        _user_prefs_store_singleton = _create_store(backend)
        logger.info("prefs_store_factory: using backend=%s", backend)
    return _user_prefs_store_singleton


def _create_store(backend: str) -> UserPrefsStoreProtocol:
    """Instantiate the requested backend."""
    if backend == BACKEND_MEMORY:
        return get_in_memory_user_prefs_store()
    # Default + BACKEND_FIRESTORE: lazy import to avoid pulling firebase_admin
    # at module load time when memory backend is selected.
    from utils.auto_router.firestore_user_prefs_store import FirestoreUserPrefsStore

    return FirestoreUserPrefsStore()


def reset_user_prefs_store_for_testing() -> None:
    """Drop the singleton. Test helper — never call in production.

    Also resets the underlying in-memory singleton (if the factory had
    picked the memory backend). For Firestore, there's no per-test cleanup
    needed — tests use a fresh mock per test.
    """
    global _user_prefs_store_singleton
    _user_prefs_store_singleton = None
    # Also reset the underlying in-memory store (so tests that switch
    # backends don't leak state between tests).
    reset_in_memory_user_prefs_store_for_testing()


# Module-level singleton (matches MetricsCollector, BenchmarksFetcher pattern).
_user_prefs_store_singleton: Optional[UserPrefsStoreProtocol] = None

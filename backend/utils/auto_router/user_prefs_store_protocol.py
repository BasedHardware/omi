"""Storage interface for per-user weight overrides (v4 protocol).

v4 introduces a pluggable storage backend for per-user prefs. v3's
`UserPrefsStore` (in-memory, lost on restart) is one implementation;
v4's `FirestoreUserPrefsStore` is another. The protocol enables:
- Contract testing (verify both implementations satisfy the same interface)
- Easy mocking in tests
- Future backends (Redis, Postgres, etc.) without changing call sites

Why `typing.Protocol` (not abc.ABC): structural typing means backends
just need to implement the methods — no explicit inheritance required.
This makes the protocol trivially mockable and future-proof.

The protocol uses `StoredPrefs` as the return type for `get`/`set`. The
type lives in this module so both backends can import it from one place.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from utils.auto_router.user_prefs import UserPrefs


class PrefsStoreUnavailableError(Exception):
    """Raised by a UserPrefsStore when the backing persistence layer is unavailable.

    Distinct from generic Exception so callers (endpoints) can map this to a
    structured 503 (code: prefs_store_unavailable) instead of bubbling a 500.
    Implementations should raise this — not bare Exception — for any failure
    where the persistence layer is unreachable, timing out, or otherwise
    cannot complete the operation.

    Use cases:
    - Firestore: transient connection errors, deadline exceeded, internal error
    - Redis: connection lost, timeout, cluster failover in progress
    - Future backends: any equivalent "backend unavailable" condition

    Does NOT cover:
    - Input validation errors (caller's bug — should raise ValueError/TypeError)
    - Permission errors (caller's bug — should raise PermissionError)
    - Programmer errors (should bubble as 500)
    """


@dataclass(frozen=True)
class StoredPrefs:
    """A user's stored prefs + the timestamp of the last write.

    `updated_at` is epoch seconds (UTC). The endpoint surfaces it as
    ISO 8601 in the JSON response. `updated_at=0.0` indicates a
    "never set" entry (returned by `get()` for missing users).
    """

    prefs: UserPrefs
    updated_at: float


@runtime_checkable
class UserPrefsStoreProtocol(Protocol):
    """Storage interface for per-user weight overrides.

    Implementations:
    - `UserPrefsStore` (v3): thread-safe in-memory dict. Process-local.
      Resets on restart. Used for tests + dev without Firestore.
    - `FirestoreUserPrefsStore` (v4): Firestore-backed with 5-min read
      cache. Survives restarts. Used for production.

    Contract:
    - `get(uid)` MUST never raise — returns empty `StoredPrefs` for
      missing uids (callers treat this as "no overrides" + use defaults).
    - `set(uid, prefs)` MUST return the new `StoredPrefs` with a fresh
      `updated_at` timestamp.
    - `clear(uid)` MUST be a no-op if the uid is not present.
    - `reset_for_testing()` MUST drop ALL entries (test helper).
    - All methods MUST be safe to call concurrently (thread-safe).
    """

    def get(self, uid: str) -> StoredPrefs:
        """Return the user's stored prefs, or empty prefs if no entry."""
        ...

    def set(self, uid: str, prefs: UserPrefs) -> StoredPrefs:
        """Store the user's prefs and return the new entry with timestamp.

        MUST raise `PrefsStoreUnavailableError` (not generic Exception)
        when the backing persistence layer is unreachable. Endpoints map
        this to a structured 503 (code: prefs_store_unavailable); a bare
        Exception would bubble as a generic 500.
        """
        ...

    def clear(self, uid: str) -> None:
        """Remove the user's entry. Next `get(uid)` returns empty prefs."""
        ...

    def reset_for_testing(self) -> None:
        """Drop all entries. Test helper — never call in production."""
        ...

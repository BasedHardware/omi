"""Firestore-backed store for per-user weight overrides (v4).

Persists per-user prefs to `users/{uid}.auto_router_prefs` sub-map.
Survives backend restarts. Used for production.

Read path:
    1. Check Redis cache via `firestore_cache.get_or_fetch` (5min TTL)
    2. On cache miss, fetch from Firestore (`users/{uid}.auto_router_prefs`)
    3. Store in cache for next call
    4. If Firestore errors, fall back to empty prefs + WARNING (fail-open)

Write path:
    1. Validate (already done by UserPrefs.__post_init__)
    2. Write to Firestore (`user_ref.set({auto_router_prefs: {...}}, merge=True)`)
    3. Invalidate cache AFTER successful write (race-safe: subsequent reads see fresh data)

Thread-safety:
    The Firestore client is thread-safe (google-cloud-firestore uses gRPC under
    the hood with its own connection pool). We don't add an extra lock here;
    the protocol's contract says "safe to call concurrently" and Firestore
    client satisfies that.

Test isolation:
    Tests use `firestore_user_prefs_mock.py` — a fake `db` client that
    implements the same surface as the real Firestore client (in-memory dict
    + call counter). No external dependencies required.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from database.firestore_cache import (
    CachePolicy,
    get_or_fetch,
    invalidate,
)
from database._client import db as default_db_client

from utils.auto_router.user_prefs import UserPrefs
from utils.auto_router.user_prefs_store_protocol import StoredPrefs

logger = logging.getLogger(__name__)


# Module-level cache policy. Matches the pattern in database/users.py
# (_USER_LANGUAGE_CACHE, _USER_TRANSCRIPTION_PREFS_CACHE).
_AUTO_ROUTER_PREFS_CACHE = CachePolicy(
    namespace='auto_router_prefs',
    version=1,
    ttl_seconds=300,  # 5 minutes
)


class FirestoreUserPrefsStore:
    """Firestore-backed per-user prefs store.

    Implements `UserPrefsStoreProtocol`. The factory in
    `prefs_store_factory.py` picks this or `UserPrefsStore` (v3 in-memory)
    based on the `AUTO_ROUTER_PREFS_BACKEND` env var.

    Persistence: `users/{uid}.auto_router_prefs.overrides` sub-map.
    Caching: Redis via existing `firestore_cache.get_or_fetch` (5min TTL).

    Args:
        db_client: Firestore client. Defaults to the shared `db` singleton.
        cache: Cache policy. Defaults to the module-level one.
        clock: Time function. Defaults to `time.time`. Injectable for tests.
    """

    def __init__(
        self,
        db_client: Any = None,
        cache: Optional[CachePolicy] = None,
        clock: Any = None,
    ) -> None:
        self._db = db_client if db_client is not None else default_db_client
        self._cache = cache if cache is not None else _AUTO_ROUTER_PREFS_CACHE
        self._clock = clock if clock is not None else time.time

    def get(self, uid: str) -> StoredPrefs:
        """Return the user's stored prefs, or empty prefs if no entry.

        Never raises. If Firestore is unreachable, falls back to empty prefs
        + logs WARNING (fail-open). The caller treats empty prefs as
        "no overrides" + uses task defaults.
        """
        try:
            data = get_or_fetch(self._cache, uid, lambda: self._fetch_from_firestore(uid))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "FirestoreUserPrefsStore: read failed for uid=%s (%s: %s), " "returning empty prefs (fail-open)",
                uid,
                type(e).__name__,
                e,
            )
            return StoredPrefs(prefs=UserPrefs.empty(), updated_at=0.0)

        if not data:
            return StoredPrefs(prefs=UserPrefs.empty(), updated_at=0.0)

        # Parse overrides + updated_at from the Firestore sub-map.
        overrides_dict = data.get("overrides", {}) or {}
        try:
            prefs = UserPrefs.from_dict(overrides_dict)
        except (ValueError, TypeError) as e:
            logger.warning(
                "FirestoreUserPrefsStore: invalid overrides for uid=%s (%s), " "returning empty prefs",
                uid,
                e,
            )
            return StoredPrefs(prefs=UserPrefs.empty(), updated_at=0.0)

        updated_at = self._parse_timestamp(data.get("updated_at"))
        return StoredPrefs(prefs=prefs, updated_at=updated_at)

    def set(self, uid: str, prefs: UserPrefs) -> StoredPrefs:
        """Store the user's prefs and return the new entry with timestamp.

        Writes to Firestore + invalidates the cache AFTER successful write.
        Raises if Firestore is unreachable (the router catches + returns 503).

        Use `update()` (shallow merge) instead of `set(merge=True)` (deep
        merge). With deep merge, sending `{"overrides": {"a": ...}}` then
        `{"overrides": {"b": ...}}` would keep BOTH tasks (old `a` + new `b`)
        because deep merge preserves unspecified nested fields. With
        `update()`, the top-level `auto_router_prefs` field is REPLACED
        entirely — the PUT semantics match the user's intent ("this is my
        complete prefs now").

        Cache invalidation order: AFTER write commits. If write fails, the
        cache stays valid (might serve stale data briefly — that's safer than
        invalidating before write and having the write fail, leaving the
        cache empty for the next read).
        """
        now_dt = datetime.now(timezone.utc)
        payload = {
            "overrides": prefs.to_dict(),
            "updated_at": now_dt,
        }

        # Write to Firestore FIRST. If this raises, no cache change happens.
        #
        # We need SHALLOW merge at the user-doc level (replace the entire
        # `auto_router_prefs` sub-map wholesale so old task overrides
        # don't accumulate via deep-merge). That means `update()`, NOT
        # `set(merge=True)`.
        #
        # The race window (cubic review): if the user doc is deleted between
        # the get() and update() calls, update() raises NotFound. We catch
        # that and retry with set() (one extra round-trip in the rare
        # delete-during-write case).
        user_ref = self._db.collection("users").document(uid)
        try:
            doc = user_ref.get(["auto_router_prefs"])
            if doc.exists:
                user_ref.update({"auto_router_prefs": payload})
            else:
                # First-time write for this uid — use set() to create the doc.
                user_ref.set({"auto_router_prefs": payload}, merge=True)
        except Exception as e:  # noqa: BLE001
            # Catch the narrow NotFound race: doc was deleted between get()
            # and update(). Fall back to set() to create the doc from scratch.
            # For all OTHER errors (Firestore down, auth, etc.), propagate
            # so the router returns 503 (don't swallow transport errors).
            if "NotFound" not in type(e).__name__:
                raise
            user_ref.set({"auto_router_prefs": payload}, merge=True)
            logger.info(
                "FirestoreUserPrefsStore: recovered from update() NotFound race for uid=%s",
                uid,
            )

        # THEN invalidate cache (race-safe: subsequent reads see fresh data).
        invalidate(self._cache, uid)

        return StoredPrefs(prefs=prefs, updated_at=now_dt.timestamp())

    def clear(self, uid: str) -> None:
        """Remove the user's prefs entry.

        Writes an empty overrides dict (preserves the sub-map + updated_at
        field for observability). Invalidates the cache. Same shallow-merge
        pattern as `set()`.
        """
        now_dt = datetime.now(timezone.utc)
        payload = {
            "overrides": {},
            "updated_at": now_dt,
        }
        user_ref = self._db.collection("users").document(uid)
        doc = user_ref.get(["auto_router_prefs"])
        if doc.exists:
            user_ref.update({"auto_router_prefs": payload})
        else:
            user_ref.set({"auto_router_prefs": payload}, merge=True)
        invalidate(self._cache, uid)

    def reset_for_testing(self) -> None:
        """Drop all entries. Test helper — never call in production.

        Firestore doesn't have a "drop all" operation for a sub-collection;
        instead, we invalidate the cache for all known keys. Tests should
        use a fresh Firestore mock per test for full isolation.
        """
        # No-op for Firestore (we don't enumerate keys). Cache invalidation
        # for specific uids should be done by the test fixture.
        pass

    # ---------------------------------------------------------------------------
    # Firestore I/O
    # ---------------------------------------------------------------------------

    def _fetch_from_firestore(self, uid: str) -> Optional[Dict[str, Any]]:
        """Fetch the user's auto_router_prefs sub-map from Firestore.

        Returns None if the user doc doesn't exist (first-ever prefs lookup
        for this uid). Returns the sub-map dict if the doc exists but the
        sub-map may be empty if prefs were never set.
        """
        user_ref = self._db.collection("users").document(uid)
        # Read only the auto_router_prefs sub-map (efficient — avoids loading
        # the entire user doc which may contain entitlement, BYOK, etc.).
        doc = user_ref.get(["auto_router_prefs"])
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        return data.get("auto_router_prefs")

    @staticmethod
    def _parse_timestamp(value: Any) -> float:
        """Convert a Firestore timestamp (or epoch number) to epoch seconds.

        Handles:
          - datetime (with or without tzinfo) → .timestamp()
          - Firestore Timestamp (has .timestamp() method) → .timestamp()
          - int/float (epoch seconds) → as-is
          - None → 0.0 (treated as "never set")
        """
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, datetime):
            # datetime may be naive or aware; treat naive as UTC.
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc).timestamp()
            return value.timestamp()
        # Firestore Timestamp has a .timestamp() method
        if hasattr(value, "timestamp"):
            try:
                return float(value.timestamp())
            except Exception:  # noqa: BLE001
                return 0.0
        return 0.0

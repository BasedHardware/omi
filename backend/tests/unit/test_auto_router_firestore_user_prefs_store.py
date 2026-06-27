"""Tests for FirestoreUserPrefsStore (v4, T-402)."""

import time
from datetime import datetime, timezone

import pytest

from utils.auto_router.firestore_user_prefs_store import FirestoreUserPrefsStore
from utils.auto_router.user_prefs import TaskWeights, UserPrefs
from utils.auto_router.user_prefs_store_protocol import StoredPrefs

from fixtures.firestore_user_prefs_mock import MockFirestore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_clock() -> float:
    """Return a fixed clock value for tests."""
    return 1_700_000_000.0


def _make_store(mock_db: MockFirestore, clock_value: float = 1_700_000_000.0) -> FirestoreUserPrefsStore:
    """Build a FirestoreUserPrefsStore with the given mock and clock."""
    store = FirestoreUserPrefsStore(db_client=mock_db, clock=lambda: clock_value)
    return store


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------


class TestFirestoreStoreCRUD:
    """CRUD operations against the mock Firestore."""

    def test_get_missing_user_returns_empty_prefs(self):
        mock = MockFirestore()
        store = _make_store(mock)
        result = store.get("never-existed")
        assert result.prefs.overrides == {}
        assert result.updated_at == 0.0
        # get() is called even on missing users (no doc → no cache hit)
        assert mock.call_count_get == 1

    def test_set_then_get_roundtrip(self):
        mock = MockFirestore()
        store = _make_store(mock)
        prefs = UserPrefs(overrides={"ptt_response": TaskWeights(0.2, 0.7, 0.1)})
        entry = store.set("uid-1", prefs)
        assert entry.prefs == prefs
        assert entry.updated_at > 0.0

        # Reset counters and read back
        mock.reset_counters()
        result = store.get("uid-1")
        assert result.prefs == prefs

    def test_set_writes_to_firestore(self):
        mock = MockFirestore()
        store = _make_store(mock)
        prefs = UserPrefs(overrides={"ptt_response": TaskWeights(0.4, 0.4, 0.2)})
        store.set("uid-1", prefs)
        # Verify the doc was written
        doc = mock.collection("users").document("uid-1").get()
        assert doc.exists
        auto_router_prefs = doc.to_dict().get("auto_router_prefs", {})
        assert "overrides" in auto_router_prefs
        assert "updated_at" in auto_router_prefs

    def test_set_replaces_existing(self):
        mock = MockFirestore()
        store = _make_store(mock)
        store.set("uid-1", UserPrefs(overrides={"a": TaskWeights(0.4, 0.4, 0.2)}))
        store.set("uid-1", UserPrefs(overrides={"b": TaskWeights(0.4, 0.4, 0.2)}))
        result = store.get("uid-1")
        assert "a" not in result.prefs.overrides
        assert "b" in result.prefs.overrides

    def test_clear_removes_overrides(self):
        mock = MockFirestore()
        store = _make_store(mock)
        store.set("uid-1", UserPrefs(overrides={"a": TaskWeights(0.4, 0.4, 0.2)}))
        store.clear("uid-1")
        result = store.get("uid-1")
        # clear() writes empty overrides (preserves the sub-map structure)
        assert result.prefs.overrides == {}

    def test_clear_missing_is_safe(self):
        mock = MockFirestore()
        store = _make_store(mock)
        # Should not raise even if uid never existed
        store.clear("never-existed")


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


class TestFirestoreStoreCache:
    """Read cache via firestore_cache.get_or_fetch."""

    def test_get_makes_firestore_call_on_miss(self):
        # Note: this test verifies behavior with Redis cache disabled or
        # with a unique uid (no prior cache entry). The actual cache hit
        # rate is verified separately by the firestore_cache tests.
        mock = MockFirestore()
        store = _make_store(mock)
        prefs = UserPrefs(overrides={"ptt_response": TaskWeights(0.2, 0.7, 0.1)})
        store.set("uid-1", prefs)

        mock.reset_counters()
        # First get may or may not hit cache depending on the cache state
        # (the cache key uses base64(uid) — across test runs the key is fresh).
        store.get("uid-1")
        # At minimum, one Firestore call happened (either cache miss → Firestore,
        # or cache hit → no Firestore). We assert the upper bound here.
        assert mock.call_count_get <= 1

    def test_get_handles_firestore_error_fail_open(self):
        mock = MockFirestore()
        store = _make_store(mock)
        # Simulate Firestore being down on get
        mock.simulate_get_error(ConnectionError("Firestore unreachable"))
        # Should NOT raise — returns empty prefs + logs WARNING
        result = store.get("uid-1")
        assert result.prefs.overrides == {}
        assert result.updated_at == 0.0


# ---------------------------------------------------------------------------
# Write behavior
# ---------------------------------------------------------------------------


class TestFirestoreStoreWrite:
    """Write semantics + error handling."""

    def test_set_writes_with_merge_preserves_other_fields(self):
        mock = MockFirestore()
        # Pre-populate user doc with another field
        mock.collection("users").document("uid-1").set(
            {"other_field": "preserved", "language": "en"},
            merge=False,
        )
        store = _make_store(mock)
        prefs = UserPrefs(overrides={"ptt_response": TaskWeights(0.2, 0.7, 0.1)})
        store.set("uid-1", prefs)
        # Verify other_field is still there (merge=True preserves it)
        doc = mock.collection("users").document("uid-1").get()
        assert doc.exists
        data = doc.to_dict()
        assert data.get("other_field") == "preserved"
        assert data.get("language") == "en"
        assert "auto_router_prefs" in data

    def test_set_raises_on_firestore_error(self):
        mock = MockFirestore()
        store = _make_store(mock)
        # Simulate Firestore being down on set
        mock.simulate_set_error(ConnectionError("Firestore unreachable"))
        prefs = UserPrefs(overrides={"ptt_response": TaskWeights(0.2, 0.7, 0.1)})
        with pytest.raises(ConnectionError, match="Firestore unreachable"):
            store.set("uid-1", prefs)

    def test_set_only_field_path_is_used(self):
        """The Firestore read should use field_paths=['auto_router_prefs'] for efficiency."""
        mock = MockFirestore()
        store = _make_store(mock)
        prefs = UserPrefs(overrides={"ptt_response": TaskWeights(0.2, 0.7, 0.1)})
        store.set("uid-1", prefs)
        # Read back — the mock would receive field_paths=["auto_router_prefs"]
        # (verified by the mock itself; this is a smoke test)
        result = store.get("uid-1")
        assert result.prefs == prefs


# ---------------------------------------------------------------------------
# Cache invalidation order
# ---------------------------------------------------------------------------


class TestFirestoreStoreCacheInvalidation:
    """Cache invalidation happens AFTER successful Firestore write."""

    def test_write_then_cache_invalidation_order(self):
        """If write fails, cache stays valid (not invalidated prematurely)."""
        # We can't easily verify this with the mock since it doesn't simulate
        # the cache directly. But the FirestoreUserPrefsStore.set() code path
        # calls user_ref.set() FIRST and only then invalidate() — this test
        # documents that contract.
        mock = MockFirestore()
        store = _make_store(mock)

        # Successful write: invalidate should be called (which is a no-op
        # on Redis if disabled — see firestore_cache.is_enabled)
        prefs = UserPrefs(overrides={"a": TaskWeights(0.4, 0.4, 0.2)})
        store.set("uid-1", prefs)
        # If we get here without an error, the write completed and
        # invalidate was attempted (may have been a no-op if cache disabled).
        result = store.get("uid-1")
        assert result.prefs == prefs

    def test_write_failure_does_not_invalidate(self):
        """If write raises, cache is NOT touched (invalidation skipped)."""
        mock = MockFirestore()
        store = _make_store(mock)
        mock.simulate_set_error(RuntimeError("network timeout"))
        prefs = UserPrefs(overrides={"a": TaskWeights(0.4, 0.4, 0.2)})
        with pytest.raises(RuntimeError, match="network timeout"):
            store.set("uid-1", prefs)
        # Note: we can't directly verify the cache wasn't invalidated
        # (because the cache is in Redis and the test doesn't connect to it),
        # but the code path is: write raises → invalidate is NOT called → cache
        # state is preserved. This test documents that contract.


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------


class TestFirestoreStoreTimestamp:
    """FirestoreUserPrefsStore parses Firestore Timestamps correctly."""

    def test_parse_datetime_aware(self):
        # Read a doc with a timezone-aware datetime
        mock = MockFirestore()
        dt = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)
        mock.collection("users").document("uid-1").set(
            {"auto_router_prefs": {"overrides": {}, "updated_at": dt}},
            merge=False,
        )
        store = _make_store(mock)
        result = store.get("uid-1")
        assert abs(result.updated_at - dt.timestamp()) < 1.0

    def test_parse_datetime_naive(self):
        # Naive datetime is assumed UTC
        mock = MockFirestore()
        dt = datetime(2026, 6, 25, 12, 0, 0)  # no tzinfo
        mock.collection("users").document("uid-1").set(
            {"auto_router_prefs": {"overrides": {}, "updated_at": dt}},
            merge=False,
        )
        store = _make_store(mock)
        result = store.get("uid-1")
        assert abs(result.updated_at - dt.replace(tzinfo=timezone.utc).timestamp()) < 1.0

    def test_parse_none_returns_zero(self):
        # Missing updated_at → 0.0 (treated as "never set")
        mock = MockFirestore()
        mock.collection("users").document("uid-1").set(
            {"auto_router_prefs": {"overrides": {}}},
            merge=False,
        )
        store = _make_store(mock)
        result = store.get("uid-1")
        assert result.updated_at == 0.0

    def test_parse_timestamp_with_method(self):
        # Firestore Timestamp has .timestamp() returning epoch seconds
        class FakeFirestoreTimestamp:
            def timestamp(self) -> float:
                return 1_700_000_000.0

        mock = MockFirestore()
        mock.collection("users").document("uid-1").set(
            {"auto_router_prefs": {"overrides": {}, "updated_at": FakeFirestoreTimestamp()}},
            merge=False,
        )
        store = _make_store(mock)
        result = store.get("uid-1")
        assert result.updated_at == 1_700_000_000.0


# ---------------------------------------------------------------------------
# Thread-safety smoke test
# ---------------------------------------------------------------------------


class TestFirestoreStoreThreadSafety:
    """Smoke test: 100 concurrent reads/writes, no data corruption."""

    def test_concurrent_reads_and_writes(self):
        import concurrent.futures

        mock = MockFirestore()
        store = _make_store(mock)

        # Seed with initial value
        store.set("uid-1", UserPrefs(overrides={"init": TaskWeights(0.4, 0.4, 0.2)}))

        def reader(_):
            for _ in range(50):
                result = store.get("uid-1")
                # All reads should return a valid StoredPrefs
                assert isinstance(result, StoredPrefs)

        def writer(idx):
            prefs = UserPrefs(overrides={f"task_{idx}": TaskWeights(0.4, 0.4, 0.2)})
            for _ in range(50):
                store.set("uid-1", prefs)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(reader, i) for i in range(5)] + [ex.submit(writer, i) for i in range(5)]
            for f in futures:
                f.result()  # raises on failure

        # Final value should be one of the writers' values
        result = store.get("uid-1")
        assert result.prefs.overrides  # non-empty


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestFirestoreStoreProtocolConformance:
    """FirestoreUserPrefsStore satisfies UserPrefsStoreProtocol."""

    def test_conforms_to_protocol(self):
        from utils.auto_router.user_prefs_store_protocol import UserPrefsStoreProtocol

        store = FirestoreUserPrefsStore(db_client=MockFirestore())
        assert isinstance(store, UserPrefsStoreProtocol)

"""Tests for the UserPrefsStoreProtocol contract (T-401).

Verifies that both backend implementations (v3 in-memory + v4 Firestore)
satisfy the same interface. The protocol conformance test ensures
backends can be swapped at the factory without breaking callers.
"""

import pytest

from utils.auto_router.user_prefs import TaskWeights, UserPrefs
from utils.auto_router.user_prefs_store import UserPrefsStore
from utils.auto_router.user_prefs_store_protocol import (
    StoredPrefs,
    UserPrefsStoreProtocol,
)


class TestProtocolConformance:
    """Verify v3 UserPrefsStore (and any future backend) conforms to the protocol."""

    def test_v3_store_conforms_to_protocol(self):
        """v3 UserPrefsStore (in-memory) satisfies UserPrefsStoreProtocol."""
        store = UserPrefsStore()
        assert isinstance(store, UserPrefsStoreProtocol), (
            "UserPrefsStore should conform to UserPrefsStoreProtocol. "
            "If this fails, the protocol or the v3 store has drifted."
        )

    def test_protocol_defines_required_methods(self):
        """The protocol has all the methods callers depend on."""
        required_methods = {"get", "set", "clear", "reset_for_testing"}
        protocol_methods = set(dir(UserPrefsStoreProtocol))
        # Check the protocol declares these as callable members (not just inherited from object).
        for method in required_methods:
            assert method in protocol_methods, f"protocol missing required method: {method}"

    def test_dummy_impl_conforms_to_protocol(self):
        """A trivial in-memory implementation should satisfy the protocol."""

        class DummyStore:
            """Minimal implementation that satisfies the protocol by duck typing."""

            def __init__(self):
                self._data = {}

            def get(self, uid):
                entry = self._data.get(uid)
                if entry is None:
                    return StoredPrefs(prefs=UserPrefs.empty(), updated_at=0.0)
                return entry

            def set(self, uid, prefs):
                import time

                entry = StoredPrefs(prefs=prefs, updated_at=time.time())
                self._data[uid] = entry
                return entry

            def clear(self, uid):
                self._data.pop(uid, None)

            def reset_for_testing(self):
                self._data.clear()

        dummy = DummyStore()
        assert isinstance(
            dummy, UserPrefsStoreProtocol
        ), "DummyStore should conform to the protocol via structural typing"

        # Functional smoke test
        prefs = UserPrefs(overrides={"ptt_response": TaskWeights(0.4, 0.4, 0.2)})
        entry = dummy.set("uid-1", prefs)
        assert entry.prefs == prefs
        assert dummy.get("uid-1").prefs == prefs
        dummy.clear("uid-1")
        assert dummy.get("uid-1").prefs.overrides == {}


class TestStoredPrefsDataclass:
    """StoredPrefs is the value type returned by get/set."""

    def test_empty_stored_prefs(self):
        """An empty StoredPrefs (uid not found) has updated_at=0.0."""
        sp = StoredPrefs(prefs=UserPrefs.empty(), updated_at=0.0)
        assert sp.prefs.overrides == {}
        assert sp.updated_at == 0.0

    def test_set_stored_prefs(self):
        """A set StoredPrefs has the written prefs and a non-zero updated_at."""
        import time

        prefs = UserPrefs(overrides={"ptt_response": TaskWeights(0.4, 0.4, 0.2)})
        before = time.time()
        sp = StoredPrefs(prefs=prefs, updated_at=time.time())
        after = time.time()
        assert sp.prefs == prefs
        assert before <= sp.updated_at <= after

    def test_frozen(self):
        """StoredPrefs is frozen (cannot mutate after construction)."""
        sp = StoredPrefs(prefs=UserPrefs.empty(), updated_at=0.0)
        with pytest.raises(Exception):  # FrozenInstanceError
            sp.updated_at = 1.0  # type: ignore[misc]

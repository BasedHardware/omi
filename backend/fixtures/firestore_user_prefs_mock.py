"""In-memory Firestore mock for testing FirestoreUserPrefsStore.

A fake `db` client that implements the surface used by
`FirestoreUserPrefsStore`:
    - `db.collection('users').document(uid).get(field_paths)` → returns a
      fake DocumentSnapshot with `.exists` and `.to_dict()`
    - `db.collection('users').document(uid).set(data, merge=True)` → stores
      the data in an in-memory dict

Why this mock exists:
    - Tests run without external Firestore / GCP credentials
    - Tests can count calls to verify cache behavior (cache hits skip Firestore)
    - Tests can simulate Firestore errors by raising from the mock

Pattern modeled after `database/firestore_cache.py` tests (in-memory dict
+ call counter).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class MockDocumentSnapshot:
    """Fake DocumentSnapshot returned by `db.collection('users').document(uid).get()`."""

    exists: bool
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return the document's data (always returns the stored dict)."""
        return dict(self.data)


class MockDocumentReference:
    """Fake DocumentReference for a single user doc."""

    def __init__(self, store: "MockFirestore", collection_id: str, document_id: str) -> None:
        self._store = store
        self._collection_id = collection_id
        self._document_id = document_id

    def get(self, field_paths: Optional[List[str]] = None) -> MockDocumentSnapshot:
        """Fetch the document. Optionally project to specific field paths."""
        self._store.call_count_get += 1
        full_data = self._store.docs.get(self._collection_id, {}).get(self._document_id, {})
        if not full_data:
            return MockDocumentSnapshot(exists=False, data={})
        if field_paths:
            projected = {}
            for fp in field_paths:
                # Support dot-notation for sub-maps: "auto_router_prefs" → data["auto_router_prefs"]
                parts = fp.split(".")
                cursor = full_data
                for part in parts:
                    if isinstance(cursor, dict) and part in cursor:
                        cursor = cursor[part]
                    else:
                        cursor = None
                        break
                if cursor is not None:
                    projected[parts[0]] = cursor
            return MockDocumentSnapshot(exists=True, data=projected)
        return MockDocumentSnapshot(exists=True, data=full_data)

    def set(self, data: Dict[str, Any], merge: bool = False) -> None:
        """Write the document. With merge=True, only set the keys in `data`."""
        self._store.call_count_set += 1
        if self._store.raise_on_set is not None:
            raise self._store.raise_on_set
        existing = self._store.docs.setdefault(self._collection_id, {}).setdefault(self._document_id, {})
        if merge:
            # Deep merge: sub-maps are merged, not replaced.
            self._deep_merge(existing, data)
        else:
            existing.clear()
            existing.update(data)

    def update(self, data: Dict[str, Any]) -> None:
        """Update specific fields (shallow merge — replaces top-level fields entirely).

        Unlike `set(merge=True)`, `update()` does NOT deep-merge. The top-level
        keys in `data` are either overwritten (if they exist) or added (if they
        don't). Nested objects within those top-level values are NOT recursively
        merged — they're replaced wholesale as part of the new value.
        """
        self._store.call_count_set += 1
        if self._store.raise_on_set is not None:
            raise self._store.raise_on_set
        existing = self._store.docs.setdefault(self._collection_id, {}).setdefault(self._document_id, {})
        # Shallow merge: top-level keys are overwritten entirely.
        existing.update(data)

    @staticmethod
    def _deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """Recursively merge source into target. Sub-dicts are merged; other values replaced."""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                MockDocumentReference._deep_merge(target[key], value)
            else:
                target[key] = value


class MockCollectionReference:
    """Fake CollectionReference for a top-level collection."""

    def __init__(self, store: "MockFirestore", collection_id: str) -> None:
        self._store = store
        self._collection_id = collection_id

    def document(self, document_id: str) -> MockDocumentReference:
        """Get a reference to a specific document."""
        return MockDocumentReference(self._store, self._collection_id, document_id)


class MockFirestore:
    """In-memory Firestore mock for testing.

    Usage:
        mock_db = MockFirestore()
        store = FirestoreUserPrefsStore(db_client=mock_db)
        entry = store.set("uid-1", UserPrefs(...))
        assert mock_db.call_count_set == 1
    """

    def __init__(self) -> None:
        # docs: {collection_id: {document_id: data_dict}}
        self.docs: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # Call counters (verify cache behavior)
        self.call_count_get: int = 0
        self.call_count_set: int = 0
        # Set this to an exception instance to make `set()` raise on next call
        # (one-shot — caller resets after assertion).
        self.raise_on_set: Optional[Exception] = None
        # Set this to an exception instance to make `get()` raise on next call.
        self.raise_on_get: Optional[Exception] = None

    def collection(self, collection_id: str) -> MockCollectionReference:
        """Get a reference to a top-level collection."""
        return MockCollectionReference(self, collection_id)

    def reset_counters(self) -> None:
        """Reset call counters (between test phases)."""
        self.call_count_get = 0
        self.call_count_set = 0

    def simulate_get_error(self, exc: Exception) -> None:
        """Make the next `get()` call raise this exception (one-shot)."""
        self.raise_on_get = exc

    def simulate_set_error(self, exc: Exception) -> None:
        """Make the next `set()` call raise this exception (one-shot)."""
        self.raise_on_set = exc

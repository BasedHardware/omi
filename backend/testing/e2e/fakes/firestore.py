"""
Fake Firestore using fake-firestore (MockFirestore).

Provides a hermetic in-memory Firestore replacement that supports
the same API surface as google.cloud.firestore — collections,
subcollections, where filters, batch operations, get_all, etc.
"""

import sys
from datetime import datetime, timezone
from typing import Optional

from fake_firestore import MockFirestore

# Module-level singleton — set by conftest.py before backend imports.
_mock_store: Optional[MockFirestore] = None


def get_mock_firestore() -> MockFirestore:
    """Return the shared MockFirestore instance. Raises if not initialized."""
    if _mock_store is None:
        raise RuntimeError("MockFirestore not initialized — call setup_fake_firestore() first")
    return _mock_store


def setup_fake_firestore() -> MockFirestore:
    """Create and register the global MockFirestore singleton."""
    global _mock_store
    _mock_store = MockFirestore()
    return _mock_store


def teardown_fake_firestore():
    """Clear the singleton so a fresh one can be created."""
    global _mock_store
    _mock_store = None


def patch_google_firestore():
    """
    Monkeypatch google.cloud.firestore.Client so that ``firestore.Client()```
    (as used in database/_client.py) returns our MockFirestore instance.

    Must be called BEFORE any omi backend module is imported.
    Note: google.auth.default is already patched at conftest import time
    to prevent DefaultCredentialsError during Client() construction.
    """
    from google.cloud import firestore

    original_init = firestore.Client.__init__

    def _fake_client_init(self, *args, **kwargs):
        # Call original init with fake creds (it won't hit network thanks
        # to our google.auth.default patch)
        try:
            original_init(self, *args, **kwargs)
        except Exception:
            pass  # Init may fail with anonymous creds — that's ok
        # Replace internal state with mock store methods. Delegate the fake
        # client surface broadly so new backend routes do not accidentally
        # fall through to an uninitialized real Firestore client.
        mock = get_mock_firestore()
        for attr in dir(mock):
            if attr.startswith("_"):
                continue
            value = getattr(mock, attr, None)
            if callable(value):
                setattr(self, attr, value)
        if not hasattr(mock, "document"):

            def _unsupported_document(*args, **kwargs):
                raise NotImplementedError("E2E fake Firestore does not support document() yet")

            self.document = _unsupported_document
        if not hasattr(mock, "collection_group"):

            def _unsupported_collection_group(*args, **kwargs):
                raise NotImplementedError("E2E fake Firestore does not support collection_group() yet")

            self.collection_group = _unsupported_collection_group
        self._mock = mock

    firestore.Client.__init__ = _fake_client_init


def seed_conversation(uid: str, conversation_data: dict):
    """Seed a conversation document into fake Firestore for testing."""
    db = get_mock_firestore()
    conv_id = conversation_data["id"]
    db.collection("users").document(uid).collection("conversations").document(conv_id).set(conversation_data)


def seed_memory(uid: str, memory_data: dict):
    """Seed a memory document into fake Firestore for testing."""
    db = get_mock_firestore()
    data = dict(memory_data)
    # The real Firestore query in database/memories.py orders by scoring and created_at.
    # Firestore tolerates sparse legacy docs, but fake-firestore sorts by direct key lookup.
    # Add defaults in the fake seeder so legacy-shape tests exercise backend validation
    # instead of fake-firestore's stricter implementation detail.
    data.setdefault("uid", uid)
    data.setdefault("reviewed", False)
    data.setdefault("manually_added", False)
    data.setdefault("edited", False)
    data.setdefault("is_locked", False)
    data.setdefault("scoring", "00_999_0000000000")
    data.setdefault("visibility", "public")
    data.setdefault("user_review", True)
    for timestamp_field in ("created_at", "updated_at"):
        value = data.get(timestamp_field)
        if isinstance(value, str):
            data[timestamp_field] = datetime.fromisoformat(value.replace("Z", "+00:00"))
    data.setdefault("created_at", datetime.now(timezone.utc))
    data.setdefault("updated_at", data["created_at"])
    mem_id = data["id"]
    db.collection("users").document(uid).collection("memories").document(mem_id).set(data)


def seed_action_item(uid: str, action_item_data: dict):
    """Seed an action item document into fake Firestore for testing."""
    db = get_mock_firestore()
    ai_id = action_item_data["id"]
    db.collection("users").document(uid).collection("action_items").document(ai_id).set(action_item_data)


def read_conversation(uid: str, conversation_id: str) -> Optional[dict]:
    """Read a conversation directly from fake Firestore (bypassing API)."""
    db = get_mock_firestore()
    doc = db.collection("users").document(uid).collection("conversations").document(conversation_id).get()
    if doc.exists:
        return doc.to_dict()
    return None


def read_memories(uid: str) -> list:
    """Read all memories for a user from fake Firestore."""
    db = get_mock_firestore()
    docs = db.collection("users").document(uid).collection("memories").stream()
    return [d.to_dict() for d in docs]


def read_action_items(uid: str) -> list:
    """Read all action items for a user from fake Firestore."""
    db = get_mock_firestore()
    docs = db.collection("users").document(uid).collection("action_items").stream()
    return [d.to_dict() for d in docs]


def clear_user_data(uid: str):
    """Remove all data for a user from fake Firestore."""
    db = get_mock_firestore()
    user_ref = db.collection("users").document(uid)
    for coll_name in ["conversations", "memories", "action_items"]:
        docs = list(user_ref.collection(coll_name).stream())
        for d in docs:
            d.reference.delete()

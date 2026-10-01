import pytest
from unittest.mock import MagicMock
from datetime import datetime
from google.cloud import firestore

from database.screen_frames import (
    _clean_id,
    _resolve_client,
    get_conversation_screen_frames,
    store_conversation_screen_frames,
    delete_conversation_screen_frame_doc,
    delete_conversation_screen_frame_docs,
    bump_conversation_screen_frames_revision,
    get_conversation_screen_frames_revision,
    mark_conversation_screen_frames_adjudicated,
    get_conversation_screen_frames_adjudicated_at,
    get_conversation_screen_frames_selection_fingerprint,
    get_conversation_screenshot_sharing_enabled,
    set_conversation_screenshot_sharing_enabled,
    MAX_ID_LENGTH,
)


@pytest.fixture(autouse=True)
def mock_firestore_transactional(monkeypatch):
    """Ensure firestore.transactional is a transparent pass-through during unit tests."""
    monkeypatch.setattr(firestore, "transactional", lambda fn: fn)


class FakeSnapshot:
    def __init__(self, exists=True, data=None, reference=None):
        self.exists = exists
        self._data = data or {}
        self.reference = reference

    def to_dict(self):
        return dict(self._data)


class FakeDocRef:
    def __init__(self, doc_id):
        self.doc_id = doc_id
        self.data = None
        self.subcollections = {}
        self.deleted = False

    def get(self, transaction=None, field_paths=None):
        if self.data is not None and not self.deleted:
            return FakeSnapshot(exists=True, data=self.data, reference=self)
        return FakeSnapshot(exists=False, data=None, reference=self)

    def set(self, data, merge=False):
        self.deleted = False
        if merge and self.data is not None:
            merged = dict(self.data)
            for k, v in data.items():
                if hasattr(v, "value"):
                    merged[k] = merged.get(k, 0) + v.value
                elif type(v).__name__ == "Increment":
                    merged[k] = merged.get(k, 0) + 1
                else:
                    merged[k] = v
            self.data = merged
        else:
            self.data = dict(data) if isinstance(data, dict) else data

    def update(self, updates):
        if self.data is None or self.deleted:
            raise Exception("Doc not found")
        self.data.update(updates)

    def delete(self):
        self.deleted = True
        self.data = None

    def collection(self, name):
        if name not in self.subcollections:
            self.subcollections[name] = FakeCollection()
        return self.subcollections[name]

    @property
    def reference(self):
        return self


class FakeBatch:
    def __init__(self):
        self.ops = []

    def delete(self, ref):
        self.ops.append(("delete", ref))

    def commit(self):
        for op, ref in self.ops:
            if op == "delete":
                ref.delete()
        self.ops.clear()


class FakeCollection:
    def __init__(self):
        self.docs = {}

    def document(self, doc_id):
        if doc_id not in self.docs:
            self.docs[doc_id] = FakeDocRef(doc_id)
        return self.docs[doc_id]

    def stream(self):
        return [ref.get() for ref in self.docs.values() if not ref.deleted and ref.data is not None]


class FakeFirestoreClient:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]

    def transaction(self):
        class FakeTxn:
            def set(self, ref, data, merge=False):
                ref.set(data, merge=merge)

            def update(self, ref, data):
                ref.update(data)

        return FakeTxn()

    def batch(self):
        return FakeBatch()


# --- Test Cases ---


def test_clean_id_validates_and_normalizes():
    assert _clean_id("user_123") == "user_123"
    assert _clean_id("  conv-abc  ") == "conv-abc"
    assert _clean_id("") == ""
    assert _clean_id("   ") == ""
    assert _clean_id(None) == ""
    assert _clean_id(1234) == ""  # type: ignore[arg-type]
    # Path traversal & control chars
    assert _clean_id("../bad") == ""
    assert _clean_id("users/123") == ""
    assert _clean_id("users\\123") == ""
    assert _clean_id("frame\x00null") == ""
    # Length bound
    assert _clean_id("x" * (MAX_ID_LENGTH + 1)) == ""
    assert _clean_id("x" * MAX_ID_LENGTH) == "x" * MAX_ID_LENGTH


def test_get_conversation_screen_frames_valid():
    client = FakeFirestoreClient()
    conv_ref = client.collection("users").document("u1").collection("conversations").document("c1")
    conv_ref.set({"exists": True})
    conv_ref.collection("screen_frames").document("f1").set({"id": "f1", "rank": 1})
    conv_ref.collection("screen_frames").document("f2").set({"id": "f2", "rank": 2})

    frames = get_conversation_screen_frames("u1", "c1", firestore_client=client)
    assert len(frames) == 2
    assert {f["id"] for f in frames} == {"f1", "f2"}


def test_get_conversation_screen_frames_invalid_inputs_and_error_propagation():
    client = MagicMock()
    # Empty uid is blocked by security decorator
    with pytest.raises(TypeError):
        get_conversation_screen_frames("", "c1", firestore_client=client)

    # Empty conversation ID or malformed ID returns empty list safely without querying
    assert get_conversation_screen_frames("u1", "", firestore_client=client) == []
    assert get_conversation_screen_frames("u1", "../bad", firestore_client=client) == []
    assert get_conversation_screen_frames("..traversal", "c1", firestore_client=client) == []
    client.collection.assert_not_called()

    # Transient stream error propagates so composite deletion never skips GCS blobs
    client_err = MagicMock()
    client_err.collection.side_effect = RuntimeError("Transport error")
    with pytest.raises(RuntimeError, match="Transport error"):
        get_conversation_screen_frames("u1", "c1", firestore_client=client_err)


def test_store_conversation_screen_frames_valid_flow():
    client = FakeFirestoreClient()
    conv_ref = client.collection("users").document("u1").collection("conversations").document("c1")
    conv_ref.set({"has_content": False})

    frames = [
        {"id": "f1", "caption": "Screenshot of terminal", "role": "primary"},
        {"id": "f2", "caption": "Screenshot of browser", "role": "secondary"},
    ]
    res = store_conversation_screen_frames("u1", "c1", frames, firestore_client=client)
    assert res is True

    saved = get_conversation_screen_frames("u1", "c1", firestore_client=client)
    assert len(saved) == 2
    assert conv_ref.get().to_dict()["has_content"] is True


def test_store_conversation_screen_frames_missing_parent_conversation():
    client = FakeFirestoreClient()
    frames = [{"id": "f1", "caption": "Test"}]
    res = store_conversation_screen_frames("u1", "nonexistent_conv", frames, firestore_client=client)
    assert res is False


def test_store_conversation_screen_frames_invalid_inputs_and_skipped_frames():
    client = FakeFirestoreClient()
    # Empty uid blocked by decorator
    with pytest.raises(TypeError):
        store_conversation_screen_frames("", "c1", [], firestore_client=client)

    # Empty conversation ID, malformed path, or non-list returns False
    assert store_conversation_screen_frames("u1", "", [], firestore_client=client) is False
    assert store_conversation_screen_frames("u1", "../c1", [], firestore_client=client) is False

    # Existing parent conversation: non-list frames returns False up front without entering transaction or raising AttributeError
    conv_ref = client.collection("users").document("u1").collection("conversations").document("c1")
    conv_ref.set({"has_content": False})
    assert store_conversation_screen_frames("u1", "c1", "not_a_list", firestore_client=client) is False  # type: ignore[arg-type]
    assert store_conversation_screen_frames("u1", "c1", 12345, firestore_client=client) is False  # type: ignore[arg-type]
    assert store_conversation_screen_frames("u1", "c1", {"id": "not_in_list"}, firestore_client=client) is False  # type: ignore[arg-type]
    assert store_conversation_screen_frames("u1", "c1", [], firestore_client=client) is True

    # Frames with missing or invalid IDs or non-dict items are skipped; conversation remains untouched if none stored
    res = store_conversation_screen_frames(
        "u1", "c1", ["not_a_dict", None, {"id": ""}, {"id": "../bad"}], firestore_client=client  # type: ignore[list-item]
    )
    assert res is True
    assert conv_ref.get().to_dict()["has_content"] is False


def test_delete_conversation_screen_frame_doc():
    client = FakeFirestoreClient()
    conv_ref = client.collection("users").document("u1").collection("conversations").document("c1")
    conv_ref.set({"has_content": True})
    conv_ref.collection("screen_frames").document("f1").set({"id": "f1"})

    assert delete_conversation_screen_frame_doc("u1", "c1", "f1", firestore_client=client) is True
    assert delete_conversation_screen_frame_doc("u1", "c1", "nonexistent_f", firestore_client=client) is False
    assert delete_conversation_screen_frame_doc("", "c1", "f1", firestore_client=client) is False
    assert delete_conversation_screen_frame_doc("u1", "../c1", "f1", firestore_client=client) is False


def test_delete_conversation_screen_frame_docs_batch():
    client = FakeFirestoreClient()
    conv_ref = client.collection("users").document("u1").collection("conversations").document("c1")
    conv_ref.set({"has_content": True})
    frames_col = conv_ref.collection("screen_frames")
    for i in range(5):
        frames_col.document(f"f_{i}").set({"id": f"f_{i}"})

    count = delete_conversation_screen_frame_docs("u1", "c1", firestore_client=client)
    assert count == 5
    assert len(get_conversation_screen_frames("u1", "c1", firestore_client=client)) == 0

    # Invalid input
    assert delete_conversation_screen_frame_docs("", "c1", firestore_client=client) == 0


def test_bump_and_get_revision():
    client = FakeFirestoreClient()
    conv_ref = client.collection("users").document("u1").collection("conversations").document("c1")
    conv_ref.set({})

    rev = bump_conversation_screen_frames_revision("u1", "c1", firestore_client=client)
    assert rev == 1
    assert get_conversation_screen_frames_revision("u1", "c1", firestore_client=client) == 1

    # Invalid inputs
    assert bump_conversation_screen_frames_revision("", "c1", firestore_client=client) == 0
    assert get_conversation_screen_frames_revision("u1", "", firestore_client=client) == 0


def test_mark_and_get_adjudicated():
    client = FakeFirestoreClient()
    conv_ref = client.collection("users").document("u1").collection("conversations").document("c1")
    conv_ref.set({})

    stamp = mark_conversation_screen_frames_adjudicated(
        uid="u1", conversation_id="c1", selection_fingerprint="fp_12345", firestore_client=client
    )
    assert stamp is not None
    assert isinstance(stamp, datetime)

    read_stamp = get_conversation_screen_frames_adjudicated_at("u1", "c1", firestore_client=client)
    assert read_stamp == stamp

    fp = get_conversation_screen_frames_selection_fingerprint("u1", "c1", firestore_client=client)
    assert fp == "fp_12345"

    # Invalid inputs
    assert (
        mark_conversation_screen_frames_adjudicated(
            uid="", conversation_id="c1", selection_fingerprint="x", firestore_client=client
        )
        is None
    )
    assert get_conversation_screen_frames_adjudicated_at("u1", "", firestore_client=client) is None
    assert get_conversation_screen_frames_selection_fingerprint("", "c1", firestore_client=client) is None


def test_screenshot_sharing_enabled_helpers():
    client = FakeFirestoreClient()
    conv_ref = client.collection("users").document("u1").collection("conversations").document("c1")
    conv_ref.set({"screenshot_sharing_enabled": True})

    # Read helper
    assert get_conversation_screenshot_sharing_enabled({"screenshot_sharing_enabled": False}) is False
    assert get_conversation_screenshot_sharing_enabled({"screenshot_sharing_enabled": True}) is True
    assert get_conversation_screenshot_sharing_enabled({}) is True  # Default True per ruling
    assert get_conversation_screenshot_sharing_enabled("not a dict") is True  # type: ignore[arg-type]

    # Set helper - success
    set_conversation_screenshot_sharing_enabled("u1", "c1", False, firestore_client=client)
    assert conv_ref.get().to_dict()["screenshot_sharing_enabled"] is False

    # Invalid inputs raise ValueError so privacy toggles never fail silently
    with pytest.raises(ValueError, match="Invalid uid or conversation_id"):
        set_conversation_screenshot_sharing_enabled("", "c1", True, firestore_client=client)

    with pytest.raises(ValueError, match="Invalid uid or conversation_id"):
        set_conversation_screenshot_sharing_enabled("u1", "../c1", True, firestore_client=client)


def test_resolve_client_fallback():
    mock_c = MagicMock()
    assert _resolve_client(mock_c) is mock_c

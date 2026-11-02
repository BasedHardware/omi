"""Unit tests for announcements database resilience, input sanitization, and error boundaries.

Verifies:
- Whitespace stripping on UID and announcement_id across user dismissal tracking.
- Strict ValueError rejection of empty/blank UID and announcement_id on writes.
- Safe fallbacks (set() / False / None / []) on empty/blank UID or Firestore outages on reads.
- Resilience against malformed/corrupted announcement documents in streams.
- Whitespace normalization in pending announcement test_uids targeting.
- Custom Firestore client injection support across all functions.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

import database.announcements as announcements_db
from models.announcement import Announcement, AnnouncementType, Display, Targeting, TriggerType


class _FakeDocSnapshot:
    def __init__(self, doc_id: str, data: dict, exists: bool = True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, store: dict, path: tuple):
        self._store = store
        self._path = path
        self.id = path[-1]

    def set(self, data: dict, merge: bool = False):
        current = self._store.get(self._path, {})
        if merge and isinstance(current, dict):
            current.update(data)
            self._store[self._path] = current
        else:
            self._store[self._path] = dict(data)

    def get(self):
        if self._path in self._store:
            return _FakeDocSnapshot(self.id, self._store[self._path], exists=True)
        return _FakeDocSnapshot(self.id, {}, exists=False)

    def update(self, updates: dict):
        if self._path not in self._store:
            raise KeyError(f"Document {self._path} not found")
        self._store[self._path].update(updates)

    def delete(self):
        self._store.pop(self._path, None)


class _FakeCollection:
    def __init__(self, store: dict, prefix: tuple):
        self._store = store
        self._prefix = prefix

    def document(self, doc_id: str):
        return _FakeDocRef(self._store, self._prefix + (doc_id,))

    def stream(self):
        for path, data in list(self._store.items()):
            if len(path) == len(self._prefix) + 1 and path[: len(self._prefix)] == self._prefix:
                yield _FakeDocSnapshot(path[-1], data, exists=True)

    def where(self, *args, **kwargs):
        return self


class _FakeFirestoreClient:
    def __init__(self):
        self.store = {}

    def collection(self, name: str):
        if name == "users":
            return _FakeUserCollection(self.store)
        return _FakeCollection(self.store, (name,))


class _FakeUserDocRef:
    def __init__(self, store: dict, uid: str):
        self.store = store
        self.uid = uid

    def collection(self, sub_collection: str):
        return _FakeCollection(self.store, ("users", self.uid, sub_collection))


class _FakeUserCollection:
    def __init__(self, store: dict):
        self.store = store

    def document(self, uid: str):
        return _FakeUserDocRef(self.store, uid)


@pytest.fixture
def fake_client():
    return _FakeFirestoreClient()


def test_dismiss_announcement_sanitizes_whitespace_and_writes(fake_client):
    success = announcements_db.dismiss_announcement(
        "  user_123  ", "  ann_456  ", cta_clicked=True, firestore_client=fake_client
    )
    assert success is True
    # Asserts canonical path: users/user_123/dismissed_announcements/ann_456
    stored = fake_client.store.get(("users", "user_123", "dismissed_announcements", "ann_456"))
    assert stored is not None
    assert stored["cta_clicked"] is True
    assert "dismissed_at" in stored


def test_dismiss_announcement_rejects_empty_or_blank_uid(fake_client):
    with pytest.raises(ValueError, match="uid cannot be empty"):
        announcements_db.dismiss_announcement("", "ann_1", firestore_client=fake_client)

    with pytest.raises(ValueError, match="uid cannot be empty"):
        announcements_db.dismiss_announcement("   ", "ann_1", firestore_client=fake_client)


def test_dismiss_announcement_rejects_empty_or_blank_announcement_id(fake_client):
    with pytest.raises(ValueError, match="announcement_id cannot be empty"):
        announcements_db.dismiss_announcement("user_123", "", firestore_client=fake_client)

    with pytest.raises(ValueError, match="announcement_id cannot be empty"):
        announcements_db.dismiss_announcement("user_123", "   ", firestore_client=fake_client)


def test_get_dismissed_announcement_ids_handles_whitespace_and_empty_uid(fake_client):
    # Empty / blank uid returns safe empty set
    assert announcements_db.get_dismissed_announcement_ids("", firestore_client=fake_client) == set()
    assert announcements_db.get_dismissed_announcement_ids("   ", firestore_client=fake_client) == set()

    # Pre-populate canonical document
    fake_client.store[("users", "user_123", "dismissed_announcements", "ann_1")] = {
        "dismissed_at": datetime.now(timezone.utc)
    }
    fake_client.store[("users", "user_123", "dismissed_announcements", "ann_2")] = {
        "dismissed_at": datetime.now(timezone.utc)
    }

    # Caller with untrimmed uid reads canonical documents
    ids = announcements_db.get_dismissed_announcement_ids("  user_123  ", firestore_client=fake_client)
    assert ids == {"ann_1", "ann_2"}


def test_get_dismissed_announcement_ids_returns_empty_set_on_firestore_error():
    broken_client = MagicMock()
    broken_client.collection.side_effect = RuntimeError("Firestore unavailable")
    res = announcements_db.get_dismissed_announcement_ids("user_123", firestore_client=broken_client)
    assert res == set()


def test_is_announcement_dismissed_handles_empty_uid_and_whitespace(fake_client):
    assert announcements_db.is_announcement_dismissed("", "ann_1", firestore_client=fake_client) is False
    assert announcements_db.is_announcement_dismissed("user_123", "", firestore_client=fake_client) is False
    assert announcements_db.is_announcement_dismissed("   ", "   ", firestore_client=fake_client) is False

    fake_client.store[("users", "user_123", "dismissed_announcements", "ann_1")] = {"cta_clicked": False}

    assert announcements_db.is_announcement_dismissed("  user_123  ", "  ann_1  ", firestore_client=fake_client) is True
    assert (
        announcements_db.is_announcement_dismissed("  user_123  ", "  ann_unknown  ", firestore_client=fake_client)
        is False
    )


def test_is_announcement_dismissed_returns_false_on_firestore_error():
    broken_client = MagicMock()
    broken_client.collection.side_effect = RuntimeError("Firestore connection reset")
    assert announcements_db.is_announcement_dismissed("user_123", "ann_1", firestore_client=broken_client) is False


def test_doc_to_announcement_skips_malformed_docs():
    non_existent = SimpleNamespace(exists=False, to_dict=lambda: {"id": "1"})
    assert announcements_db._doc_to_announcement(non_existent) is None

    non_dict = SimpleNamespace(exists=True, to_dict=lambda: "not-a-dict")
    assert announcements_db._doc_to_announcement(non_dict) is None

    # Corrupted dict where from_dict would fail unexpectedly
    bad_doc = MagicMock()
    bad_doc.exists = True
    bad_doc.to_dict.return_value = {"id": 12345}  # id not string, may cause unexpected failure in downstream models
    bad_doc.id = "bad_doc"
    # Should safely return an Announcement or None without raising out
    result = announcements_db._doc_to_announcement(bad_doc)
    assert result is None or isinstance(result, Announcement)


def test_get_pending_announcements_returns_empty_on_blank_uid(fake_client):
    res = announcements_db.get_pending_announcements(
        uid="   ",
        app_version="1.0.0",
        platform="ios",
        trigger="app_launch",
        firestore_client=fake_client,
    )
    assert res == []


def test_get_pending_announcements_sanitizes_test_uids(fake_client):
    announcement = Announcement(
        id="ann_test_exclusive",
        type=AnnouncementType.ANNOUNCEMENT,
        created_at=datetime.now(timezone.utc),
        content={"title": "Test Feature", "body": "Exclusive test announcement"},
        targeting=Targeting(platforms=["ios"], trigger=TriggerType.IMMEDIATE, test_uids=[" user_vip "]),
        display=Display(priority=100),
        active=True,
    )
    announcements_db.create_announcement(announcement, firestore_client=fake_client)

    # Calling with clean or untrimmed uid matches successfully
    res = announcements_db.get_pending_announcements(
        uid="user_vip",
        app_version="1.0.0",
        platform="ios",
        trigger="app_launch",
        firestore_client=fake_client,
    )
    assert len(res) == 1
    assert res[0].id == "ann_test_exclusive"

    # Non-targeted user is excluded
    res_other = announcements_db.get_pending_announcements(
        uid="user_normal",
        app_version="1.0.0",
        platform="ios",
        trigger="app_launch",
        firestore_client=fake_client,
    )
    assert len(res_other) == 0


def test_get_pending_announcements_handles_firestore_stream_error():
    broken_client = MagicMock()
    broken_client.collection.side_effect = RuntimeError("Firestore query stream failed")
    res = announcements_db.get_pending_announcements(
        uid="user_123",
        app_version="1.0.0",
        platform="ios",
        trigger="app_launch",
        firestore_client=broken_client,
    )
    assert res == []


def test_get_recent_changelogs_zero_or_negative_limit(fake_client):
    assert announcements_db.get_recent_changelogs(limit=0, firestore_client=fake_client) == []
    assert announcements_db.get_recent_changelogs(limit=-1, firestore_client=fake_client) == []


def test_crud_operations_empty_id_handling(fake_client):
    assert announcements_db.get_announcement_by_id("", firestore_client=fake_client) is None
    assert announcements_db.get_announcement_by_id("   ", firestore_client=fake_client) is None
    assert announcements_db.update_announcement("", {"title": "new"}, firestore_client=fake_client) is None
    assert announcements_db.update_announcement("   ", {"title": "new"}, firestore_client=fake_client) is None
    assert announcements_db.delete_announcement("", firestore_client=fake_client) is False
    assert announcements_db.delete_announcement("   ", firestore_client=fake_client) is False
    assert announcements_db.deactivate_announcement("", firestore_client=fake_client) is False
    assert announcements_db.deactivate_announcement("   ", firestore_client=fake_client) is False


def test_custom_firestore_client_injection(fake_client):
    ann = Announcement(
        id="ann_injected",
        type=AnnouncementType.ANNOUNCEMENT,
        created_at=datetime.now(timezone.utc),
        content={"title": "Custom Client", "body": "Testing injected client seam"},
        active=True,
    )
    announcements_db.create_announcement(ann, firestore_client=fake_client)

    fetched = announcements_db.get_announcement_by_id("ann_injected", firestore_client=fake_client)
    assert fetched is not None
    assert fetched.id == "ann_injected"

    all_ann = announcements_db.get_all_announcements(firestore_client=fake_client)
    assert len(all_ann) == 1
    assert all_ann[0].id == "ann_injected"

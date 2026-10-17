"""Hermetic unit tests for durable, owner-generation-fenced first-open conversation obligations."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from database import first_open_obligations as foo


class FakeDocumentSnapshot:
    def __init__(self, exists=True, data=None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return dict(self._data)


class FakeDocumentRef:
    def __init__(self, path="fake"):
        self.path = path
        self.updates = []
        self.sets = []

    def collection(self, name):
        return FakeCollectionRef(f"{self.path}/{name}")

    def get(self, transaction=None):
        return FakeDocumentSnapshot(exists=True, data={})

    def update(self, data):
        self.updates.append(data)

    def set(self, data, merge=False):
        self.sets.append((data, merge))


class FakeCollectionRef:
    def __init__(self, name="col"):
        self.name = name

    def document(self, doc_id):
        if not doc_id or "/" in str(doc_id):
            raise ValueError(f"Invalid doc_id: {doc_id}")
        return FakeDocumentRef(f"{self.name}/{doc_id}")

    def collection(self, sub_name):
        return FakeCollectionRef(f"{self.name}/{sub_name}")


class FakeFirestoreClient:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return FakeCollectionRef(name)


def test_is_valid_id():
    assert foo._is_valid_id("valid_id_123") is True
    assert foo._is_valid_id("user-abc-xyz") is True
    assert foo._is_valid_id("") is False
    assert foo._is_valid_id("   ") is False
    assert foo._is_valid_id("invalid/path") is False
    assert foo._is_valid_id("null\x00byte") is False
    assert foo._is_valid_id(None) is False
    assert foo._is_valid_id(123) is False
    assert foo._is_valid_id([]) is False


def test_conversation_ref_guards():
    client = FakeFirestoreClient()
    assert foo._conversation_ref(client, "valid_u", "valid_c") is not None
    assert foo._conversation_ref(client, "", "valid_c") is None
    assert foo._conversation_ref(client, "valid_u", "") is None
    assert foo._conversation_ref(client, "u/bad", "valid_c") is None
    assert foo._conversation_ref(client, "valid_u", "c/bad") is None


def test_initialize_first_open_work_invalid_ids():
    client = FakeFirestoreClient()
    assert foo.initialize_first_open_work("", "conv_1", firestore_client=client) is False
    assert foo.initialize_first_open_work("uid_1", "", firestore_client=client) is False
    assert foo.initialize_first_open_work("uid/bad", "conv_1", firestore_client=client) is False
    assert foo.initialize_first_open_work("uid_1", "conv/bad", firestore_client=client) is False


def test_first_open_effect_is_authorized_invalid_inputs():
    client = FakeFirestoreClient()
    assert (
        foo.first_open_effect_is_authorized("", "conv_1", "tok", "folder_assignment", firestore_client=client) is False
    )
    assert foo.first_open_effect_is_authorized("u1", "", "tok", "folder_assignment", firestore_client=client) is False
    assert (
        foo.first_open_effect_is_authorized("u1", "conv_1", "", "folder_assignment", firestore_client=client) is False
    )
    assert (
        foo.first_open_effect_is_authorized("u1", "conv_1", "tok", "invalid_effect", firestore_client=client) is False
    )


def test_commit_first_open_conversation_patch_invalid_inputs():
    client = FakeFirestoreClient()
    assert (
        foo.commit_first_open_conversation_patch("", "c1", "tok", "app_fanout", {"key": "val"}, firestore_client=client)
        is False
    )
    assert (
        foo.commit_first_open_conversation_patch("u1", "", "tok", "app_fanout", {"key": "val"}, firestore_client=client)
        is False
    )
    assert (
        foo.commit_first_open_conversation_patch("u1", "c1", "", "app_fanout", {"key": "val"}, firestore_client=client)
        is False
    )
    assert (
        foo.commit_first_open_conversation_patch("u1", "c1", "tok", "invalid", {"key": "val"}, firestore_client=client)
        is False
    )
    assert (
        foo.commit_first_open_conversation_patch("u1", "c1", "tok", "app_fanout", {}, firestore_client=client) is False
    )


def test_commit_first_open_app_result_invalid_inputs():
    client = FakeFirestoreClient()
    assert foo.commit_first_open_app_result("", "c1", "tok", "app1", {"patch": 1}, firestore_client=client) is False
    assert foo.commit_first_open_app_result("u1", "", "tok", "app1", {"patch": 1}, firestore_client=client) is False
    assert foo.commit_first_open_app_result("u1", "c1", "", "app1", {"patch": 1}, firestore_client=client) is False
    assert foo.commit_first_open_app_result("u1", "c1", "tok", "", {"patch": 1}, firestore_client=client) is False
    assert (
        foo.commit_first_open_app_result("u1", "c1", "tok", "app/bad", {"patch": 1}, firestore_client=client) is False
    )
    assert foo.commit_first_open_app_result("u1", "c1", "tok", "app1", {}, firestore_client=client) is False


def test_complete_first_open_effect_unknown_effect():
    client = FakeFirestoreClient()
    with pytest.raises(ValueError, match="unknown first-open effect"):
        foo.complete_first_open_effect("u1", "c1", "tok", "unknown_xyz", firestore_client=client)


def test_complete_first_open_effect_invalid_ids():
    client = FakeFirestoreClient()
    assert foo.complete_first_open_effect("", "c1", "tok", "folder_assignment", firestore_client=client) is False
    assert foo.complete_first_open_effect("u1", "", "tok", "folder_assignment", firestore_client=client) is False
    assert foo.complete_first_open_effect("u1", "c1", "", "folder_assignment", firestore_client=client) is False


def test_commit_first_open_folder_count_guards(monkeypatch):
    client = FakeFirestoreClient()
    assert foo.commit_first_open_folder_count("", "c1", "tok", "f1", firestore_client=client) is False
    assert foo.commit_first_open_folder_count("u1", "", "tok", "f1", firestore_client=client) is False
    assert foo.commit_first_open_folder_count("u1", "c1", "", "f1", firestore_client=client) is False
    assert foo.commit_first_open_folder_count("u1", "c1", "tok", "", firestore_client=client) is False
    assert foo.commit_first_open_folder_count("u1", "c1", "tok", "f/bad", firestore_client=client) is False


def test_commit_first_open_folder_count_handles_aggregation_error(monkeypatch):
    client = FakeFirestoreClient()
    # Mock query builder where count().get() raises an exception
    mock_query = MagicMock()
    mock_count = MagicMock()
    mock_count.get.side_effect = RuntimeError("Quota or network error")
    mock_query.count.return_value = mock_count

    monkeypatch.setattr(foo.FIRST_OPEN_FOLDER_CONVERSATION_COUNT_QUERY, "build", lambda *a, **k: mock_query)
    # The count query failure should be caught, defaulting count to 0 and proceeding cleanly
    res = foo.commit_first_open_folder_count("u1", "c1", "tok", "f1", firestore_client=client)
    assert res is False  # transaction fails safely because conversation/authority mock is absent, without raising


def test_commit_first_open_app_usage_guards():
    client = FakeFirestoreClient()
    assert foo.commit_first_open_app_usage("", "c1", "tok", "app1", "chat", firestore_client=client) is False
    assert foo.commit_first_open_app_usage("u1", "", "tok", "app1", "chat", firestore_client=client) is False
    assert foo.commit_first_open_app_usage("u1", "c1", "", "app1", "chat", firestore_client=client) is False
    assert foo.commit_first_open_app_usage("u1", "c1", "tok", "", "chat", firestore_client=client) is False
    assert foo.commit_first_open_app_usage("u1", "c1", "tok", "app/bad", "chat", firestore_client=client) is False


def test_claim_first_open_work_guards():
    client = FakeFirestoreClient()
    assert foo.claim_first_open_work("", "c1", firestore_client=client) is None
    assert foo.claim_first_open_work("u1", "", firestore_client=client) is None
    assert foo.claim_first_open_work("u/bad", "c1", firestore_client=client) is None


def test_finish_first_open_work_guards():
    client = FakeFirestoreClient()
    assert foo.finish_first_open_work("", "c1", "tok", firestore_client=client) is False
    assert foo.finish_first_open_work("u1", "", "tok", firestore_client=client) is False
    assert foo.finish_first_open_work("u1", "c1", "", firestore_client=client) is False

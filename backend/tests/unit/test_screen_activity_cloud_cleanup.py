"""Hermetic tests for the retired screen-activity cloud-copy purge lane."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

import utils.other.screen_activity_cleanup as cleanup


class FakeOwnerRef:
    def __init__(self, parent: "FakeUserDoc") -> None:
        self._parent = parent

    @property
    def parent(self) -> "FakeCollection":
        return FakeCollection(self._parent)


class FakeCollection:
    def __init__(self, user_doc: "FakeUserDoc") -> None:
        self.user_doc = user_doc

    @property
    def parent(self) -> "FakeUserDoc":
        return self.user_doc


class FakeSnapshot:
    def __init__(self, user_doc: "FakeUserDoc") -> None:
        self.reference = FakeOwnerRef(user_doc)


class FakeUserDoc:
    def __init__(self, uid: str) -> None:
        self.id = uid


class FakeFirestore:
    """Minimal collection_group discovery surface (IDs only)."""

    def __init__(self, owners: list[str]) -> None:
        self.owners = [FakeUserDoc(uid) for uid in owners]

    def collection_group(self, _name: str) -> "FakeGroupQuery":
        return FakeGroupQuery(self)


class FakeGroupQuery:
    def __init__(self, client: FakeFirestore) -> None:
        self.client = client

    def select(self, _fields: Any) -> "FakeGroupQuery":
        return self

    def stream(self):
        for doc in self.client.owners:
            yield FakeSnapshot(doc)


def make_cleanup(monkeypatch, owners, vector_error: Exception | None = None):
    client = FakeFirestore(owners)
    monkeypatch.setattr(cleanup, "get_firestore_client", lambda: client)

    def fake_ids(uid: str, firestore_client: Any = None) -> list[str]:
        return ["1", "2"]

    deleted_vectors: list[str] = []
    deleted_docs: dict[str, list[str]] = {}

    def fake_vectors(uid: str, ids: list[str]) -> None:
        if vector_error is not None:
            raise vector_error
        deleted_vectors.extend(ids)

    def fake_delete_docs(uid: str, ids: list[str], firestore_client: Any = None) -> int:
        # Only reachable when vector deletion succeeded: the production code
        # deletes documents strictly after the vectors.
        deleted_docs.setdefault(uid, []).extend(ids)
        return len(ids)

    monkeypatch.setattr(cleanup, "get_screen_activity_ids", fake_ids)
    monkeypatch.setattr(cleanup, "delete_screen_activity_vectors", fake_vectors)
    monkeypatch.setattr(cleanup, "delete_screen_activity", fake_delete_docs)
    return SimpleNamespace(deleted_vectors=deleted_vectors, deleted_docs=deleted_docs)


def test_purge_deletes_both_stores_per_user(monkeypatch):
    harness = make_cleanup(monkeypatch, owners=["user-a", "user-b"])

    async def run() -> dict[str, int]:
        return await cleanup.purge_retired_screen_activity_copies()

    result = asyncio.run(run())

    assert sorted(harness.deleted_vectors) == ["1", "1", "2", "2"]
    assert set(harness.deleted_docs) == {"user-a", "user-b"}
    assert result["users_scanned"] == 2
    assert result["vectors_deleted"] == 4
    assert result["docs_deleted"] == 4
    assert result["users_failed"] == 0


def test_vector_failure_keeps_documents_as_the_retry_list(monkeypatch):
    harness = make_cleanup(monkeypatch, owners=["user-a"], vector_error=RuntimeError("pinecone down"))

    async def run() -> dict[str, int]:
        return await cleanup.purge_retired_screen_activity_copies()

    result = asyncio.run(run())

    assert harness.deleted_docs == {}, "documents must survive so the next pass retries"
    assert result["users_failed"] == 1
    assert result["docs_deleted"] == 0


def test_users_per_run_zero_disables_the_pass(monkeypatch):
    make_cleanup(monkeypatch, owners=["user-a"])
    monkeypatch.setenv("SCREEN_ACTIVITY_CLOUD_PURGE_USERS_PER_RUN", "0")

    async def run() -> dict[str, int]:
        return await cleanup.purge_retired_screen_activity_copies()

    result = asyncio.run(run())
    assert result == {"users_scanned": 0, "docs_deleted": 0, "vectors_deleted": 0, "users_failed": 0}


def test_invalid_users_per_run_config_fails_loud(monkeypatch):
    make_cleanup(monkeypatch, owners=["user-a"])
    monkeypatch.setenv("SCREEN_ACTIVITY_CLOUD_PURGE_USERS_PER_RUN", "ten")

    async def run():
        await cleanup.purge_retired_screen_activity_copies()

    with pytest.raises(ValueError):
        asyncio.run(run())

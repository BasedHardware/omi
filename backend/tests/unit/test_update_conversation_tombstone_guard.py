"""Tests for update_conversation soft-deleted tombstone guard.

Contract:
``database.conversations.update_conversation`` documents that it:
    'Returns False when the conversation no longer exists, so callers that keep
    producing work for it (e.g. the pusher's private-cloud audio sync) can stop
    instead of writing into a deleted owner.'

Soft-deleted conversation tombstones (``deleted: True``) must be treated as
gone/non-existent by ``update_conversation``:
1. Returns False to caller so work ceases.
2. The tombstone document is not mutated.
3. Downstream side effects (cache invalidation, search index sync) do not execute.
"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import database.conversations as conversations_db

UID = "test-uid"
CONVERSATION_ID = "test-conversation-id"
CONVERSATION_PATH = ("users", UID, "conversations", CONVERSATION_ID)


class _MockDocumentRef:
    def __init__(self, store: "_MockFirestore", path: tuple):
        self._store = store
        self._path = path

    def collection(self, name: str) -> "_MockCollectionRef":
        return _MockCollectionRef(self._store, self._path + (name,))

    def get(self):
        documents = self._store.documents
        if self._path not in documents:
            return SimpleNamespace(exists=False, to_dict=lambda: None)
        data = deepcopy(documents[self._path])
        return SimpleNamespace(exists=True, to_dict=lambda: data)

    def update(self, updates: dict):
        documents = self._store.documents
        if self._path not in documents:
            raise RuntimeError(f"Document not found: {self._path}")
        documents[self._path].update(deepcopy(updates))


class _MockCollectionRef:
    def __init__(self, store: "_MockFirestore", path: tuple):
        self._store = store
        self._path = path

    def document(self, document_id: str) -> _MockDocumentRef:
        return _MockDocumentRef(self._store, self._path + (document_id,))


class _MockFirestore:
    def __init__(self, documents: dict = None):
        self.documents = documents if documents is not None else {}

    def collection(self, name: str) -> _MockCollectionRef:
        return _MockCollectionRef(self, (name,))


def _install_store(monkeypatch, **conversation_data) -> _MockFirestore:
    store = _MockFirestore({CONVERSATION_PATH: dict(conversation_data)})
    monkeypatch.setattr(conversations_db, "db", store)
    return store


def test_update_conversation_rejects_soft_deleted_tombstone(monkeypatch):
    """update_conversation must return False and not mutate a soft-deleted tombstone."""
    store = _install_store(
        monkeypatch,
        id=CONVERSATION_ID,
        deleted=True,
        language="en",
        data_protection_level="standard",
    )
    sync_mock = MagicMock()
    monkeypatch.setattr(conversations_db, "_sync_conversation_search_index", sync_mock)

    result = conversations_db.update_conversation(
        UID,
        CONVERSATION_ID,
        {"language": "es", "structured.title": "New Title"},
    )

    assert result is False, "Expected False for soft-deleted tombstone conversation"
    assert store.documents[CONVERSATION_PATH]["language"] == "en"
    assert "structured.title" not in store.documents[CONVERSATION_PATH]
    sync_mock.assert_not_called()


def test_update_conversation_succeeds_for_live_conversation(monkeypatch):
    """update_conversation must return True and mutate a live conversation."""
    store = _install_store(
        monkeypatch,
        id=CONVERSATION_ID,
        language="en",
        data_protection_level="standard",
    )
    sync_mock = MagicMock()
    monkeypatch.setattr(conversations_db, "_sync_conversation_search_index", sync_mock)

    result = conversations_db.update_conversation(
        UID,
        CONVERSATION_ID,
        {"language": "es"},
    )

    assert result is True, "Expected True for live active conversation"
    assert store.documents[CONVERSATION_PATH]["language"] == "es"

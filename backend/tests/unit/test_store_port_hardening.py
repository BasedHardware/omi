"""Hermetic guards for storage-port hardening fixes (adapter/factory parity, ADR-0002/0004/0032).

These cover the backend-neutral contract points a fake can prove without a live service:
  * ``update`` on a missing document raises the neutral ``NotFound`` (parity with the Firestore
    reference adapter, which raises; the Mongo adapter matches via ``matched_count==0``). The live
    dual-backend proof is ``tests/contract/test_document_store_contract.py``.
  * the document-store factory refuses ``STORAGE_BACKEND=mongo`` with no ``MONGO_URI`` instead of
    silently falling back to PyMongo's localhost default.
  * the object-store factory treats an empty ``OBJECT_STORE_BACKEND`` as the documented GCS default,
    like the store and vector factories.
"""

from __future__ import annotations

import pytest

from database.store.errors import NotFound
from tests.store_fakes import FakeDocumentStore


def test_fake_update_missing_raises_not_found():
    store = FakeDocumentStore()
    with pytest.raises(NotFound):
        store.update("users/u1", {"a": 1})
    assert not store.exists("users/u1")  # a failed update must not upsert


def test_fake_update_existing_applies():
    store = FakeDocumentStore()
    store.set("users/u1", {"a": 1})
    store.update("users/u1", {"a": 2, "b": 3})
    assert store.get("users/u1").to_dict() == {"a": 2, "b": 3}


def test_store_factory_mongo_requires_mongo_uri(monkeypatch):
    from database.store import factory as store_factory

    monkeypatch.setenv("STORAGE_BACKEND", "mongo")
    monkeypatch.delenv("MONGO_URI", raising=False)
    with pytest.raises(ValueError, match="MONGO_URI"):
        store_factory._build_store()


def test_object_store_factory_empty_backend_defaults_to_gcs(monkeypatch):
    from utils.object_store import factory as object_store_factory

    captured = {}

    def _fake_build(backend):
        captured["backend"] = backend
        return object()

    monkeypatch.setattr(object_store_factory, "_build", _fake_build)
    object_store_factory.reset_object_store_for_tests()
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "")
    object_store_factory.get_object_store()
    object_store_factory.reset_object_store_for_tests()
    assert captured["backend"] == "gcs"


def test_reset_document_store_closes_previous_adapter(monkeypatch):
    """reset_document_store() releases the previous adapter's client (the Mongo adapter holds a
    MongoClient) so repeated resets don't accumulate open connections."""
    from database.store import factory as store_factory

    closed = {"n": 0}

    class _ClosableStore:
        def close(self):
            closed["n"] += 1

    monkeypatch.setattr(store_factory, "_build_store", lambda: _ClosableStore())
    store_factory.reset_document_store()  # drop any instance a prior test left cached
    store_factory.get_document_store()  # build our closable under the patched factory
    store_factory.reset_document_store()  # must call close() on it
    assert closed["n"] == 1

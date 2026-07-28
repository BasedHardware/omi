"""database.conversations core paths, proven on BOTH backends (WP2 rollout, ADR-0002).

Exercises the migrated create/get/query/count/delete/create-marker paths through the live Firestore
emulator and a real Mongo replica set via the ``_store`` seam, catching any backend-specific issue
the port contract test can't (e.g. enum filter values, revision stamping). Data uses
``data_protection_level='standard'`` so the encryption decorators are no-ops.

Live services required (skipped when absent): ``FIRESTORE_EMULATOR_HOST``, ``MONGO_URI``.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

import database.conversations as conversations_db
from models.conversation_enums import ConversationStatus


@pytest.fixture(params=["firestore", "mongo"])
def bind_store(request, monkeypatch):
    backend = request.param
    if backend == "firestore":
        if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
            pytest.skip("FIRESTORE_EMULATOR_HOST not set")
        from database.store.adapters.firestore import FirestoreDocumentStore

        store = FirestoreDocumentStore()
    else:
        uri = os.environ.get("MONGO_URI")
        if not uri:
            pytest.skip("MONGO_URI not set")
        from database.store.adapters.mongo import MongoDocumentStore

        store = MongoDocumentStore(uri=uri, db_name="omi_contract")
    monkeypatch.setattr(conversations_db, "_store", lambda: store)
    return store


@pytest.fixture
def uid() -> str:
    return f"u_{uuid.uuid4().hex}"


def _conv(cid: str, **extra):
    base = {
        "id": cid,
        "status": ConversationStatus.completed.value,
        "discarded": False,
        "data_protection_level": "standard",
        "created_at": datetime.now(timezone.utc),
        "structured": {"title": f"title-{cid}"},
    }
    base.update(extra)
    return base


def test_create_if_absent_then_conflict_and_get(bind_store, uid):
    assert conversations_db.create_conversation_if_absent_with_lifecycle(uid, _conv("c1")) is True
    assert conversations_db.create_conversation_if_absent_with_lifecycle(uid, _conv("c1")) is False
    got = conversations_db.get_conversation(uid, "c1")
    assert got is not None and got["status"] == ConversationStatus.completed.value
    assert got.get("updated_at") is not None  # neutral revision stamped (ADR-0017)


def test_query_count_and_delete(bind_store, uid):
    for cid in ("c1", "c2", "c3"):
        conversations_db.create_conversation_if_absent_with_lifecycle(uid, _conv(cid))

    listed = conversations_db.get_conversations_without_photos(uid, limit=10)
    assert {c["id"] for c in listed} == {"c1", "c2", "c3"}
    assert conversations_db.get_conversations_count(uid) == 3

    conversations_db.delete_conversation(uid, "c2")
    assert conversations_db.get_conversation(uid, "c2") is None
    assert conversations_db.get_conversations_count(uid) == 2


def test_last_completed_uses_enum_filter(bind_store, uid):
    conversations_db.create_conversation_if_absent_with_lifecycle(uid, _conv("c1"))
    last = conversations_db.get_last_completed_conversation(uid)
    assert last is not None and last["id"] == "c1"


def test_try_claim_marker_is_create_once(bind_store, uid):
    assert conversations_db.try_claim_conversation_memory_analytics(uid, "c1") is True
    assert conversations_db.try_claim_conversation_memory_analytics(uid, "c1") is False

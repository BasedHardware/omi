"""Exercise the visibility route's retry boundary against the real Firestore SDK."""

import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import Aborted
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database.memory_apply_store import firestore_data
from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState
from routers import memories
from utils.memory import canonical_memory_adapter as adapter

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("outcome", ["recovery", "exhaustion", "deadline"])
def test_visibility_contention(monkeypatch, outcome):
    if not os.environ.get("FIRESTORE_EMULATOR_HOST", "").startswith(("127.0.0.1:", "localhost:")):
        pytest.skip("requires an owned local Firestore emulator")

    uid = f"visibility-{uuid4().hex}"
    db = firestore.Client(project="demo-visibility-contention", credentials=AnonymousCredentials())
    memory_id = adapter.write_canonical_external_memory(
        uid,
        {"id": "test-memory", "uid": uid, "content": "I like hiking", "visibility": "private"},
        db_client=db,
    )
    collections = MemoryCollections(uid=uid)
    item_ref = db.document(f"{collections.memory_items}/{memory_id}")
    control_ref = db.document(collections.memory_apply_control_state)
    before = item_ref.get().to_dict()
    before_control = control_ref.get().to_dict()

    # Advance the head after planning but before the transaction reads it.
    # Inject a definitive Aborted at the Commit RPC on subsequent attempts.
    api = db._firestore_api
    begin = api.begin_transaction
    commit = api.commit
    transaction_ids = []
    write_attempts = []

    def begin_with_head_race(request, **kwargs):
        if outcome == "recovery" and not transaction_ids:
            control = MemoryControlState.model_validate(before_control).advance_head("competing-head")
            control_ref.set(firestore_data(control))
        result = begin(request, **kwargs)
        transaction_ids.append(result.transaction)
        return result

    def commit_with_contention(request, **kwargs):
        if request.get("transaction") and any(
            write.update.name == item_ref._document_path for write in request["writes"]
        ):
            write_attempts.append(request["transaction"])
            assert item_ref.get().to_dict() == before
            if outcome != "recovery" or len(write_attempts) == 1:
                raise Aborted("synthetic cross-transaction contention")
        return commit(request, **kwargs)

    monkeypatch.setattr(api, "begin_transaction", begin_with_head_race)
    monkeypatch.setattr(api, "commit", commit_with_contention)
    monkeypatch.setattr(memories.db_client_module, "db", db)
    monkeypatch.setattr(memories.MemoryService, "_invalidate_prompt_cache", lambda *_: None)

    delays = []

    def retry_delay(attempt):
        delays.append(attempt)
        return 9.0 if outcome == "deadline" else 0.01

    monkeypatch.setattr(adapter, "equal_jitter_delay", retry_delay)
    side_effects = []

    def record_effect(effect):
        assert item_ref.get().to_dict()["visibility"] == "public"
        side_effects.append(effect)

    monkeypatch.setattr(memories, "submit_with_context", lambda *_: record_effect("personas"))
    monkeypatch.setattr(memories, "record_product_event", lambda event, **kw: record_effect((event, kw["op"])))
    app = FastAPI()
    app.include_router(memories.router)
    path = "/v3/memories/{memory_id}/visibility"
    route = next(route for route in app.routes if getattr(route, "path", None) == path)
    app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: uid

    with TestClient(app) as client:
        response = client.patch(path.format(memory_id=memory_id), json={"value": "public"})

    after = item_ref.get().to_dict()
    after_control = control_ref.get().to_dict()
    assert len(set(transaction_ids)) == len(transaction_ids)
    if outcome == "recovery":
        assert len(transaction_ids) == 3
        assert write_attempts == transaction_ids[1:]
        assert delays == [1, 2]
        assert response.status_code == 200, response.text
        assert side_effects == ["personas", ("memory_updated", "visibility")]
        assert after["visibility"] == "public"
        assert after["item_revision"] == before["item_revision"] + 1
        assert after["ledger_commit_id"] == after_control["head_commit_id"]
    else:
        attempts = 1 if outcome == "deadline" else 5
        assert write_attempts == transaction_ids
        assert len(transaction_ids) == attempts
        assert delays == ([1] if outcome == "deadline" else [1, 2, 3, 4])
        assert response.status_code == 409, response.text
        assert response.headers["Retry-After"] == "1"
        assert side_effects == []
        assert after == before
        assert after_control == before_control

"""Exercise the visibility route's retry boundary against the real Firestore SDK."""

import os
from contextvars import copy_context
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import Aborted, DeadlineExceeded, ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import rpc_deadline
from database.memory_apply_store import firestore_data
from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState
from routers import memories
from utils.memory import canonical_memory_adapter as adapter
from utils.memory import memory_service

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "outcome",
    [
        "recovery",
        "exhaustion",
        "deadline",
        "commit_timeout",
        "lost_ack",
        "control_timeout",
        "preflight_timeout",
        "begin_unavailable",
        "legacy_recovery",
        "legacy_exhaustion",
        "legacy_cleanup_expired",
    ],
)
def test_visibility_contention(monkeypatch, outcome):
    if not os.environ.get("FIRESTORE_EMULATOR_HOST", "").startswith(("127.0.0.1:", "localhost:")):
        pytest.skip("requires an owned local Firestore emulator")

    uid = f"visibility-{uuid4().hex}"
    db = firestore.Client(project="demo-visibility-contention", credentials=AnonymousCredentials())
    monkeypatch.setenv("MEMORY_ENABLED", "on")
    legacy = outcome.startswith("legacy_")
    memory_id = "test-memory"
    requested_visibility = "private" if outcome == "legacy_cleanup_expired" else "public"
    previous_visibility = "private" if requested_visibility == "public" else "public"
    payload = {"id": memory_id, "uid": uid, "content": "I like hiking", "visibility": previous_visibility}
    collections = MemoryCollections(uid=uid)
    item_ref = db.document(f"{collections.memory_items}/{memory_id}")
    legacy_ref = db.document(f"users/{uid}/memories/{memory_id}")
    control_ref = db.document(collections.memory_apply_control_state)
    if legacy:
        now = datetime.now(timezone.utc)
        legacy_ref.set({**payload, "created_at": now, "updated_at": now})
        adapter.ensure_canonical_apply_control_state(uid, db_client=db)
    else:
        assert adapter.write_canonical_external_memory(uid, payload, db_client=db) == memory_id
    before = item_ref.get().to_dict()
    before_control = control_ref.get().to_dict()

    # Advance the head after planning but before the transaction reads it.
    # Inject a definitive Aborted at the Commit RPC on subsequent attempts.
    api = db._firestore_api
    begin = api.begin_transaction
    commit = api.commit
    batch_get = api.batch_get_documents
    transaction_ids = []
    write_attempts = []
    preflight_deadlines = []
    cleanup_deadlines = []
    receipt_reads = []
    post_commit_reads = []
    scheduled_cleanup = []

    def begin_with_head_race(request, **kwargs):
        assert rpc_deadline.current() == adapter.visibility_write_deadline(preflight_deadlines[0])
        assert kwargs["retry"] is None
        assert 0 < kwargs["timeout"] <= 6
        if outcome == "begin_unavailable":
            raise ServiceUnavailable("synthetic begin unavailable")
        if outcome in {"recovery", "legacy_recovery"} and not transaction_ids:
            control = MemoryControlState.model_validate(before_control).advance_head("competing-head")
            control_ref.set(firestore_data(control))
        result = begin(request, **kwargs)
        transaction_ids.append(result.transaction)
        return result

    def commit_with_contention(request, **kwargs):
        if any(write.delete == legacy_ref._document_path for write in request["writes"]):
            cleanup_deadlines.append(rpc_deadline.current())
            assert kwargs["retry"] is None
            assert 0 < kwargs["timeout"] <= 8
        if request.get("transaction") and any(
            write.update.name == item_ref._document_path for write in request["writes"]
        ):
            write_attempts.append(request["transaction"])
            if outcome == "lost_ack":
                commit(request, **kwargs)
                raise DeadlineExceeded("synthetic lost commit acknowledgment")
            if outcome == "commit_timeout":
                raise DeadlineExceeded("synthetic unconfirmed commit")
            if outcome in {"exhaustion", "deadline", "legacy_exhaustion"} or (
                outcome in {"recovery", "legacy_recovery"} and len(write_attempts) == 1
            ):
                assert item_ref.get().to_dict() == before
                raise Aborted("synthetic cross-transaction contention")
        return commit(request, **kwargs)

    def observe_batch_get(request, **kwargs):
        deadline = rpc_deadline.current()
        documents = request["documents"]
        if item_ref._document_path in documents and not preflight_deadlines:
            assert deadline is not None, "route preflight must be inside the visibility budget"
            assert kwargs["retry"] is None
            assert 0 < kwargs["timeout"] <= 8
            preflight_deadlines.append(deadline)
            if outcome == "preflight_timeout":
                raise DeadlineExceeded("synthetic route preflight timeout")
        if outcome == "lost_ack" and write_attempts and deadline is not None:
            if item_ref._document_path in documents:
                post_commit_reads.append(deadline)
                raise ServiceUnavailable("synthetic post-commit item outage")
            if any("/memory_operations/" in path for path in documents):
                receipt_reads.append(deadline)
        if outcome == "control_timeout" and deadline is not None and control_ref._document_path in documents:
            raise DeadlineExceeded("synthetic control read timeout")
        return batch_get(request, **kwargs)

    def queue_cleanup(_executor, fn, *args, **kwargs):
        assert rpc_deadline.current() == preflight_deadlines[0]
        scheduled_cleanup.append((copy_context(), fn, args, kwargs))

    monkeypatch.setattr(memory_service, "submit_with_context", queue_cleanup)
    monkeypatch.setattr(api, "batch_get_documents", observe_batch_get)
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
        assert item_ref.get().to_dict()["visibility"] == requested_visibility
        side_effects.append(effect)

    monkeypatch.setattr(memories, "submit_with_context", lambda *_: record_effect("personas"))
    monkeypatch.setattr(memories, "record_product_event", lambda event, **kw: record_effect((event, kw["op"])))
    app = FastAPI()
    app.include_router(memories.router)
    path = "/v3/memories/{memory_id}/visibility"
    route = next(route for route in app.routes if getattr(route, "path", None) == path)
    app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: uid

    with TestClient(app) as client:
        response = client.patch(path.format(memory_id=memory_id), json={"value": requested_visibility})

    after = item_ref.get().to_dict()
    after_control = control_ref.get().to_dict()
    assert len(set(transaction_ids)) == len(transaction_ids)
    if outcome in {"recovery", "legacy_recovery", "legacy_cleanup_expired", "lost_ack"}:
        expected_attempts = {"recovery": 3, "legacy_recovery": 4, "legacy_cleanup_expired": 2, "lost_ack": 1}[outcome]
        assert len(transaction_ids) == expected_attempts
        fresh_head_race = outcome in {"recovery", "legacy_recovery"}
        assert write_attempts == (transaction_ids[1:] if fresh_head_race else transaction_ids)
        assert delays == ([1, 2] if fresh_head_race else [])
        assert response.status_code == 200, response.text
        assert side_effects == ["personas", ("memory_updated", "visibility")]
        assert after["visibility"] == requested_visibility
        assert after["item_revision"] == (2 if legacy else before["item_revision"] + 1)
        assert after["ledger_commit_id"] == after_control["head_commit_id"]
        if outcome == "lost_ack":
            assert len(receipt_reads) == 1
            assert post_commit_reads == []
        if legacy:
            assert legacy_ref.get().exists
            [(ctx, cleanup, args, kwargs)] = scheduled_cleanup
            with monkeypatch.context() as clock:
                if outcome == "legacy_cleanup_expired":
                    clock.setattr(rpc_deadline, "now", lambda: preflight_deadlines[0])
                ctx.run(cleanup, *args, **kwargs)
            if outcome == "legacy_cleanup_expired":
                assert legacy_ref.get().to_dict()["visibility"] == "public"
                assert memory_service.MemoryService(db_client=db).fetch(uid, memory_id).visibility == "private"
                assert cleanup_deadlines == []
            else:
                assert not legacy_ref.get().exists
                assert cleanup_deadlines == preflight_deadlines
    else:
        attempts, expected_delays, status = {
            "exhaustion": (5, [1, 2, 3, 4], 409),
            "legacy_exhaustion": (5, [1, 2, 3, 4], 409),
            "deadline": (1, [1], 409),
            "commit_timeout": (1, [], 503),
            "control_timeout": (0, [], 503),
            "preflight_timeout": (0, [], 503),
            "begin_unavailable": (0, [], 503),
        }[outcome]
        assert write_attempts == transaction_ids
        assert len(transaction_ids) == attempts
        assert delays == expected_delays
        assert response.status_code == status, response.text
        assert response.headers["Retry-After"] == "1"
        assert side_effects == []
        assert scheduled_cleanup == []
        assert after == before
        assert after_control == before_control
        if legacy:
            assert legacy_ref.get().to_dict()["visibility"] == "private"

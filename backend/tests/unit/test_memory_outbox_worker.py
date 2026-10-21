from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest

from database.memory_collections import MemoryCollections
from database.memory_outbox_worker import (
    CanonicalMemoryOutboxSideEffects,
    CanonicalMemoryOutboxWorkerConfig,
    lease_canonical_memory_outbox_events,
    run_canonical_memory_outbox_worker_tick,
)
from models.memory_apply import (
    MemoryControlState,
    MemoryOutboxEvent,
    MemoryOutboxEventType,
    MemoryOutboxStatus,
)
from models.memory_evidence import SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryTier, ProcessingState
from utils.memory.short_term_promotion import _canonical_outbox_side_effects

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
UID = "uid-outbox"
CONTROL_PATH = f"users/{UID}/memory_state/apply_control"
OUTBOX_PATH = f"users/{UID}/memory_outbox"


class _FakeSnapshot:
    def __init__(self, path: str, data: Optional[Dict[str, Any]]):
        self.reference = _FakeDocumentReference(path, None)
        self.id = path.rsplit("/", 1)[-1]
        self.exists = data is not None
        self._data = copy.deepcopy(data)

    def to_dict(self):
        return copy.deepcopy(self._data)


class _FakeDocumentReference:
    def __init__(self, path: str, db: Optional["_FakeFirestore"]):
        self.path = path
        self._db = db

    def get(self, transaction=None):
        assert self._db is not None
        return _FakeSnapshot(self.path, self._db.docs.get(self.path))

    def collection(self, name: str):
        assert self._db is not None
        return _FakeQuery(self._db, f"{self.path}/{name}")

    def delete(self):
        assert self._db is not None
        self._db.docs.pop(self.path, None)


class _FakeQuery:
    def __init__(
        self,
        db: "_FakeFirestore",
        collection_path: str,
        filters=None,
        limit_count: Optional[int] = None,
    ):
        self._db = db
        self._collection_path = collection_path
        self._filters = list(filters or [])
        self._limit_count = limit_count

    def where(
        self,
        field: Optional[str] = None,
        operation: Optional[str] = None,
        value: Any = None,
        *,
        filter: Any = None,
    ):
        if filter is not None:
            field = filter.field_path
            operation = filter.op_string
            value = filter.value
        assert field is not None
        assert operation is not None
        return _FakeQuery(
            self._db,
            self._collection_path,
            self._filters + [(field, operation, value)],
            self._limit_count,
        )

    def limit(self, count: int):
        return _FakeQuery(self._db, self._collection_path, self._filters, count)

    def document(self, document_id: str):
        return _FakeDocumentReference(f"{self._collection_path}/{document_id}", self._db)

    def stream(self):
        prefix = f"{self._collection_path}/"
        matches = []
        for path, data in sorted(self._db.docs.items()):
            if not path.startswith(prefix):
                continue
            if all(self._matches(data, field, operation, value) for field, operation, value in self._filters):
                matches.append(_FakeSnapshot(path, data))
        return matches[: self._limit_count]

    @staticmethod
    def _matches(data: Dict[str, Any], field: str, operation: str, value: Any) -> bool:
        actual = data.get(field)
        if operation == "==":
            return actual == value
        if operation == "<=":
            return actual is not None and actual <= value
        raise AssertionError(f"unsupported fake query operation: {operation}")


class _FakeTransaction:
    def __init__(self, db: "_FakeFirestore"):
        self._db = db
        self._writes = []

    def _begin(self):
        self._writes = []

    def update(self, ref: _FakeDocumentReference, patch: Dict[str, Any]):
        status = patch.get("status")
        if status in self._db.fail_update_statuses:
            raise RuntimeError("injected write failure with PRIVATE MEMORY TEXT")
        self._writes.append(("update", ref.path, copy.deepcopy(patch)))

    def set(self, ref: _FakeDocumentReference, payload: Dict[str, Any]):
        self._writes.append(("set", ref.path, copy.deepcopy(payload)))

    def delete(self, ref: _FakeDocumentReference):
        self._writes.append(("delete", ref.path, None))

    def _commit(self):
        for operation, path, payload in self._writes:
            if operation == "delete":
                self._db.docs.pop(path, None)
            elif operation == "set":
                assert payload is not None
                self._db.docs[path] = payload
            else:
                assert payload is not None
                self._db.docs[path].update(payload)

    def _rollback(self):
        self._writes = []

    def _clean_up(self):
        return None


class _FakeFirestore:
    def __init__(self, docs: Optional[Dict[str, Dict[str, Any]]] = None):
        self.docs = copy.deepcopy(docs or {})
        self.fail_update_statuses: set[str] = set()

    def collection(self, path: str):
        return _FakeQuery(self, path)

    def document(self, path: str):
        return _FakeDocumentReference(path, self)

    def transaction(self):
        return _FakeTransaction(self)


def _stored(model):
    return model.model_dump(mode="python")


def _control(*, account_generation: int = 7, source_generation: int = 3):
    return _stored(
        MemoryControlState(
            uid=UID,
            head_commit_id="head-7",
            account_generation=account_generation,
            source_generation=source_generation,
        )
    )


def _item(memory_id: str = "mem-1", **overrides):
    tier = overrides.pop("tier", MemoryTier.long_term)
    status = overrides.pop("status", MemoryItemStatus.active)
    captured_at = NOW - timedelta(days=2)
    data = {
        "memory_id": memory_id,
        "uid": UID,
        "version": 1,
        "tier": tier,
        "status": status,
        "processing_state": ProcessingState.processed,
        "content": "PRIVATE MEMORY TEXT from authoritative storage",
        "evidence": [],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": True,
        "captured_at": captured_at,
        "updated_at": captured_at,
        "expires_at": captured_at + timedelta(days=7) if tier == MemoryTier.short_term else None,
        "ledger_commit_id": "commit-1",
        "ledger_sequence": 1,
        "item_revision": 4,
        "content_hash": "content-hash-4",
        "account_generation": 7,
    }
    data.update(overrides)
    return _stored(MemoryItem(**data))


def _event(
    event_id: str = "evt-1",
    *,
    event_type: MemoryOutboxEventType = MemoryOutboxEventType.projection_sync,
    memory_id: Optional[str] = "mem-1",
    action: str = "upsert",
    status: MemoryOutboxStatus = MemoryOutboxStatus.pending,
    available_at: datetime = NOW,
    attempt_count: int = 0,
    account_generation: int = 7,
    source_generation: int = 3,
    item_revision: int = 4,
    content_hash: str = "content-hash-4",
    payload_overrides: Optional[Dict[str, Any]] = None,
):
    payload: Dict[str, Any] = {"action": action}
    if memory_id is not None:
        payload.update(
            {
                "memory_id": memory_id,
                "item_revision": item_revision,
                "content_hash": content_hash,
            }
        )
    payload.update(payload_overrides or {})
    return _stored(
        MemoryOutboxEvent(
            event_id=event_id,
            uid=UID,
            event_type=event_type,
            status=status,
            commit_id=f"commit-{event_id}",
            parent_commit_id="head-7",
            commit_sequence=1,
            memory_id=memory_id,
            operation_id=f"operation-{event_id}",
            account_generation=account_generation,
            source_generation=source_generation,
            payload=payload,
            available_at=available_at,
            attempt_count=attempt_count,
        )
    )


def _event_path(event_id: str) -> str:
    return f"{OUTBOX_PATH}/{event_id}"


def _item_path(memory_id: str) -> str:
    return f"users/{UID}/memory_items/{memory_id}"


def _db(*events: Dict[str, Any], items: Optional[Dict[str, Dict[str, Any]]] = None, control=None):
    docs = {CONTROL_PATH: control or _control()}
    for event in events:
        docs[_event_path(str(event["event_id"]))] = event
    for memory_id, item in (items or {}).items():
        docs[_item_path(memory_id)] = item
    return _FakeFirestore(docs)


def _recording_side_effects(calls, *, results: Optional[Dict[str, Any]] = None):
    results = results or {}

    def run(name: str, *args):
        calls.append((name, *args))
        result = results.get(name, True)
        if isinstance(result, Exception):
            raise result
        return result

    return CanonicalMemoryOutboxSideEffects(
        projection_upsert=lambda item, account_generation: run("projection_upsert", item),
        projection_delete=lambda uid, memory_id, account_generation: run("projection_delete", uid, memory_id),
        vector_upsert=lambda item, commit_id: run("vector_upsert", item, commit_id),
        vector_delete=lambda uid, memory_id: run("vector_delete", uid, memory_id),
    )


def _config(**overrides):
    data = {
        "worker_id": "worker-1",
        "limit": 25,
        "scan_limit": 100,
        "lease_seconds": 60,
        "max_attempts": 3,
        "base_backoff_seconds": 10,
        "max_backoff_seconds": 60,
    }
    data.update(overrides)
    return CanonicalMemoryOutboxWorkerConfig(**data)


def test_lease_is_bounded_and_claims_pending_retryable_and_expired_processing():
    pending = _event("pending", available_at=NOW - timedelta(minutes=3))
    retryable = _event(
        "retryable",
        event_type=MemoryOutboxEventType.vector_sync,
        status=MemoryOutboxStatus.retryable_failure,
        available_at=NOW - timedelta(minutes=2),
    )
    expired = _event("expired", status=MemoryOutboxStatus.processing, available_at=NOW - timedelta(minutes=1))
    expired["lease_owner"] = "old-worker"
    expired["lease_epoch"] = 5
    expired["lease_expires_at"] = NOW - timedelta(seconds=1)
    overflow = _event("overflow", available_at=NOW)
    future = _event("future", available_at=NOW + timedelta(minutes=1))
    live_lease = _event("live", status=MemoryOutboxStatus.processing)
    live_lease["lease_owner"] = "live-worker"
    live_lease["lease_epoch"] = 2
    live_lease["lease_expires_at"] = NOW + timedelta(minutes=1)
    delivered = _event("delivered", status=MemoryOutboxStatus.delivered)
    unrelated = _event("repair")
    unrelated["event_type"] = "vector_repair_purge"
    db = _db(pending, retryable, expired, overflow, future, live_lease, delivered, unrelated)

    leases = lease_canonical_memory_outbox_events(
        db_client=db,
        uid=UID,
        worker_id="new-worker",
        limit=3,
        scan_limit=10,
        lease_seconds=30,
        now=NOW,
    )

    assert [lease.document_id for lease in leases] == ["pending", "retryable", "expired"]
    assert all(
        db.docs[_event_path(event_id)]["status"] == MemoryOutboxStatus.processing.value
        for event_id in {
            "pending",
            "retryable",
            "expired",
        }
    )
    assert db.docs[_event_path("expired")]["lease_epoch"] == 6
    assert db.docs[_event_path("overflow")]["status"] == MemoryOutboxStatus.pending
    assert db.docs[_event_path("future")]["status"] == MemoryOutboxStatus.pending
    assert db.docs[_event_path("live")]["lease_owner"] == "live-worker"
    assert db.docs[_event_path("delivered")]["status"] == MemoryOutboxStatus.delivered
    assert db.docs[_event_path("repair")]["status"] == MemoryOutboxStatus.pending

    second_leases = lease_canonical_memory_outbox_events(
        db_client=db,
        uid=UID,
        worker_id="other-worker",
        limit=3,
        scan_limit=10,
        lease_seconds=30,
        now=NOW,
    )
    assert [lease.document_id for lease in second_leases] == ["overflow"]


@pytest.mark.parametrize(
    ("document_kind", "expected_error_code", "expected_path"),
    [
        ("event", "invalid_event", _event_path("malformed")),
        ("control", "invalid_control_state", CONTROL_PATH),
        ("item", "invalid_authoritative_item", _item_path("mem-1")),
    ],
)
def test_malformed_firestore_models_retry_with_sanitized_boundary_errors(
    document_kind,
    expected_error_code,
    expected_path,
    caplog,
):
    private_value = "PRIVATE MALFORMED MEMORY VALUE"
    event = _event("malformed")
    control = _control()
    item = _item()
    if document_kind == "event":
        event["uid"] = {"private": private_value}
    elif document_kind == "control":
        control["account_generation"] = {"private": private_value}
    else:
        item["uid"] = {"private": private_value}
    db = _db(event, items={"mem-1": item}, control=control)
    calls = []

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=_recording_side_effects(calls),
        now=NOW,
    )

    stored = db.docs[_event_path("malformed")]
    assert result["retryable_failure_count"] == 1
    assert result["delivered_count"] == 0
    assert result["errors"] == [
        {
            "stage": "process",
            "event_id": "malformed",
            "code": expected_error_code,
        }
    ]
    assert stored["status"] == MemoryOutboxStatus.retryable_failure.value
    assert stored["last_error_code"] == expected_error_code
    assert calls == []
    assert expected_path in caplog.text
    assert private_value not in caplog.text


def test_projection_sync_hydrates_authoritative_short_and_long_term_items():
    long_event = _event(
        "long",
        memory_id="mem-long",
        payload_overrides={"content": "FORGED EVENT MEMORY TEXT"},
    )
    short_event = _event("short", memory_id="mem-short")
    db = _db(
        long_event,
        short_event,
        items={
            "mem-long": _item("mem-long"),
            "mem-short": _item("mem-short", tier=MemoryTier.short_term),
        },
    )
    calls = []

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=_recording_side_effects(calls),
        now=NOW,
    )

    assert result["delivered_count"] == 2
    assert calls[0][0] == "projection_upsert"
    assert calls[0][1].memory_id == "mem-long"
    projected_item = calls[0][1]
    assert projected_item.content == "PRIVATE MEMORY TEXT from authoritative storage"
    assert "FORGED EVENT MEMORY TEXT" not in projected_item.content
    assert calls[1][0] == "projection_upsert"
    assert calls[1][1].memory_id == "mem-short"
    assert db.docs[_event_path("long")]["status"] == MemoryOutboxStatus.delivered.value
    assert db.docs[_event_path("short")]["side_effect_action"] == "projection_upsert"


def test_projection_sync_deletes_restricted_long_term_memory_instead_of_exposing_it():
    event = _event("restricted", memory_id="mem-restricted")
    db = _db(
        event,
        items={
            "mem-restricted": _item(
                "mem-restricted",
                sensitivity_labels=["health"],
            )
        },
    )
    calls = []

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=_recording_side_effects(calls),
        now=NOW,
    )

    assert result["delivered_count"] == 1
    assert calls == [("projection_delete", UID, "mem-restricted")]
    assert db.docs[_event_path("restricted")]["side_effect_action"] == "projection_delete"


def test_vector_sync_deletes_restricted_memory_instead_of_embedding_it():
    event = _event(
        "restricted-vector",
        event_type=MemoryOutboxEventType.vector_sync,
        memory_id="mem-restricted",
    )
    db = _db(
        event,
        items={
            "mem-restricted": _item(
                "mem-restricted",
                sensitivity_labels=["credential"],
            )
        },
    )
    calls = []

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=_recording_side_effects(calls),
        now=NOW,
    )

    assert result["delivered_count"] == 1
    assert calls == [("vector_delete", UID, "mem-restricted")]
    assert db.docs[_event_path("restricted-vector")]["side_effect_action"] == "vector_delete"


def test_vector_sync_repairs_when_item_becomes_restricted_during_delivery():
    event = _event(
        "restricted-during-delivery",
        event_type=MemoryOutboxEventType.vector_sync,
    )
    db = _db(event, items={"mem-1": _item()})
    calls = []

    def vector_upsert(item: MemoryItem, commit_id: str) -> bool:
        calls.append(("vector_upsert", item.item_revision))
        db.docs[_item_path("mem-1")] = _item(sensitivity_labels=["credential"])
        return True

    def vector_delete(uid: str, memory_id: str) -> bool:
        calls.append(("vector_delete", uid, memory_id))
        return True

    side_effects = CanonicalMemoryOutboxSideEffects(
        projection_upsert=lambda item, account_generation: True,
        projection_delete=lambda uid, memory_id, account_generation: True,
        vector_upsert=vector_upsert,
        vector_delete=vector_delete,
    )

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=side_effects,
        now=NOW,
    )

    assert result["delivered_count"] == 1
    assert calls == [
        ("vector_upsert", 4),
        ("vector_delete", UID, "mem-1"),
    ]
    assert db.docs[_event_path("restricted-during-delivery")]["side_effect_action"] == "vector_delete"


def test_account_deletion_fence_makes_projection_delivery_delete_only():
    event = _event("delete-fenced-vector", event_type=MemoryOutboxEventType.vector_sync)
    db = _db(event, items={"mem-1": _item()})
    db.docs[f"account_deletions/{UID}"] = {"wipe_status": "running"}
    calls = []

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=_recording_side_effects(calls),
        now=NOW,
    )

    assert result["delivered_count"] == 1
    assert calls == [("vector_delete", UID, "mem-1")]
    assert db.docs[_event_path("delete-fenced-vector")]["side_effect_action"] == "vector_delete"


def test_account_deletion_fence_appearing_during_upsert_is_repaired_before_ack():
    event = _event("delete-race-vector", event_type=MemoryOutboxEventType.vector_sync)
    db = _db(event, items={"mem-1": _item()})
    calls = []

    def vector_upsert(item: MemoryItem, commit_id: str) -> bool:
        calls.append(("vector_upsert", item.memory_id))
        db.docs[f"account_deletions/{UID}"] = {"wipe_status": "running"}
        return True

    side_effects = CanonicalMemoryOutboxSideEffects(
        projection_upsert=lambda item, account_generation: True,
        projection_delete=lambda uid, memory_id, account_generation: True,
        vector_upsert=vector_upsert,
        vector_delete=lambda uid, memory_id: calls.append(("vector_delete", memory_id)) or True,
    )

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=side_effects,
        now=NOW,
    )

    assert result["delivered_count"] == 1
    assert calls == [("vector_upsert", "mem-1"), ("vector_delete", "mem-1")]
    assert db.docs[_event_path("delete-race-vector")]["side_effect_action"] == "vector_delete"


def test_projection_sync_converges_keyword_graph_and_review_side_effects():
    create = _event("projection-create")
    db = _db(create, items={"mem-1": _item()})
    paths = MemoryCollections(uid=UID)
    graph_assertion_path = f"{paths.memory_graph_assertions}/mem-1"
    db.docs[graph_assertion_path] = {"memory_id": "mem-1"}
    side_effects = _canonical_outbox_side_effects(db_client=db)

    with (
        patch(
            "utils.memory.short_term_promotion.sync_atom_keyword_index_for_item",
            return_value=True,
        ) as keyword_upsert,
        patch(
            "utils.memory.short_term_promotion.delete_atom_keyword_doc",
            return_value=True,
        ) as keyword_delete,
        patch(
            "utils.memory.short_term_promotion.kg_db.prune_memory_citations_from_kg",
            return_value=0,
        ) as citation_prune,
        patch(
            "utils.memory.short_term_promotion.purge_stale_review_conflicts_for_memories",
            return_value=[],
        ) as review_purge,
    ):
        created = run_canonical_memory_outbox_worker_tick(
            db_client=db,
            uid=UID,
            config=_config(),
            side_effects=side_effects,
            now=NOW,
        )
        assert created["delivered_count"] == 1
        assert keyword_upsert.call_count == 1

        db.docs[_item_path("mem-1")] = _item(
            content="UPDATED PRIVATE MEMORY TEXT",
            item_revision=5,
            content_hash="content-hash-5",
            ledger_commit_id="commit-update",
            ledger_sequence=2,
        )
        update = _event(
            "projection-update",
            item_revision=5,
            content_hash="content-hash-5",
        )
        db.docs[_event_path("projection-update")] = update
        updated = run_canonical_memory_outbox_worker_tick(
            db_client=db,
            uid=UID,
            config=_config(),
            side_effects=side_effects,
            now=NOW,
        )
        assert updated["delivered_count"] == 1
        assert keyword_upsert.call_count == 2

        db.docs[_item_path("mem-1")] = _item(
            tier=MemoryTier.archive,
            status=MemoryItemStatus.hidden,
            item_revision=6,
            content_hash="content-hash-6",
            ledger_commit_id="commit-delete",
            ledger_sequence=3,
        )
        delete = _event(
            "projection-delete",
            action="delete",
            item_revision=6,
            content_hash="content-hash-6",
        )
        db.docs[_event_path("projection-delete")] = delete
        deleted = run_canonical_memory_outbox_worker_tick(
            db_client=db,
            uid=UID,
            config=_config(),
            side_effects=side_effects,
            now=NOW,
        )

    assert deleted["delivered_count"] == 1
    assert graph_assertion_path not in db.docs
    keyword_delete.assert_called_once_with(UID, "mem-1", db_client=db)
    citation_prune.assert_called_once_with(UID, ["mem-1"], db_client=db)
    review_purge.assert_called_once_with(
        UID,
        ["mem-1"],
        reason="memory_outbox_projection_deleted",
        db_client=db,
    )


def test_vector_sync_upserts_live_item_and_deletes_nonprojectable_or_missing_items():
    active = _event("active", event_type=MemoryOutboxEventType.vector_sync, memory_id="mem-active")
    archived = _event(
        "archived",
        event_type=MemoryOutboxEventType.vector_sync,
        memory_id="mem-archived",
        action="delete",
    )
    superseded = _event(
        "superseded",
        event_type=MemoryOutboxEventType.vector_sync,
        memory_id="mem-superseded",
        action="delete",
    )
    missing = _event(
        "missing",
        event_type=MemoryOutboxEventType.vector_sync,
        memory_id="mem-missing",
    )
    db = _db(
        active,
        archived,
        superseded,
        missing,
        items={
            "mem-active": _item("mem-active", tier=MemoryTier.short_term),
            "mem-archived": _item("mem-archived", tier=MemoryTier.archive),
            "mem-superseded": _item("mem-superseded", status=MemoryItemStatus.superseded),
        },
    )
    calls = []

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=_recording_side_effects(calls),
        now=NOW,
    )

    assert result["delivered_count"] == 4
    assert calls[0][0] == "vector_upsert"
    assert calls[0][1].memory_id == "mem-active"
    assert calls[0][2] == "commit-active"
    assert calls[1:] == [
        ("vector_delete", UID, "mem-archived"),
        ("vector_delete", UID, "mem-missing"),
        ("vector_delete", UID, "mem-superseded"),
    ]


@pytest.mark.parametrize(
    ("control_generation", "item_overrides", "event_overrides", "settled_reason"),
    [
        (8, {}, {}, "stale_account_generation"),
        (7, {"account_generation": 6}, {}, "stale_item_account_generation"),
        (7, {}, {"item_revision": 3}, "stale_item_revision"),
        (7, {}, {"content_hash": "older-hash"}, "stale_content_hash"),
    ],
)
def test_stale_fences_are_safely_settled_without_side_effect(
    control_generation,
    item_overrides,
    event_overrides,
    settled_reason,
):
    event = _event("stale", event_type=MemoryOutboxEventType.vector_sync, **event_overrides)
    db = _db(
        event,
        items={"mem-1": _item(**item_overrides)},
        control=_control(account_generation=control_generation),
    )
    calls = []

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=_recording_side_effects(calls),
        now=NOW,
    )

    stored = db.docs[_event_path("stale")]
    assert stored["status"] == MemoryOutboxStatus.delivered.value
    assert stored["settled_reason"] == settled_reason
    assert result["stale_settled_count"] == 1
    assert calls == []


def test_reclaimed_processing_lease_repairs_current_state_before_ack_with_stale_fences():
    event = _event(
        "crashed-stale-write",
        event_type=MemoryOutboxEventType.vector_sync,
        status=MemoryOutboxStatus.processing,
    )
    event.update(
        {
            "lease_owner": "crashed-worker",
            "lease_epoch": 4,
            "lease_expires_at": NOW - timedelta(seconds=1),
        }
    )
    db = _db(
        event,
        items={
            "mem-1": _item(
                status=MemoryItemStatus.hidden,
                account_generation=8,
                item_revision=5,
                content_hash="content-hash-5",
                ledger_commit_id="commit-newer",
                ledger_sequence=2,
            )
        },
        control=_control(account_generation=8),
    )
    provider_state: Dict[str, Any] = {
        "present": True,
        "item_revision": 4,
    }
    calls = []

    def vector_delete(uid: str, memory_id: str) -> bool:
        calls.append(("vector_delete", uid, memory_id))
        provider_state.clear()
        provider_state["present"] = False
        return True

    side_effects = CanonicalMemoryOutboxSideEffects(
        projection_upsert=lambda item, account_generation: True,
        projection_delete=lambda uid, memory_id, account_generation: True,
        vector_upsert=lambda item, commit_id: True,
        vector_delete=vector_delete,
    )

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=side_effects,
        now=NOW,
    )

    assert result["delivered_count"] == 1
    assert result["stale_settled_count"] == 0
    assert calls == [("vector_delete", UID, "mem-1")]
    assert provider_state == {"present": False}
    stored = db.docs[_event_path("crashed-stale-write")]
    assert stored["status"] == MemoryOutboxStatus.delivered.value
    assert stored["settled_reason"] == "projected"
    assert stored["side_effect_action"] == "vector_delete"


def test_prior_source_generation_event_projects_unchanged_authoritative_item():
    event = _event(
        "prior-source",
        event_type=MemoryOutboxEventType.vector_sync,
        source_generation=2,
    )
    db = _db(
        event,
        items={"mem-1": _item()},
        control=_control(source_generation=3),
    )
    calls = []

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=_recording_side_effects(calls),
        now=NOW,
    )

    assert result["stale_settled_count"] == 0
    assert db.docs[_event_path("prior-source")]["settled_reason"] == "projected"
    assert len(calls) == 1
    assert calls[0][0] == "vector_upsert"
    assert calls[0][1].memory_id == "mem-1"
    assert calls[0][2] == "commit-prior-source"


def test_older_overlapping_run_repairs_newer_provider_state_before_acknowledging():
    older = _event("older", available_at=NOW - timedelta(seconds=1))
    newer = _event(
        "newer",
        item_revision=5,
        content_hash="content-hash-5",
        available_at=NOW,
    )
    db = _db(older, newer, items={"mem-1": _item()})
    provider_state: dict[str, int] = {}
    chronology: list[tuple[str, int]] = []
    nested_summary: dict[str, Any] = {}
    in_nested_run = False

    def projection_upsert(item: MemoryItem, account_generation: int) -> bool:
        nonlocal in_nested_run
        if item.item_revision == 4:
            db.docs[_item_path("mem-1")] = _item(
                item_revision=5,
                content_hash="content-hash-5",
                ledger_commit_id="commit-newer",
                ledger_sequence=2,
            )
            in_nested_run = True
            nested_summary.update(
                run_canonical_memory_outbox_worker_tick(
                    db_client=db,
                    uid=UID,
                    config=_config(worker_id="worker-newer"),
                    side_effects=side_effects,
                    now=NOW,
                )
            )
            in_nested_run = False
            chronology.append(("older_stale_write", item.item_revision))
        else:
            chronology.append(
                (
                    "newer_write" if in_nested_run else "older_repair",
                    item.item_revision,
                )
            )
        provider_state["revision"] = item.item_revision
        return True

    side_effects = CanonicalMemoryOutboxSideEffects(
        projection_upsert=projection_upsert,
        projection_delete=lambda uid, memory_id, account_generation: True,
        vector_upsert=lambda item, commit_id: True,
        vector_delete=lambda uid, memory_id: True,
    )

    older_summary = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(limit=1),
        side_effects=side_effects,
        now=NOW,
    )

    assert nested_summary["delivered_count"] == 1
    assert older_summary["delivered_count"] == 1
    assert chronology == [
        ("newer_write", 5),
        ("older_stale_write", 4),
        ("older_repair", 5),
    ]
    assert provider_state == {"revision": 5}
    assert db.docs[_event_path("older")]["status"] == MemoryOutboxStatus.delivered.value
    assert db.docs[_event_path("newer")]["status"] == MemoryOutboxStatus.delivered.value


def test_barriers_settle_without_item_hydration_or_external_side_effect():
    projection = _event("projection-barrier", memory_id=None, action="barrier")
    vector = _event(
        "vector-barrier",
        event_type=MemoryOutboxEventType.vector_sync,
        memory_id=None,
        action="barrier",
    )
    db = _db(projection, vector)
    calls = []

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=_recording_side_effects(calls),
        now=NOW,
    )

    assert result["delivered_count"] == 2
    assert result["barrier_count"] == 2
    assert calls == []
    assert db.docs[_event_path("projection-barrier")]["settled_reason"] == "barrier"
    assert db.docs[_event_path("vector-barrier")]["settled_reason"] == "barrier"


def test_failures_retry_with_deterministic_backoff_then_dead_letter_without_raw_text(caplog):
    event = _event("failure", event_type=MemoryOutboxEventType.vector_sync)
    db = _db(event, items={"mem-1": _item()})
    private_error = RuntimeError("provider rejected PRIVATE MEMORY TEXT")
    side_effects = _recording_side_effects([], results={"vector_upsert": private_error})
    config = _config(max_attempts=3, base_backoff_seconds=10, max_backoff_seconds=60)

    first = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=config,
        side_effects=side_effects,
        now=NOW,
    )
    stored = db.docs[_event_path("failure")]
    assert stored["status"] == MemoryOutboxStatus.retryable_failure.value
    assert stored["attempt_count"] == 1
    assert stored["available_at"] == NOW + timedelta(seconds=10)
    assert stored["last_error_code"] == "vector_upsert_failed"
    assert first["retryable_failure_count"] == 1
    assert first["delivered_count"] == 0
    assert "oldest_ready_age_seconds" in first

    second_now = NOW + timedelta(seconds=10)
    second = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=config,
        side_effects=side_effects,
        now=second_now,
    )
    stored = db.docs[_event_path("failure")]
    assert stored["status"] == MemoryOutboxStatus.retryable_failure.value
    assert stored["attempt_count"] == 2
    assert stored["available_at"] == second_now + timedelta(seconds=20)
    assert second["retryable_failure_count"] == 1

    third_now = second_now + timedelta(seconds=20)
    third = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=config,
        side_effects=side_effects,
        now=third_now,
    )
    stored = db.docs[_event_path("failure")]
    assert stored["status"] == MemoryOutboxStatus.dead_letter.value
    assert stored["attempt_count"] == 3
    assert stored["last_error_code"] == "vector_upsert_failed"
    assert third["dead_letter_count"] == 1
    assert third["delivered_count"] == 0
    assert "PRIVATE MEMORY TEXT" not in repr(first)
    assert "PRIVATE MEMORY TEXT" not in repr(second)
    assert "PRIVATE MEMORY TEXT" not in repr(third)
    assert "PRIVATE MEMORY TEXT" not in caplog.text


def test_poison_event_does_not_block_the_event_behind_it():
    poison = _event("poison", memory_id="mem-poison", available_at=NOW - timedelta(minutes=2))
    healthy = _event("healthy", memory_id="mem-healthy", available_at=NOW - timedelta(minutes=1))
    db = _db(
        poison,
        healthy,
        items={"mem-poison": _item("mem-poison"), "mem-healthy": _item("mem-healthy")},
    )
    processed: list[str] = []

    def projection_upsert(item, account_generation):
        processed.append(item.memory_id)
        if item.memory_id == "mem-poison":
            raise RuntimeError("malformed payload")
        return True

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=CanonicalMemoryOutboxSideEffects(
            projection_upsert=projection_upsert,
            projection_delete=lambda *_args, **_kwargs: True,
            vector_upsert=lambda *_args, **_kwargs: True,
            vector_delete=lambda *_args, **_kwargs: True,
        ),
        now=NOW,
    )

    assert processed == ["mem-poison", "mem-healthy"]
    assert result["delivered_count"] == 1
    assert result["retryable_failure_count"] == 1
    assert db.docs[_event_path("poison")]["status"] == MemoryOutboxStatus.retryable_failure.value
    assert db.docs[_event_path("healthy")]["status"] == MemoryOutboxStatus.delivered.value


def test_false_side_effect_result_is_not_acknowledged_as_delivered():
    event = _event("false-result")
    db = _db(event, items={"mem-1": _item()})

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=_recording_side_effects([], results={"projection_upsert": False}),
        now=NOW,
    )

    assert result["delivered_count"] == 0
    assert result["retryable_failure_count"] == 1
    assert db.docs[_event_path("false-result")]["status"] == MemoryOutboxStatus.retryable_failure.value


def test_retry_after_inconclusive_provider_write_repairs_newer_authoritative_revision():
    event = _event("inconclusive-provider-write", event_type=MemoryOutboxEventType.vector_sync)
    db = _db(event, items={"mem-1": _item()})
    provider_state: dict[str, Any] = {}

    def vector_upsert(item: MemoryItem, commit_id: str) -> bool:
        provider_state["revision"] = item.item_revision
        provider_state["commit_id"] = commit_id
        if item.item_revision == 4:
            db.docs[_item_path("mem-1")] = _item(
                item_revision=5,
                content_hash="content-hash-5",
                ledger_commit_id="commit-newer",
                ledger_sequence=2,
            )
            return False
        return True

    side_effects = CanonicalMemoryOutboxSideEffects(
        projection_upsert=lambda item, account_generation: True,
        projection_delete=lambda uid, memory_id, account_generation: True,
        vector_upsert=vector_upsert,
        vector_delete=lambda uid, memory_id: True,
    )

    first = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=side_effects,
        now=NOW,
    )
    second = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=side_effects,
        now=NOW + timedelta(seconds=10),
    )

    assert first["retryable_failure_count"] == 1
    assert second["delivered_count"] == 1
    assert second["stale_settled_count"] == 0
    assert provider_state == {"revision": 5, "commit_id": "commit-newer"}
    assert db.docs[_event_path("inconclusive-provider-write")]["status"] == MemoryOutboxStatus.delivered.value


def test_successful_side_effect_is_not_delivered_after_lease_ownership_is_lost():
    event = _event("lease-lost", event_type=MemoryOutboxEventType.vector_sync)
    db = _db(event, items={"mem-1": _item()})
    calls = []

    def steal_lease(item, commit_id):
        calls.append((item.memory_id, commit_id))
        stored = db.docs[_event_path("lease-lost")]
        stored["lease_owner"] = "replacement-worker"
        stored["lease_epoch"] += 1
        return True

    side_effects = CanonicalMemoryOutboxSideEffects(
        projection_upsert=lambda item, account_generation: True,
        projection_delete=lambda uid, memory_id, account_generation: True,
        vector_upsert=steal_lease,
        vector_delete=lambda uid, memory_id: True,
    )

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=side_effects,
        now=NOW,
    )

    assert calls == [("mem-1", "commit-lease-lost")]
    assert result["delivered_count"] == 0
    assert result["ack_failed_count"] == 1
    assert db.docs[_event_path("lease-lost")]["status"] == MemoryOutboxStatus.processing.value
    assert db.docs[_event_path("lease-lost")]["lease_owner"] == "replacement-worker"


def test_delivered_ack_write_failure_leaves_processing_lease_for_safe_replay():
    event = _event("ack-failure", event_type=MemoryOutboxEventType.vector_sync)
    db = _db(event, items={"mem-1": _item()})
    db.fail_update_statuses.add(MemoryOutboxStatus.delivered.value)
    calls = []

    result = run_canonical_memory_outbox_worker_tick(
        db_client=db,
        uid=UID,
        config=_config(),
        side_effects=_recording_side_effects(calls),
        now=NOW,
    )

    assert calls[0][0] == "vector_upsert"
    assert result["delivered_count"] == 0
    assert result["ack_failed_count"] == 1
    stored = db.docs[_event_path("ack-failure")]
    assert stored["status"] == MemoryOutboxStatus.processing.value
    assert stored["lease_expires_at"] == NOW + timedelta(seconds=60)

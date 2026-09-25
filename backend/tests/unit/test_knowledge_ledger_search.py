from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database.memory_vector_metadata import build_ledger_memory_vector_filter
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items_by_ids
from utils.memory.atom_keyword_index import (
    TYPESENSE_PROJECTION_READINESS_COLLECTION,
    TYPESENSE_PROJECTION_READINESS_DOCUMENT_ID,
    TYPESENSE_PROJECTION_READINESS_SCHEMA_VERSION,
    TypesenseProjectionNotReady,
    keyword_search_ledger_memory_ids,
    require_typesense_projection_ready,
)
from models.knowledge_ledger_search import (
    LEDGER_INDEX_VERSION,
    LedgerRowIndexState,
    LedgerSearchSurface,
    build_ledger_index_metadata,
    is_ledger_row_admissible,
    ledger_row_index_state,
    validate_ledger_kinds,
)
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    ProcessingState,
)


def _row(**updates):
    payload = {
        "uid": "u1",
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": MemoryKind.fact,
        "content": "The user works at Omi",
        "intent_backed": True,
        "write_reason": LedgerWriteReason.direct_user_statement,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "promotion": {},
        "user_asserted": True,
        "subject_scope": "primary_user",
        "valid_to": None,
        "invalid_at": None,
        "superseded_by": None,
    }
    payload.update(updates)
    return SimpleNamespace(**payload)


def _canonical_item_payload(memory_id: str, *, uid: str = "u1"):
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    return MemoryItem(
        memory_id=memory_id,
        uid=uid,
        version=1,
        tier=MemoryLayer.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=f"content-{memory_id}",
        evidence=[
            MemoryEvidence(
                evidence_id=f"ev-{memory_id}",
                source_type="conversation",
                source_id="conversation-1",
                source_version="v1",
                conversation_id="conversation-1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=now,
        updated_at=now,
        ledger_commit_id=f"commit-{memory_id}",
        ledger_sequence=1,
        ledger_schema_version="knowledge_ledger.v1",
        kind=MemoryKind.fact,
        intent_backed=True,
        write_reason=LedgerWriteReason.agent_reusable_conclusion,
    ).model_dump(mode="python")


def test_current_search_admits_open_unslotted_facts_documents_and_triggers():
    for kind, extra in (
        (MemoryKind.fact, {"slot": None}),
        (MemoryKind.document, {"subject_scope": "primary_user", "body": "private body"}),
        (MemoryKind.trigger, {"subject_scope": "primary_user", "trigger_condition": {"keyword": "release"}}),
    ):
        assert is_ledger_row_admissible(
            _row(kind=kind, **extra),
            uid="u1",
            surface=LedgerSearchSurface.current,
            kinds={kind.value},
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"uid": "u2"},
        {"status": MemoryItemStatus.superseded},
        {"valid_to": "closed"},
        {"intent_backed": False, "write_reason": LedgerWriteReason.daily_reconciliation},
        {"promotion": {"user_review": False}},
        {"promotion": {"is_locked": True}},
        {"sensitivity_labels": ["financial"]},
        {"source_state": SourceState.tombstoned},
        {"kind": MemoryKind.document, "subject_scope": "third_party"},
    ],
)
def test_current_search_fails_closed_for_owner_lifecycle_and_privacy_boundaries(updates):
    assert not is_ledger_row_admissible(
        _row(**updates),
        uid="u1",
        surface=LedgerSearchSurface.current,
    )


def test_history_is_fact_only_and_preserves_legacy_generated_data():
    closed = _row(status=MemoryItemStatus.superseded)
    legacy = _row(intent_backed=False, write_reason=LedgerWriteReason.legacy_migration)
    active = _row()
    document = _row(kind=MemoryKind.document, status=MemoryItemStatus.superseded, subject_scope="primary_user")

    assert is_ledger_row_admissible(closed, uid="u1", surface=LedgerSearchSurface.history, kinds={"fact"})
    assert is_ledger_row_admissible(legacy, uid="u1", surface=LedgerSearchSurface.history, kinds={"fact"})
    assert not is_ledger_row_admissible(active, uid="u1", surface=LedgerSearchSurface.history, kinds={"fact"})
    assert not is_ledger_row_admissible(document, uid="u1", surface=LedgerSearchSurface.history, kinds={"fact"})


def test_history_rejected_rows_are_audit_only():
    rejected = _row(status=MemoryItemStatus.superseded, promotion={"user_review": False})
    assert not is_ledger_row_admissible(rejected, uid="u1", surface=LedgerSearchSurface.history)
    assert is_ledger_row_admissible(
        rejected,
        uid="u1",
        surface=LedgerSearchSurface.history,
        include_rejected=True,
    )


def test_index_metadata_versions_and_labels_open_vs_closed_rows():
    open_metadata = build_ledger_index_metadata(_row(kind=MemoryKind.fact, slot=None))
    closed_metadata = build_ledger_index_metadata(_row(status=MemoryItemStatus.superseded))

    assert open_metadata == {
        "ledger_index_version": LEDGER_INDEX_VERSION,
        "ledger_schema_version": "knowledge_ledger.v1",
        "ledger_kind": "fact",
        "ledger_row_state": "open",
        "ledger_has_slot": False,
        "ledger_subject_scope": "primary_user",
    }
    assert closed_metadata["ledger_row_state"] == "closed"
    assert ledger_row_index_state(_row(ledger_schema_version=None)) is LedgerRowIndexState.not_ledger


def test_vector_filter_requires_versioned_open_ledger_metadata():
    vector_filter = build_ledger_memory_vector_filter("u1", {"document", "fact"})
    clauses = vector_filter["$and"]
    assert {"uid": {"$eq": "u1"}} in clauses
    assert {"ledger_index_version": {"$eq": LEDGER_INDEX_VERSION}} in clauses
    assert {"ledger_schema_version": {"$eq": "knowledge_ledger.v1"}} in clauses
    assert {"ledger_row_state": {"$eq": "open"}} in clauses
    assert {"ledger_kind": {"$in": ["document", "fact"]}} in clauses


def test_kind_validation_fails_closed_for_unknown_kinds():
    assert validate_ledger_kinds(["fact", "trigger"]) == frozenset({"fact", "trigger"})
    with pytest.raises(ValueError, match="only fact, document, or trigger"):
        validate_ledger_kinds(["screen"])


def test_bounded_authoritative_hydration_reads_only_requested_ids_and_checks_owner():
    class Snapshot:
        def __init__(self, document_id, payload):
            self.id = document_id
            self.exists = payload is not None
            self._payload = payload

        def to_dict(self):
            return self._payload

    class Ref:
        def __init__(self, db, path):
            self.db = db
            self.path = path

    class Db:
        def __init__(self):
            self.payloads = {
                "candidate": _canonical_item_payload("candidate"),
                "lineage": _canonical_item_payload("lineage", uid="u2"),
                "unrelated": _canonical_item_payload("unrelated"),
            }
            self.requested_paths = []

        def document(self, path):
            self.requested_paths.append(path)
            return Ref(self, path)

        def get_all(self, refs):
            return [
                Snapshot(ref.path.rsplit("/", 1)[-1], self.payloads.get(ref.path.rsplit("/", 1)[-1])) for ref in refs
            ]

    db = Db()
    items = fetch_authoritative_product_memory_items_by_ids(
        "u1",
        ["candidate", "lineage"],
        db_client=db,
    )

    assert db.requested_paths == ["users/u1/memory_items/candidate", "users/u1/memory_items/lineage"]
    assert [item.memory_id for item in items] == ["candidate"]


def test_keyword_search_requires_versioned_open_ledger_filter_and_bound(monkeypatch):
    fields = [
        {"name": name}
        for name in (
            "memory_id",
            "userId",
            "content",
            "category",
            "layer",
            "status",
            "schema_version",
            "entity_terms",
            "predicate",
            "created_at",
            "ledger_index_version",
            "ledger_schema_version",
            "ledger_kind",
            "ledger_row_state",
            "ledger_has_slot",
            "ledger_subject_scope",
        )
    ]
    documents = MagicMock()
    documents.search.return_value = {"hits": [{"document": {"memory_id": "mem-open"}}]}
    collection = MagicMock()
    collection.retrieve.return_value = {"fields": fields}
    collection.documents = documents
    client = MagicMock()
    client.collections.__getitem__.return_value = collection
    monkeypatch.setattr("utils.memory.atom_keyword_index._typesense_client", lambda: client)
    monkeypatch.setattr("utils.memory.atom_keyword_index.user_allows_atom_keyword_index", lambda *args, **kwargs: True)

    assert keyword_search_ledger_memory_ids("u1", "release", kinds={"fact", "trigger"}, limit=10_000) == ["mem-open"]
    params = documents.search.call_args.args[0]
    assert params["per_page"] == 60
    assert "ledger_index_version:=1" in params["filter_by"]
    assert "ledger_row_state:=`open`" in params["filter_by"]
    assert "ledger_kind:=[`fact`,`trigger`]" in params["filter_by"]


def test_keyword_search_returns_no_rows_when_ledger_schema_is_not_adopted(monkeypatch):
    client = MagicMock()
    collection = MagicMock()
    collection.retrieve.return_value = {"fields": [{"name": "userId"}]}
    client.collections.__getitem__.return_value = collection
    monkeypatch.setattr("utils.memory.atom_keyword_index._typesense_client", lambda: client)
    monkeypatch.setattr("utils.memory.atom_keyword_index.user_allows_atom_keyword_index", lambda *args, **kwargs: True)

    assert keyword_search_ledger_memory_ids("u1", "release") == []


def test_qa_ledger_search_requires_live_typesense_readiness_epoch(monkeypatch):
    marker = {
        "id": TYPESENSE_PROJECTION_READINESS_DOCUMENT_ID,
        "userId": "u1",
        "readiness_schema_version": TYPESENSE_PROJECTION_READINESS_SCHEMA_VERSION,
        "projection_epoch": "sha:run-1",
        "source_sha": "a" * 40,
        "projection_count": 1,
    }
    document = MagicMock()
    document.retrieve.return_value = marker
    documents = MagicMock()
    documents.__getitem__.return_value = document
    collection = MagicMock(documents=documents)
    client = MagicMock()
    client.collections.__getitem__.return_value = collection
    monkeypatch.setenv("MEMORY_TYPESENSE_READINESS_REQUIRED", "true")
    monkeypatch.setenv("MEMORY_TYPESENSE_READINESS_COLLECTION", TYPESENSE_PROJECTION_READINESS_COLLECTION)
    monkeypatch.setenv("MEMORY_TYPESENSE_READINESS_SOURCE_SHA", "a" * 40)
    monkeypatch.setattr("utils.memory.atom_keyword_index._typesense_client", lambda: client)

    require_typesense_projection_ready("u1")

    marker["projection_epoch"] = ""
    with pytest.raises(TypesenseProjectionNotReady, match="no epoch"):
        require_typesense_projection_ready("u1")


def test_normal_ledger_search_keeps_readiness_gate_disabled(monkeypatch):
    monkeypatch.delenv("MEMORY_TYPESENSE_READINESS_REQUIRED", raising=False)
    monkeypatch.delenv("MEMORY_TYPESENSE_READINESS_COLLECTION", raising=False)
    monkeypatch.delenv("MEMORY_TYPESENSE_READINESS_SOURCE_SHA", raising=False)
    require_typesense_projection_ready("u1")

"""External creates are deduped by text; a row that no longer holds the text frees it (#17296).

Content-derived row ids outlive the text: an edited, superseded, or rejected row
keeps its id. A resend of the original text must become a new memory instead of
colliding with that row on every retry.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from database.document_ids import document_id_from_seed
from database.memory_apply_store import EvidenceIdentityConflict
from models.memory_evidence import (
    ArtifactPreservationState,
    MemoryEvidence,
    SourceState,
    SourceStateReason,
)
from models.product_memory import MemoryItemStatus
from tests.unit.fixtures.memory_adapter_fakes import FirestoreFake, memory_item, stored_item
from utils.memory import canonical_memory_adapter as adapter

TEXT = "Prefers window seats"


def _db(**rows):
    return FirestoreFake({f"users/u1/memory_items/{memory_id}": stored_item(row) for memory_id, row in rows.items()})


def _row(memory_id, **overrides):
    return memory_item(memory_id, content=overrides.pop("content", TEXT), quote_text=TEXT, **overrides)


def _external_evidence(evidence_id="ev-ext", **overrides):
    fields = {
        "evidence_id": evidence_id,
        "source_id": "external:mem1",
        "source_type": "api",
        "source_version": "v1",
        "artifact_preservation": ArtifactPreservationState.preserved,
        "source_state": SourceState.active,
    }
    fields.update(overrides)
    return MemoryEvidence(**fields)


def _evidence_db(*items):
    return FirestoreFake(
        {f"users/u1/memory_evidence/{item.evidence_id}": item.model_dump(mode="json") for item in items}
    )


def test_new_text_keeps_its_derived_id():
    assert adapter._available_external_memory_id("u1", "m1", TEXT, db_client=_db()) == "m1"


def test_text_the_user_still_has_reuses_that_row():
    db = _db(m1=_row("m1"))

    assert adapter._available_external_memory_id("u1", "m1", f"  {TEXT} ", db_client=db) == "m1"


def test_edited_superseded_or_rejected_rows_free_the_text_under_one_stable_id():
    occupied = {
        "edited": _row("m1", content="Prefers aisle seats"),
        "superseded": _row("m1", status=MemoryItemStatus.superseded),
        "rejected": _row("m1", promotion={"user_review": False}),
    }
    reissued = {}
    for reason, row in occupied.items():
        db = _db(m1=row)
        first = adapter._available_external_memory_id("u1", "m1", TEXT, db_client=db)
        retry = adapter._available_external_memory_id("u1", "m1", TEXT, db_client=db)
        assert first == retry != "m1", reason
        reissued[reason] = first

    # The reissued id depends only on the occupied identity, so a retry after the
    # new row commits resolves to that row rather than minting another.
    assert len(set(reissued.values())) == 1
    db = _db(m1=occupied["edited"], **{reissued["edited"]: _row(reissued["edited"])})
    assert adapter._available_external_memory_id("u1", "m1", TEXT, db_client=db) == reissued["edited"]


def test_reissue_skips_every_occupied_candidate():
    first = adapter._available_external_memory_id(
        "u1", "m1", TEXT, db_client=_db(m1=_row("m1", content="Prefers aisle seats"))
    )
    db = _db(
        m1=_row("m1", content="Prefers aisle seats"),
        **{first: _row(first, content="Prefers the front row")},
    )

    second = adapter._available_external_memory_id("u1", "m1", TEXT, db_client=db)

    assert second not in {"m1", first}


def test_active_evidence_with_identical_source_is_reused():
    item = _external_evidence(client_device_id="web_11111111")
    db = _evidence_db(item.model_copy(update={"captured_at": datetime(2026, 9, 23, tzinfo=timezone.utc)}))

    result = adapter._reissued_external_evidence("u1", [item], db_client=db)

    assert result[0].evidence_id == item.evidence_id


def test_active_evidence_with_different_source_identity_reissues_deterministically():
    stored = _external_evidence(client_device_id="web_22222222")
    proposed = _external_evidence(client_device_id="web_11111111")
    db = _evidence_db(stored)

    first = adapter._reissued_external_evidence("u1", [proposed], db_client=db)
    retry = adapter._reissued_external_evidence("u1", [proposed], db_client=db)

    assert first[0].evidence_id == retry[0].evidence_id != proposed.evidence_id

    committed = first[0]
    db_after_commit = _evidence_db(stored, committed)
    again = adapter._reissued_external_evidence("u1", [proposed], db_client=db_after_commit)
    assert again[0].evidence_id == committed.evidence_id


def test_retired_evidence_reissue_keeps_working():
    retired = _external_evidence(
        source_state=SourceState.tombstoned,
        source_state_reason=SourceStateReason.deleted_by_user,
    )
    proposed = _external_evidence()
    db = _evidence_db(retired)

    result = adapter._reissued_external_evidence("u1", [proposed], db_client=db)

    assert result[0].evidence_id != proposed.evidence_id


def test_conversation_evidence_is_never_reissued():
    conversation = _external_evidence(
        source_id="conv-1",
        source_type="conversation",
        conversation_id="conv-1",
    )
    conflicting = conversation.model_copy(update={"client_device_id": "web_99999999"})
    retired = conversation.model_copy(
        update={
            "source_state": SourceState.tombstoned,
            "source_state_reason": SourceStateReason.deleted_by_user,
        }
    )

    assert (
        adapter._reissued_external_evidence("u1", [conversation], db_client=_evidence_db(conflicting))[0].evidence_id
        == conversation.evidence_id
    )
    assert (
        adapter._reissued_external_evidence("u1", [conversation], db_client=_evidence_db(retired))[0].evidence_id
        == conversation.evidence_id
    )


def test_malformed_stored_evidence_fails_closed():
    db = FirestoreFake({"users/u1/memory_evidence/ev-ext": {"evidence_id": "ev-ext", "source_state": "active"}})

    with pytest.raises(ValidationError):
        adapter._reissued_external_evidence("u1", [_external_evidence()], db_client=db)


def test_live_identical_row_short_circuits_the_write():
    memory_id = document_id_from_seed(TEXT)
    db = _db(**{memory_id: _row(memory_id)})

    result = adapter.write_canonical_external_memory(
        "u1",
        {"id": memory_id, "content": f"  {TEXT} "},
        db_client=db,
    )

    assert result == memory_id


def test_occupied_evidence_keeps_the_content_derived_row_id(monkeypatch):
    memory_id = document_id_from_seed(TEXT)
    proposed = adapter._evidence_items_from_payload({"id": memory_id, "content": TEXT})[0]
    db = _evidence_db(proposed.model_copy(update={"client_device_id": "web_99999999"}))
    calls = []

    def _capture(uid, payload, **kwargs):
        calls.append((payload["id"], [item.evidence_id for item in kwargs["evidence_items"]]))
        return payload["id"]

    monkeypatch.setattr(adapter, "write_canonical_extraction_memory", _capture)

    result = adapter.write_canonical_external_memory("u1", {"id": memory_id, "content": TEXT}, db_client=db)

    assert result == memory_id
    assert len(calls) == 1
    assert calls[0][0] == memory_id
    assert calls[0][1] != [proposed.evidence_id]


def test_conflict_recovery_returns_a_concurrently_committed_row(monkeypatch):
    memory_id = document_id_from_seed(TEXT)
    db = _db()
    calls = []

    def _concurrently_committed(*args, **kwargs):
        calls.append(kwargs)
        db.docs[f"users/u1/memory_items/{memory_id}"] = stored_item(_row(memory_id))
        raise EvidenceIdentityConflict("proposed evidence conflicts with existing evidence identity")

    monkeypatch.setattr(adapter, "write_canonical_extraction_memory", _concurrently_committed)

    result = adapter.write_canonical_external_memory("u1", {"id": memory_id, "content": TEXT}, db_client=db)

    assert result == memory_id
    assert len(calls) == 1


def test_concurrent_distinct_device_resend_converges_to_one_row(monkeypatch):
    memory_id = document_id_from_seed(TEXT)
    proposed = adapter._evidence_items_from_payload({"id": memory_id, "content": TEXT})[0]
    db = _evidence_db(proposed.model_copy(update={"client_device_id": "web_99999999"}))
    calls = []

    def _concurrently_committed(uid, payload, **kwargs):
        calls.append(payload["id"])
        db.docs[f"users/u1/memory_items/{memory_id}"] = stored_item(_row(memory_id))
        raise EvidenceIdentityConflict("proposed evidence conflicts with existing evidence identity")

    monkeypatch.setattr(adapter, "write_canonical_extraction_memory", _concurrently_committed)

    result = adapter.write_canonical_external_memory("u1", {"id": memory_id, "content": TEXT}, db_client=db)

    assert result == memory_id
    assert calls == [memory_id]


def test_persistent_conflict_stays_bounded_and_fails_closed(monkeypatch):
    memory_id = document_id_from_seed(TEXT)
    calls = []

    def _always_conflict(*args, **kwargs):
        calls.append(kwargs)
        raise EvidenceIdentityConflict("proposed evidence conflicts with existing evidence identity")

    monkeypatch.setattr(adapter, "write_canonical_extraction_memory", _always_conflict)

    with pytest.raises(EvidenceIdentityConflict):
        adapter.write_canonical_external_memory("u1", {"id": memory_id, "content": TEXT}, db_client=_db())

    assert len(calls) == adapter._EXTERNAL_WRITE_CONFLICT_ATTEMPTS


def test_conflict_on_a_caller_supplied_id_fails_closed(monkeypatch):
    calls = []

    def _always_conflict(*args, **kwargs):
        calls.append(kwargs)
        raise EvidenceIdentityConflict("proposed evidence conflicts with existing evidence identity")

    monkeypatch.setattr(adapter, "write_canonical_extraction_memory", _always_conflict)

    with pytest.raises(EvidenceIdentityConflict):
        adapter.write_canonical_external_memory("u1", {"id": "caller-supplied-id", "content": TEXT}, db_client=_db())

    assert len(calls) == 1


def test_conversation_conflict_fails_closed(monkeypatch):
    memory_id = document_id_from_seed(TEXT)
    calls = []

    def _always_conflict(*args, **kwargs):
        calls.append(kwargs)
        raise EvidenceIdentityConflict("proposed evidence conflicts with existing evidence identity")

    monkeypatch.setattr(adapter, "write_canonical_extraction_memory", _always_conflict)

    with pytest.raises(EvidenceIdentityConflict):
        adapter.write_canonical_external_memory(
            "u1",
            {"id": memory_id, "content": TEXT, "conversation_id": "conv-1"},
            db_client=_db(),
        )

    assert len(calls) == 1

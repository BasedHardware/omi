from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.belief_evidence import EvidenceEventJudgment, EvidenceEventKind, _default_applier
from tests.unit.fixtures.canonical_memory_fakes import _FakeDb, _fresh_short_term_item

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def _item(memory_id: str, source_id: str, *, item_revision: int = 1) -> MemoryItem:
    return MemoryItem(
        memory_id=memory_id,
        uid="uid-1",
        version=1,
        tier=MemoryLayer.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="Lives in NYC",
        evidence=[
            MemoryEvidence(
                evidence_id=f"ev-{source_id}",
                source_type="conversation",
                source_id=source_id,
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
                source_state=SourceState.active,
                source_signal="transcription",
                attribution="user_spoken",
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(days=2),
        item_revision=item_revision,
    )


def _canonical_pair(uid: str) -> tuple[MemoryItem, MemoryItem, _FakeDb]:
    existing = _fresh_short_term_item(
        uid=uid, memory_id="mem-old", conversation_id="conv-old", content="Lives in NYC"
    ).model_copy(
        update={
            "evidence": [
                _fresh_short_term_item(uid=uid, memory_id="mem-old", conversation_id="conv-old", content="Lives in NYC")
                .evidence[0]
                .model_copy(update={"source_signal": "transcription", "attribution": "user_spoken"})
            ]
        }
    )
    new = _fresh_short_term_item(
        uid=uid, memory_id="mem-new", conversation_id="conv-new", content="Lives in NYC"
    ).model_copy(
        update={
            "evidence": [
                _fresh_short_term_item(uid=uid, memory_id="mem-new", conversation_id="conv-new", content="Lives in NYC")
                .evidence[0]
                .model_copy(
                    update={"evidence_id": "ev-new", "source_signal": "transcription", "attribution": "user_spoken"}
                )
            ]
        }
    )
    docs = {
        f"users/{uid}/memory_state/apply_control": MemoryControlState(
            uid=uid,
            head_commit_id="head0",
            account_generation=1,
            source_generation=1,
        ).model_dump(mode="json"),
        f"users/{uid}/memory_items/{existing.memory_id}": existing.model_dump(mode="json"),
        f"users/{uid}/memory_items/{new.memory_id}": new.model_dump(mode="json"),
    }
    for item in (existing, new):
        for evidence in item.evidence:
            docs[f"users/{uid}/memory_evidence/{evidence.evidence_id}"] = evidence.model_dump(mode="json")
    return existing, new, _FakeDb(docs)


def test_default_applier_fences_judgment_against_a_newer_target_revision(monkeypatch):
    existing = _item("mem-old", "conv-old")
    new = _item("mem-new", "conv-new")
    seen: dict[str, object] = {}

    def fake_apply(uid, memory_id, *, build_patch, **kwargs):
        seen.update({"uid": uid, "memory_id": memory_id, **kwargs})
        with pytest.raises(ValueError, match="target changed after judgment"):
            build_patch(existing.model_copy(update={"item_revision": 2}), NOW)
        return existing, existing

    monkeypatch.setattr("utils.memory.canonical_memory_adapter.apply_canonical_user_mutation", fake_apply)

    _default_applier(
        "uid-1",
        existing,
        new,
        EvidenceEventJudgment(event=EvidenceEventKind.restated, target_memory_id="mem-old"),
        SimpleNamespace(),
    )

    assert seen["uid"] == "uid-1"
    assert seen["memory_id"] == "mem-old"
    assert seen["required_source_item"] is new
    assert seen["automated"] is True


def test_default_applier_replay_with_already_merged_evidence_is_a_noop(monkeypatch):
    existing = _item("mem-old", "conv-old")
    new = _item("mem-new", "conv-new")
    current = existing.model_copy(update={"item_revision": 2, "evidence": [*existing.evidence, *new.evidence]})
    called = []

    def fake_apply(uid, memory_id, *, build_patch, **kwargs):
        called.append((uid, memory_id, kwargs))
        assert build_patch(current, NOW) is None
        return current, current

    monkeypatch.setattr("utils.memory.canonical_memory_adapter.apply_canonical_user_mutation", fake_apply)

    _default_applier(
        "uid-1",
        existing,
        new,
        EvidenceEventJudgment(event=EvidenceEventKind.restated, target_memory_id="mem-old"),
        SimpleNamespace(),
    )

    assert len(called) == 1


def test_default_applier_rejects_a_deleted_source_without_mutating_target(monkeypatch):
    existing = _item("mem-old", "conv-old")
    new = _item(
        "mem-new",
        "conv-new",
    ).model_copy(
        update={
            "source_state": SourceState.tombstoned,
            "evidence": [
                _item("mem-new", "conv-new")
                .evidence[0]
                .model_copy(update={"source_state": SourceState.tombstoned, "source_state_reason": "deleted_by_user"})
            ],
        }
    )
    called = []

    def fake_apply(uid, memory_id, *, build_patch, **kwargs):
        called.append(build_patch(existing, NOW))
        return existing, existing

    monkeypatch.setattr("utils.memory.canonical_memory_adapter.apply_canonical_user_mutation", fake_apply)

    _default_applier(
        "uid-1",
        existing,
        new,
        EvidenceEventJudgment(event=EvidenceEventKind.restated, target_memory_id="mem-old"),
        SimpleNamespace(),
    )

    assert called == [None]


def test_default_applier_commits_a_restatement_through_the_canonical_store(monkeypatch):
    """Exercise the real operation journal, source fence, and evidence merge."""
    monkeypatch.setenv("MEMORY_MODE", "write")
    monkeypatch.delenv("MEMORY_ENABLED", raising=False)
    uid = "uid-belief-e2e"
    existing = _fresh_short_term_item(
        uid=uid, memory_id="mem-old", conversation_id="conv-old", content="Lives in NYC"
    ).model_copy(
        update={
            "evidence": [
                _fresh_short_term_item(uid=uid, memory_id="mem-old", conversation_id="conv-old", content="Lives in NYC")
                .evidence[0]
                .model_copy(update={"source_signal": "transcription", "attribution": "user_spoken"})
            ]
        }
    )
    new = _fresh_short_term_item(
        uid=uid, memory_id="mem-new", conversation_id="conv-new", content="Lives in NYC"
    ).model_copy(
        update={
            "evidence": [
                _fresh_short_term_item(uid=uid, memory_id="mem-new", conversation_id="conv-new", content="Lives in NYC")
                .evidence[0]
                .model_copy(
                    update={"evidence_id": "ev-new", "source_signal": "transcription", "attribution": "user_spoken"}
                )
            ]
        }
    )
    control_path = f"users/{uid}/memory_state/apply_control"
    docs = {
        control_path: MemoryControlState(
            uid=uid,
            head_commit_id="head0",
            account_generation=1,
            source_generation=1,
        ).model_dump(mode="json"),
        f"users/{uid}/memory_items/{existing.memory_id}": existing.model_dump(mode="json"),
        f"users/{uid}/memory_items/{new.memory_id}": new.model_dump(mode="json"),
    }
    for item in (existing, new):
        for evidence in item.evidence:
            docs[f"users/{uid}/memory_evidence/{evidence.evidence_id}"] = evidence.model_dump(mode="json")
    db = _FakeDb(docs)

    updated = _default_applier(
        uid,
        existing,
        new,
        EvidenceEventJudgment(event=EvidenceEventKind.restated, target_memory_id=existing.memory_id),
        db,
    )

    assert updated.item_revision == existing.item_revision + 1
    assert updated.corroboration_count == 1
    assert {evidence.evidence_id for evidence in updated.evidence} == {"ev1", "ev-new"}
    operation_docs = [path for path in db.docs if path.startswith(f"users/{uid}/memory_operations/")]
    assert len(operation_docs) == 1


def test_default_applier_rejects_a_source_revision_that_changed_after_judgment(monkeypatch):
    """The real transaction must reject a delayed judgment before target writes."""
    monkeypatch.setenv("MEMORY_MODE", "write")
    monkeypatch.delenv("MEMORY_ENABLED", raising=False)
    uid = "uid-belief-source-race"
    existing = _fresh_short_term_item(
        uid=uid, memory_id="mem-old", conversation_id="conv-old", content="Lives in NYC"
    ).model_copy(
        update={
            "evidence": [
                _fresh_short_term_item(uid=uid, memory_id="mem-old", conversation_id="conv-old", content="Lives in NYC")
                .evidence[0]
                .model_copy(update={"source_signal": "transcription", "attribution": "user_spoken"})
            ]
        }
    )
    judged_source = _fresh_short_term_item(
        uid=uid, memory_id="mem-new", conversation_id="conv-new", content="Lives in NYC"
    ).model_copy(
        update={
            "evidence": [
                _fresh_short_term_item(uid=uid, memory_id="mem-new", conversation_id="conv-new", content="Lives in NYC")
                .evidence[0]
                .model_copy(
                    update={"evidence_id": "ev-new", "source_signal": "transcription", "attribution": "user_spoken"}
                )
            ]
        }
    )
    changed_source = judged_source.model_copy(update={"item_revision": judged_source.item_revision + 1})
    docs = {
        f"users/{uid}/memory_state/apply_control": MemoryControlState(
            uid=uid,
            head_commit_id="head0",
            account_generation=1,
            source_generation=1,
        ).model_dump(mode="json"),
        f"users/{uid}/memory_items/{existing.memory_id}": existing.model_dump(mode="json"),
        f"users/{uid}/memory_items/{changed_source.memory_id}": changed_source.model_dump(mode="json"),
    }
    for item in (existing, changed_source):
        for evidence in item.evidence:
            docs[f"users/{uid}/memory_evidence/{evidence.evidence_id}"] = evidence.model_dump(mode="json")
    db = _FakeDb(docs)

    with pytest.raises(RuntimeError, match="source_not_active"):
        _default_applier(
            uid,
            existing,
            judged_source,
            EvidenceEventJudgment(event=EvidenceEventKind.restated, target_memory_id=existing.memory_id),
            db,
        )

    stored_target = MemoryItem(**db.docs[f"users/{uid}/memory_items/{existing.memory_id}"])
    assert stored_target.corroboration_count == existing.corroboration_count
    assert stored_target.item_revision == existing.item_revision


def test_default_applier_real_retry_does_not_increment_corroboration_twice(monkeypatch):
    monkeypatch.setenv("MEMORY_MODE", "write")
    monkeypatch.delenv("MEMORY_ENABLED", raising=False)
    uid = "uid-belief-real-retry"
    existing, new, db = _canonical_pair(uid)
    judgment = EvidenceEventJudgment(event=EvidenceEventKind.restated, target_memory_id=existing.memory_id)

    first = _default_applier(uid, existing, new, judgment, db)
    second = _default_applier(uid, existing, new, judgment, db)

    assert first.corroboration_count == 1
    assert second.corroboration_count == 1
    assert second.item_revision == first.item_revision
    operation_docs = [path for path in db.docs if path.startswith(f"users/{uid}/memory_operations/")]
    assert len(operation_docs) == 1


def test_default_applier_real_contradiction_supersedes_target(monkeypatch):
    monkeypatch.setenv("MEMORY_MODE", "write")
    monkeypatch.delenv("MEMORY_ENABLED", raising=False)
    uid = "uid-belief-real-contradiction"
    existing, new, db = _canonical_pair(uid)

    updated = _default_applier(
        uid,
        existing,
        new,
        EvidenceEventJudgment(event=EvidenceEventKind.contradicted, target_memory_id=existing.memory_id),
        db,
    )

    assert updated.status == MemoryItemStatus.superseded
    assert updated.confidence == 0.0
    assert updated.superseded_by == new.memory_id
    assert updated.item_revision == existing.item_revision + 1


def test_default_applier_real_resolution_sets_valid_to_without_archiving_row(monkeypatch):
    monkeypatch.setenv("MEMORY_MODE", "write")
    monkeypatch.delenv("MEMORY_ENABLED", raising=False)
    uid = "uid-belief-real-resolution"
    existing, new, db = _canonical_pair(uid)

    updated = _default_applier(
        uid,
        existing,
        new,
        EvidenceEventJudgment(event=EvidenceEventKind.resolved, target_memory_id=existing.memory_id),
        db,
    )

    assert updated.status == MemoryItemStatus.active
    assert updated.valid_to == max(existing.captured_at, new.captured_at)
    assert updated.item_revision == existing.item_revision + 1

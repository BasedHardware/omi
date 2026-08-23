from datetime import datetime, timedelta, timezone

import pytest

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
    ProcessingState,
)
from utils.retrieval.tools import entity_timeline_tools as timeline_tools

NOW = datetime(2026, 8, 23, 14, 30, tzinfo=timezone.utc)


def _evidence(memory_id: str, *, source_id: str | None = None, evidence_id: str | None = None) -> MemoryEvidence:
    source = source_id or f"conversation-{memory_id}"
    return MemoryEvidence(
        evidence_id=evidence_id or f"evidence-{memory_id}",
        source_type="conversation",
        source_id=source,
        conversation_id=source,
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _item(
    memory_id: str,
    *,
    occurred_at: datetime = NOW,
    entity: str = "person:alice",
    kind: MemoryKind = MemoryKind.fact,
    status: MemoryItemStatus = MemoryItemStatus.active,
    source_state: SourceState = SourceState.active,
    content: str = "Alice is reviewing the release plan",
    evidence: list[MemoryEvidence] | None = None,
    **updates,
) -> MemoryItem:
    data = {
        "memory_id": memory_id,
        "uid": "u1",
        "version": 1,
        "tier": MemoryLayer.long_term,
        "status": status,
        "processing_state": ProcessingState.processed,
        "content": content,
        "evidence": evidence if evidence is not None else [_evidence(memory_id)],
        "source_state": source_state,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": True,
        "captured_at": occurred_at,
        "updated_at": occurred_at + timedelta(minutes=1),
        "ledger_commit_id": f"commit-{memory_id}",
        "ledger_sequence": 1,
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": kind,
        "subject_scope": MemorySubjectScope.third_party,
        "subject_entity_id": entity,
        "valid_from": occurred_at,
        "intent_backed": True,
        "write_reason": LedgerWriteReason.agent_reusable_conclusion,
    }
    data.update(updates)
    return MemoryItem(**data)


def test_entity_reference_is_canonical_and_unsupported_names_fail_closed():
    assert timeline_tools.parse_entity_reference("ME").key == "user"
    assert timeline_tools.parse_entity_reference("Person:Alice").key == "person:alice"

    for raw in ("Alice", "person", "email:alice", "person:Alice Smith", "person:", "user:someone-else"):
        with pytest.raises(ValueError):
            timeline_tools.parse_entity_reference(raw)


def test_timeline_filters_projects_and_orders_deterministically():
    older = _item("mem-older", occurred_at=NOW - timedelta(days=2), content="Alice joined the team\nprivate body")
    newer = _item("mem-newer", occurred_at=NOW - timedelta(days=1), content="Alice owns the release review")
    same_time = _item("mem-same", occurred_at=NOW - timedelta(days=1), content="Alice is on call")
    unrelated = _item("mem-other", entity="person:bob", content="Bob owns the release review")
    trigger = _item("mem-trigger", kind=MemoryKind.trigger, trigger_condition={"keywords": ["release"]})
    document = _item("mem-document", kind=MemoryKind.document, body="secret full profile/body")
    hidden = _item("mem-hidden", status=MemoryItemStatus.hidden)
    source_deleted = _item("mem-source-deleted", source_state=SourceState.tombstoned)

    result = timeline_tools.build_entity_timeline(
        [newer, unrelated, hidden, same_time, trigger, source_deleted, document, older],
        "person:alice",
    )

    assert [entry.memory_id for entry in result.entries] == ["mem-older", "mem-newer", "mem-same"]
    assert [entry.occurred_at for entry in result.entries] == sorted(entry.occurred_at for entry in result.entries)
    assert result.entries[0].content == "Alice joined the team private body"
    assert result.entries[0].evidence_refs == ("memory:mem-older:evidence:evidence-mem-older",)
    assert result.entries[0].source_refs == ("conversation:conversation-mem-older",)

    rendered = timeline_tools.format_entity_timeline(result)
    assert "secret full profile/body" not in rendered
    assert "private body" in rendered
    assert "conversation:conversation-mem-older" in rendered
    assert "\nprivate body" not in rendered


def test_timeline_limit_date_range_and_scan_count_are_explicit():
    items = [_item(f"mem-{index:02d}", occurred_at=NOW + timedelta(days=index)) for index in range(3)]
    result = timeline_tools.build_entity_timeline(
        items,
        "person:alice",
        limit=2,
        start=NOW + timedelta(days=1),
        end=NOW + timedelta(days=2),
        scanned_count=99,
    )

    assert [entry.memory_id for entry in result.entries] == ["mem-01", "mem-02"]
    assert result.truncated is False
    assert result.scanned_count == 99

    limited = timeline_tools.build_entity_timeline(items, "person:alice", limit=1)
    assert [entry.memory_id for entry in limited.entries] == ["mem-02"]
    assert limited.truncated is True

    with pytest.raises(ValueError, match="between"):
        timeline_tools.build_entity_timeline(items, "person:alice", limit=0)
    with pytest.raises(ValueError, match="before"):
        timeline_tools.build_entity_timeline(items, "person:alice", start=NOW, end=NOW - timedelta(seconds=1))


def test_tool_is_read_only_bounded_and_double_run_stable(monkeypatch):
    items = [_item("mem-1"), _item("mem-2", occurred_at=NOW + timedelta(days=1))]
    seen = []

    def reader(uid: str, *, db_client):
        seen.append((uid, db_client))
        yield from items

    monkeypatch.setattr(timeline_tools, "_iter_authoritative_items", reader)
    first = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "limit": 2},
        config={"configurable": {"user_id": "u1"}},
    )
    second = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "limit": 2},
        config={"configurable": {"user_id": "u1"}},
    )

    assert first == second
    assert "Entity timeline: person:alice" in first
    assert [uid for uid, _ in seen] == ["u1", "u1"]
    assert "body" not in first
    assert "arguments" not in first


def test_tool_rejects_unsupported_entity_before_reader(monkeypatch):
    calls = []
    monkeypatch.setattr(timeline_tools, "_iter_authoritative_items", lambda *args, **kwargs: calls.append(args))

    result = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "Alice", "limit": 20},
        config={"configurable": {"user_id": "u1"}},
    )

    assert result.startswith("Error: unsupported or invalid entity timeline request:")
    assert calls == []


def test_tool_scan_is_hard_bounded(monkeypatch):
    consumed = []

    def reader(uid: str, *, db_client):
        for index in range(timeline_tools.MAX_TIMELINE_SCAN + 50):
            consumed.append(index)
            yield _item(f"mem-{index:03d}")

    monkeypatch.setattr(timeline_tools, "_iter_authoritative_items", reader)
    result = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "limit": 1},
        config={"configurable": {"user_id": "u1"}},
    )

    assert len(consumed) == timeline_tools.MAX_TIMELINE_SCAN + 1
    assert "Timeline output is bounded" in result

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
from utils.memory.product_memory_read_service import iter_authoritative_product_memory_items_newest_first
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


class _TimelineSnapshot:
    def __init__(self, document_id: str, payload: dict):
        self.id = document_id
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _OrderedTimelineQuery:
    def __init__(self, db_client, *, orderings=(), limit_value=None):
        self._db_client = db_client
        self._orderings = orderings
        self._limit_value = limit_value

    def order_by(self, field_path, direction=None):
        return _OrderedTimelineQuery(
            self._db_client,
            orderings=(*self._orderings, (field_path, direction)),
            limit_value=self._limit_value,
        )

    def limit(self, value):
        self._db_client.limits.append(value)
        return _OrderedTimelineQuery(self._db_client, orderings=self._orderings, limit_value=value)

    def stream(self):
        self._db_client.orderings.append(self._orderings)
        rows = list(self._db_client.rows)
        for field_path, direction in reversed(self._orderings):
            reverse = direction == "DESCENDING"
            if field_path == "__name__":
                key = lambda snapshot: snapshot.id
            else:
                key = lambda snapshot, field_path=field_path: snapshot.to_dict()[field_path]
            rows.sort(key=key, reverse=reverse)
        return rows[: self._limit_value]


class _OrderedTimelineFirestore:
    def __init__(self, rows):
        self.rows = rows
        self.orderings = []
        self.limits = []

    def collection(self, path):
        assert path == "users/u1/memory_items"
        return _OrderedTimelineQuery(self)


def _ordered_rows(items):
    return [_TimelineSnapshot(item.memory_id, item.model_dump(mode="python")) for item in items]


def test_ordered_authoritative_iterator_uses_newest_first_updated_at_and_id_tiebreaker():
    tie_later_id = _item("memory-z", occurred_at=NOW - timedelta(minutes=1), updated_at=NOW)
    tie_earlier_id = _item("memory-a", occurred_at=NOW - timedelta(minutes=1), updated_at=NOW)
    older = _item(
        "memory-older",
        occurred_at=NOW - timedelta(minutes=2),
        updated_at=NOW - timedelta(minutes=1),
    )
    db_client = _OrderedTimelineFirestore(_ordered_rows([older, tie_later_id, tie_earlier_id]))

    result = list(
        iter_authoritative_product_memory_items_newest_first(
            "u1",
            db_client=db_client,
            limit=3,
        )
    )

    assert [item.memory_id for item in result] == ["memory-a", "memory-z", "memory-older"]
    assert db_client.orderings == [(('updated_at', "DESCENDING"), ("__name__", None))]
    assert db_client.limits == [3]


def test_ordered_authoritative_iterator_has_deterministic_membership_at_500_row_cap():
    items = [
        _item(
            f"memory-{index:03d}",
            occurred_at=NOW - timedelta(minutes=index // 2 + 1),
            updated_at=NOW - timedelta(minutes=index // 2),
        )
        for index in range(505)
    ]
    expected = sorted(items, key=lambda item: (-item.updated_at.timestamp(), item.memory_id))[:500]

    first_store = _OrderedTimelineFirestore(_ordered_rows(items))
    second_store = _OrderedTimelineFirestore(_ordered_rows(list(reversed(items))))
    first_result = list(
        iter_authoritative_product_memory_items_newest_first(
            "u1",
            db_client=first_store,
            limit=500,
        )
    )
    second_result = list(
        iter_authoritative_product_memory_items_newest_first(
            "u1",
            db_client=second_store,
            limit=500,
        )
    )

    expected_ids = [item.memory_id for item in expected]
    assert len(first_result) == len(second_result) == 500
    assert [item.memory_id for item in first_result] == expected_ids
    assert [item.memory_id for item in second_result] == expected_ids
    assert first_store.limits == second_store.limits == [500]


def test_ordered_authoritative_iterator_is_explicitly_non_exhaustive_at_scan_boundary():
    items = [
        _item(
            f"memory-{index:03d}",
            occurred_at=NOW - timedelta(minutes=index + 1),
            updated_at=NOW - timedelta(minutes=index),
        )
        for index in range(501)
    ]
    db_client = _OrderedTimelineFirestore(_ordered_rows(items))

    bounded_page = list(
        iter_authoritative_product_memory_items_newest_first(
            "u1",
            db_client=db_client,
            limit=timeline_tools.MAX_TIMELINE_SCAN,
        )
    )

    assert len(bounded_page) == timeline_tools.MAX_TIMELINE_SCAN
    assert bounded_page[0].memory_id == "memory-000"
    assert bounded_page[-1].memory_id == "memory-499"
    assert "memory-500" not in {item.memory_id for item in bounded_page}
    # The iterator returns only the requested prefix; callers must mark the
    # result non-exhaustive when they probe one extra row.
    probe = list(
        iter_authoritative_product_memory_items_newest_first(
            "u1",
            db_client=db_client,
            limit=timeline_tools.MAX_TIMELINE_SCAN + 1,
        )
    )
    assert len(probe) == timeline_tools.MAX_TIMELINE_SCAN + 1
    assert probe[-1].memory_id == "memory-500"


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
    import database._client as database_client

    items = [_item("mem-1"), _item("mem-2", occurred_at=NOW + timedelta(days=1))]
    seen = []
    firestore_client = object()
    monkeypatch.setattr(database_client, "get_firestore_client", lambda: firestore_client)

    def reader(uid: str, *, db_client, limit: int):
        seen.append((uid, db_client, limit))
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
    assert [(uid, limit) for uid, _, limit in seen] == [("u1", timeline_tools.MAX_TIMELINE_SCAN + 1)] * 2
    assert [client for _, client, _ in seen] == [firestore_client, firestore_client]
    assert "body" not in first
    assert "arguments" not in first


def test_tool_applies_chat_visibility_before_projecting_timeline(monkeypatch):
    import database._client as database_client

    monkeypatch.setattr(database_client, "get_firestore_client", lambda: object())
    allowed = _item("mem-allowed")
    restricted = _item("mem-restricted", sensitivity_labels=["credential"])
    blocked = _item(
        "mem-blocked",
        tier=MemoryLayer.short_term,
        processing_state=ProcessingState.blocked,
        expires_at=NOW + timedelta(days=1),
    )
    locked = _item("mem-locked", promotion={"is_locked": True})
    rejected = _item("mem-rejected", promotion={"user_review": False})
    archived = _item("mem-archived", tier=MemoryLayer.archive)
    superseded = _item("mem-superseded", status=MemoryItemStatus.superseded)

    monkeypatch.setattr(
        timeline_tools,
        "_iter_authoritative_items",
        lambda uid, *, db_client, limit: iter([allowed, restricted, blocked, locked, rejected, archived, superseded]),
    )
    result = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "limit": 20},
        config={"configurable": {"user_id": "u1"}},
    )

    assert "mem-allowed" in result
    for memory_id in (
        "mem-restricted",
        "mem-blocked",
        "mem-locked",
        "mem-rejected",
        "mem-archived",
        "mem-superseded",
    ):
        assert memory_id not in result


def test_tool_rejects_unsupported_entity_before_reader(monkeypatch):
    calls = []
    monkeypatch.setattr(timeline_tools, "_iter_authoritative_items", lambda *args, **kwargs: calls.append(args))

    result = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "Alice", "limit": 20},
        config={"configurable": {"user_id": "u1"}},
    )

    assert result.startswith("Error: unsupported or invalid entity timeline request:")
    assert calls == []


def test_tool_fails_closed_when_storage_authority_is_unavailable(monkeypatch):
    import database._client as database_client

    def unavailable_client():
        raise RuntimeError("detail")

    monkeypatch.setattr(database_client, "get_firestore_client", unavailable_client)
    result = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "limit": 20},
        config={"configurable": {"user_id": "u1"}},
    )

    assert result == "Error reading entity timeline: RuntimeError"


def test_tool_scan_is_hard_bounded(monkeypatch):
    import database._client as database_client

    monkeypatch.setattr(database_client, "get_firestore_client", lambda: object())
    consumed = []

    def reader(uid: str, *, db_client, limit: int):
        # Deliberately violate the reader's limit contract: the tool itself
        # must still stop after the 500-row scan plus one truncation sentinel.
        for index in range(limit + 50):
            consumed.append(index)
            yield _item(f"mem-{index:03d}")

    monkeypatch.setattr(timeline_tools, "_iter_authoritative_items", reader)
    result = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "limit": 1},
        config={"configurable": {"user_id": "u1"}},
    )

    assert len(consumed) == timeline_tools.MAX_TIMELINE_SCAN + 1
    assert "Timeline output is bounded" in result

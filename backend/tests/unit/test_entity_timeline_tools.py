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


def test_character_budget_truncation_is_always_disclosed():
    items = [
        _item(
            f"mem-{index:02d}",
            occurred_at=NOW + timedelta(seconds=index),
            content=f"entry-{index} " + ("x" * 700),
        )
        for index in range(40)
    ]

    timeline = timeline_tools.build_entity_timeline(items, "person:alice", limit=40)
    timeline = timeline.model_copy(
        update={
            "truncated_sources": (timeline_tools.TimelineSource.conversations, timeline_tools.TimelineSource.calendar),
            "unavailable_sources": (timeline_tools.TimelineSource.screen,),
            "aliases_resolved": False,
        }
    )
    rendered = timeline_tools.format_entity_timeline(timeline)

    assert len(rendered) <= timeline_tools.MAX_TIMELINE_RESULT_CHARS
    assert "Timeline output is bounded" in rendered
    assert "Source windows were partial" in rendered
    assert "Sources unavailable" in rendered
    assert "No owner-scoped alias record" in rendered
    assert sum(1 for line in rendered.splitlines() if line.startswith("- ")) < len(items)


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


class _AliasSnapshot:
    def __init__(self, document_id, payload, *, exists=True):
        self.id = document_id
        self.exists = exists
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _AliasDocument:
    def __init__(self, path, seen):
        self._path = path
        self._seen = seen

    def collection(self, name):
        return _AliasCollection((*self._path, name), self._seen)

    def get(self):
        self._seen.append(self._path)
        payload = self._seen.payloads.get(self._path)
        return _AliasSnapshot(self._path[-1], payload or {}, exists=payload is not None)


class _AliasCollection:
    def __init__(self, path, seen):
        self._path = path
        self._seen = seen
        self._limit = timeline_tools.MAX_ALIAS_PEOPLE_SCAN + 1

    def document(self, document_id):
        return _AliasDocument((*self._path, document_id), self._seen)

    def limit(self, value):
        self._limit = value
        return self

    def stream(self):
        rows = []
        for path, payload in sorted(self._seen.payloads.items()):
            if path[:-1] == self._path:
                rows.append(_AliasSnapshot(path[-1], payload))
        return iter(rows[: self._limit])


class _AliasReads(list):
    def __init__(self, payloads):
        super().__init__()
        self.payloads = payloads


class _AliasFirestore:
    def __init__(self, payloads):
        self.seen = _AliasReads(payloads)

    def collection(self, name):
        return _AliasCollection((name,), self.seen)


def test_alias_resolution_is_owner_scoped_by_stable_person_id_and_values_stay_match_only():
    store = _AliasFirestore(
        {
            ("users", "u1"): {"name": "Owner"},
            ("users", "u1", "people", "person-123"): {
                "name": "Alice Smith",
                "aliases": ["Alice", "A. Smith"],
                "emails": ["alice@example.com"],
            },
            ("users", "u1", "people", "person-456"): {"name": "Bob"},
        }
    )
    entity = timeline_tools.parse_entity_reference("person:person-123")

    aliases = timeline_tools._resolve_entity_aliases("u1", entity, db_client=store)

    assert aliases.resolved is True
    assert aliases.values == ("a. smith", "alice", "alice smith", "alice@example.com")
    assert store.seen == [("users", "u1", "people", "person-123"), ("users", "u1")]


def test_alias_resolution_suppresses_owner_and_sibling_collisions_without_losing_stable_id():
    store = _AliasFirestore(
        {
            ("users", "u1"): {"name": "Alice"},
            ("users", "u1", "people", "person-123"): {
                "name": "Alice Smith",
                "aliases": ["Alice"],
                "emails": ["alice@example.com"],
            },
            ("users", "u1", "people", "person-456"): {
                "name": "Alice Smith",
                "emails": ["other@example.com"],
            },
        }
    )
    entity = timeline_tools.parse_entity_reference("person:person-123")

    aliases = timeline_tools._resolve_entity_aliases("u1", entity, db_client=store)

    assert aliases.resolved is True
    assert aliases.ambiguous is True
    assert aliases.values == ("alice@example.com",)


def test_alias_resolution_fails_alias_joins_closed_when_people_scan_is_not_exhaustive():
    payloads = {
        ("users", "u1", "people", "person-123"): {"name": "Alice", "email": "alice@example.com"},
        **{
            ("users", "u1", "people", f"sibling-{index:03d}"): {"name": f"Person {index}"}
            for index in range(timeline_tools.MAX_ALIAS_PEOPLE_SCAN + 1)
        },
    }
    aliases = timeline_tools._resolve_entity_aliases(
        "u1",
        timeline_tools.parse_entity_reference("person:person-123"),
        db_client=_AliasFirestore(payloads),
    )

    assert aliases.resolved is True
    assert aliases.ambiguous is True
    assert aliases.values == ()


def test_explicit_history_flag_controls_superseded_and_rejected_rows(monkeypatch):
    import database._client as database_client

    monkeypatch.setattr(database_client, "get_firestore_client", lambda: object())
    monkeypatch.setattr(
        timeline_tools,
        "_resolve_entity_aliases",
        lambda uid, entity, *, db_client: timeline_tools.EntityAliases(entity=entity, resolved=True),
    )
    current = _item("mem-current", content="Alice currently owns release review")
    superseded = _item(
        "mem-history",
        status=MemoryItemStatus.superseded,
        valid_to=NOW + timedelta(hours=1),
        superseded_by="mem-current",
        content="Alice previously owned release review",
    )
    rejected = _item("mem-rejected-audit", promotion={"user_review": False}, content="Rejected claim about Alice")
    monkeypatch.setattr(
        timeline_tools,
        "_iter_authoritative_items",
        lambda uid, *, db_client, limit: iter([current, superseded, rejected]),
    )

    current_only = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "sources": ["ledger"]},
        config={"configurable": {"user_id": "u1"}},
    )
    with_history = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "sources": ["ledger"], "include_history": True},
        config={"configurable": {"user_id": "u1"}},
    )
    audit = timeline_tools.get_entity_timeline_tool.invoke(
        {
            "entity": "person:alice",
            "sources": ["ledger"],
            "include_history": True,
            "include_rejected": True,
        },
        config={"configurable": {"user_id": "u1"}},
    )

    assert "mem-current" in current_only
    assert "mem-history" not in current_only
    assert "mem-rejected-audit" not in current_only
    assert "mem-history" in with_history
    assert "mem-rejected-audit" not in with_history
    assert "mem-rejected-audit" in audit


def test_multi_source_alias_merge_is_deterministic_and_never_returns_transcript_ocr_or_email(monkeypatch):
    import database._client as database_client

    monkeypatch.setattr(database_client, "get_firestore_client", lambda: object())
    monkeypatch.setattr(
        timeline_tools,
        "_resolve_entity_aliases",
        lambda uid, entity, *, db_client: timeline_tools.EntityAliases(
            entity=entity,
            values=("alice smith", "alice@example.com"),
            resolved=True,
        ),
    )
    ledger = _item("mem-ledger", occurred_at=NOW, content="Alice owns the release review")
    monkeypatch.setattr(
        timeline_tools,
        "_iter_authoritative_items",
        lambda uid, *, db_client, limit: iter([ledger]),
    )
    monkeypatch.setattr(
        timeline_tools,
        "list_entity_timeline_conversations",
        lambda *args, **kwargs: [
            {
                "id": "conversation-1",
                "status": "completed",
                "discarded": False,
                "created_at": NOW,
                "structured": {"title": "Release review", "overview": "Reviewed the ship checklist"},
                "transcript_segments": [{"person_id": "alice", "text": "TRANSCRIPT_SECRET_SHOULD_NOT_RENDER"}],
            }
        ],
    )
    monkeypatch.setattr(
        timeline_tools,
        "list_entity_timeline_meetings",
        lambda *args, **kwargs: [
            {
                "id": "meeting-1",
                "start_time": NOW,
                "title": "Calendar release review",
                "participants": [{"email": "alice@example.com"}],
                "notes": "CALENDAR_NOTES_SECRET_SHOULD_NOT_RENDER",
            }
        ],
    )
    monkeypatch.setattr(
        timeline_tools,
        "list_entity_timeline_screen_activity",
        lambda *args, **kwargs: [
            {
                "id": "screen-1",
                "timestamp": NOW,
                "appName": "Slack",
                "windowTitle": "Release thread with Alice Smith alice@example.com",
                "ocrText": "OCR_SECRET_SHOULD_NOT_RENDER alice@example.com",
            }
        ],
    )

    first = timeline_tools.get_entity_timeline_tool.invoke(
        {
            "entity": "person:alice",
            "sources": ["screen", "calendar", "conversations", "ledger"],
            "limit": 10,
        },
        config={"configurable": {"user_id": "u1"}},
    )
    second = timeline_tools.get_entity_timeline_tool.invoke(
        {
            "entity": "person:alice",
            "sources": ["ledger", "conversations", "calendar", "screen"],
            "limit": 10,
        },
        config={"configurable": {"user_id": "u1"}},
    )

    for record_id in ("mem-ledger", "conversation-1", "meeting-1", "screen-1"):
        assert record_id in first
        assert record_id in second
    for secret in (
        "TRANSCRIPT_SECRET_SHOULD_NOT_RENDER",
        "CALENDAR_NOTES_SECRET_SHOULD_NOT_RENDER",
        "OCR_SECRET_SHOULD_NOT_RENDER",
        "alice@example.com",
    ):
        assert secret not in first
        assert secret not in second
    # Source argument order cannot affect the deterministic time/source/id merge.
    assert [line for line in first.splitlines() if line.startswith("- ")] == [
        line for line in second.splitlines() if line.startswith("- ")
    ]


def test_malformed_metadata_and_unicode_emails_never_cross_projection_boundary():
    aliases = timeline_tools.EntityAliases(
        entity=timeline_tools.parse_entity_reference("person:alice"),
        values=("alice", "alice@example.com"),
        resolved=True,
    )
    conversation = timeline_tools._conversation_entry(
        {
            "id": "conversation-1",
            "created_at": NOW,
            "structured": {
                "title": {"transcript": "TRANSCRIPT_SECRET"},
                "overview": ["CALENDAR_NOTE_SECRET"],
            },
            "transcript_segments": [{"person_id": "alice"}],
        },
        aliases,
    )
    calendar = timeline_tools._calendar_entry(
        {
            "id": "meeting-1",
            "start_time": NOW,
            "title": "Review with alice@例子.公司",
            "participants": [{"email": "alice@example.com"}],
        },
        aliases,
    )
    screen = timeline_tools._screen_entry(
        {
            "id": "screen-1",
            "timestamp": NOW,
            "appName": {"frame": "FRAME_SECRET"},
            "windowTitle": "Alice alice@例子.公司",
            "ocrText": "Alice OCR_SECRET",
        },
        aliases,
    )

    assert conversation is not None and conversation.content == "Conversation"
    assert calendar is not None and calendar.content == "Review with [redacted email]"
    assert screen is not None and screen.content == "Screen activity — Alice [redacted email]"
    combined = " ".join(entry.content for entry in (conversation, calendar, screen) if entry is not None)
    for secret in ("TRANSCRIPT_SECRET", "CALENDAR_NOTE_SECRET", "FRAME_SECRET", "alice@例子.公司"):
        assert secret not in combined


def test_non_ledger_source_consumer_stays_bounded_when_reader_violates_its_limit(monkeypatch):
    monkeypatch.setattr(timeline_tools.database_client, "get_firestore_client", lambda: object())
    monkeypatch.setattr(
        timeline_tools,
        "_resolve_entity_aliases",
        lambda uid, entity, *, db_client: timeline_tools.EntityAliases(
            entity=entity,
            values=("alice",),
            resolved=True,
        ),
    )
    rows = [
        {
            "id": f"meeting-{index}",
            "start_time": NOW + timedelta(seconds=index),
            "title": "Review",
            "participants": [{"name": "Alice"}],
        }
        for index in range(timeline_tools.MAX_TIMELINE_SOURCE_SCAN + 50)
    ]
    monkeypatch.setattr(timeline_tools, "list_entity_timeline_meetings", lambda *args, **kwargs: rows)

    result = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "sources": ["calendar"], "limit": 1},
        config={"configurable": {"user_id": "u1"}},
    )

    assert "Source windows were partial: calendar" in result
    assert f"meeting-{timeline_tools.MAX_TIMELINE_SOURCE_SCAN}" not in result


def test_source_failure_is_partial_and_disclosed_without_falling_back(monkeypatch):
    import database._client as database_client

    monkeypatch.setattr(database_client, "get_firestore_client", lambda: object())
    monkeypatch.setattr(
        timeline_tools,
        "_resolve_entity_aliases",
        lambda uid, entity, *, db_client: timeline_tools.EntityAliases(entity=entity, resolved=True),
    )

    def unavailable(*args, **kwargs):
        raise RuntimeError("private upstream detail")

    monkeypatch.setattr(timeline_tools, "list_entity_timeline_conversations", unavailable)
    result = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "sources": ["conversations"]},
        config={"configurable": {"user_id": "u1"}},
    )

    assert "No entity timeline entries" in result
    assert "Sources unavailable: conversations" in result
    assert "private upstream detail" not in result


def test_sources_and_history_audit_mode_are_explicitly_validated_before_storage(monkeypatch):
    calls = []
    monkeypatch.setattr(timeline_tools.database_client, "get_firestore_client", lambda: calls.append(True))

    unknown = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "sources": ["semantic_guess"]},
        config={"configurable": {"user_id": "u1"}},
    )
    invalid_audit = timeline_tools.get_entity_timeline_tool.invoke(
        {"entity": "person:alice", "include_rejected": True},
        config={"configurable": {"user_id": "u1"}},
    )

    assert "unsupported timeline source" in unknown
    assert "include_rejected requires include_history" in invalid_audit
    assert calls == []

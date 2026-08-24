from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from models.memories import MemoryDB
from models.memory_evidence import SourceState
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
    ProcessingState,
)
from utils.retrieval.tools import knowledge_ledger_tools as tools

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _memory(memory_id: str, *, kind: MemoryKind, **updates) -> MemoryDB:
    payload = {
        "id": memory_id,
        "uid": "u1",
        "content": f"description {memory_id}",
        "created_at": NOW,
        "updated_at": NOW,
        "memory_tier": MemoryLayer.long_term,
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": kind,
        "subject_scope": MemorySubjectScope.primary_user,
        "intent_backed": True,
    }
    payload.update(updates)
    return MemoryDB(**payload)


def _playbook(memory_id: str = "mem_playbook", **updates) -> MemoryItem:
    payload = {
        "memory_id": memory_id,
        "uid": "u1",
        "version": 1,
        "tier": MemoryLayer.long_term,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "content": "Deploy the release safely",
        "body": "1. Run checks\n2. Publish the candidate",
        "evidence": [],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": True,
        "captured_at": NOW,
        "updated_at": NOW,
        "ledger_commit_id": "commit-1",
        "ledger_sequence": 1,
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": MemoryKind.document,
        "subject_scope": MemorySubjectScope.primary_user,
        "intent_backed": True,
        "write_reason": LedgerWriteReason.recurring_workflow,
    }
    payload.update(updates)
    return MemoryItem(**payload)


def test_search_current_knowledge_returns_only_requested_current_ledger_kinds(monkeypatch):
    rows = [
        _memory("mem_fact", kind=MemoryKind.fact, slot="home_city"),
        _memory("mem_doc", kind=MemoryKind.document, body="private body"),
        _memory("mem_trigger", kind=MemoryKind.trigger, trigger_condition={"keywords": ["release"]}),
        _memory("mem_legacy", kind=MemoryKind.fact, ledger_schema_version=None),
        _memory("mem_locked", kind=MemoryKind.document, is_locked=True),
        _memory("mem_rejected", kind=MemoryKind.document, user_review=False),
        _memory("mem_closed", kind=MemoryKind.document, invalid_at=NOW),
        _memory("mem_passive", kind=MemoryKind.document, intent_backed=False),
        _memory(
            "mem_third_party_doc",
            kind=MemoryKind.document,
            subject_scope=MemorySubjectScope.third_party,
            body="private third-party body",
        ),
        _memory("mem_wrong_owner", kind=MemoryKind.document, uid="u2"),
    ]

    class FakeService:
        def __init__(self, *, db_client):
            assert db_client == "db"

        def search(self, uid, query, *, limit, canonical_item_filter, result_filter, ledger_kinds=None):
            assert ledger_kinds == frozenset({"document", "trigger"})
            assert (uid, query, limit) == ("u1", "release", 8)
            assert canonical_item_filter(_playbook()) is True
            assert canonical_item_filter(_playbook().model_copy(update={"kind": MemoryKind.fact})) is False
            assert (
                canonical_item_filter(_playbook().model_copy(update={"subject_scope": MemorySubjectScope.third_party}))
                is False
            )
            return [SimpleNamespace(memory=row) for row in rows if result_filter(row)]

    monkeypatch.setattr(tools, "MemoryService", FakeService)
    result = tools.search_current_knowledge(
        "u1",
        "release",
        kinds=frozenset({"document", "trigger"}),
        limit=8,
        db_client="db",
    )

    assert [row.id for row in result] == ["mem_doc", "mem_trigger"]
    rendered = tools._format_search_results(result, query="release")
    assert "[document] mem_doc" in rendered
    assert "[trigger] mem_trigger" in rendered
    assert "private body" not in rendered
    assert "keywords" not in rendered
    assert "mem_third_party_doc" not in rendered


def test_search_compacts_and_caps_legacy_playbook_handles():
    row = _memory(
        "legacy-long-playbook",
        kind=MemoryKind.document,
        content="Deploy safely\n" + ("x" * 4_000),
        body="private full workflow",
    )

    rendered = tools._format_search_results([row], query="deploy")
    handle = rendered.splitlines()[1].split(": ", 1)[1]

    assert "\n" not in handle
    assert len(handle) == tools.MAX_PLAYBOOK_DESCRIPTION_CHARACTERS
    assert "private full workflow" not in rendered


def test_read_current_playbook_applies_chat_visibility_and_ledger_semantics(monkeypatch):
    current = _playbook()
    monkeypatch.setattr(tools, "read_canonical_memory_item", lambda uid, memory_id, *, db_client: current)
    assert tools.read_current_playbook("u1", "mem_playbook", db_client="db") == current

    excluded = [
        _playbook(kind=MemoryKind.fact, body=None),
        _playbook(subject_scope=MemorySubjectScope.third_party),
        _playbook(valid_to=NOW),
        _playbook(promotion={"is_locked": True}),
        _playbook(promotion={"user_review": False}),
        _playbook(sensitivity_labels=["credential"]),
        _playbook(tier=MemoryLayer.archive),
        _playbook(uid="u2"),
        _playbook(memory_id="other-id"),
    ]
    for item in excluded:
        monkeypatch.setattr(tools, "read_canonical_memory_item", lambda uid, memory_id, *, db_client, item=item: item)
        assert tools.read_current_playbook("u1", "mem_playbook", db_client="db") is None


def test_tools_are_owner_scoped_bounded_and_fail_closed(monkeypatch):
    import database._client as database_client

    monkeypatch.setattr(database_client, "get_firestore_client", lambda: "db")
    monkeypatch.setattr(
        tools,
        "search_current_knowledge",
        lambda uid, query, *, kinds, limit, db_client: [_memory("mem_doc", kind=MemoryKind.document)],
    )
    search_result = tools.search_knowledge.invoke(
        {"query": "release", "kinds": "document", "limit": 8},
        config={"configurable": {"user_id": "u1"}},
    )
    assert search_result == "Current knowledge matching 'release':\n- [document] mem_doc: description mem_doc"

    playbook = _playbook()
    monkeypatch.setattr(tools, "read_current_playbook", lambda uid, memory_id, *, db_client: playbook)
    read_result = tools.read_playbook.invoke(
        {"memory_id": "mem_playbook"},
        config={"configurable": {"user_id": "u1"}},
    )
    assert "Deploy the release safely" in read_result
    assert "Run checks" in read_result

    assert tools.search_knowledge.invoke(
        {"query": "", "limit": 8}, config={"configurable": {"user_id": "u1"}}
    ).startswith("Error:")
    assert tools.search_knowledge.invoke(
        {"query": "release", "kinds": "screen", "limit": 8},
        config={"configurable": {"user_id": "u1"}},
    ).startswith("Error:")
    assert (
        tools.read_playbook.invoke({"memory_id": "../../other-user"}, config={"configurable": {"user_id": "u1"}})
        == "Error: invalid playbook id"
    )

    monkeypatch.setattr(tools, "read_current_playbook", lambda uid, memory_id, *, db_client: None)
    assert (
        tools.read_playbook.invoke({"memory_id": "mem_missing"}, config={"configurable": {"user_id": "u1"}})
        == "Playbook unavailable."
    )


def test_search_historical_facts_is_fact_only_owner_scoped_and_partial(monkeypatch):
    import database._client as database_client

    fact = _memory(
        "historical-fact",
        kind=MemoryKind.fact,
        content="Previously lived in Boston",
        valid_at=NOW,
        invalid_at=NOW,
    )
    document = _memory(
        "historical-playbook",
        kind=MemoryKind.document,
        content="Release workflow",
        body="private workflow body",
        invalid_at=NOW,
    )
    trigger = _memory(
        "historical-trigger",
        kind=MemoryKind.trigger,
        content="Watch release windows",
        invalid_at=NOW,
        trigger_condition={"keywords": ["release"]},
    )
    locked = _memory(
        "historical-locked",
        kind=MemoryKind.fact,
        content="Private locked fact",
        invalid_at=NOW,
        is_locked=True,
    )
    rejected = _memory(
        "historical-rejected",
        kind=MemoryKind.fact,
        content="Rejected Boston claim",
        user_review=False,
    )
    migrated_legacy = _memory(
        "historical-legacy",
        kind=MemoryKind.fact,
        content="Generated Boston history",
        intent_backed=False,
        write_reason=LedgerWriteReason.legacy_migration,
    )
    passive = _memory(
        "historical-passive",
        kind=MemoryKind.fact,
        content="Unratified passive Boston extraction",
        intent_backed=False,
    )

    class FakeService:
        def __init__(self, *, db_client):
            assert db_client == "db"

        def search_ledger_history_page(self, uid, query, *, limit, offset, include_rejected):
            assert (uid, query, limit, offset, include_rejected) == ("u1", "Boston", 8, 0, False)
            return SimpleNamespace(
                matches=[
                    SimpleNamespace(memory=fact),
                    SimpleNamespace(memory=document),
                    SimpleNamespace(memory=trigger),
                    SimpleNamespace(memory=locked),
                    SimpleNamespace(memory=rejected),
                    SimpleNamespace(memory=migrated_legacy),
                    SimpleNamespace(memory=passive),
                ],
                truncated=True,
                scanned_count=501,
                next_offset=8,
            )

    monkeypatch.setattr(database_client, "get_firestore_client", lambda: "db")
    monkeypatch.setattr(tools, "MemoryService", FakeService)

    result = tools.search_historical_facts.invoke(
        {"query": "Boston", "limit": 8},
        config={"configurable": {"user_id": "u1"}},
    )

    assert "historical-fact" in result
    assert "Previously lived in Boston" in result
    assert "historical-playbook" not in result
    assert "private workflow body" not in result
    assert "historical-trigger" not in result
    assert "historical-locked" not in result
    assert "historical-rejected" not in result
    assert "historical-legacy" in result
    assert "fact/legacy-migrated" in result
    assert "historical-passive" not in result
    assert "valid_at=2026-08-23T12:00:00+00:00" in result
    assert "invalid_at=2026-08-23T12:00:00+00:00" in result
    assert "Partial historical search" in result
    assert "not exhaustive" in result
    assert "offset=8" in result
    assert tools.HISTORICAL_LIVE_WINDOW_NOTICE in result


def test_historical_fact_renderer_hard_cap_preserves_both_disclosures():
    rows = [
        _memory(
            f"oversized-{index}",
            kind=MemoryKind.fact,
            content="x" * 100_000,
            valid_at=NOW,
            invalid_at=NOW,
        )
        for index in range(30)
    ]

    result = tools._format_historical_fact_results(
        rows,
        query="Boston",
        truncated=True,
        next_offset=20,
        include_rejected=True,
    )

    assert len(result) <= tools.MAX_KNOWLEDGE_RESULT_CHARACTERS
    assert tools.HISTORICAL_OUTPUT_TRUNCATION_NOTICE in result
    assert tools.HISTORICAL_PROVIDER_PARTIAL_NOTICE in result
    assert "offset=20" in result
    assert tools.HISTORICAL_LIVE_WINDOW_NOTICE in result
    assert tools.HISTORICAL_REJECTED_AUDIT_NOTICE in result


def test_search_historical_facts_rejects_unsearchable_and_oversized_requests(monkeypatch):
    import database._client as database_client

    monkeypatch.setattr(database_client, "get_firestore_client", lambda: "db")
    service = SimpleNamespace(search_ledger_history_page=MagicMock())
    service.search_ledger_history_page.side_effect = ValueError("historical ledger query must contain a token")
    monkeypatch.setattr(tools, "MemoryService", lambda *, db_client: service)
    config = {"configurable": {"user_id": "u1"}}

    assert tools.search_historical_facts.invoke({"query": "!"}, config=config).startswith("Error:")
    service.search_ledger_history_page.assert_called_once_with(
        "u1",
        "!",
        limit=8,
        offset=0,
        include_rejected=False,
    )
    service.search_ledger_history_page.reset_mock()
    assert tools.search_historical_facts.invoke({"query": "Boston", "limit": 0}, config=config).startswith("Error:")
    assert tools.search_historical_facts.invoke(
        {"query": "Boston", "limit": tools.MAX_KNOWLEDGE_SEARCH_LIMIT + 1}, config=config
    ).startswith("Error:")
    assert tools.search_historical_facts.invoke(
        {"query": "Boston", "limit": 8, "offset": 495}, config=config
    ).startswith("Error:")
    service.search_ledger_history_page.assert_not_called()


def test_search_historical_facts_requires_explicit_rejected_audit(monkeypatch):
    import database._client as database_client

    rejected = _memory(
        "historical-rejected",
        kind=MemoryKind.fact,
        content="Rejected Boston claim",
        user_review=False,
    )

    class FakeService:
        def __init__(self, *, db_client):
            assert db_client == "db"

        def search_ledger_history_page(self, uid, query, *, limit, offset, include_rejected):
            assert (uid, query, limit, offset, include_rejected) == ("u1", "Boston", 8, 16, True)
            return SimpleNamespace(
                matches=[SimpleNamespace(memory=rejected)],
                truncated=False,
                scanned_count=1,
                next_offset=None,
            )

    monkeypatch.setattr(database_client, "get_firestore_client", lambda: "db")
    monkeypatch.setattr(tools, "MemoryService", FakeService)

    result = tools.search_historical_facts.invoke(
        {"query": "Boston", "limit": 8, "offset": 16, "include_rejected": True},
        config={"configurable": {"user_id": "u1"}},
    )

    assert "historical-rejected" in result
    assert "fact/rejected" in result
    assert tools.HISTORICAL_REJECTED_AUDIT_NOTICE in result


def test_tool_errors_do_not_echo_storage_details(monkeypatch):
    import database._client as database_client

    def unavailable():
        raise RuntimeError("private-project users/u1/memory_items")

    monkeypatch.setattr(database_client, "get_firestore_client", unavailable)
    config = {"configurable": {"user_id": "u1"}}
    assert tools.search_knowledge.invoke({"query": "release"}, config=config) == "Error searching current knowledge"
    assert tools.read_playbook.invoke({"memory_id": "mem_playbook"}, config=config) == "Playbook unavailable."


def test_read_playbook_bounds_malformed_stored_content(monkeypatch):
    import database._client as database_client

    monkeypatch.setattr(database_client, "get_firestore_client", lambda: "db")
    oversized = _playbook().model_copy(
        update={
            "content": "d" * (tools.MAX_PLAYBOOK_DESCRIPTION_CHARACTERS + 20),
            "body": "b" * (tools.MAX_LEDGER_PLAYBOOK_BODY_CHARACTERS + 20),
        }
    )
    monkeypatch.setattr(tools, "read_current_playbook", lambda uid, memory_id, *, db_client: oversized)

    result = tools.read_playbook.invoke(
        {"memory_id": "mem_playbook"},
        config={"configurable": {"user_id": "u1"}},
    )

    assert "d" * tools.MAX_PLAYBOOK_DESCRIPTION_CHARACTERS in result
    assert "d" * (tools.MAX_PLAYBOOK_DESCRIPTION_CHARACTERS + 1) not in result
    assert result.endswith("b" * tools.MAX_LEDGER_PLAYBOOK_BODY_CHARACTERS)

from datetime import datetime, timezone

from models.memories import MemoryCategory, MemoryDB
from models.product_memory import LedgerWriteReason, MemoryKind, MemorySubjectScope
from utils.llms import memory as prompt_memory
from utils.llms.memory import _render_ledger_prompt_context, get_prompt_memories

NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)


def _row(memory_id: str, **updates) -> MemoryDB:
    data = {
        "id": memory_id,
        "uid": "u1",
        "content": "Brooklyn",
        "category": MemoryCategory.manual,
        "tags": [],
        "created_at": NOW,
        "updated_at": NOW,
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": MemoryKind.fact,
        "subject_scope": MemorySubjectScope.primary_user,
        "slot": "home_city",
        "intent_backed": True,
        "write_reason": LedgerWriteReason.direct_user_statement,
        "valid_at": NOW,
    }
    data.update(updates)
    return MemoryDB(**data)


def test_prompt_is_profile_not_wholesale_memory_dump():
    current = _row("current")
    episodic = _row("episodic", slot=None, content="Private episodic observation")
    third_party = _row(
        "sarah",
        content="Queens",
        subject_scope=MemorySubjectScope.third_party,
        subject_entity_id="person-sarah",
    )
    old = _row("old", content="Boston", invalid_at=NOW)

    rendered = _render_ledger_prompt_context("David", [episodic, third_party, old, current])

    assert "home_city: Brooklyn" in rendered
    assert "Private episodic observation" not in rendered
    assert "Queens" not in rendered
    assert "Boston" not in rendered


def test_prompt_progressively_discloses_playbook_body():
    playbook = _row(
        "playbook-1",
        kind=MemoryKind.document,
        slot=None,
        content="Release the macOS beta",
        body="private full workflow",
        write_reason=LedgerWriteReason.recurring_workflow,
    )

    rendered = _render_ledger_prompt_context("David", [playbook])

    assert "playbook-1: Release the macOS beta" in rendered
    assert "private full workflow" not in rendered
    assert "read_playbook" in rendered


def test_partial_migration_keeps_legacy_knowledge_visible(monkeypatch):
    ledger = _row("ledger")
    legacy = _row(
        "legacy",
        content="Prefers the old compatibility fact",
        ledger_schema_version=None,
        kind=None,
        subject_scope=None,
        slot=None,
        intent_backed=False,
        write_reason=None,
    )
    monkeypatch.setattr(
        prompt_memory,
        "get_prompt_data",
        lambda _uid: ("David", [], [], [ledger, legacy]),
    )
    monkeypatch.setattr(prompt_memory, "read_ledger_migration_completion", lambda *_args, **_kwargs: None)

    _, rendered = get_prompt_memories("u1")

    assert "home_city: Brooklyn" in rendered
    assert "Prefers the old compatibility fact" in rendered
    assert "Migration compatibility context" in rendered


def test_stale_completion_proof_cannot_hide_a_later_legacy_row(monkeypatch):
    ledger = _row("ledger")
    legacy = _row(
        "legacy",
        content="Legacy-only text",
        ledger_schema_version=None,
        kind=None,
        subject_scope=None,
        slot=None,
        intent_backed=False,
        write_reason=None,
    )
    monkeypatch.setattr(
        prompt_memory,
        "get_prompt_data",
        lambda _uid: ("David", [], [], [ledger, legacy]),
    )
    monkeypatch.setattr(prompt_memory, "read_ledger_migration_completion", lambda *_args, **_kwargs: object())

    _, rendered = get_prompt_memories("u1")

    assert "home_city: Brooklyn" in rendered
    assert "Legacy-only text" in rendered
    assert "Migration compatibility context" in rendered


def test_completion_proof_retires_bridge_only_for_zero_legacy_snapshot(monkeypatch):
    ledger = _row("ledger")
    monkeypatch.setattr(
        prompt_memory,
        "get_prompt_data",
        lambda _uid: ("David", [], [], [ledger]),
    )
    monkeypatch.setattr(prompt_memory, "read_ledger_migration_completion", lambda *_args, **_kwargs: object())

    _, rendered = get_prompt_memories("u1")

    assert "home_city: Brooklyn" in rendered
    assert "Migration compatibility context" not in rendered

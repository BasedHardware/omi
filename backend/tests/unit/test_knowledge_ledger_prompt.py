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


def _row_from_promotion(memory_id: str, promotion: dict, **updates) -> MemoryDB:
    """Build the prompt's legacy view of canonical ``promotion.user_review``."""
    return _row(memory_id, user_review=promotion.get("user_review"), **updates)


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


def test_prompt_compacts_historical_multiline_playbook_description():
    playbook = _row(
        "playbook-multiline",
        kind=MemoryKind.document,
        slot=None,
        content="Deploy safely\n1. Export artifacts\n2. Verify release",
        body="private full workflow",
        write_reason=LedgerWriteReason.recurring_workflow,
    )

    rendered = _render_ledger_prompt_context("David", [playbook])

    assert "playbook-multiline: Deploy safely 1. Export artifacts 2. Verify release" in rendered
    assert rendered.count("\n1. Export artifacts") == 0


def test_prompt_excludes_unhydratable_third_party_playbook():
    primary = _row(
        "primary-playbook",
        kind=MemoryKind.document,
        slot=None,
        content="Release safely",
        body="private workflow",
        write_reason=LedgerWriteReason.recurring_workflow,
    )
    third_party = _row(
        "third-party-playbook",
        kind=MemoryKind.document,
        slot=None,
        content="How Sarah releases",
        body="third-party workflow",
        write_reason=LedgerWriteReason.recurring_workflow,
        subject_scope=MemorySubjectScope.third_party,
        subject_entity_id="person-sarah",
    )

    rendered = _render_ledger_prompt_context("David", [third_party, primary])

    assert "primary-playbook: Release safely" in rendered
    assert "third-party-playbook" not in rendered
    assert "How Sarah releases" not in rendered


def test_prompt_uses_the_same_authority_first_slot_winner_policy():
    direct = _row(
        "direct",
        content="Brooklyn",
        valid_at=NOW,
        curation_weight=-100,
        write_reason=LedgerWriteReason.direct_user_statement,
    )
    newer_daily = _row(
        "daily",
        content="Boston",
        valid_at=NOW.replace(day=24),
        curation_weight=100,
        write_reason=LedgerWriteReason.daily_reconciliation,
    )
    alias = _row(
        "alias",
        content="Queens",
        slot="home_location",
        valid_at=NOW.replace(day=22),
        write_reason=LedgerWriteReason.direct_user_statement,
    )

    rendered = _render_ledger_prompt_context("David", [newer_daily, alias, direct])

    assert rendered.count("home_city:") == 1
    assert "home_city: Brooklyn" in rendered
    assert "Boston" not in rendered
    assert "Queens" not in rendered


def test_prompt_projection_rejects_promotion_without_changing_order_or_bounds():
    """Rejected canonical rows must not displace visible facts or playbook handles."""
    accepted_fact_without_review = _row_from_promotion(
        "accepted-fact-without-review",
        {},
        content="Brooklyn",
        slot="home_city",
        curation_weight=2,
    )
    accepted_fact_with_review = _row_from_promotion(
        "accepted-fact-with-review",
        {"user_review": True},
        content="Engineer",
        slot="occupation",
        curation_weight=1,
    )
    rejected_fact = _row_from_promotion(
        "rejected-fact",
        {"user_review": False},
        content="Rejected",
        slot="blocked_fact",
        curation_weight=100,
    )
    accepted_playbook_without_review = _row_from_promotion(
        "playbook-a",
        {},
        kind=MemoryKind.document,
        slot=None,
        content="Alpha",
        body="alpha body",
        curation_weight=2,
    )
    accepted_playbook_with_review = _row_from_promotion(
        "playbook-b",
        {"user_review": True},
        kind=MemoryKind.document,
        slot=None,
        content="Beta",
        body="beta body",
        curation_weight=1,
    )
    rejected_playbook = _row_from_promotion(
        "rejected-playbook",
        {"user_review": False},
        kind=MemoryKind.document,
        slot=None,
        content="y" * 760,
        body="private rejected workflow",
        curation_weight=100,
    )
    unrelated = _row(
        "unrelated-third-party",
        content="Queens",
        subject_scope=MemorySubjectScope.third_party,
        subject_entity_id="person-sarah",
    )

    visible_rows = [
        accepted_fact_without_review,
        accepted_fact_with_review,
        accepted_playbook_without_review,
        accepted_playbook_with_review,
        unrelated,
    ]
    rows_with_rejections = [
        rejected_fact,
        accepted_playbook_with_review,
        unrelated,
        rejected_playbook,
        accepted_fact_with_review,
        accepted_playbook_without_review,
        accepted_fact_without_review,
    ]

    expected = _render_ledger_prompt_context("David", visible_rows)
    rendered = _render_ledger_prompt_context("David", rows_with_rejections)

    assert expected == (
        "Current profile for David:\n"
        "home_city: Brooklyn\n"
        "occupation: Engineer\n\n"
        "Available playbooks (call read_playbook for the body; do not infer it from the title):\n"
        "playbook-a: Alpha\n"
        "playbook-b: Beta\n"
    )
    assert rendered == expected
    assert "blocked_fact:" not in rendered
    assert "rejected-playbook" not in rendered
    assert "private rejected workflow" not in rendered


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

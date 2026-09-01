from datetime import datetime, timedelta, timezone

import pytest

from models.memory_apply import (
    ApplyStatus,
    MemoryControlState,
    apply_long_term_patch_transaction,
    build_patch_mutation_identity,
)
from models.memory_contracts import DurablePatchDecision, LifecycleState
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
    ProcessingState,
)
from utils.memory import canonical_memory_adapter, knowledge_ledger
from utils.memory.canonical_memory_adapter import _canonical_extraction_apply_write
from utils.memory.knowledge_ledger import (
    LedgerProvenance,
    LedgerWrite,
    close_fact,
    render_playbook_index,
    render_profile,
    reopen_standalone_fact,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _evidence() -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id="ev-ledger-1",
        source_type="chat_turn",
        source_id="turn-1",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _item(memory_id: str, **updates) -> MemoryItem:
    data = {
        "memory_id": memory_id,
        "uid": "u1",
        "version": 1,
        "tier": MemoryLayer.long_term,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "content": "Lives in Brooklyn",
        "evidence": [_evidence()],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": True,
        "captured_at": NOW,
        "updated_at": NOW,
        "ledger_commit_id": "commit-1",
        "ledger_sequence": 1,
        "content_hash": "hash-1",
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": MemoryKind.fact,
        "subject_scope": MemorySubjectScope.primary_user,
        "slot": "home_city",
        "valid_from": NOW,
        "intent_backed": True,
        "write_reason": LedgerWriteReason.direct_user_statement,
    }
    data.update(updates)
    return MemoryItem(**data)


def test_ledger_create_is_durable_without_short_term_promotion():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    patch = {
        "patch_id": "patch-ledger-1",
        "packet_id": "turn-1",
        "run_id": "run-1",
        "observed_head_commit_id": "head0",
        "idempotency_key": "idem-ledger-1",
        "decision": DurablePatchDecision.add.value,
        "result_status": LifecycleState.active.value,
        "evidence_ids": ["ev-ledger-1"],
        "new_memory_id": "mem-ledger-1",
        "memory_text": "Lives in Brooklyn",
        "initial_tier": MemoryLayer.long_term.value,
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": MemoryKind.fact.value,
        "subject_scope": MemorySubjectScope.primary_user.value,
        "slot": "home_city",
        "valid_from": NOW,
        "intent_backed": True,
        "write_reason": LedgerWriteReason.direct_user_statement.value,
        "user_asserted": True,
    }
    mutation_identity = build_patch_mutation_identity(patch)
    patch["mutation_metadata"] = mutation_identity
    logical_payload = {
        "decision": DurablePatchDecision.add.value,
        "memory_text": "Lives in Brooklyn",
        "result_status": LifecycleState.active.value,
        "supersedes": [],
        "mutation_metadata": mutation_identity,
    }
    operation = MemoryOperation.new(
        uid="u1",
        operation_type=MemoryOperationType.ledger_mutation,
        source_packet_id="turn-1",
        target_memory_id=None,
        evidence_ids=["ev-ledger-1"],
        logical_payload=logical_payload,
        account_generation=1,
        source_generation=2,
        observed_head_commit_id="head0",
    )
    patch["evidence"] = [_evidence()]

    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=operation,
        patch_payload=patch,
    )

    assert result.status == ApplyStatus.committed
    item = result.memory_items[0]
    assert item.tier == MemoryLayer.long_term
    assert item.expires_at is None
    assert item.kind == MemoryKind.fact
    assert item.slot == "home_city"

    wrong_operation = MemoryOperation.new(
        uid="u1",
        operation_type=MemoryOperationType.source_candidate,
        source_packet_id="turn-1",
        target_memory_id=None,
        evidence_ids=["ev-ledger-1"],
        logical_payload=logical_payload,
        account_generation=1,
        source_generation=2,
        observed_head_commit_id="head0",
    )
    wrong_authority = apply_long_term_patch_transaction(
        control_state=control,
        operation=wrong_operation,
        patch_payload=patch,
    )
    assert wrong_authority.status == ApplyStatus.invalid_patch
    assert "ledger_mutation authority" in (wrong_authority.reason or "")


def test_ledger_amendment_appends_and_supersedes_in_one_commit():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    prior = _item("prior", content="Boston")
    write, replacement_id = _canonical_extraction_apply_write(
        "u1",
        {
            "id": "replacement",
            "content": "Brooklyn",
            "ledger_schema_version": "knowledge_ledger.v1",
            "kind": MemoryKind.fact.value,
            "subject_scope": MemorySubjectScope.primary_user.value,
            "slot": "home_city",
            "valid_from": NOW + timedelta(days=1),
            "intent_backed": True,
            "write_reason": LedgerWriteReason.direct_user_statement.value,
            "user_asserted": True,
            "supersedes": [prior.memory_id],
        },
        control=control,
        evidence_items=[_evidence()],
    )
    patch = {
        **write.patch_payload,
        "evidence": write.evidence,
        "superseded_items": [prior.model_dump(mode="python")],
    }

    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=write.operation,
        patch_payload=patch,
    )

    assert result.status == ApplyStatus.committed
    replacement = next(item for item in result.memory_items if item.memory_id == replacement_id)
    historical = next(item for item in result.memory_items if item.memory_id == prior.memory_id)
    assert replacement.status == MemoryItemStatus.active
    assert replacement.content == "Brooklyn"
    assert historical.status == MemoryItemStatus.superseded
    assert historical.superseded_by == replacement.memory_id
    assert historical.valid_to is not None
    assert historical.valid_to >= replacement.valid_from
    assert {event.payload["action"] for event in result.outbox_events} == {"upsert", "delete"}


def test_standalone_reopen_builds_preserving_append_and_stable_receipt(monkeypatch):
    source = _item(
        "closed",
        content="Lives in Brooklyn",
        status=MemoryItemStatus.superseded,
        valid_to=NOW + timedelta(hours=1),
        canonical_memory_id=None,
        superseded_by=None,
        predicate="lives_in",
        arguments={"city": "Brooklyn"},
        sensitivity_labels=["location"],
    )
    captured = {}

    def write_ledger(
        uid,
        payload,
        *,
        db_client=None,
        required_source_item=None,
        ledger_reopen_receipt=None,
    ):
        captured.update(
            {
                "uid": uid,
                "payload": payload,
                "db_client": db_client,
                "required_source_item": required_source_item,
                "ledger_reopen_receipt": ledger_reopen_receipt,
            }
        )
        return payload["id"]

    monkeypatch.setattr(
        knowledge_ledger,
        "ensure_canonical_apply_control_state",
        lambda *args, **kwargs: MemoryControlState(
            uid="u1", head_commit_id="head0", account_generation=7, source_generation=8
        ),
    )
    monkeypatch.setattr(knowledge_ledger, "read_canonical_memory_item", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        knowledge_ledger,
        "write_canonical_direct_user_knowledge_ledger_memory",
        write_ledger,
    )
    provenance = LedgerProvenance(
        source_id="closed",
        source_type="explicit_user_reopen",
        source_version="item_revision:1",
        action_id="memory_ui_reopen:client-op",
    )

    replacement_id = reopen_standalone_fact(
        "u1",
        source,
        operation_id="client-op",
        provenance=provenance,
        db_client="db",
    )

    assert replacement_id == captured["payload"]["id"]
    assert captured["required_source_item"] == source
    assert captured["payload"]["visibility"] == source.visibility
    assert captured["payload"]["predicate"] == source.predicate
    assert captured["payload"]["arguments"] == source.arguments
    assert captured["payload"]["sensitivity_labels"] == source.sensitivity_labels
    assert {item["evidence_id"] for item in captured["payload"]["evidence"]} == {
        "ev-ledger-1",
        knowledge_ledger.evidence_id_for_ledger_provenance("u1", provenance),
    }
    assert captured["ledger_reopen_receipt"].source_memory_id == source.memory_id
    assert captured["ledger_reopen_receipt"].account_generation == 7


def test_amend_fact_carries_visibility_into_the_atomic_replacement(monkeypatch):
    captured = {}

    def write_ledger(uid, payload, *, db_client=None, required_source_item=None):
        captured.update(
            {
                "uid": uid,
                "payload": payload,
                "db_client": db_client,
                "required_source_item": required_source_item,
            }
        )
        return payload["id"]

    monkeypatch.setattr(knowledge_ledger, "write_canonical_knowledge_ledger_memory", write_ledger)
    provenance = LedgerProvenance(
        source_id="prior",
        source_type="explicit_user_correction",
        source_version="item_revision:4",
        action_id="correction-1",
    )

    replacement_id = knowledge_ledger.amend_fact(
        "u1",
        "prior",
        "Lives in Brooklyn",
        provenance=provenance,
        write_reason=LedgerWriteReason.direct_user_statement,
        slot="home_city",
        visibility="shared",
        db_client="db",
    )

    assert replacement_id == captured["payload"]["id"]
    assert captured["uid"] == "u1"
    assert captured["db_client"] == "db"
    assert captured["payload"]["visibility"] == "shared"
    assert captured["required_source_item"] is None
    assert captured["payload"]["supersedes"] == ["prior"]


def test_generic_external_writer_cannot_forge_ledger_authority():
    with pytest.raises(ValueError, match="dedicated ledger authority"):
        canonical_memory_adapter.write_canonical_external_memory(
            "u1",
            {
                "id": "forged",
                "content": "Bypass promotion",
                "ledger_schema_version": "knowledge_ledger.v1",
            },
            db_client=object(),
        )


def test_distinct_ledger_actions_with_same_source_and_text_do_not_collapse():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)

    def build(memory_id: str):
        return _canonical_extraction_apply_write(
            "u1",
            {
                "id": memory_id,
                "content": "Lives in Brooklyn",
                "ledger_schema_version": "knowledge_ledger.v1",
                "kind": MemoryKind.fact.value,
                "subject_scope": MemorySubjectScope.primary_user.value,
                "slot": "home_city",
                "valid_from": NOW,
                "intent_backed": True,
                "write_reason": LedgerWriteReason.agent_reusable_conclusion.value,
                "conversation_id": "conversation-1",
            },
            control=control,
            evidence_items=[_evidence()],
        )[0]

    first = build("mem-action-1")
    retry = build("mem-action-1")
    second_action = build("mem-action-2")

    assert first.patch_payload["idempotency_key"] == retry.patch_payload["idempotency_key"]
    assert first.operation.operation_id == retry.operation.operation_id
    assert first.patch_payload["idempotency_key"] != second_action.patch_payload["idempotency_key"]
    assert first.operation.operation_id != second_action.operation.operation_id


def test_ledger_amendment_cannot_supersede_a_different_subject():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    prior = _item(
        "prior-third-party",
        subject_scope=MemorySubjectScope.third_party,
        subject_entity_id="person:sarah",
    )
    write, _ = _canonical_extraction_apply_write(
        "u1",
        {
            "id": "replacement-user",
            "content": "Lives in Brooklyn",
            "ledger_schema_version": "knowledge_ledger.v1",
            "kind": MemoryKind.fact.value,
            "subject_scope": MemorySubjectScope.primary_user.value,
            "slot": "home_city",
            "valid_from": NOW + timedelta(days=1),
            "intent_backed": True,
            "write_reason": LedgerWriteReason.direct_user_statement.value,
            "user_asserted": True,
            "supersedes": [prior.memory_id],
        },
        control=control,
        evidence_items=[_evidence()],
    )

    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=write.operation,
        patch_payload={
            **write.patch_payload,
            "evidence": write.evidence,
            "superseded_items": [prior.model_dump(mode="python")],
        },
    )

    assert result.status == ApplyStatus.invalid_patch
    assert "preserve kind and subject identity" in (result.reason or "")


def test_ledger_contract_rejects_unbacked_or_third_party_profile_rows():
    provenance = LedgerProvenance(
        source_id="turn-1",
        source_type="chat_turn",
        action_id="action-1",
    )
    with pytest.raises(ValueError, match="subject_entity_id"):
        LedgerWrite(
            kind=MemoryKind.fact,
            content="Sarah lives in Queens",
            provenance=provenance,
            write_reason=LedgerWriteReason.agent_reusable_conclusion,
            subject_scope=MemorySubjectScope.third_party,
        )

    with pytest.raises(ValueError, match="write reason"):
        _item("invalid", intent_backed=False, write_reason=None)

    with pytest.raises(ValueError, match="non-empty body"):
        LedgerWrite(
            kind=MemoryKind.document,
            content="Release playbook",
            body="",
            provenance=provenance,
            write_reason=LedgerWriteReason.recurring_workflow,
        )

    with pytest.raises(ValueError, match="serialized limit"):
        LedgerProvenance(
            source_id="turn-1",
            source_type="chat_turn",
            action_id="action-oversized",
            artifact_ref={"uri": "x" * 2_100},
        )

    with pytest.raises(ValueError, match="serialized limit"):
        LedgerWrite(
            kind=MemoryKind.trigger,
            content="When the release window appears",
            provenance=provenance,
            write_reason=LedgerWriteReason.standing_trigger,
            trigger_condition={"keyword": "x" * 8_100},
        )


def test_profile_renderer_is_current_user_only_deterministic_and_bounded():
    current = _item("current", content="Brooklyn", curation_weight=5)
    older = _item(
        "older",
        content="Boston",
        status=MemoryItemStatus.superseded,
        valid_to=NOW + timedelta(days=1),
    )
    third_party = _item(
        "third-party",
        content="Queens",
        subject_scope=MemorySubjectScope.third_party,
        subject_entity_id="person-sarah",
    )
    episodic = _item("episodic", content="Went to a concert", slot=None)

    assert render_profile([episodic, third_party, older, current]) == "home_city: Brooklyn"
    assert render_profile([current], character_budget=10) == ""


def test_ledger_slot_aliases_are_canonical_and_unknown_new_slots_fail_closed():
    provenance = LedgerProvenance(
        source_id="turn-slot",
        source_type="chat_turn",
        action_id="action-slot",
    )
    aliased = LedgerWrite(
        kind=MemoryKind.fact,
        content="Brooklyn",
        provenance=provenance,
        write_reason=LedgerWriteReason.direct_user_statement,
        slot=" Home-Location ",
    )

    assert aliased.slot == "home_city"

    with pytest.raises(ValueError, match="unsupported knowledge ledger slot"):
        LedgerWrite(
            kind=MemoryKind.fact,
            content="Unknown",
            provenance=provenance,
            write_reason=LedgerWriteReason.agent_reusable_conclusion,
            slot="invented_slot",
        )

    migrated = LedgerWrite(
        kind=MemoryKind.fact,
        content="Retained legacy knowledge",
        provenance=provenance,
        write_reason=LedgerWriteReason.legacy_migration,
        slot="historic_custom_label",
    )
    assert migrated.slot is None


def test_playbook_and_trigger_writes_require_their_own_authority():
    provenance = LedgerProvenance(
        source_id="turn-authority",
        source_type="chat_turn",
        action_id="action-authority",
    )

    with pytest.raises(ValueError, match="recurring_workflow authority"):
        LedgerWrite(
            kind=MemoryKind.document,
            content="Release workflow",
            body="Do the safe release steps.",
            provenance=provenance,
            write_reason=LedgerWriteReason.agent_reusable_conclusion,
        )

    with pytest.raises(ValueError, match="standing_trigger authority"):
        LedgerWrite(
            kind=MemoryKind.trigger,
            content="Notify on release readiness",
            trigger_condition={"keyword": "ready"},
            provenance=provenance,
            write_reason=LedgerWriteReason.agent_reusable_conclusion,
        )

    with pytest.raises(ValueError, match="primary_user scope"):
        LedgerWrite(
            kind=MemoryKind.document,
            content="Third-party workflow",
            body="Private third-party steps",
            provenance=provenance,
            write_reason=LedgerWriteReason.recurring_workflow,
            subject_scope=MemorySubjectScope.third_party,
            subject_entity_id="person-sarah",
        )

    for invalid_reason in (LedgerWriteReason.recurring_workflow, LedgerWriteReason.standing_trigger):
        with pytest.raises(ValueError, match="facts cannot use document or trigger authority"):
            LedgerWrite(
                kind=MemoryKind.fact,
                content="Wrong authority",
                provenance=provenance,
                write_reason=invalid_reason,
                slot="home_city",
            )


def test_playbook_description_is_one_bounded_handle_in_write_and_projection():
    provenance = LedgerProvenance(
        source_id="turn-playbook",
        source_type="chat_turn",
        action_id="action-playbook",
    )
    write = LedgerWrite(
        kind=MemoryKind.document,
        content="Deploy safely\n1. Export artifacts\n2. Verify release",
        body="Full private workflow",
        provenance=provenance,
        write_reason=LedgerWriteReason.recurring_workflow,
    )
    historical = _item(
        "playbook-multiline",
        kind=MemoryKind.document,
        slot=None,
        content="Deploy safely\n1. Export artifacts\n2. Verify release",
        body="Full private workflow",
        write_reason=LedgerWriteReason.recurring_workflow,
    )
    third_party = historical.model_copy(
        update={
            "memory_id": "third-party-playbook",
            "subject_scope": MemorySubjectScope.third_party,
            "subject_entity_id": "person-sarah",
        }
    )

    assert write.content == "Deploy safely 1. Export artifacts 2. Verify release"
    assert render_playbook_index([historical]) == (
        "playbook-multiline: Deploy safely 1. Export artifacts 2. Verify release"
    )
    assert render_playbook_index([third_party, historical]) == (
        "playbook-multiline: Deploy safely 1. Export artifacts 2. Verify release"
    )

    with pytest.raises(ValueError, match="compact handle limit"):
        LedgerWrite(
            kind=MemoryKind.document,
            content="x" * 361,
            body="Full private workflow",
            provenance=provenance,
            write_reason=LedgerWriteReason.recurring_workflow,
        )


def test_profile_renderer_selects_one_slot_winner_by_authority_then_recency():
    direct = _item(
        "direct",
        content="Brooklyn",
        valid_from=NOW,
        curation_weight=-100,
        write_reason=LedgerWriteReason.direct_user_statement,
    )
    newer_daily = _item(
        "newer-daily",
        content="Boston",
        valid_from=NOW + timedelta(days=2),
        curation_weight=100,
        write_reason=LedgerWriteReason.daily_reconciliation,
        user_asserted=False,
    )
    newer_direct = _item(
        "newer-direct",
        content="Queens",
        valid_from=NOW + timedelta(days=1),
        write_reason=LedgerWriteReason.direct_user_statement,
    )
    preferred_name = _item(
        "preferred-name",
        content="David",
        slot="preferred_name",
    )
    unknown_historic = _item(
        "unknown",
        content="Must stay out of the prompt",
        slot="future_slot",
        write_reason=LedgerWriteReason.legacy_migration,
    )

    assert render_profile([newer_daily, unknown_historic, direct, preferred_name]) == (
        "preferred_name: David\nhome_city: Brooklyn"
    )
    assert render_profile([direct, newer_direct]) == "home_city: Queens"


def test_profile_renderer_rejects_promotion_without_changing_order_or_budget():
    """A rejected high-priority row must not consume the profile projection budget."""
    accepted_without_review = _item(
        "accepted-without-review",
        content="Brooklyn",
        slot="home_city",
        curation_weight=2,
        promotion=None,
    )
    accepted_with_review = _item(
        "accepted-with-review",
        content="Engineer",
        slot="occupation",
        curation_weight=1,
        promotion={"user_review": True},
    )
    rejected = _item(
        "rejected",
        content="Rejected",
        slot="blocked_fact",
        curation_weight=100,
        promotion={"user_review": False},
    )
    unrelated = _item(
        "unrelated-playbook",
        kind=MemoryKind.document,
        slot=None,
        body="private body",
        promotion={"user_review": False},
    )
    budget = len("home_city: Brooklyn\noccupation: Engineer")

    expected = render_profile(
        [accepted_without_review, accepted_with_review, unrelated],
        character_budget=budget,
    )
    rendered = render_profile(
        [rejected, accepted_with_review, unrelated, accepted_without_review],
        character_budget=budget,
    )

    assert expected == "home_city: Brooklyn\noccupation: Engineer"
    assert rendered == expected
    assert "blocked_fact" not in rendered
    assert len(rendered) <= budget


def test_playbook_index_never_injects_body():
    playbook = _item(
        "playbook-1",
        kind=MemoryKind.document,
        slot=None,
        content="Release the macOS beta",
        body="secret implementation detail",
        write_reason=LedgerWriteReason.recurring_workflow,
    )

    rendered = render_playbook_index([playbook])

    assert rendered == "playbook-1: Release the macOS beta"
    assert "secret implementation detail" not in rendered


def test_playbook_index_rejects_promotion_without_changing_order_or_budget():
    """A rejected high-priority playbook must not hide approved handles at the bound."""
    accepted_without_review = _item(
        "playbook-a",
        kind=MemoryKind.document,
        slot=None,
        content="Alpha",
        body="alpha body",
        curation_weight=2,
        promotion=None,
    )
    accepted_with_review = _item(
        "playbook-b",
        kind=MemoryKind.document,
        slot=None,
        content="Beta",
        body="beta body",
        curation_weight=1,
        promotion={"user_review": True},
    )
    rejected = _item(
        "rejected-playbook",
        kind=MemoryKind.document,
        slot=None,
        content="Rejected",
        body="private rejected workflow",
        curation_weight=100,
        promotion={"user_review": False},
    )
    unrelated = _item("unrelated-fact", content="not a playbook", promotion={"user_review": False})
    budget = len("playbook-a: Alpha\nplaybook-b: Beta")

    expected = render_playbook_index(
        [accepted_without_review, accepted_with_review, unrelated],
        character_budget=budget,
    )
    rendered = render_playbook_index(
        [rejected, accepted_with_review, unrelated, accepted_without_review],
        character_budget=budget,
    )

    assert expected == "playbook-a: Alpha\nplaybook-b: Beta"
    assert rendered == expected
    assert "rejected-playbook" not in rendered
    assert "private rejected workflow" not in rendered
    assert len(rendered) <= budget


def test_close_fact_retry_returns_identical_closed_history(monkeypatch):
    closed_at = NOW + timedelta(hours=1)
    closed = _item(
        "closed",
        status=MemoryItemStatus.superseded,
        valid_to=closed_at,
    )
    monkeypatch.setattr(
        canonical_memory_adapter,
        "_read_canonical_memory_item_for_lineage",
        lambda *_args, **_kwargs: closed,
    )
    monkeypatch.setattr(
        canonical_memory_adapter,
        "_apply_canonical_user_mutation",
        lambda *_args, **_kwargs: pytest.fail("idempotent close must not write again"),
    )

    assert close_fact("u1", "closed", valid_to=closed_at, db_client=object()) == closed


def test_close_fact_retry_rejects_a_different_close_time(monkeypatch):
    closed = _item(
        "closed",
        status=MemoryItemStatus.superseded,
        valid_to=NOW + timedelta(hours=1),
    )
    monkeypatch.setattr(
        canonical_memory_adapter,
        "_read_canonical_memory_item_for_lineage",
        lambda *_args, **_kwargs: closed,
    )

    with pytest.raises(ValueError, match="different valid_to"):
        close_fact("u1", "closed", valid_to=NOW + timedelta(hours=2), db_client=object())


def test_ledger_migration_adapter_retry_is_a_noop(monkeypatch):
    adapted = _item(
        "legacy",
        item_revision=5,
        user_asserted=False,
        intent_backed=False,
        write_reason=LedgerWriteReason.legacy_migration,
    )
    updates = {
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": MemoryKind.fact.value,
        "subject_scope": MemorySubjectScope.primary_user.value,
        "slot": "home_city",
        "valid_from": NOW,
        "valid_to": None,
        "curation_weight": 0,
        "trigger_condition": {},
        "intent_backed": False,
        "write_reason": LedgerWriteReason.legacy_migration.value,
    }
    monkeypatch.setattr(
        canonical_memory_adapter,
        "_read_canonical_memory_item_for_lineage",
        lambda *_args, **_kwargs: adapted,
    )
    monkeypatch.setattr(
        canonical_memory_adapter,
        "_apply_canonical_user_mutation",
        lambda *_args, **_kwargs: pytest.fail("adapted rows must not be rewritten"),
    )

    result = canonical_memory_adapter.adapt_canonical_memory_to_knowledge_ledger(
        "u1",
        "legacy",
        expected_item_revision=4,
        updates=updates,
        db_client=object(),
    )

    assert result == adapted


def test_write_playbook_and_create_trigger_persist_their_own_kind(monkeypatch):
    """The two dormant write verbs land the exact kind their JIT tools rely on."""
    captured: dict = {}

    def fake_write(uid, data, **kwargs):
        captured["uid"] = uid
        captured["data"] = data
        return data["id"]

    monkeypatch.setattr(knowledge_ledger, "write_canonical_knowledge_ledger_memory", fake_write)

    playbook_provenance = LedgerProvenance(
        source_id="turn-playbook", source_type="agent_chat", action_id="action-playbook"
    )
    playbook_id = knowledge_ledger.write_playbook(
        "u1",
        "Cut a release candidate",
        "1. Run checks\n2. Publish",
        provenance=playbook_provenance,
    )
    assert captured["uid"] == "u1"
    assert captured["data"]["id"] == playbook_id
    assert captured["data"]["kind"] == MemoryKind.document.value
    assert captured["data"]["body"] == "1. Run checks\n2. Publish"
    assert captured["data"]["write_reason"] == LedgerWriteReason.recurring_workflow.value
    assert captured["data"]["subject_scope"] == MemorySubjectScope.primary_user.value

    trigger_provenance = LedgerProvenance(
        source_id="turn-trigger", source_type="agent_chat", action_id="action-trigger"
    )
    trigger_condition = {
        "keywords": ["jane"],
        "action": {"type": "agent_prompt", "prompt": "Tell the user Jane emailed."},
    }
    trigger_id = knowledge_ledger.create_trigger(
        "u1",
        "Watch for Jane",
        trigger_condition,
        provenance=trigger_provenance,
        arguments={"wakeup_budget_per_day": 1},
    )
    assert captured["data"]["id"] == trigger_id
    assert captured["data"]["kind"] == MemoryKind.trigger.value
    assert captured["data"]["trigger_condition"] == trigger_condition
    assert captured["data"]["arguments"] == {"wakeup_budget_per_day": 1}
    assert captured["data"]["write_reason"] == LedgerWriteReason.standing_trigger.value

    # The pre-existing verb signature omitted ``arguments`` entirely, which
    # made it impossible for any caller to ever populate
    # ``wakeup_budget_per_day`` — the one field the paid-work trigger snapshot
    # (utils.memory.jit_trigger_snapshot) requires before it will admit a row.
    # Confirm the additive default still behaves for a caller that omits it.
    trigger_id_no_arguments = knowledge_ledger.create_trigger(
        "u1",
        "Watch for Jane again",
        trigger_condition,
        provenance=LedgerProvenance(source_id="turn-trigger-2", source_type="agent_chat", action_id="action-trigger-2"),
    )
    assert captured["data"]["id"] == trigger_id_no_arguments
    assert captured["data"]["arguments"] == {}


def test_close_fact_sets_valid_to_via_canonical_mutation(monkeypatch):
    """A fresh (not already-closed) fact close commits a ``valid_to`` patch."""
    open_fact = _item("open-fact", status=MemoryItemStatus.active, valid_to=None)
    captured: dict = {}

    def fake_apply_mutation(uid, memory_id, *, mutation_kind, build_patch, operation_type, db_client):
        captured["memory_id"] = memory_id
        captured["mutation_kind"] = mutation_kind
        _logical, patch = build_patch(open_fact, NOW)
        captured["patch"] = patch
        closed = open_fact.model_copy(update={"status": MemoryItemStatus.superseded, **patch})
        return open_fact, closed

    monkeypatch.setattr(canonical_memory_adapter, "_read_canonical_memory_item_for_lineage", lambda *_a, **_k: None)
    monkeypatch.setattr(canonical_memory_adapter, "_apply_canonical_user_mutation", fake_apply_mutation)

    result = close_fact("u1", "open-fact", valid_to=NOW, db_client=object())

    assert captured["memory_id"] == "open-fact"
    assert captured["mutation_kind"] == "ledger_close"
    assert captured["patch"] == {"valid_to": NOW}
    assert result.status == MemoryItemStatus.superseded
    assert result.valid_to == NOW

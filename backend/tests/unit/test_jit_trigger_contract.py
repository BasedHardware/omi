import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

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
from utils.memory.jit_trigger_contract import (
    MAX_FEEDBACK_IDS,
    TriggerDecisionStatus,
    TriggerFeedback,
    TriggerFeedbackAction,
    TriggerEmbeddingPolicy,
    TriggerObservation,
    TriggerRuntimePolicy,
    apply_trigger_feedback,
    compile_memory_item_trigger,
    compile_trigger_condition,
    evaluate_memory_item_trigger,
    evaluate_trigger,
)
from utils.retrieval.tools.knowledge_ledger_write_tools import build_paid_trigger_condition

NOW = datetime(2026, 8, 23, 14, 30, tzinfo=timezone.utc)
SHARED_TRIGGER_MATRIX = (
    Path(__file__).resolve().parents[2].parent / "contracts" / "parity" / "jit_trigger_condition_matrix.json"
)
ADVERTISED_TOOL_MANIFEST = (
    Path(__file__).resolve().parents[2].parent
    / "desktop"
    / "macos"
    / "agent"
    / "tests"
    / "fixtures"
    / "tool-manifest.json"
)
EMBEDDING = {
    "prototype_id": "release-review",
    "prototype_revision": "prototype-v1",
    "model_id": "local-embedder",
    "model_version": "v1",
    "language": "en",
    "min_similarity": 0.82,
}
EMBEDDING_ATTESTATION = {
    "prototype_revision": "prototype-v1",
    "model_id": "local-embedder",
    "model_version": "v1",
    "language": "en",
}
ENABLED_EMBEDDING_POLICY = TriggerRuntimePolicy(
    embedding=TriggerEmbeddingPolicy(
        enabled=True,
        model_id="local-embedder",
        model_version="v1",
        language="en",
    )
)


def _trigger(condition: dict, **updates) -> MemoryItem:
    data = {
        "memory_id": "trigger-1",
        "uid": "uid-1",
        "version": 1,
        "tier": MemoryLayer.long_term,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "content": "Watch for release review conversations",
        "evidence": [
            MemoryEvidence(
                evidence_id="evidence-1",
                source_type="chat_turn",
                source_id="turn-1",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": True,
        "captured_at": NOW,
        "updated_at": NOW,
        "ledger_commit_id": "commit-1",
        "ledger_sequence": 1,
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": MemoryKind.trigger,
        "subject_scope": MemorySubjectScope.primary_user,
        "trigger_condition": condition,
        "intent_backed": True,
        "write_reason": LedgerWriteReason.standing_trigger,
    }
    data.update(updates)
    return MemoryItem(**data)


def test_compiler_normalizes_all_local_watchlist_selectors_deterministically():
    condition = {
        "schema_version": "jit_trigger.v1",
        "match_mode": "all",
        "entity_aliases": {"release_owner": ["David", " dave "]},
        "keywords": ["budget", "Release"],
        "regex": [r"ship\s+the\s+release"],
        "apps": ["Slack"],
        "windows": ["#release"],
        "time": {"weekdays": [5], "start": "09:00", "end": "17:00", "timezone": "UTC"},
        "calendar": {"event_keywords": ["release review"]},
        "embedding": EMBEDDING,
    }

    compiled = compile_trigger_condition(condition)

    assert compiled.as_condition() == {
        "schema_version": "jit_trigger.v1",
        "match_mode": "all",
        "entity_aliases": {"release_owner": ["dave", "david"]},
        "keywords": ["budget", "release"],
        "regex": [r"ship\s+the\s+release"],
        "apps": ["slack"],
        "windows": ["#release"],
        "time": {"weekdays": [5], "start": "09:00:00", "end": "17:00:00", "timezone": "UTC"},
        "calendar": {"event_keywords": ["release review"], "event_types": []},
        "embedding": EMBEDDING,
    }
    assert compiled.as_condition() == compile_trigger_condition(compiled.as_condition()).as_condition()


def test_trigger_action_is_bounded_typed_and_round_trips_with_selectors():
    compiled = compile_trigger_condition(
        {
            "keywords": ["release"],
            "action": {"type": "agent_prompt", "prompt": " Summarize the next release step. "},
        }
    )

    assert compiled.condition.action is not None
    assert compiled.condition.action.prompt == "Summarize the next release step."
    assert compile_trigger_condition(compiled.as_condition()).as_condition() == compiled.as_condition()
    with pytest.raises(ValueError):
        compile_trigger_condition({"keywords": ["release"], "action": {"type": "notify", "prompt": "x"}})
    with pytest.raises(ValueError):
        compile_trigger_condition({"keywords": ["release"], "action": {"type": "agent_prompt", "prompt": "x" * 2001}})


@pytest.mark.parametrize(
    "condition",
    [
        {"unknown": ["x"]},
        {"keywords": [f"x-{index}" for index in range(33)]},
        {"regex": ["["]},
        {"regex": [r"(a+)+$"]},
        {"keywords": ["x"], "extra": True},
        {"time": {"start": "09:00", "end": "17:00", "timezone": "Not/AZone"}},
        {"embedding": {"prototype_id": "x", "min_similarity": 2}},
        {"calendar": {}},
    ],
)
def test_compiler_rejects_unbounded_or_ambiguous_schema(condition):
    with pytest.raises((TypeError, ValueError)):
        compile_trigger_condition(condition)


def test_shared_model_facing_trigger_payloads_compile_in_backend():
    matrix = json.loads(SHARED_TRIGGER_MATRIX.read_text(encoding="utf-8"))

    for payload in matrix["valid_payloads"]:
        compiled = build_paid_trigger_condition(payload["description"], payload["condition"])
        assert compiled["action"] == {"type": "agent_prompt", "prompt": payload["description"]}
        assert compiled["schema_version"] == "jit_trigger.v1"


def test_shared_model_facing_trigger_payloads_validate_against_advertised_schema():
    matrix = json.loads(SHARED_TRIGGER_MATRIX.read_text(encoding="utf-8"))
    manifest = json.loads(ADVERTISED_TOOL_MANIFEST.read_text(encoding="utf-8"))
    tool = next(entry for entry in manifest if entry["name"] == "create_standing_trigger")
    validator = Draft202012Validator(tool["inputSchema"])
    Draft202012Validator.check_schema(tool["inputSchema"])

    for payload in matrix["valid_payloads"]:
        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
        assert errors == [], [error.message for error in errors]


@pytest.mark.parametrize(
    "payload",
    [
        {"description": "Watch for an incident", "condition": {"match_mode": "exact", "keywords": ["incident"]}},
        {"description": "Watch for an incident", "condition": {"regex": {"pattern": "incident"}}},
        {"description": "Watch for an incident", "condition": {"keywords": []}},
    ],
)
def test_advertised_schema_rejects_historical_malformed_trigger_shapes(payload):
    manifest = json.loads(ADVERTISED_TOOL_MANIFEST.read_text(encoding="utf-8"))
    tool = next(entry for entry in manifest if entry["name"] == "create_standing_trigger")
    validator = Draft202012Validator(tool["inputSchema"])

    assert list(validator.iter_errors(payload))


def test_all_conditions_match_and_double_run_is_byte_stable():
    compiled = compile_trigger_condition(
        {
            "entity_aliases": {"release_owner": ["David"]},
            "keywords": ["budget"],
            "regex": [r"ship\s+the\s+release"],
            "apps": ["Slack"],
            "windows": ["#release"],
            "time": {"weekdays": [6], "start": "09:00", "end": "17:00", "timezone": "UTC"},
            "calendar": {"event_keywords": ["release review"]},
            "embedding": EMBEDDING,
        }
    )
    observation = TriggerObservation(
        event_id="event-1",
        text="David and the team will ship the release after the budget review.",
        app_name="Slack",
        window_title="#release",
        occurred_at=NOW,
        calendar_events=[{"title": "Release review", "event_type": "meeting"}],
        calendar_authorized=True,
        embedding_scores={"release-review": 0.91},
        embedding_attestation=EMBEDDING_ATTESTATION,
    )

    first = evaluate_trigger(compiled, observation, policy=ENABLED_EMBEDDING_POLICY)
    second = evaluate_trigger(compiled, observation, policy=ENABLED_EMBEDDING_POLICY)

    assert first.status == TriggerDecisionStatus.match
    assert first.reason == "all_conditions_satisfied"
    assert first.matched_conditions == (
        "app",
        "calendar",
        "embedding:release-review",
        "entity:release_owner",
        "keywords",
        "regex",
        "time",
        "window",
    )
    assert first.matched_fraction == 1.0
    assert first.model_dump() == second.model_dump()


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.739999, TriggerDecisionStatus.no_match),
        (0.74, TriggerDecisionStatus.triage),
        (0.819999, TriggerDecisionStatus.triage),
        (0.82, TriggerDecisionStatus.match),
    ],
)
def test_embedding_boundaries_require_an_enabled_attested_runtime_policy(score, expected):
    compiled = compile_trigger_condition({"embedding": EMBEDDING})
    observation = TriggerObservation(
        embedding_scores={"release-review": score},
        embedding_attestation=EMBEDDING_ATTESTATION,
    )

    assert evaluate_trigger(compiled, observation).status == TriggerDecisionStatus.no_match
    assert evaluate_trigger(compiled, observation, policy=ENABLED_EMBEDDING_POLICY).status == expected


def test_missing_calendar_authority_and_embedding_scorer_fail_closed_without_triage():
    compiled = compile_trigger_condition(
        {
            "entity_aliases": {"owner": ["David", "Dave"]},
            "time": {"weekdays": [5], "start": "09:00", "end": "17:00", "timezone": "UTC"},
            "calendar": {"event_types": ["meeting"]},
            "embedding": {**EMBEDDING, "prototype_id": "release"},
        }
    )
    decision = evaluate_trigger(
        compiled,
        TriggerObservation(text="David mentioned the release but no local context was attached."),
    )
    assert decision.status == TriggerDecisionStatus.no_match
    assert decision.reason == "condition_not_satisfied"
    assert decision.missing_conditions == ("time",)


def test_ambiguous_entity_alias_is_triage_and_mismatch_is_no_match():
    compiled = compile_trigger_condition(
        {"entity_aliases": {"alice": ["Alex"], "alex": ["Alex"]}, "keywords": ["release"]}
    )
    ambiguous = evaluate_trigger(compiled, TriggerObservation(text="Alex discussed the release."))
    mismatch = evaluate_trigger(compiled, TriggerObservation(text="Jordan discussed the budget."))

    assert ambiguous.status == TriggerDecisionStatus.triage
    assert "entity:alex" in ambiguous.missing_conditions
    assert "entity:alice" in ambiguous.missing_conditions
    assert mismatch.status == TriggerDecisionStatus.no_match


def test_memory_item_contract_gates_lifecycle_without_persistence():
    condition = {"keywords": ["release"]}
    item = _trigger(condition)
    observation = TriggerObservation(text="release review", occurred_at=NOW)

    assert compile_memory_item_trigger(item).as_condition()["keywords"] == ["release"]
    assert evaluate_memory_item_trigger(item, observation).status == TriggerDecisionStatus.match
    hidden = item.model_copy(update={"status": MemoryItemStatus.hidden})
    assert evaluate_memory_item_trigger(hidden, observation).reason == "trigger_not_active"
    with pytest.raises(ValueError, match="not a trigger"):
        compile_memory_item_trigger(item.model_copy(update={"kind": MemoryKind.fact}))


def test_trigger_authority_validity_and_source_gates_fail_closed():
    item = _trigger({"keywords": ["release"]})
    observation = TriggerObservation(text="release", occurred_at=NOW)

    assert (
        evaluate_memory_item_trigger(item.model_copy(update={"ledger_schema_version": None}), observation).reason
        == "trigger_not_ledger_authoritative"
    )
    assert (
        evaluate_memory_item_trigger(item.model_copy(update={"valid_to": NOW}), observation).reason
        == "trigger_validity_closed"
    )
    assert (
        evaluate_memory_item_trigger(item.model_copy(update={"superseded_by": "trigger-2"}), observation).reason
        == "trigger_validity_closed"
    )
    assert (
        evaluate_memory_item_trigger(item.model_copy(update={"intent_backed": False}), observation).reason
        == "trigger_not_intent_authoritative"
    )
    assert (
        evaluate_memory_item_trigger(
            item.model_copy(
                update={
                    "subject_scope": MemorySubjectScope.third_party,
                    "subject_entity_id": "person-2",
                }
            ),
            observation,
        ).reason
        == "trigger_not_intent_authoritative"
    )
    assert (
        evaluate_memory_item_trigger(
            item.model_copy(update={"source_state": SourceState.tombstoned}), observation
        ).reason
        == "trigger_source_inactive"
    )


def test_trigger_observation_rejects_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        TriggerObservation(text="release", occurred_at=datetime(2026, 8, 23, 14, 30))


def test_feedback_is_bounded_idempotent_and_changes_trigger_state():
    item = _trigger({"keywords": ["release"]})
    reinforce = TriggerFeedback(
        feedback_id="1" * 64, action=TriggerFeedbackAction.reinforce, recorded_at=NOW + timedelta(minutes=1)
    )
    reinforced = apply_trigger_feedback(item, reinforce)
    duplicate = apply_trigger_feedback(reinforced.item, reinforce)
    snooze = TriggerFeedback(
        feedback_id="2" * 64,
        action=TriggerFeedbackAction.snooze,
        recorded_at=NOW + timedelta(minutes=2),
        snoozed_until=NOW + timedelta(hours=1),
    )
    snoozed = apply_trigger_feedback(reinforced.item, snooze)

    assert reinforced.applied is True
    assert reinforced.item.curation_weight == 1
    assert duplicate.applied is False
    assert duplicate.reason == "duplicate_feedback"
    assert evaluate_memory_item_trigger(snoozed.item, TriggerObservation(text="release", occurred_at=NOW)).reason == (
        "trigger_snoozed"
    )

    disabled = apply_trigger_feedback(
        snoozed.item,
        TriggerFeedback(feedback_id="3" * 64, action=TriggerFeedbackAction.disable, recorded_at=NOW),
    )
    assert disabled.item.status == MemoryItemStatus.hidden
    assert evaluate_memory_item_trigger(disabled.item, TriggerObservation(text="release", occurred_at=NOW)).status == (
        TriggerDecisionStatus.no_match
    )


def test_corrupted_snooze_state_fails_closed_without_crashing():
    item = _trigger(
        {"keywords": ["release"]},
        arguments={"jit_trigger_feedback": {"snoozed_until": "not-a-time"}},
    )

    decision = evaluate_memory_item_trigger(item, TriggerObservation(text="release", occurred_at=NOW))

    assert decision.status == TriggerDecisionStatus.no_match
    assert decision.reason == "trigger_feedback_invalid"


def test_snooze_without_observation_time_triages_without_wall_clock():
    snoozed = apply_trigger_feedback(
        _trigger({"keywords": ["release"]}),
        TriggerFeedback(
            feedback_id="4" * 64,
            action=TriggerFeedbackAction.snooze,
            recorded_at=NOW,
            snoozed_until=NOW + timedelta(hours=1),
        ),
    )

    decision = evaluate_memory_item_trigger(snoozed.item, TriggerObservation(text="release"))

    assert decision.status == TriggerDecisionStatus.triage
    assert decision.reason == "trigger_snooze_requires_observation_time"


def test_feedback_state_keeps_a_bounded_rolling_window_while_durable_receipts_own_idempotency():
    item = _trigger(
        {"keywords": ["release"]},
        arguments={
            "jit_trigger_feedback": {"applied_feedback_ids": [f"feedback-{index}" for index in range(MAX_FEEDBACK_IDS)]}
        },
    )
    update = apply_trigger_feedback(
        item,
        TriggerFeedback(
            feedback_id="f" * 64,
            action=TriggerFeedbackAction.reinforce,
            recorded_at=NOW,
        ),
    )

    assert update.applied is True
    state = update.item.arguments["jit_trigger_feedback"]
    assert len(state["applied_feedback_ids"]) == MAX_FEEDBACK_IDS
    assert state["applied_feedback_ids"][0] == "feedback-1"
    assert state["applied_feedback_ids"][-1] == "f" * 64


def test_same_feedback_id_with_different_payload_is_rejected():
    first = apply_trigger_feedback(
        _trigger({"keywords": ["release"]}),
        TriggerFeedback(feedback_id="a" * 64, action=TriggerFeedbackAction.useful, recorded_at=NOW),
    )

    with pytest.raises(ValueError, match="different payload"):
        apply_trigger_feedback(
            first.item,
            TriggerFeedback(feedback_id="a" * 64, action=TriggerFeedbackAction.false_positive, recorded_at=NOW),
        )


def test_evaluate_trigger_rejects_fading_row_when_belief_flag_on(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    item = _trigger({"keywords": ["release"]}).model_copy(
        update={
            "half_life_days": 1,
            "last_corroborated_at": NOW - timedelta(days=3),
            "captured_at": NOW - timedelta(days=3),
            "user_asserted": False,
        }
    )
    decision = evaluate_memory_item_trigger(item, TriggerObservation(text="release", occurred_at=NOW))
    assert decision.status == TriggerDecisionStatus.no_match
    assert decision.reason == "trigger_not_current_belief"


def test_evaluate_trigger_still_matches_when_belief_flag_off(monkeypatch):
    monkeypatch.delenv("MEMORY_BELIEF_MODEL_ENABLED", raising=False)
    item = _trigger({"keywords": ["release"]}).model_copy(
        update={
            "half_life_days": 1,
            "last_corroborated_at": NOW - timedelta(days=3),
            "captured_at": NOW - timedelta(days=3),
            "user_asserted": False,
        }
    )
    decision = evaluate_memory_item_trigger(item, TriggerObservation(text="release", occurred_at=NOW))
    assert decision.status == TriggerDecisionStatus.match

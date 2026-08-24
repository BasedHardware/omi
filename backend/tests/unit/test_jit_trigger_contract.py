from datetime import datetime, time, timedelta, timezone

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
from utils.memory.jit_trigger_contract import (
    MAX_FEEDBACK_IDS,
    TriggerDecisionStatus,
    TriggerFeedback,
    TriggerFeedbackAction,
    TriggerObservation,
    apply_trigger_feedback,
    compile_memory_item_trigger,
    compile_trigger_condition,
    evaluate_memory_item_trigger,
    evaluate_trigger,
)

NOW = datetime(2026, 8, 23, 14, 30, tzinfo=timezone.utc)


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
        "embedding": {"prototype_id": "release-review", "min_similarity": 0.8},
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
        "embedding": {"prototype_id": "release-review", "min_similarity": 0.8},
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
            "embedding": {"prototype_id": "release-review", "min_similarity": 0.8},
        }
    )
    observation = TriggerObservation(
        event_id="event-1",
        text="David and the team will ship the release after the budget review.",
        app_name="Slack",
        window_title="#release",
        occurred_at=NOW,
        calendar_events=[{"title": "Release review", "event_type": "meeting"}],
        embedding_scores={"release-review": 0.91},
    )

    first = evaluate_trigger(compiled, observation)
    second = evaluate_trigger(compiled, observation)

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


def test_missing_context_is_triage_not_a_false_match():
    compiled = compile_trigger_condition(
        {
            "entity_aliases": {"owner": ["David", "Dave"]},
            "time": {"weekdays": [5], "start": "09:00", "end": "17:00", "timezone": "UTC"},
            "calendar": {"event_types": ["meeting"]},
            "embedding": {"prototype_id": "release", "min_similarity": 0.8},
        }
    )
    decision = evaluate_trigger(
        compiled,
        TriggerObservation(text="David mentioned the release but no local context was attached."),
    )
    assert decision.status == TriggerDecisionStatus.triage
    assert decision.reason == "insufficient_or_ambiguous_context"
    assert decision.missing_conditions == ("calendar", "embedding:release", "time")


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
        feedback_id="feedback-1", action=TriggerFeedbackAction.reinforce, recorded_at=NOW + timedelta(minutes=1)
    )
    reinforced = apply_trigger_feedback(item, reinforce)
    duplicate = apply_trigger_feedback(reinforced.item, reinforce)
    snooze = TriggerFeedback(
        feedback_id="feedback-2",
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
        TriggerFeedback(feedback_id="feedback-3", action=TriggerFeedbackAction.disable, recorded_at=NOW),
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
            feedback_id="feedback-snooze",
            action=TriggerFeedbackAction.snooze,
            recorded_at=NOW,
            snoozed_until=NOW + timedelta(hours=1),
        ),
    )

    decision = evaluate_memory_item_trigger(snoozed.item, TriggerObservation(text="release"))

    assert decision.status == TriggerDecisionStatus.triage
    assert decision.reason == "trigger_snooze_requires_observation_time"


def test_feedback_history_fails_closed_instead_of_evicting_idempotency_keys():
    item = _trigger(
        {"keywords": ["release"]},
        arguments={
            "jit_trigger_feedback": {"applied_feedback_ids": [f"feedback-{index}" for index in range(MAX_FEEDBACK_IDS)]}
        },
    )
    update = apply_trigger_feedback(
        item,
        TriggerFeedback(
            feedback_id="feedback-new",
            action=TriggerFeedbackAction.reinforce,
            recorded_at=NOW,
        ),
    )

    assert update.applied is False
    assert update.reason == "feedback_history_full"
    assert update.item == item

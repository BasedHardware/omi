from datetime import date

import pytest

from utils.memory.daily_reconciliation import (
    MAX_CANDIDATES,
    plan_daily_reconciliation,
)


def _fact(**updates):
    data = {
        "candidate_id": "fact-alice-role",
        "kind": "fact",
        "operation": "add",
        "content": "Alice owns the release review",
        "evidence_ids": ["ev-conversation-1"],
        "source_refs": ["conversation:conversation-1"],
        "subject_entity_id": "person:alice",
    }
    data.update(updates)
    return data


def test_plan_is_review_only_bounded_and_byte_stable():
    candidates = [
        _fact(),
        _fact(
            candidate_id="trigger-release",
            kind="trigger",
            operation="repair",
            content="Watch for release review conversations",
            evidence_ids=["ev-conversation-2"],
            target_memory_id="trigger-1",
            trigger_condition={"schema_version": "jit_trigger.v1", "keywords": ["release", "review"]},
        ),
        _fact(
            candidate_id="direct-conflict",
            operation="amend",
            target_memory_id="fact-direct",
            target_is_direct_user_asserted=True,
        ),
        _fact(candidate_id="missing-evidence", evidence_ids=[]),
        _fact(candidate_id="fact-alice-role"),
    ]

    first = plan_daily_reconciliation("uid-1", "2026-08-23", candidates)
    second = plan_daily_reconciliation("uid-1", date(2026, 8, 23), candidates)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.status == "planned"
    assert first.input_count == 5
    assert len(first.proposals) == 3
    assert all(proposal.status == "review" and proposal.requires_review for proposal in first.proposals)
    assert all(proposal.idempotency_key.startswith("daily-reconciliation:") for proposal in first.proposals)
    assert {proposal.kind for proposal in first.proposals} == {"fact", "trigger"}
    assert any(proposal.reason_code == "direct_user_statement_conflict" for proposal in first.proposals)
    assert [item.reason_code for item in first.skipped] == ["duplicate_candidate", "missing_evidence"]


def test_missed_days_are_not_replayed_and_same_day_is_idempotently_skipped():
    candidate = _fact()
    missed = plan_daily_reconciliation(
        "uid-1",
        "2026-08-23",
        [candidate],
        last_swept_date="2026-08-20",
    )
    already = plan_daily_reconciliation(
        "uid-1",
        "2026-08-23",
        [candidate],
        last_swept_date="2026-08-23",
    )

    assert missed.sweep_date == date(2026, 8, 23)
    assert missed.missed_days_ignored == 2
    assert len(missed.proposals) == 1
    assert already.status == "already_swept"
    assert already.proposals == ()
    assert already.blocked_reason == "already_swept"


def test_input_window_overflow_fails_closed_without_partial_proposals():
    result = plan_daily_reconciliation(
        "uid-1",
        "2026-08-23",
        [_fact(candidate_id=f"f-{i}") for i in range(MAX_CANDIDATES + 1)],
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "input_window_exceeded"
    assert result.proposals == ()


def test_input_window_never_consumes_past_one_overflow_item():
    consumed = []

    def candidates():
        index = 0
        while True:
            consumed.append(index)
            yield _fact(candidate_id=f"unbounded-{index}")
            index += 1

    result = plan_daily_reconciliation("uid-1", "2026-08-23", candidates())

    assert result.status == "blocked"
    assert len(consumed) == MAX_CANDIDATES + 1


@pytest.mark.parametrize(
    "candidate",
    [
        _fact(evidence_ids=[]),
        _fact(kind="trigger", trigger_condition={}),
        _fact(
            kind="trigger",
            trigger_condition={"schema_version": "future", "keywords": ["release"]},
        ),
        _fact(
            kind="trigger",
            trigger_condition={
                "schema_version": "jit_trigger.v1",
                "keywords": [f"keyword-{index}" for index in range(100)],
            },
        ),
        _fact(trigger_condition={"keywords": ["not valid for facts"]}),
        _fact(operation="repair", target_memory_id=None),
        _fact(content="\n\t"),
    ],
)
def test_malformed_candidates_are_skipped_fail_closed(candidate):
    result = plan_daily_reconciliation("uid-1", "2026-08-23", [candidate])

    assert result.status == "planned"
    assert result.proposals == ()
    assert len(result.skipped) == 1
    assert result.skipped[0].reason_code in {"invalid_candidate", "missing_evidence"}


def test_invalid_sweep_state_fails_before_any_plan():
    with pytest.raises(ValueError, match="last_swept_date"):
        plan_daily_reconciliation("uid-1", "2026-08-23", [], last_swept_date="2026-08-24")
    with pytest.raises(ValueError, match="sweep_date"):
        plan_daily_reconciliation("uid-1", "not-a-date", [])

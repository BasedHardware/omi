from pydantic import ValidationError

from models.v17_memory_contracts import (
    DurableMemoryPatch,
    L2SearchPlan,
    LifecycleState,
    WorkingMemoryObservation,
    derive_allowed_use,
    deterministic_contract_id,
)


def test_working_memory_observation_uses_canonical_status_and_derived_allowed_use():
    observation = WorkingMemoryObservation(
        observation_id="obs_existing",
        packet_id="pkt_1",
        content="User prefers automatic memory capture.",
        evidence_ids=["ev_1"],
        source_refs=[{"source_id": "src_1", "quote": "I want something automatic."}],
        status=LifecycleState.working,
        confidence="high",
        risk_flags=[],
    )

    assert observation.allowed_use == "read_with_status"
    assert derive_allowed_use(LifecycleState.active, []) == "stable_profile_fact"
    assert derive_allowed_use(LifecycleState.review, []) == "review_only"
    assert derive_allowed_use(LifecycleState.working, ["secret"]) == "hidden"


def test_unknown_lifecycle_status_is_rejected():
    try:
        WorkingMemoryObservation(
            observation_id="obs_bad",
            packet_id="pkt_1",
            content="User prefers automatic memory capture.",
            evidence_ids=["ev_1"],
            source_refs=[{"source_id": "src_1", "quote": "I want something automatic."}],
            status="pending_consolidation",
            confidence="high",
        )
    except ValidationError as exc:
        assert "status" in str(exc)
    else:
        raise AssertionError("unknown lifecycle status should be rejected")


def test_durable_memory_patch_requires_target_for_merge_update_and_add_evidence():
    for decision in ["merge", "update", "add_evidence", "skip_duplicate"]:
        try:
            DurableMemoryPatch(
                patch_id="patch_1",
                packet_id="pkt_1",
                run_id="v17_test",
                observed_head_commit_id="head_1",
                idempotency_key="idem_1",
                decision=decision,
                result_status=LifecycleState.active,
                evidence_ids=["ev_1"],
            )
        except ValidationError as exc:
            assert "target_memory_id" in str(exc)
        else:
            raise AssertionError(f"{decision} should require target_memory_id")


def test_durable_memory_patch_idempotency_key_is_deterministic():
    first = deterministic_contract_id(
        "durable-patch",
        {"packet_id": "pkt_1", "decision": "add", "memory_text": "User prefers automatic memory capture."},
    )
    second = deterministic_contract_id(
        "durable-patch",
        {"memory_text": "User prefers automatic memory capture.", "decision": "add", "packet_id": "pkt_1"},
    )

    assert first == second
    assert len(first) == 64


def test_l2_search_plan_enforces_same_user_budget_and_labels_results():
    plan = L2SearchPlan(
        packet_id="pkt_1",
        search_budget=3,
        searches=[
            {"query": "automatic memory capture", "reason": "find existing preference memories"},
            {"query": "manual knowledge base", "reason": "find related dislike memories"},
            {"query": "digital second brain", "reason": "find related knowledge management memories"},
        ],
    )

    assert plan.same_user_only is True
    assert plan.read_only is True

    try:
        L2SearchPlan(
            packet_id="pkt_1",
            search_budget=3,
            searches=[
                {"query": "one", "reason": "1"},
                {"query": "two", "reason": "2"},
                {"query": "three", "reason": "3"},
                {"query": "four", "reason": "4"},
            ],
        )
    except ValidationError as exc:
        assert "searches" in str(exc)
    else:
        raise AssertionError("custom search plans must enforce the three-search budget")

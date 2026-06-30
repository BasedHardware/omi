import json

import pytest
from langchain_core.messages import AIMessage

from models.memory_contracts import DurablePatchDecision, LifecycleState
from utils.llm.promotion_proposals import (
    CandidateOutcomeStatus,
    SynthesisStatus,
    synthesize_durable_memory_patch_result,
    synthesize_durable_memory_patches,
)


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return AIMessage(content=json.dumps(self.payload))


def _packet():
    return {
        "packet_id": "pkt_auto_memory",
        "run_id": "memory_test_run",
        "evidence_ids": ["ev_1"],
        "source_refs": [{"evidence_id": "ev_1", "quote": "I want automatic memory capture."}],
        "observations": [
            {
                "content": "User wants automatic memory capture.",
                "evidence_ids": ["ev_1"],
                "source_refs": [{"evidence_id": "ev_1", "quote": "I want automatic memory capture."}],
            }
        ],
        "retrieved_memory_context": [
            {"memory_id": "mem_auto", "content": "User prefers automated memory systems.", "status": "active"}
        ],
    }


def _patch(decision, **overrides):
    payload = {
        "decision": decision,
        "result_status": "active" if decision in {"add", "add_evidence", "update", "merge", "keep_both"} else "review",
        "evidence_ids": ["ev_1"],
        "memory_text": "User prefers automatic memory capture.",
        "predicate": "prefers",
        "arguments": {"object": "automatic memory capture"},
        "confidence": "medium",
        "relationship_to_user": "self",
        "subject_entity_id": "user",
        "subject_label": "the user",
        "aboutness": "primary_user",
        "rationale": "Supported by direct quote.",
    }
    payload.update(overrides)
    return payload


def test_l2_patch_synthesizer_covers_all_patch_decisions_with_mocked_llm():
    decisions = [decision.value for decision in DurablePatchDecision]
    patches = []
    for decision in decisions:
        overrides = {}
        if decision in {"merge", "update", "add_evidence", "skip_duplicate"}:
            overrides["target_memory_id"] = "mem_auto"
        if decision in {"context_only", "reject", "review", "skip_duplicate"}:
            if decision == "review":
                overrides["result_status"] = "review"
            elif decision == "reject":
                overrides["result_status"] = "rejected"
            else:
                overrides["result_status"] = decision.replace("skip_duplicate", "active")
            overrides["memory_text"] = None
        patches.append(_patch(decision, **overrides))

    result = synthesize_durable_memory_patches(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": patches}),
    )

    assert [patch.decision.value for patch in result] == decisions
    assert all(patch.patch_id for patch in result)
    assert all(patch.idempotency_key for patch in result)


def test_l2_patch_synthesizer_requires_target_memory_ids_for_existing_memory_decisions():
    result = synthesize_durable_memory_patch_result(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": [_patch("merge", target_memory_id=None)]}),
    )

    assert result.status == SynthesisStatus.retryable_failure
    assert result.outcomes[0].status == CandidateOutcomeStatus.invalid
    assert result.outcomes[0].reason_code == "validation_error"


def test_l2_patch_synthesizer_rejects_quote_wrapper_card():
    result = synthesize_durable_memory_patch_result(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": [_patch("add", memory_text='User said "I want automatic memory capture."')]}),
    )

    assert result.status == SynthesisStatus.success
    assert result.patches == []
    assert result.outcomes[0].status == CandidateOutcomeStatus.reject


def test_l2_patch_synthesizer_prompt_includes_existing_memory_context_for_merge_update_skip():
    fake = FakeLLM({"patches": [_patch("add_evidence", target_memory_id="mem_auto")]})

    result = synthesize_durable_memory_patches(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=fake,
    )

    prompt_text = "\n".join(str(message.content) for message in fake.messages)
    assert result[0].target_memory_id == "mem_auto"
    assert "mem_auto" in prompt_text
    assert "User prefers automated memory systems" in prompt_text


def test_l2_patch_contract_preserves_relationship_entity_and_confidence_for_benchmark_parity():
    result = synthesize_durable_memory_patches(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM(
            {
                "patches": [
                    _patch(
                        "add",
                        confidence="high",
                        relationship_to_user="self",
                        subject_entity_id="user",
                        subject_label="the user",
                        aboutness="primary_user",
                    )
                ]
            }
        ),
    )

    assert result[0].confidence == "high"
    assert result[0].relationship_to_user == "self"
    assert result[0].subject_entity_id == "user"
    assert result[0].subject_label == "the user"
    assert result[0].aboutness == "primary_user"


def test_l2_patch_prompt_contains_production_usefulness_rubric_and_drift_marker():
    fake = FakeLLM({"patches": [_patch("add")]})

    synthesize_durable_memory_patches(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=fake,
    )

    prompt_text = "\n".join(str(message.content) for message in fake.messages)
    assert "PROMOTION RUBRIC" in prompt_text
    assert "Future agent/user would benefit from remembering this" in prompt_text
    assert "Use review when attribution, durability, or sensitivity is uncertain" in prompt_text
    assert "DRIFT GUARD" in prompt_text


def test_l2_patch_safety_guard_keeps_third_party_or_encountered_out_of_active_memory():
    result = synthesize_durable_memory_patches(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM(
            {
                "patches": [
                    _patch(
                        "add",
                        memory_text="Karl Beckner is on assignment in Kabul.",
                        relationship_to_user="encountered",
                        aboutness="third_party",
                        subject_label="Karl Beckner",
                    )
                ]
            }
        ),
    )

    assert result[0].decision.value == "context_only"
    assert result[0].result_status.value == "context_only"
    assert result[0].memory_text is None


def test_l2_patch_safety_guard_routes_unclear_active_memory_to_review():
    result = synthesize_durable_memory_patches(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": [_patch("add", relationship_to_user="unclear", aboutness="unclear")]}),
    )

    assert result[0].result_status.value == "review"
    assert result[0].decision.value == "review"


def test_compatibility_wrapper_raises_on_retryable_failure():
    with pytest.raises(RuntimeError):
        synthesize_durable_memory_patches(
            packet=_packet(),
            custom_search_artifact={"search_results": []},
            observed_head_commit_id="head_1",
            llm=FakeLLM({"patches": []}),
        )

import json

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from models.memory_contracts import DurablePatchDecision, LifecycleState, MemoryTier, SourceBackedMemoryCandidate
from utils.llm.promotion_proposals import (
    CandidateOutcomeStatus,
    SynthesisStatus,
    synthesize_durable_memory_patch_result,
)


class FakeLLM:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return AIMessage(content=json.dumps(self.payload))


def _packet():
    return {
        "packet_id": "pkt_auto_memory",
        "run_id": "memory_test_run",
        "evidence_ids": ["ev_1", "ev_2"],
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


def test_source_backed_candidate_defaults_to_short_term_not_archive():
    candidate = SourceBackedMemoryCandidate(
        candidate_id="cand_1",
        user_id="u1",
        source_id="conv1",
        source_type="conversation",
        source_version="v1",
        text="User wants automatic memory capture.",
        evidence_ids=["ev_1"],
        captured_at="2026-06-19T00:00:00+00:00",
        expires_at="2026-07-19T00:00:00+00:00",
    )

    assert candidate.initial_tier == MemoryTier.short_term
    assert candidate.archive_id is None
    assert candidate.default_access_candidate is True


def test_source_backed_candidate_blocks_default_access_for_secret_risks_and_naive_times():
    candidate = SourceBackedMemoryCandidate(
        candidate_id="cand_secret",
        user_id="u1",
        source_id="conv1",
        source_type="conversation",
        source_version="v1",
        text="The API key is sk-...",
        evidence_ids=["ev_1"],
        risk_flags=["credential"],
        captured_at="2026-06-19T00:00:00+00:00",
        expires_at="2026-07-19T00:00:00+00:00",
    )
    assert candidate.default_access_candidate is False

    try:
        SourceBackedMemoryCandidate(
            candidate_id="cand_bad_time",
            user_id="u1",
            source_id="conv1",
            source_type="conversation",
            source_version="v1",
            text="User wants automatic memory capture.",
            evidence_ids=["ev_1"],
            captured_at="2026-06-19T00:00:00",
            expires_at="2026-07-19T00:00:00",
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("naive timestamps must be rejected")


def test_synthesis_result_reports_provider_failure_without_empty_list_semantics():
    result = synthesize_durable_memory_patch_result(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM(error=TimeoutError("provider timed out")),
    )

    assert result.status == SynthesisStatus.retryable_failure
    assert result.patches == []
    assert result.error_code == "provider_error"
    assert result.synthesis_terminal is False


def test_empty_output_without_explicit_noop_is_retryable():
    result = synthesize_durable_memory_patch_result(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": []}),
    )
    assert result.status == SynthesisStatus.retryable_failure
    assert result.error_code == "empty_output_without_explicit_noop"
    assert result.synthesis_terminal is False


def test_synthesis_result_validates_each_candidate_independently_and_records_invalid_outcome():
    result = synthesize_durable_memory_patch_result(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": [_patch("add"), _patch("merge", target_memory_id=None)]}),
    )

    assert result.status == SynthesisStatus.partial
    assert len(result.patches) == 1
    assert result.outcomes[0].status == CandidateOutcomeStatus.proposed
    assert result.outcomes[1].status == CandidateOutcomeStatus.invalid
    assert result.outcomes[1].reason_code == "validation_error"
    assert result.synthesis_terminal is True


def test_quote_wrapper_becomes_audited_reject_not_silent_drop():
    result = synthesize_durable_memory_patch_result(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": [_patch("add", memory_text='User said "I want automatic memory capture."')]}),
    )

    assert result.status == SynthesisStatus.success
    assert result.patches == []
    assert result.outcomes[0].status == CandidateOutcomeStatus.reject
    assert result.outcomes[0].reason_code == "quote_wrapper_quality_guard"
    assert result.synthesis_terminal is True


def test_model_supplied_control_fields_are_rejected_and_all_invalid_retries():
    result = synthesize_durable_memory_patch_result(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": [_patch("add", patch_id="evil", idempotency_key="reuse_me")]}),
    )

    assert result.status == SynthesisStatus.retryable_failure
    assert result.patches == []
    assert result.outcomes[0].status == CandidateOutcomeStatus.invalid
    assert result.outcomes[0].reason_code == "untrusted_control_field"


def test_logical_operation_fingerprint_is_stable_across_head_and_output_order():
    first = synthesize_durable_memory_patch_result(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": [_patch("add", evidence_ids=["ev_2", "ev_1"])]}),
    )
    second = synthesize_durable_memory_patch_result(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_2",
        llm=FakeLLM({"patches": [_patch("add", evidence_ids=["ev_1", "ev_2"])]}),
    )

    assert first.patches[0].idempotency_key == second.patches[0].idempotency_key
    assert first.patches[0].observed_head_commit_id == "head_1"
    assert second.patches[0].observed_head_commit_id == "head_2"


def test_evidence_ids_must_belong_to_packet():
    result = synthesize_durable_memory_patch_result(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": [_patch("add", evidence_ids=["ev_missing"])]}),
    )

    assert result.status == SynthesisStatus.retryable_failure
    assert result.patches == []
    assert result.outcomes[0].status == CandidateOutcomeStatus.invalid
    assert result.outcomes[0].reason_code == "evidence_not_in_packet"


def test_target_memory_must_be_same_user_retrieved_context():
    result = synthesize_durable_memory_patch_result(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": [_patch("update", target_memory_id="mem_other")]}),
    )

    assert result.status == SynthesisStatus.retryable_failure
    assert result.outcomes[0].reason_code == "memory_ref_not_authorized"

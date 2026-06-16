import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from utils.memory_ingestion.models import WorkingMemoryCandidate, WorkingMemoryEvidence


def _evidence(**overrides):
    data = {
        "evidence_id": "ev_voice_1",
        "source_id": "raw_voice_1",
        "source_unit_id": "raw_voice_1:seg:1",
        "quote": "I always watch Knicks games with my dad on Sundays.",
        "source_type": "voice_transcript",
        "source_signal": "direct_user",
        "source_speaker_label": "speaker_0",
        "speaker_scope": "session-local",
        "capture_confidence": "high",
    }
    data.update(overrides)
    return WorkingMemoryEvidence(**data)


def test_working_memory_candidate_allows_broad_source_grounded_l1_candidate():
    candidate = WorkingMemoryCandidate(
        candidate_id="wmc_1",
        user_id="user_1",
        session_id="session_1",
        source_id="raw_voice_1",
        source_type="voice_transcript",
        candidate_text="User always watches Knicks games with their dad on Sundays.",
        subject_scope="primary_user",
        subject_evidence_type="direct_user_statement",
        actor_role="user",
        evidence=[_evidence()],
        capture_confidence="high",
        candidate_kind_hint="relationship_context",
        risk_flags=[],
        route_hint="pending_l2",
        allowed_use="read_with_status",
    )

    assert candidate.schema_version == "working_memory_candidate.v1"
    assert candidate.evidence[0].speaker_scope == "session-local"
    assert candidate.route_hint == "pending_l2"
    assert candidate.allowed_use == "read_with_status"


def test_working_memory_candidate_rejects_circular_evidence_quote():
    with pytest.raises(ValidationError, match="source quote"):
        WorkingMemoryCandidate(
            candidate_id="wmc_circular",
            user_id="user_1",
            session_id="session_1",
            source_id="raw_voice_1",
            source_type="voice_transcript",
            candidate_text="User works on Omi.",
            subject_scope="primary_user",
            subject_evidence_type="direct_user_statement",
            actor_role="user",
            evidence=[_evidence(quote="User works on Omi.")],
            capture_confidence="medium",
            candidate_kind_hint="project_context",
            route_hint="pending_l2",
            allowed_use="read_with_status",
        )


def test_working_memory_candidate_requires_evidence_for_metric_eligible_candidates():
    with pytest.raises(ValidationError, match="evidence"):
        WorkingMemoryCandidate(
            candidate_id="wmc_no_evidence",
            user_id="user_1",
            session_id="session_1",
            source_id="raw_chat_1",
            source_type="chat_exchange",
            candidate_text="User prefers concise answers.",
            subject_scope="primary_user",
            subject_evidence_type="direct_user_statement",
            actor_role="user",
            evidence=[],
            capture_confidence="high",
            candidate_kind_hint="preference",
            route_hint="pending_l2",
            allowed_use="read_with_status",
        )


def test_working_memory_candidate_forbids_l2_durable_state_fields():
    with pytest.raises(ValidationError):
        WorkingMemoryCandidate.model_validate(
            {
                "candidate_id": "wmc_extra",
                "user_id": "user_1",
                "session_id": "session_1",
                "source_id": "raw_chat_1",
                "source_type": "chat_exchange",
                "candidate_text": "User prefers concise answers.",
                "subject_scope": "primary_user",
                "subject_evidence_type": "direct_user_statement",
                "actor_role": "user",
                "evidence": [_evidence(source_type="chat_exchange", source_signal="direct_user").model_dump()],
                "capture_confidence": "high",
                "candidate_kind_hint": "preference",
                "route_hint": "pending_l2",
                "allowed_use": "read_with_status",
                "memory_state": "active",
            }
        )


def test_v15_1_schema_fixtures_validate_and_cover_required_families():
    fixture_path = Path(__file__).parent / "fixtures" / "working_memory_candidates_v15_1.jsonl"
    rows = [json.loads(line) for line in fixture_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    candidates = [WorkingMemoryCandidate.model_validate(row) for row in rows]
    assert {candidate.candidate_id for candidate in candidates} == {
        "wmc_direct_user_statement",
        "wmc_assistant_observed_activity",
        "wmc_ocr_workspace_signal",
        "wmc_non_primary_speaker_context",
        "wmc_bundled_candidate_needs_split",
        "wmc_hard_secret_scrubbed_source",
    }
    assert all(candidate.evidence for candidate in candidates)
    assert all(
        candidate.allowed_use in {"read_with_status", "review_only", "context_only", "hidden_until_l2"}
        for candidate in candidates
    )

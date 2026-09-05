"""Contract tests for the frozen baseline/JIT quality and cost corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIXTURE = (
    Path(__file__).parents[2] / "testing" / "jit_processing" / "fixtures" / "jit_architecture_quality_cost_v1.json"
)
V2_FIXTURE = FIXTURE.with_name("jit_architecture_quality_cost_v2.json")


def test_frozen_corpus_has_identical_evidence_and_stable_prompt_hashes() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert fixture["schema_version"] == "jit_architecture_quality_cost.v1"
    assert fixture["provenance"].startswith("synthetic-only; frozen before any model call")
    assert fixture["execution_contract"]["same_evidence_required"] is True
    assert len(fixture["cases"]) >= 5

    for case in fixture["cases"]:
        evidence = json.dumps(case["evidence"], sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(evidence.encode("utf-8")).hexdigest() == case["same_evidence_sha256"]
        assert set(case["prompts"]) == {"legacy", "jit"}
        for prompt in case["prompts"].values():
            assert hashlib.sha256(prompt["text"].encode("utf-8")).hexdigest() == prompt["sha256"]
            assert prompt["text"]
            assert prompt["source"]


def test_frozen_corpus_pins_safety_caps_and_adjudication_cases() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    contract = fixture["execution_contract"]

    assert contract["hard_caps"] == {
        "notifications_per_day": 3,
        "nano_triage_per_day": 8,
        "full_turns_per_day": 3,
        "full_turns_per_candidate": 1,
    }
    assert contract["operational_cost_cap_usd"] == 5.0
    assert {
        "empty_context",
        "derived_intent_match",
        "ambiguous_match",
        "already_visible",
        "duplicate_delivery",
        "timezone_boundary",
    } <= {case["category"] for case in fixture["cases"]}

    by_id = {case["case_id"]: case for case in fixture["cases"]}
    assert by_id["empty_context_silence"]["expected"]["decision"] == "silence"
    assert by_id["exact_intent_actionable"]["expected"]["grounded_fact_ids"] == ["fact:release-review"]
    assert by_id["duplicate_recent_delivery_silence"]["expected"]["full_turn_allowed"] is False
    assert by_id["dst_local_deadline"]["evidence"]["timezone"] == "America/New_York"


def test_v2_replays_real_prompt_builders_without_provider_calls() -> None:
    fixture = json.loads(V2_FIXTURE.read_text(encoding="utf-8"))

    assert fixture["schema_version"] == "jit_architecture_quality_cost.v2"
    assert fixture["supersedes"].endswith("_v1.json")
    assert len(fixture["v1_rejected_rationale"]) == 3
    assert fixture["execution_contract"]["paid_run_status"] == ("blocked_until_billing_resolution_and_parent_approval")
    assert fixture["billing_receipt_contract"]["resolution_status"].startswith("pending")
    assert fixture["billing_receipt_contract"]["provider"] is None
    assert fixture["billing_receipt_contract"]["model"] is None

    brief = fixture["prompt_contract"]["fixed_general_brief"]
    assert fixture["prompt_contract"]["expected_labels_not_in_prompt"] is True
    assert fixture["execution_contract"]["same_available_context_required"] is True
    assert len(fixture["cases"]) >= 5

    for case in fixture["cases"]:
        evidence = json.dumps(case["shared_evidence"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert hashlib.sha256(evidence.encode("utf-8")).hexdigest() == case["shared_evidence_sha256"]
        assert case["prompt_inputs"]["fixed_general_brief"] == brief

        legacy = case["prompts"]["legacy"]
        materialized_legacy = legacy["materialized_prompt"]
        if materialized_legacy is None:
            assert case["execution_schedule"]["legacy"]["full_reasoning_calls_exact"] == 0
            assert legacy["prompt_sha256"] is None
            assert legacy["uncached_prompt_sha256"] is None
        else:
            assert hashlib.sha256(materialized_legacy.encode("utf-8")).hexdigest() == legacy["prompt_sha256"]
            assert (
                hashlib.sha256(legacy["materialized_uncached_prompt"].encode("utf-8")).hexdigest()
                == legacy["uncached_prompt_sha256"]
            )
            assert legacy["operation"] == "proactive_reasoning"
            assert legacy["max_completion_tokens"] == 800

        jit = case["prompts"]["jit"]
        assert hashlib.sha256(jit["materialized_nano_prompt"].encode("utf-8")).hexdigest() == jit["nano_prompt_sha256"]
        assert (
            hashlib.sha256(jit["materialized_full_system_prompt"].encode("utf-8")).hexdigest()
            == jit["full_system_prompt_sha256"]
        )
        assert hashlib.sha256(jit["materialized_full_prompt"].encode("utf-8")).hexdigest() == jit["full_prompt_sha256"]
        # The only case-specific bytes in the JIT execution instruction are the
        # shared evidence projection; every case uses one identical general brief.
        assert brief in jit["materialized_full_prompt"]
        assert case["review_oracle"]["reason"] not in jit["materialized_full_prompt"]


def test_v2_records_real_lane_schedules_and_hard_caps() -> None:
    fixture = json.loads(V2_FIXTURE.read_text(encoding="utf-8"))
    contract = fixture["execution_contract"]
    assert contract["hard_caps"] == {
        "notifications_per_day": 3,
        "nano_triage_per_day": 8,
        "full_turns_per_day": 3,
        "full_turns_per_candidate": 1,
    }
    assert contract["operational_cost_cap_usd"] == 5.0

    by_id = {case["case_id"]: case for case in fixture["cases"]}
    assert by_id["empty_context_silence"]["execution_schedule"]["legacy"]["full_reasoning_calls_exact"] == 0
    for case in fixture["cases"]:
        facts = case["shared_evidence"]["validated_facts"]
        expected = 0 if not facts else 1
        assert case["execution_schedule"]["legacy"]["full_reasoning_calls_exact"] == expected
        assert case["execution_schedule"]["jit"]["nano_triage_calls_exact"] == expected
        assert case["execution_schedule"]["jit"]["full_turns_per_candidate_max"] == 1
        assert case["review_oracle"]["oracle_is_not_sent_to_provider"] is True

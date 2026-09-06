"""Contract tests for the frozen baseline/JIT quality and cost corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIXTURE = (
    Path(__file__).parents[2] / "testing" / "jit_processing" / "fixtures" / "jit_architecture_quality_cost_v1.json"
)
V2_FIXTURE = FIXTURE.with_name("jit_architecture_quality_cost_v2.json")
NANO_PROMPT_BUILDER_SOURCE = (
    Path(__file__).parents[3]
    / "desktop"
    / "macos"
    / "Desktop"
    / "Sources"
    / "ProactiveAssistants"
    / "Core"
    / "JITProactivityDelivery.swift"
)
NANO_RUNTIME_SOURCE = (
    Path(__file__).parents[3]
    / "desktop"
    / "macos"
    / "Desktop"
    / "Sources"
    / "ProactiveAssistants"
    / "Core"
    / "JITProactivityRuntime.swift"
)


def _production_nano_prompt_prefix() -> str:
    """Materialize the literal prefix from the production Swift source.

    The interpolation line is intentionally excluded; this verifies the byte
    boundary before each fixture's bounded evidence without duplicating the
    production prompt in a Python constant.
    """

    builder_source = (
        NANO_PROMPT_BUILDER_SOURCE.read_text(encoding="utf-8") if NANO_PROMPT_BUILDER_SOURCE.exists() else ""
    )
    if "static func nanoTriagePrompt" in builder_source:
        source = builder_source
        operation = source.index("static func nanoTriagePrompt")
        start = source.index('"""', operation) + len('"""')
        end = source.index('"""', start)
    else:
        source = NANO_RUNTIME_SOURCE.read_text(encoding="utf-8")
        operation = source.index("operation: ModelQoS.Proactivity.extractionOperation")
        start = source.index('prompt: """', operation) + len('prompt: """')
        end = source.index('""",', start)
    lines = source[start:end].splitlines()
    # The first line is the newline after the opening delimiter.  Stop at the
    # evidence interpolation so later source-owned temporal sections do not
    # change this fixture's deliberately prefix-only contract.
    evidence_line = next(index for index, line in enumerate(lines) if "\\(context.boundedEvidence)" in line)
    indentation = len(lines[1]) - len(lines[1].lstrip())
    return "\n".join(line[indentation:] for line in lines[1:evidence_line]) + "\n"


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
    assert fixture["execution_contract"]["paid_run_status"] == (
        "blocked_until_runtime_cost_receipts_full_cap_and_parent_approval"
    )
    assert fixture["billing_receipt_contract"]["resolution_status"].startswith("runtime_routes_resolved")
    assert fixture["billing_receipt_contract"]["provider"] is None
    assert fixture["billing_receipt_contract"]["model"] is None

    brief = fixture["prompt_contract"]["fixed_general_brief"]
    assert fixture["prompt_contract"]["expected_labels_not_in_prompt"] is True
    assert fixture["execution_contract"]["same_available_context_required"] is False
    assert fixture["prompt_replay_scope"]["status"] == "prompt_only_proxy"
    assert fixture["prompt_replay_scope"]["provider_calls_executed"] == 0

    routes = fixture["billing_receipt_contract"]["runtime_route_contract"]
    assert routes["legacy_director"]["gateway_lane"] == "omi:auto:desktop-proactive-reasoning"
    assert routes["legacy_director"]["model"] == "gpt-5.6-luna"
    assert routes["jit_nano"]["gateway_lane"] == "omi:auto:desktop-proactive-extraction"
    assert routes["jit_nano"]["model"] == "gpt-5-nano"
    assert routes["jit_full"]["gateway_lane"] == "omi:auto:chat-agent"
    assert routes["jit_full"]["requested_model_alias"] == "claude-sonnet-4-6 -> omi-sonnet"
    assert routes["jit_full"]["model"] == "gpt-5.6-luna"
    assert routes["jit_full"]["requested_max_completion_tokens"] is None
    for environment in ("dev", "prod"):
        configured = routes["configured_runtime"][environment]
        assert configured["OMI_LLM_GATEWAY_FEATURE_MODE"] == "gateway"
        assert configured["OMI_LLM_CHAT_AGENT_ROUTE"] == "gateway"
        assert configured["OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION"] == "false"

    prefix = _production_nano_prompt_prefix()
    assert hashlib.sha256(prefix.encode("utf-8")).hexdigest() == (
        fixture["prompt_contract"]["nano_materialization"]["source_prompt_prefix_sha256"]
    )
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
        bounded_evidence = case["prompt_inputs"]["jit_projection"]["bounded_evidence"]
        assert jit["materialized_nano_prompt"] == prefix + bounded_evidence
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
        assert jit["full_operation"] == "chat_agent"
        assert jit["full_gateway_lane"] == "omi:auto:chat-agent"
        assert jit["full_model"] == "gpt-5.6-luna"
        assert jit["full_max_completion_tokens"] is None

    dst = next(case for case in fixture["cases"] if case["case_id"] == "dst_local_deadline")
    assert dst["comparability"]["status"] == "blocked_context_gap"


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

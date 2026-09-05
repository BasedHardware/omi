"""Contract tests for the frozen baseline/JIT quality and cost corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIXTURE = (
    Path(__file__).parents[2] / "testing" / "jit_processing" / "fixtures" / "jit_architecture_quality_cost_v1.json"
)


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

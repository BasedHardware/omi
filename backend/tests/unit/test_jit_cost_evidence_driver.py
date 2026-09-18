"""Tests for the no-call matched-input JIT cost-evidence driver."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.jit_cost_evidence_driver as driver

FIXTURE = (
    Path(__file__).parents[2] / "testing" / "jit_processing" / "fixtures" / "jit_architecture_quality_cost_v2.json"
)


@pytest.fixture()
def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _plan(fixture: dict) -> dict:
    return driver.build_plan(fixture, driver.DEFAULT_CASE_IDS)


def _receipt(plan: dict, case_id: str, architecture: str, stage: str, *, attempt_id: str) -> tuple[dict, dict]:
    case = next(item for item in plan["cases"] if item["case_id"] == case_id)
    expected = case["legacy"] if architecture == "legacy" else case["jit"][stage]
    route = expected["route"]
    hashes = expected["prompt_hashes"]
    provider_receipt = {
        "attempt_id": attempt_id,
        "request_id": f"request-{attempt_id}",
        "api_surface": "openai_chat_completions",
        "invocation_id": f"invocation-{attempt_id}",
        "provider": route["provider"],
        "configured_model": route["served_model"],
        "actual_model_version": route["served_model"],
        "usage_status": "confirmed",
        "uncached_input_tokens": 100,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 20,
        "cache_write_ttl": None,
        "cache_status": "not_requested",
        "cost_status": "estimated",
        "rate_card_id": route["rate_card_id"],
        "cost_basis": "fixture-test",
        "estimated_cost_micro_usd": 100,
    }
    sidecar = {
        "run_id": "run-1",
        "attempt_ids": [attempt_id],
        "case_id": case_id,
        "architecture": architecture,
        "stage": stage,
        "gateway_lane": route["gateway_lane"],
        "evidence_sha256": case["matched_input"]["evidence_sha256"],
        "prompt_sha256": hashes["prompt_sha256"],
        "tool_rounds": 0,
    }
    sidecar.update({key: value for key, value in hashes.items() if key != "prompt_sha256"})
    return provider_receipt, sidecar


def _jit_gateway_receipt(provider_receipts: list[dict], *, run_id: str = "run-1") -> dict:
    return {
        "schema_version": "jit-gateway-receipt-v1",
        "run_id": run_id,
        "contract_version": "jit-cloud-qa-v1",
        "attempts": [
            {
                "attempt_id": receipt["attempt_id"],
                "provider": receipt["provider"],
                "configured_model": receipt["configured_model"],
                "actual_model_version": receipt["actual_model_version"],
                "rate_card_id": receipt["rate_card_id"],
                "cost_basis": receipt["cost_basis"],
                "usage_status": receipt["usage_status"],
                "cost_status": receipt["cost_status"],
                "normalized_uncached_input_tokens": receipt["uncached_input_tokens"],
                "cached_input_tokens": receipt["cached_input_tokens"],
                "cache_write_tokens": receipt["cache_write_tokens"],
                "output_tokens": receipt["output_tokens"],
                "estimated_cost_micro_usd": receipt.get("estimated_cost_micro_usd"),
            }
            for receipt in provider_receipts
        ],
        "aggregate": {
            "attempt_count": len(provider_receipts),
            "normalized_uncached_input_tokens": sum(item["uncached_input_tokens"] for item in provider_receipts),
            "cached_input_tokens": sum(item["cached_input_tokens"] for item in provider_receipts),
            "cache_write_tokens": sum(item["cache_write_tokens"] for item in provider_receipts),
            "output_tokens": sum(item["output_tokens"] for item in provider_receipts),
            "estimated_cost_micro_usd": sum(item.get("estimated_cost_micro_usd") or 0 for item in provider_receipts),
            "cost_status": "estimated",
        },
    }


def test_plan_is_explicitly_prompt_only_and_preserves_caps(fixture: dict) -> None:
    plan = _plan(fixture)

    assert plan["status"] == "matched_input_plan"
    assert plan["evidence_scope"] == "prompt_only_proxy; no provider calls"
    assert plan["caps"] == driver.CAPS
    assert plan["minimum_runtime_sample"]["matched_cases"] == 3
    assert plan["minimum_runtime_sample"]["maximum_reserved_jit_full_usd"] == pytest.approx(0.15)
    for case in plan["cases"]:
        assert case["matched_input"]["evaluation_time"] == "2026-09-05T10:00:00-04:00"
        assert case["matched_input"]["timezone"] == "America/New_York"
        assert case["legacy"]["route"]["served_model"] == "gpt-5.6-luna"
        assert case["jit"]["nano"]["route"]["served_model"] == "gpt-5-nano"
        assert case["jit"]["full"]["route"]["gateway_lane"] == "omi:auto:chat-agent"


def test_receipt_summary_counts_every_gateway_tool_and_cache_unit(fixture: dict) -> None:
    plan = _plan(fixture)
    legacy_provider_receipts = []
    jit_provider_receipts = []
    jit_gateway_receipts = []
    sidecars = []
    index = 0
    for case_id in driver.DEFAULT_CASE_IDS:
        for architecture, stage in (("legacy", "full"), ("jit", "nano"), ("jit", "full")):
            provider_receipt, sidecar = _receipt(plan, case_id, architecture, stage, attempt_id=f"attempt-{index}")
            sidecar["tool_rounds"] = 3 if index == 1 else 0
            if index in {1, 2}:
                provider_receipt["cached_input_tokens"] = 1
            if architecture == "legacy":
                legacy_provider_receipts.append(provider_receipt)
            else:
                jit_provider_receipts.append(provider_receipt)
                jit_gateway_receipts.append(_jit_gateway_receipt([provider_receipt]))
            sidecars.append(sidecar)
            index += 1
    result = driver.summarize_receipts(
        plan,
        {
            "legacy_provider_receipts": legacy_provider_receipts,
            "jit_gateway_receipts": jit_gateway_receipts,
            "legacy_receipt_source": "llm_gateway_attempts",
            "sidecars": sidecars,
        },
    )

    assert result["status"] == "known"
    assert result["operations"] == 9
    assert result["gateway_attempts"] == 9
    assert result["tool_rounds"] == 3
    assert result["cache_units"] == 2
    assert result["cost_micro_usd"] == 900


def test_receipt_summary_allows_one_fresh_run_id_per_case(fixture: dict) -> None:
    plan = _plan(fixture)
    legacy_provider_receipts = []
    jit_gateway_receipts = []
    sidecars = []
    index = 0
    for case_id in driver.DEFAULT_CASE_IDS:
        case_run_id = f"run-{case_id}"
        for architecture, stage in (("legacy", "full"), ("jit", "nano"), ("jit", "full")):
            provider_receipt, sidecar = _receipt(plan, case_id, architecture, stage, attempt_id=f"case-{index}")
            sidecar["run_id"] = case_run_id
            if architecture == "legacy":
                legacy_provider_receipts.append(provider_receipt)
            else:
                gateway_run_id = case_run_id if stage == "nano" else f"gateway-{case_id}"
                if stage == "full":
                    sidecar["gateway_run_id"] = gateway_run_id
                jit_gateway_receipts.append(_jit_gateway_receipt([provider_receipt], run_id=gateway_run_id))
            sidecars.append(sidecar)
            index += 1

    result = driver.summarize_receipts(
        plan,
        {
            "legacy_provider_receipts": legacy_provider_receipts,
            "jit_gateway_receipts": jit_gateway_receipts,
            "legacy_receipt_source": "llm_gateway_attempts",
            "sidecars": sidecars,
        },
    )

    assert result["status"] == "known"
    assert result["run_id"] is None
    assert result["run_ids"] == {case_id: f"run-{case_id}" for case_id in driver.DEFAULT_CASE_IDS}


def test_missing_cost_and_counters_are_unknown_not_zero(fixture: dict) -> None:
    plan = _plan(fixture)
    receipt, sidecar = _receipt(plan, "actionable_deadline", "jit", "nano", attempt_id="attempt-1")
    del receipt["estimated_cost_micro_usd"]
    del sidecar["tool_rounds"]

    result = driver.summarize_receipts(
        plan,
        {"jit_gateway_receipts": [_jit_gateway_receipt([receipt])], "sidecars": [sidecar]},
    )

    assert result["status"] == "blocked"
    assert result["cost_micro_usd"] == 0
    assert result["blocking_reasons"]


def test_endpoint_metadata_without_durable_legacy_event_cannot_claim_nano_savings(fixture: dict) -> None:
    plan = _plan(fixture)
    result = driver.summarize_receipts(
        plan,
        {
            "legacy_endpoint_responses": [
                {
                    "operation": "proactive_reasoning",
                    "lane": "omi:auto:desktop-proactive-reasoning",
                    "provider_model": "gpt-5.6-luna",
                    "usage": {"cached_tokens": 0, "cache_write_tokens": 0},
                    "cache_write": False,
                    "fallback_class": "none",
                }
            ],
            "sidecars": [],
        },
    )

    assert result["status"] == "unknown"
    assert result["cost_micro_usd"] is None
    assert result["actual_jit_architecture_cost_micro_usd"] is None
    assert result["actual_jit_architecture_cost_status"] == "unknown"
    assert any("no trusted legacy event" in reason for reason in result["blocking_reasons"])


def test_legacy_receipt_must_be_durable_event_not_endpoint_envelope(fixture: dict) -> None:
    plan = _plan(fixture)
    receipt, sidecar = _receipt(plan, "actionable_deadline", "legacy", "full", attempt_id="attempt-legacy")
    result = driver.summarize_receipts(
        plan,
        {
            "legacy_provider_receipts": [receipt],
            "legacy_receipt_source": "proactive_endpoint",
            "sidecars": [sidecar],
        },
    )

    assert result["status"] == "blocked"
    assert any("durable llm_gateway_attempts" in reason for reason in result["blocking_reasons"])


def test_route_or_prompt_mismatch_blocks(fixture: dict) -> None:
    plan = _plan(fixture)
    receipt, sidecar = _receipt(plan, "actionable_deadline", "jit", "full", attempt_id="attempt-1")
    receipt["actual_model_version"] = "omi-sonnet"

    result = driver.summarize_receipts(
        plan,
        {"jit_gateway_receipts": [_jit_gateway_receipt([receipt])], "sidecars": [sidecar]},
    )

    assert result["status"] == "blocked"
    assert any("actual_model_version" in reason for reason in result["blocking_reasons"])


def test_jit_gateway_aggregate_mismatch_blocks(fixture: dict) -> None:
    plan = _plan(fixture)
    receipt, sidecar = _receipt(plan, "actionable_deadline", "jit", "full", attempt_id="aggregate-mismatch")
    gateway_receipt = _jit_gateway_receipt([receipt])
    gateway_receipt["aggregate"]["output_tokens"] = 999
    result = driver.summarize_receipts(
        plan,
        {
            "jit_gateway_receipts": [gateway_receipt],
            "sidecars": [sidecar],
        },
    )

    assert result["status"] == "blocked"
    assert any("JIT aggregate output_tokens differs" in reason for reason in result["blocking_reasons"])


def test_durable_join_uses_exact_request_ids_and_drops_untrusted_fields(fixture: dict) -> None:
    plan = _plan(fixture)
    observations = []
    durable_rows = []
    for case_id, architecture, stage in (
        ("actionable_deadline", "legacy", "full"),
        ("actionable_deadline", "jit", "nano"),
    ):
        receipt, sidecar = _receipt(plan, case_id, architecture, stage, attempt_id=f"join-{architecture}")
        observation = {
            "case_id": case_id,
            "architecture": architecture,
            "stage": stage,
            "request_id": receipt["request_id"],
            "run_id": sidecar["run_id"],
            "evidence_sha256": sidecar["evidence_sha256"],
            "prompt_sha256": sidecar["prompt_sha256"],
            "gateway_lane": sidecar["gateway_lane"],
            "tool_rounds": 0,
        }
        observation.update(
            {key: value for key, value in sidecar.items() if key.endswith("_sha256") and key != "evidence_sha256"}
        )
        observations.append(observation)
        receipt["prompt"] = "must-not-cross-evidence-boundary"
        durable_rows.append(receipt)
    durable_rows.append({**durable_rows[0], "attempt_id": "unrelated", "request_id": "request-unrelated"})
    full_case = next(item for item in plan["cases"] if item["case_id"] == "actionable_deadline")
    existing_full_sidecar = {
        "run_id": "full-run",
        "attempt_ids": ["full-attempt"],
        "request_id": "full-request",
        "case_id": "actionable_deadline",
        "architecture": "jit",
        "stage": "full",
        "gateway_lane": full_case["jit"]["full"]["route"]["gateway_lane"],
        "evidence_sha256": full_case["matched_input"]["evidence_sha256"],
        "prompt_sha256": full_case["jit"]["full"]["prompt_hashes"]["prompt_sha256"],
        "system_prompt_sha256": full_case["jit"]["full"]["prompt_hashes"]["system_prompt_sha256"],
        "tool_rounds": 1,
        "prompt": "must-not-cross-evidence-boundary",
    }

    joined = driver.join_durable_receipts(
        plan,
        {
            "request_observations": observations,
            "llm_gateway_attempts": durable_rows,
            "sidecars": [existing_full_sidecar],
        },
    )

    assert joined["status"] == "joined"
    assert [item["attempt_id"] for item in joined["legacy_provider_receipts"]] == ["join-legacy"]
    assert [item["attempt_id"] for item in joined["jit_nano_provider_receipts"]] == ["join-jit"]
    assert all(
        "prompt" not in item for item in joined["legacy_provider_receipts"] + joined["jit_nano_provider_receipts"]
    )
    assert joined["sidecars"][0]["attempt_ids"] == ["full-attempt"]
    assert joined["sidecars"][1]["attempt_ids"] == ["join-legacy"]
    assert joined["sidecars"][2]["attempt_ids"] == ["join-jit"]
    assert all("prompt" not in item for item in joined["sidecars"])


def test_durable_join_blocks_missing_exact_request_event(fixture: dict) -> None:
    plan = _plan(fixture)
    receipt, sidecar = _receipt(plan, "actionable_deadline", "legacy", "full", attempt_id="missing")
    with pytest.raises(driver.EvidenceError, match="no durable event for exact request_id"):
        driver.join_durable_receipts(
            plan,
            {
                "request_observations": [
                    {
                        "case_id": "actionable_deadline",
                        "architecture": "legacy",
                        "stage": "full",
                        "request_id": receipt["request_id"],
                        "run_id": sidecar["run_id"],
                        "evidence_sha256": sidecar["evidence_sha256"],
                        "prompt_sha256": sidecar["prompt_sha256"],
                        "gateway_lane": sidecar["gateway_lane"],
                        "tool_rounds": 0,
                    }
                ],
                "llm_gateway_attempts": [],
            },
        )


def _mark_actual_nano(plan: dict, case_id: str, request_id: str) -> None:
    case = next(item for item in plan["cases"] if item["case_id"] == case_id)
    case["jit"]["nano"]["actual_nano_billing"] = {
        "schema_version": driver.NANO_BILLING_SCHEMA_VERSION,
        "dispatch": "observed",
        "lane": "planned",
        "owner_id": driver.QA_OWNER_UID,
        "account_generation": 0,
        "snapshot_revision": "snapshot-1",
        "budget_day": "2026-09-05",
        "context_id": "planned:trigger-1",
        "candidate_id": "candidate-1",
        "execution_id": "execution-actual-nano",
        "outcome": "approved",
        "operation": "proactive_extraction",
        "request_id": request_id,
        "usage_status": "reported",
        "cost_status": "unknown",
        "attempt_ids": [],
    }


def test_durable_join_separates_actual_nano_from_replay(fixture: dict) -> None:
    plan = _plan(fixture)
    actual_request_id = "request-actual-nano"
    _mark_actual_nano(plan, "actionable_deadline", actual_request_id)
    actual_receipt, actual_sidecar = _receipt(plan, "actionable_deadline", "jit", "nano", attempt_id="actual-nano")
    actual_receipt["request_id"] = actual_request_id
    replay_receipt, replay_sidecar = _receipt(plan, "actionable_deadline", "jit", "nano", attempt_id="replay-nano")
    observations = []
    for receipt, sidecar, origin in (
        (replay_receipt, replay_sidecar, "replay"),
        (actual_receipt, actual_sidecar, "actual"),
    ):
        observations.append(
            {
                "case_id": "actionable_deadline",
                "architecture": "jit",
                "stage": "nano",
                "request_id": receipt["request_id"],
                "run_id": sidecar["run_id"],
                "evidence_sha256": sidecar["evidence_sha256"],
                "prompt_sha256": sidecar["prompt_sha256"],
                "gateway_lane": sidecar["gateway_lane"],
                "tool_rounds": 0,
                "receipt_origin": origin,
            }
        )

    joined = driver.join_durable_receipts(
        plan,
        {
            "request_observations": observations,
            "llm_gateway_attempts": [actual_receipt, replay_receipt],
        },
    )

    assert [item["attempt_id"] for item in joined["actual_jit_nano_provider_receipts"]] == ["actual-nano"]
    assert [item["attempt_id"] for item in joined["jit_nano_provider_receipts"]] == ["replay-nano"]
    assert joined["sidecars"][0]["receipt_origin"] == "replay"
    assert joined["sidecars"][1]["receipt_origin"] == "actual"


def test_actual_nano_receipt_is_cost_source_and_replay_is_excluded(fixture: dict) -> None:
    plan = _plan(fixture)
    _mark_actual_nano(plan, "actionable_deadline", "request-actual-nano")
    legacy_provider_receipts = []
    jit_gateway_receipts = []
    sidecars = []
    actual_nano_provider_receipts = []
    replay_nano_provider_receipts = []
    index = 0
    for case_id in driver.DEFAULT_CASE_IDS:
        for architecture, stage in (("legacy", "full"), ("jit", "nano"), ("jit", "full")):
            receipt, sidecar = _receipt(plan, case_id, architecture, stage, attempt_id=f"actual-{index}")
            if architecture == "legacy":
                legacy_provider_receipts.append(receipt)
            elif stage == "nano" and case_id == "actionable_deadline":
                receipt["request_id"] = "request-actual-nano"
                sidecar["receipt_origin"] = "actual"
                actual_nano_provider_receipts.append(receipt)
                replay, replay_sidecar = _receipt(plan, case_id, architecture, stage, attempt_id="replay-excluded")
                replay_sidecar["receipt_origin"] = "replay"
                replay_nano_provider_receipts.append(replay)
                sidecars.append(replay_sidecar)
            else:
                jit_gateway_receipts.append(_jit_gateway_receipt([receipt]))
            sidecars.append(sidecar)
            index += 1

    envelope = {
        "legacy_provider_receipts": legacy_provider_receipts,
        "jit_nano_provider_receipts": replay_nano_provider_receipts,
        "actual_jit_nano_provider_receipts": actual_nano_provider_receipts,
        "jit_gateway_receipts": jit_gateway_receipts,
        "legacy_receipt_source": "llm_gateway_attempts",
        "sidecars": sidecars,
    }
    result = driver.summarize_receipts(plan, envelope)

    assert result["status"] == "known"
    assert result["jit_nano_receipt_source"] == "actual_producer"
    assert result["operations"] == 9
    assert result["gateway_attempts"] == 10
    assert result["cost_micro_usd"] == 1_000
    assert result["actual_jit_architecture_cost_micro_usd"] == 400

    missing_actual = dict(envelope)
    missing_actual["actual_jit_nano_provider_receipts"] = []
    blocked = driver.summarize_receipts(plan, missing_actual)
    assert blocked["status"] == "blocked"
    assert any("actual producer nano accounting is missing" in reason for reason in blocked["blocking_reasons"])


def test_not_dispatched_nano_is_explicit_zero_and_replay_is_optional(fixture: dict) -> None:
    plan = _plan(fixture)
    case = next(item for item in plan["cases"] if item["case_id"] == "actionable_deadline")
    case["jit"]["nano"]["actual_nano_billing"] = {
        "schema_version": driver.NANO_BILLING_SCHEMA_VERSION,
        "dispatch": "not_dispatched",
        "lane": "planned",
        "owner_id": driver.QA_OWNER_UID,
        "account_generation": 0,
        "snapshot_revision": "snapshot-1",
        "budget_day": "2026-09-05",
        "context_id": "planned:trigger-1",
        "candidate_id": "candidate-1",
        "execution_id": "execution-not-dispatched",
        "outcome": "not_dispatched",
        "operation": "proactive_extraction",
        "usage_status": "not_applicable",
        "cost_status": "not_applicable",
        "provider_attempts": 0,
        "attempt_ids": [],
    }
    legacy_provider_receipts = []
    jit_gateway_receipts = []
    sidecars = []
    index = 0
    for case_id in driver.DEFAULT_CASE_IDS:
        for architecture, stage in (("legacy", "full"), ("jit", "nano"), ("jit", "full")):
            if case_id == "actionable_deadline" and architecture == "jit" and stage == "nano":
                continue
            receipt, sidecar = _receipt(plan, case_id, architecture, stage, attempt_id=f"no-nano-{index}")
            sidecars.append(sidecar)
            if architecture == "legacy":
                legacy_provider_receipts.append(receipt)
            else:
                jit_gateway_receipts.append(_jit_gateway_receipt([receipt]))
            index += 1

    result = driver.summarize_receipts(
        plan,
        {
            "legacy_provider_receipts": legacy_provider_receipts,
            "jit_gateway_receipts": jit_gateway_receipts,
            "legacy_receipt_source": "llm_gateway_attempts",
            "sidecars": sidecars,
        },
    )

    assert result["status"] == "known"
    assert result["jit_nano_receipt_source"] == "not_dispatched"
    assert result["operations"] == 8
    assert result["gateway_attempts"] == 8
    assert result["cost_micro_usd"] == 800
    assert result["actual_jit_architecture_cost_micro_usd"] == 300


def test_join_receipts_cli_emits_a_sanitized_envelope(
    fixture: dict, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(fixture)
    receipt, sidecar = _receipt(plan, "actionable_deadline", "legacy", "full", attempt_id="cli-join")
    raw = {
        "request_observations": [
            {
                "case_id": "actionable_deadline",
                "architecture": "legacy",
                "stage": "full",
                "request_id": receipt["request_id"],
                "run_id": sidecar["run_id"],
                "evidence_sha256": sidecar["evidence_sha256"],
                "prompt_sha256": sidecar["prompt_sha256"],
                "gateway_lane": sidecar["gateway_lane"],
                "tool_rounds": 0,
            }
        ],
        "llm_gateway_attempts": [receipt],
    }
    plan_path = tmp_path / "plan.json"
    raw_path = tmp_path / "raw.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    raw_path.write_text(json.dumps(raw), encoding="utf-8")

    assert driver.main(["--join-receipts", str(raw_path), "--plan-file", str(plan_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "joined"
    assert output["legacy_provider_receipts"][0]["attempt_id"] == "cli-join"


def test_receipt_summary_counts_retries_without_duplicate_operation(fixture: dict) -> None:
    plan = _plan(fixture)
    legacy_provider_receipts = []
    jit_provider_receipts = []
    jit_gateway_receipts = []
    sidecars = []
    index = 0
    for case_id in driver.DEFAULT_CASE_IDS:
        for architecture, stage in (("legacy", "full"), ("jit", "nano"), ("jit", "full")):
            provider_receipt, sidecar = _receipt(plan, case_id, architecture, stage, attempt_id=f"retry-{index}")
            if architecture == "legacy":
                legacy_provider_receipts.append(provider_receipt)
            else:
                jit_provider_receipts.append(provider_receipt)
                jit_gateway_receipts.append(_jit_gateway_receipt([provider_receipt]))
            sidecars.append(sidecar)
            index += 1
    retry = dict(legacy_provider_receipts[0])
    retry["attempt_id"] = "retry-late"
    retry["invocation_id"] = "invocation-retry-late"
    legacy_provider_receipts.append(retry)
    sidecars[0]["attempt_ids"].append("retry-late")
    jit_retry = dict(jit_provider_receipts[1])
    jit_retry["attempt_id"] = "retry-jit-late"
    jit_retry["invocation_id"] = "invocation-retry-jit-late"
    jit_gateway_receipts[1] = _jit_gateway_receipt([jit_provider_receipts[1], jit_retry])
    sidecars[2]["attempt_ids"].append("retry-jit-late")

    result = driver.summarize_receipts(
        plan,
        {
            "legacy_provider_receipts": legacy_provider_receipts,
            "jit_gateway_receipts": jit_gateway_receipts,
            "legacy_receipt_source": "llm_gateway_attempts",
            "sidecars": sidecars,
        },
    )

    assert result["status"] == "known"
    assert result["operations"] == 9
    assert result["gateway_attempts"] == 11
    assert result["cost_micro_usd"] == 1_100


def test_explicit_zero_tool_and_cache_counters_are_known_not_unknown(fixture: dict) -> None:
    plan = _plan(fixture)
    receipt, sidecar = _receipt(plan, "actionable_deadline", "jit", "nano", attempt_id="attempt-1")
    sidecar["tool_rounds"] = 0
    sidecar["cache_units"] = 0
    result = driver.summarize_receipts(
        plan,
        {"jit_gateway_receipts": [_jit_gateway_receipt([receipt])], "sidecars": [sidecar]},
    )

    assert result["status"] == "blocked"
    assert result["gateway_attempts"] == 1
    assert result["cost_micro_usd"] == 100
    assert any("receipt coverage is incomplete" in reason for reason in result["blocking_reasons"])


def test_fixture_rejects_blocked_dst_case_and_cap_overflow(fixture: dict) -> None:
    with pytest.raises(driver.EvidenceError, match="blocked context projection"):
        driver.build_plan(fixture, ["dst_local_deadline"])
    with pytest.raises(driver.EvidenceError, match="case IDs must be unique"):
        driver.build_plan(fixture, ["actionable_deadline"] * 4)


def _tiny_tool_manifest() -> list[dict]:
    return [
        {
            "name": "get_context",
            "description": "Read the bounded context.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        }
    ]


def test_preflight_materializes_all_three_source_routes_without_calls(fixture: dict) -> None:
    result = driver.preflight_payloads(
        fixture,
        driver.DEFAULT_CASE_IDS[:1],
        tool_manifest=_tiny_tool_manifest(),
        tool_manifest_metadata={"adapter_id": "omi-tools-stdio"},
        kernel_system_prompt="Bounded kernel policy.",
    )

    assert result["status"] == "ready_for_runtime"
    assert result["evidence_scope"].startswith("no-call")
    case = result["cases"][0]
    assert case["legacy"]["fits_input_envelope"]
    assert case["jit_nano"]["fits_input_envelope"]
    assert case["jit_full"]["fits_input_envelope"]
    assert case["jit_full"]["tool_manifest"]["tool_count"] == 1
    assert case["jit_full"]["kernel_system_prompt_supplied"] is True


def test_preflight_blocks_until_source_tools_and_kernel_are_supplied(fixture: dict) -> None:
    result = driver.preflight_payloads(fixture, driver.DEFAULT_CASE_IDS[:1])

    assert result["status"] == "blocked"
    assert result["tool_manifest"] is None
    assert result["kernel_system_prompt"]["supplied"] is False
    assert any("tool manifest" in reason for reason in result["blocking_reasons"])
    assert any("kernel system-policy" in reason for reason in result["blocking_reasons"])


def test_preflight_blocks_oversized_source_tool_wire_payload(fixture: dict) -> None:
    tools = [
        {
            "name": "large_context",
            "description": "x" * 40_000,
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        }
    ]
    result = driver.preflight_payloads(
        fixture,
        driver.DEFAULT_CASE_IDS[:1],
        tool_manifest=tools,
        kernel_system_prompt="Bounded kernel policy.",
    )

    assert result["status"] == "blocked"
    assert result["cases"][0]["jit_full"]["request_utf8_bytes"] > driver.JIT_MAX_INPUT_ENVELOPE_BYTES

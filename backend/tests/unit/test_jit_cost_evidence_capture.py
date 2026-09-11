"""Tests for content-free JIT producer and durable-ledger capture."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import scripts.jit_cost_evidence_driver as driver

FIXTURE = (
    Path(__file__).parents[2] / "testing" / "jit_processing" / "fixtures" / "jit_architecture_quality_cost_v2.json"
)


def _plan() -> dict:
    return driver.build_plan(json.loads(FIXTURE.read_text(encoding="utf-8")), ["actionable_deadline"])


def _write_gateway_receipt(path: Path, *, run_id: str, attempt_id: str = "gateway-attempt") -> None:
    plan = _plan()
    route = plan["cases"][0]["jit"]["full"]["route"]
    attempt = {
        "attempt_id": attempt_id,
        "provider": route["provider"],
        "configured_model": route["served_model"],
        "actual_model_version": route["served_model"],
        "rate_card_id": route["rate_card_id"],
        "cost_basis": "test",
        "usage_status": "confirmed",
        "cost_status": "estimated",
        "normalized_uncached_input_tokens": 100,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 20,
        "estimated_cost_micro_usd": 100,
    }
    path.write_text(
        json.dumps(
            {
                "schema_version": "jit-gateway-receipt-v1",
                "run_id": run_id,
                "contract_version": "jit-cloud-qa-v1",
                "attempts": [attempt],
                "aggregate": {
                    "attempt_count": 1,
                    "normalized_uncached_input_tokens": 100,
                    "cached_input_tokens": 0,
                    "cache_write_tokens": 0,
                    "output_tokens": 20,
                    "estimated_cost_micro_usd": 100,
                    "cost_status": "estimated",
                },
            }
        ),
        encoding="utf-8",
    )


def _write_agent_db(
    root: Path,
    *,
    owner_id: str = driver.QA_OWNER_UID,
    run_id: str = "agent-run",
    gateway_run_id: str = "gateway-run",
    cost_status: str = "estimated",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    state = root.joinpath(*driver.QA_STATE_PATH_SUFFIX.parts)
    state.mkdir(parents=True)
    path = state / driver.AGENT_DATABASE_FILENAME
    snapshot = {"ownerId": owner_id, "snapshotGeneration": 1, "sourceOutcomes": [], "contextPlan": {}}
    input_json = {
        "surfaceKind": "service",
        "mode": "ask",
        "prompt": "exact producer prompt",
        "metadata": {
            "jitKnowledgeToolsEnabled": True,
            "jitBudget": {"contractVersion": "jit-cloud-qa-v1", "executionID": gateway_run_id},
        },
        "admittedContextSnapshot": snapshot,
    }
    result_json = {
        "jitCostStatus": cost_status,
        "jitProviderAttempts": 1,
        "jitReceiptAttemptIDs": ["gateway-attempt"],
    }
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE sessions(session_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL);
        CREATE TABLE runs(
          run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, request_id TEXT NOT NULL,
          status TEXT NOT NULL, input_json TEXT NOT NULL, result_json TEXT,
          system_prompt_hash TEXT
        );
        CREATE TABLE tool_invocation_ledger(
          invocation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, attempt_id TEXT NOT NULL,
          owner_id TEXT NOT NULL, status TEXT NOT NULL, prepared_at_ms INTEGER NOT NULL
        );
        """)
    connection.execute("INSERT INTO sessions VALUES (?, ?)", ("session-1", owner_id))
    connection.execute(
        "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            "session-1",
            "agent-request",
            "succeeded",
            json.dumps(input_json),
            json.dumps(result_json),
            None,
        ),
    )
    connection.executemany(
        "INSERT INTO tool_invocation_ledger VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("invocation-1", run_id, "gateway-attempt", owner_id, "succeeded", 1),
            ("invocation-2", run_id, "gateway-attempt", owner_id, "failed", 2),
        ],
    )
    connection.commit()
    connection.close()
    return path


def _append_agent_run(
    database: Path,
    *,
    owner_id: str = driver.QA_OWNER_UID,
    run_id: str,
    session_id: str,
    gateway_run_id: str,
    attempt_ids: list[str],
    prompt: str,
    lane: str,
) -> None:
    snapshot = {
        "ownerId": owner_id,
        "snapshotGeneration": 1,
        "contextID": f"context-{lane}",
        "sourceOutcomes": [],
        "contextPlan": {},
    }
    input_json = {
        "surfaceKind": "service",
        "mode": "ask",
        "prompt": prompt,
        "metadata": {
            "jitKnowledgeToolsEnabled": True,
            "jitBudget": {"contractVersion": "jit-cloud-qa-v1", "executionID": gateway_run_id},
            "temporalContext": {
                "evaluatedAt": "2026-09-05T10:00:00-04:00",
                "timezoneIdentifier": "America/New_York",
            },
            "proactivityLane": lane,
        },
        "admittedContextSnapshot": snapshot,
    }
    result_json = {
        "jitCostStatus": "estimated",
        "jitProviderAttempts": len(attempt_ids),
        "jitReceiptAttemptIDs": attempt_ids,
    }
    connection = sqlite3.connect(database)
    connection.execute("INSERT INTO sessions VALUES (?, ?)", (session_id, owner_id))
    connection.execute(
        "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            session_id,
            f"request-{lane}",
            "succeeded",
            json.dumps(input_json),
            json.dumps(result_json),
            None,
        ),
    )
    connection.executemany(
        "INSERT INTO tool_invocation_ledger VALUES (?, ?, ?, ?, ?, ?)",
        [
            (f"invocation-{lane}-{index}", run_id, attempt_ids[0], owner_id, "succeeded", index)
            for index in range(1, len(attempt_ids) + 1)
        ],
    )
    connection.commit()
    connection.close()


def _write_pair_agent_db(root: Path) -> Path:
    database = _write_agent_db(
        root,
        run_id="planned-run",
        gateway_run_id="planned-gateway",
    )
    # Replace the single-run fixture's metadata with the explicit planned
    # lane, then append the ambient turn to the same isolated snapshot.
    connection = sqlite3.connect(database)
    planned_input = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    planned_input["mode"] = "ask"
    planned_input["metadata"]["temporalContext"] = {
        "evaluatedAt": "2026-09-05T10:00:00-04:00",
        "timezoneIdentifier": "America/New_York",
    }
    planned_input["metadata"]["proactivityLane"] = "planned"
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(planned_input), "planned-run"))
    connection.commit()
    connection.close()
    _append_agent_run(
        database,
        run_id="ambient-run",
        session_id="session-ambient",
        gateway_run_id="ambient-gateway",
        attempt_ids=["ambient-attempt-1", "ambient-attempt-2"],
        prompt="ambient producer prompt",
        lane="ambient",
    )
    return database


def _attach_source_projections(database: Path) -> None:
    """Attach a faithful copy of the desktop source projection wire shape."""
    connection = sqlite3.connect(database)
    for lane, run_id, legacy_prompt in (
        ("planned", "planned-run", "legacy planned source prompt"),
        ("ambient", "ambient-run", "legacy ambient source prompt"),
    ):
        input_json = json.loads(
            connection.execute("SELECT input_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()[0]
        )
        # The full-turn prompt is materially longer than an identifier. Keep
        # this test aligned with the producer's real wire payload and assert
        # the consumer does not impose a 256-character ceiling on it.
        full_prompt = f"{input_json['prompt']} " + ("full-turn evidence " * 32)
        input_json["prompt"] = full_prompt
        snapshot = input_json["admittedContextSnapshot"]
        evidence_sha256 = driver._canonical_json_hash(snapshot)
        execution_id = input_json["metadata"]["jitBudget"]["executionID"]
        input_json[driver.SOURCE_PROJECTION_RUN_INPUT_KEY] = {
            "schema_version": driver.SOURCE_PROJECTION_SCHEMA_VERSION,
            "owner_id": driver.QA_OWNER_UID,
            "execution_id": execution_id,
            "producer_lane": lane,
            "evidence_sha256": evidence_sha256,
            "matched_input": {
                "evaluation_time": "2026-09-05T10:00:00-04:00",
                "timezone": "America/New_York",
                "context_id": f"context-{lane}",
                "evidence_sha256": evidence_sha256,
            },
            "legacy": {
                "prompt": legacy_prompt,
                "uncached_prompt": f"{legacy_prompt} volatile",
                "projection_mode": "director_baseline_v1",
                "source_builders": [
                    "ContextProactivityPromptBuilder.directorStablePrompt",
                    "ContextProactivityPromptBuilder.directorVolatilePrompt",
                ],
                "flags": [
                    "allow_lookup=false",
                    "include_interject_copy_budgets=false",
                    "workstream_pooling=false",
                    "proactive_candidates=false",
                ],
            },
            "nano": {
                "prompt": f"nano {lane} source prompt",
                "source_builder": "JITProactivityPromptBuilder.nanoTriagePrompt",
            },
            "full": {
                "prompt": full_prompt,
                "source_builder": "JITProactivityPromptBuilder.fullTurnPrompt",
            },
            "nano_billing": {
                "schema_version": driver.NANO_BILLING_SCHEMA_VERSION,
                "dispatch": "observed",
                "lane": lane,
                "owner_id": driver.QA_OWNER_UID,
                "account_generation": 1,
                "snapshot_revision": "revision-1",
                "budget_day": "2026-09-05",
                "context_id": f"{lane}:trigger-1",
                "candidate_id": execution_id,
                "execution_id": execution_id,
                "outcome": "approved",
                "operation": "proactive_extraction",
                "request_id": f"request-{lane}-nano",
                "usage_status": "reported",
                "cost_status": "unknown",
                "attempt_ids": [],
            },
        }
        connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(input_json), run_id))
    connection.commit()
    connection.close()


def _plan_for_agent_db() -> dict:
    plan = _plan()
    snapshot = {"ownerId": driver.QA_OWNER_UID, "snapshotGeneration": 1, "sourceOutcomes": [], "contextPlan": {}}
    plan["cases"][0]["matched_input"]["evidence_sha256"] = driver._canonical_json_hash(snapshot)
    plan["cases"][0]["jit"]["full"]["prompt_hashes"]["prompt_sha256"] = driver._sha256("exact producer prompt")
    return plan


def test_capture_agent_run_hashes_producer_and_counts_real_tool_rows(tmp_path: Path) -> None:
    database = _write_agent_db(tmp_path)
    receipt = tmp_path / "gateway.json"
    _write_gateway_receipt(receipt, run_id="gateway-run")

    result = driver.capture_agent_run(
        _plan_for_agent_db(),
        database_path=database,
        agent_run_id="agent-run",
        comparison_run_id="comparison-1",
        owner_id=driver.QA_OWNER_UID,
        case_id="actionable_deadline",
        gateway_receipt_path=receipt,
    )

    sidecar = result["sidecars"][0]
    assert sidecar["run_id"] == "comparison-1"
    assert sidecar["gateway_run_id"] == "gateway-run"
    assert sidecar["agent_run_id"] == "agent-run"
    assert sidecar["tool_invocations"] == 2
    assert sidecar["prompt_sha256"] == driver._sha256("exact producer prompt")
    assert result["jit_gateway_receipts"][0]["run_id"] == "gateway-run"


def test_producer_derived_plan_uses_actual_prompt_and_blocks_static_replay(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_agent_db(tmp_path)

    plan = driver.build_producer_derived_plan(
        fixture,
        database_path=database,
        agent_run_id="agent-run",
        owner_id=driver.QA_OWNER_UID,
        case_id="actionable_deadline",
    )

    assert plan["status"] == "producer_matched_jit_only"
    assert plan["comparison_ready"] is False
    case = plan["cases"][0]
    assert case["jit"]["full"]["producer_derived"] is True
    assert case["jit"]["full"]["prompt_hashes"]["prompt_sha256"] == driver._sha256("exact producer prompt")
    assert case["legacy"]["status"] == "unavailable"
    assert case["jit"]["nano"]["status"] == "unavailable"
    assert "source-owned legacy/nano prompt projection" in plan["replay_projection"]["legacy"]["reason"]

    receipt = tmp_path / "gateway.json"
    _write_gateway_receipt(receipt, run_id="gateway-run")
    captured = driver.capture_agent_run(
        plan,
        database_path=database,
        agent_run_id="agent-run",
        comparison_run_id="comparison-1",
        owner_id=driver.QA_OWNER_UID,
        case_id="actionable_deadline",
        gateway_receipt_path=receipt,
    )
    assert captured["sidecars"][0]["prompt_sha256"] == driver._sha256("exact producer prompt")


def test_producer_derived_plan_cli_is_runnable_without_provider_calls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = _write_agent_db(tmp_path)
    assert (
        driver.main(
            [
                "--producer-derived-plan",
                "--fixture",
                str(FIXTURE),
                "--case-id",
                "actionable_deadline",
                "--agent-db",
                str(database),
                "--agent-run-id",
                "agent-run",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "producer_matched_jit_only"
    assert output["comparison_ready"] is False


def test_producer_derived_pair_plan_uses_planned_and_ambient_runs(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)

    plan = driver.build_producer_derived_pair_plan(
        fixture,
        database_path=database,
        producer_runs=[("ambient", "ambient-run"), ("planned", "planned-run")],
        owner_id=driver.QA_OWNER_UID,
    )

    assert plan["status"] == "producer_matched_two_case_jit_only"
    assert plan["comparison_ready"] is False
    assert [item["case_id"] for item in plan["cases"]] == ["planned", "ambient"]
    assert [item["producer_lane"] for item in plan["cases"]] == ["planned", "ambient"]
    assert [item["provider_attempts_exact"] for item in plan["cases"]] == [1, 2]
    assert [item["tool_invocations"] for item in plan["cases"]] == [2, 2]
    assert plan["minimum_runtime_sample"]["actual_jit_full_turns_observed"] == 2
    assert plan["replay_projection"]["legacy"]["status"] == "unavailable"
    # The output is content-free: neither producer prompt crosses the plan
    # boundary, only its hash does.
    serialized = json.dumps(plan)
    assert "exact producer prompt" not in serialized
    assert "ambient producer prompt" not in serialized


def test_source_owned_pair_projection_is_pinned_and_content_free(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)

    plan = driver.build_producer_derived_pair_plan(
        fixture,
        database_path=database,
        producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
        owner_id=driver.QA_OWNER_UID,
    )

    assert plan["status"] == "producer_matched_two_case_source_owned_baselines"
    assert plan["replay_projection"]["status"] == "source_owned"
    assert [case["legacy"]["status"] for case in plan["cases"]] == ["source_owned", "source_owned"]
    assert [case["jit"]["nano"]["status"] for case in plan["cases"]] == ["source_owned", "source_owned"]
    assert plan["cases"][0]["legacy"]["projection_mode"] == "director_baseline_v1"
    assert plan["cases"][0]["legacy"]["source_builders"] == [
        "ContextProactivityPromptBuilder.directorStablePrompt",
        "ContextProactivityPromptBuilder.directorVolatilePrompt",
    ]
    assert plan["cases"][0]["jit"]["nano"]["source_builder"] == "JITProactivityPromptBuilder.nanoTriagePrompt"
    assert plan["cases"][0]["jit"]["full"]["source_builder"] == "JITProactivityPromptBuilder.fullTurnPrompt"
    serialized = json.dumps(plan)
    assert "legacy planned source prompt" not in serialized
    assert "nano ambient source prompt" not in serialized


def test_source_owned_projection_preserves_content_free_actual_nano_observation(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)
    connection = sqlite3.connect(database)
    input_json = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    projection = input_json[driver.SOURCE_PROJECTION_RUN_INPUT_KEY]
    projection["nano_billing"] = {
        "schema_version": driver.NANO_BILLING_SCHEMA_VERSION,
        "dispatch": "observed",
        "lane": "planned",
        "owner_id": driver.QA_OWNER_UID,
        "account_generation": 0,
        "snapshot_revision": "snapshot-1",
        "budget_day": "2026-09-05",
        "context_id": "planned:trigger-1",
        "candidate_id": "candidate-1",
        "execution_id": "planned-gateway",
        "outcome": "approved",
        "operation": "proactive_extraction",
        "request_id": "actual-nano-request",
        "usage_status": "reported",
        "cost_status": "unknown",
        "attempt_ids": [],
    }
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(input_json), "planned-run"))
    connection.commit()
    connection.close()

    plan = driver.build_producer_derived_pair_plan(
        fixture,
        database_path=database,
        producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
        owner_id=driver.QA_OWNER_UID,
    )
    observation = plan["cases"][0]["jit"]["nano"]["actual_nano_billing"]
    assert observation["request_id"] == "actual-nano-request"
    assert "estimated_cost_micro_usd" not in observation


def test_dedicated_run_input_projection_is_authoritative_over_metadata(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)
    connection = sqlite3.connect(database)
    input_json = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    # A malformed legacy copy cannot shadow or invalidate the dedicated field.
    input_json["metadata"][driver.SOURCE_PROJECTION_LEGACY_METADATA_KEY] = {"unexpected": []}
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(input_json), "planned-run"))
    connection.commit()
    connection.close()

    plan = driver.build_producer_derived_pair_plan(
        fixture,
        database_path=database,
        producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
        owner_id=driver.QA_OWNER_UID,
    )
    assert plan["status"] == "producer_matched_two_case_source_owned_baselines"


def test_source_projection_requires_swift_nano_billing_and_rejects_ambient_no_dispatch(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)
    connection = sqlite3.connect(database)
    planned_input = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    planned_billing = planned_input[driver.SOURCE_PROJECTION_RUN_INPUT_KEY]["nano_billing"]
    planned_billing.update(
        {
            "dispatch": "not_dispatched",
            "outcome": "not_dispatched",
            "usage_status": "not_applicable",
            "cost_status": "not_applicable",
            "provider_attempts": 0,
            "attempt_ids": [],
        }
    )
    planned_billing.pop("request_id")
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(planned_input), "planned-run"))
    connection.commit()
    connection.close()

    accepted = driver.build_producer_derived_pair_plan(
        fixture,
        database_path=database,
        producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
        owner_id=driver.QA_OWNER_UID,
    )
    assert accepted["cases"][0]["jit"]["nano"]["actual_nano_billing"]["dispatch"] == "not_dispatched"

    connection = sqlite3.connect(database)
    planned_input = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    planned_billing = planned_input[driver.SOURCE_PROJECTION_RUN_INPUT_KEY]["nano_billing"]
    planned_billing.pop("provider_attempts")
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(planned_input), "planned-run"))
    connection.commit()
    connection.close()
    with pytest.raises(driver.EvidenceError, match="requires provider_attempts=0"):
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
        )

    connection = sqlite3.connect(database)
    planned_input = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    planned_billing = planned_input[driver.SOURCE_PROJECTION_RUN_INPUT_KEY]["nano_billing"]
    planned_billing["provider_attempts"] = 0
    planned_billing["attempt_ids"] = ["unexpected-attempt"]
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(planned_input), "planned-run"))
    connection.commit()
    connection.close()
    with pytest.raises(driver.EvidenceError, match="requires empty attempt_ids"):
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
        )

    connection = sqlite3.connect(database)
    planned_input = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    planned_billing = planned_input[driver.SOURCE_PROJECTION_RUN_INPUT_KEY]["nano_billing"]
    planned_billing["attempt_ids"] = []
    planned_billing["provider"] = "openai"
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(planned_input), "planned-run"))
    connection.commit()
    connection.close()
    with pytest.raises(driver.EvidenceError, match="contains provider/usage fields"):
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
        )

    connection = sqlite3.connect(database)
    planned_input = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    planned_billing = planned_input[driver.SOURCE_PROJECTION_RUN_INPUT_KEY]["nano_billing"]
    planned_billing.pop("provider")
    planned_billing["outcome"] = "approved"
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(planned_input), "planned-run"))
    connection.commit()
    connection.close()
    with pytest.raises(driver.EvidenceError, match="outcome must be not_dispatched"):
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
        )

    connection = sqlite3.connect(database)
    planned_input = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    planned_billing = planned_input[driver.SOURCE_PROJECTION_RUN_INPUT_KEY]["nano_billing"]
    planned_billing.update(
        {
            "outcome": "not_dispatched",
            "provider_attempts": 0,
            "attempt_ids": [],
            "usage_status": "not_applicable",
            "cost_status": "not_applicable",
        }
    )
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(planned_input), "planned-run"))
    connection.commit()
    connection.close()

    connection = sqlite3.connect(database)
    ambient_input = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("ambient-run",)).fetchone()[0]
    )
    ambient_projection = ambient_input[driver.SOURCE_PROJECTION_RUN_INPUT_KEY]
    ambient_projection["nano_billing"]["dispatch"] = "not_dispatched"
    ambient_projection["nano_billing"].pop("request_id")
    ambient_projection["nano_billing"]["usage_status"] = "not_applicable"
    ambient_projection["nano_billing"]["cost_status"] = "not_applicable"
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(ambient_input), "ambient-run"))
    connection.commit()
    connection.close()

    with pytest.raises(driver.EvidenceError, match="ambient JIT nano billing cannot claim not_dispatched"):
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
        )

    connection = sqlite3.connect(database)
    ambient_input = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("ambient-run",)).fetchone()[0]
    )
    ambient_input[driver.SOURCE_PROJECTION_RUN_INPUT_KEY].pop("nano_billing")
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(ambient_input), "ambient-run"))
    connection.commit()
    connection.close()
    with pytest.raises(driver.EvidenceError, match="no required nano_billing observation"):
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
        )


def test_legacy_metadata_projection_requires_explicit_private_compatibility(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)
    connection = sqlite3.connect(database)
    for run_id in ("planned-run", "ambient-run"):
        input_json = json.loads(
            connection.execute("SELECT input_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()[0]
        )
        input_json["metadata"][driver.SOURCE_PROJECTION_LEGACY_METADATA_KEY] = input_json.pop(
            driver.SOURCE_PROJECTION_RUN_INPUT_KEY
        )
        connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(input_json), run_id))
    connection.commit()
    connection.close()

    with pytest.raises(driver.EvidenceError, match="dedicated run-input field"):
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
        )

    # Historical compatibility is allowed only after the operator explicitly
    # opts in and the exact QA state is owner-only.
    database.parent.chmod(0o700)
    database.chmod(0o600)
    plan = driver.build_producer_derived_pair_plan(
        fixture,
        database_path=database,
        producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
        owner_id=driver.QA_OWNER_UID,
        allow_legacy_private_metadata_projection=True,
    )
    assert plan["status"] == "producer_matched_two_case_source_owned_baselines"


def test_source_projection_rejects_full_prompt_different_from_admitted_prompt(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)
    connection = sqlite3.connect(database)
    input_json = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    input_json[driver.SOURCE_PROJECTION_RUN_INPUT_KEY]["full"]["prompt"] = "different admitted bytes"
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(input_json), "planned-run"))
    connection.commit()
    connection.close()

    with pytest.raises(driver.EvidenceError, match="full.prompt does not equal"):
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
        )


def test_external_source_projection_uses_private_reader_and_rejects_symlink(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)
    projection_dir = tmp_path / "source-projections"
    projection_dir.mkdir(mode=0o700)
    connection = sqlite3.connect(database)
    for lane, run_id in (("planned", "planned-run"), ("ambient", "ambient-run")):
        input_json = json.loads(
            connection.execute("SELECT input_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()[0]
        )
        projection = input_json.pop(driver.SOURCE_PROJECTION_RUN_INPUT_KEY)
        execution_id = input_json["metadata"]["jitBudget"]["executionID"]
        projection_path = projection_dir / f"{execution_id}.json"
        driver._write_private_file(projection_path, driver._json_bytes(projection))
        connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(input_json), run_id))
    connection.commit()
    connection.close()

    plan = driver.build_producer_derived_pair_plan(
        fixture,
        database_path=database,
        producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
        owner_id=driver.QA_OWNER_UID,
        projection_dir=projection_dir,
    )
    assert plan["status"] == "producer_matched_two_case_source_owned_baselines"

    planned_path = projection_dir / "planned-gateway.json"
    # The source projection target is owner-only, but the fallback must reject
    # a symlink even when it points at another owner-only JSON file.
    target = projection_dir / "target.json"
    target.write_bytes(planned_path.read_bytes())
    target.chmod(0o600)
    planned_path.unlink()
    planned_path.symlink_to(target)
    with pytest.raises(driver.EvidenceError, match="missing for execution") as exc_info:
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
            projection_dir=projection_dir,
        )
    assert exc_info.value.__cause__ is not None
    assert "symlink private source projection" in str(exc_info.value.__cause__)


def test_source_projection_export_writes_private_replay_inputs(tmp_path: Path) -> None:
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)
    output_dir = tmp_path / "private-projections"

    result = driver.export_source_projection_inputs(
        database_path=database,
        producer_runs=[("ambient", "ambient-run"), ("planned", "planned-run")],
        owner_id=driver.QA_OWNER_UID,
        output_dir=output_dir,
    )

    assert result["status"] == "exported"
    assert [item["producer_lane"] for item in result["producer_runs"]] == ["planned", "ambient"]
    assert "legacy planned source prompt" not in json.dumps(result)
    for lane in ("planned", "ambient"):
        lane_dir = output_dir / lane
        assert (lane_dir / "legacy.prompt").read_text(encoding="utf-8")
        assert (lane_dir / "legacy.uncached_prompt").read_text(encoding="utf-8")
        assert (lane_dir / "nano.prompt").read_text(encoding="utf-8")
        assert (lane_dir / "evidence.json").exists()
        assert lane_dir.stat().st_mode & 0o777 == 0o700
        for path in lane_dir.iterdir():
            assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(driver.EvidenceError, match="non-exclusive replay artifact"):
        driver.export_source_projection_inputs(
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
            output_dir=output_dir,
        )


def test_source_projection_export_rejects_symlink_root(tmp_path: Path) -> None:
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)
    target = tmp_path / "real-output"
    target.mkdir()
    output_dir = tmp_path / "private-projections"
    output_dir.symlink_to(target, target_is_directory=True)

    with pytest.raises(driver.EvidenceError, match="symlink replay directory"):
        driver.export_source_projection_inputs(
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
            output_dir=output_dir,
        )


def test_source_projection_export_cli_is_content_free(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)
    output_dir = tmp_path / "cli-projections"
    assert (
        driver.main(
            [
                "--export-source-projections",
                "--fixture",
                str(FIXTURE),
                "--producer-run",
                "planned=planned-run",
                "--producer-run",
                "ambient=ambient-run",
                "--agent-db",
                str(database),
                "--projection-output-dir",
                str(output_dir),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "legacy planned source prompt" not in output
    assert json.loads(output)["status"] == "exported"


def test_source_projection_rejects_evidence_or_lane_drift(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)
    connection = sqlite3.connect(database)
    input_json = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    input_json[driver.SOURCE_PROJECTION_RUN_INPUT_KEY]["producer_lane"] = "ambient"
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(input_json), "planned-run"))
    connection.commit()
    connection.close()
    with pytest.raises(driver.EvidenceError, match="lane"):
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
        )


def test_producer_derived_pair_plan_cli_is_explicit_and_content_free(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = _write_pair_agent_db(tmp_path)
    assert (
        driver.main(
            [
                "--producer-derived-plan",
                "--fixture",
                str(FIXTURE),
                "--agent-db",
                str(database),
                "--producer-run",
                "planned=planned-run",
                "--producer-run",
                "ambient=ambient-run",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "producer_matched_two_case_jit_only"
    assert [item["producer_lane"] for item in output["cases"]] == ["planned", "ambient"]


def test_producer_derived_pair_plan_rejects_duplicate_or_wrong_lane(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)
    with pytest.raises(driver.EvidenceError, match="exactly planned and ambient"):
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run")],
            owner_id=driver.QA_OWNER_UID,
        )
    with pytest.raises(driver.EvidenceError, match="must be unique"):
        driver.build_producer_derived_pair_plan(
            fixture,
            database_path=database,
            producer_runs=[("planned", "planned-run"), ("planned", "ambient-run")],
            owner_id=driver.QA_OWNER_UID,
        )


def test_capture_pair_member_pins_evidence_and_lane(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)
    plan = driver.build_producer_derived_pair_plan(
        fixture,
        database_path=database,
        producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
        owner_id=driver.QA_OWNER_UID,
    )
    planned_receipt = tmp_path / "planned-gateway.json"
    _write_gateway_receipt(planned_receipt, run_id="planned-gateway")
    captured = driver.capture_agent_run(
        plan,
        database_path=database,
        agent_run_id="planned-run",
        comparison_run_id="comparison-pair",
        owner_id=driver.QA_OWNER_UID,
        case_id="planned",
        gateway_receipt_path=planned_receipt,
    )
    sidecar = captured["sidecars"][0]
    assert sidecar["producer_lane"] == "planned"
    assert sidecar["tool_invocations"] == 2
    assert sidecar["evidence_sha256"] == plan["cases"][0]["matched_input"]["evidence_sha256"]

    tampered = json.loads(json.dumps(plan))
    tampered["cases"][0]["matched_input"]["evidence_sha256"] = "f" * 64
    with pytest.raises(driver.EvidenceError, match="evidence hash"):
        driver.capture_agent_run(
            tampered,
            database_path=database,
            agent_run_id="planned-run",
            comparison_run_id="comparison-pair-tampered",
            owner_id=driver.QA_OWNER_UID,
            case_id="planned",
            gateway_receipt_path=planned_receipt,
        )


def test_capture_agent_run_emits_actual_nano_request_observation(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    database = _write_pair_agent_db(tmp_path)
    _attach_source_projections(database)
    connection = sqlite3.connect(database)
    input_json = json.loads(
        connection.execute("SELECT input_json FROM runs WHERE run_id = ?", ("planned-run",)).fetchone()[0]
    )
    input_json[driver.SOURCE_PROJECTION_RUN_INPUT_KEY]["nano_billing"] = {
        "schema_version": driver.NANO_BILLING_SCHEMA_VERSION,
        "dispatch": "observed",
        "lane": "planned",
        "owner_id": driver.QA_OWNER_UID,
        "account_generation": 0,
        "snapshot_revision": "snapshot-1",
        "budget_day": "2026-09-05",
        "context_id": "planned:trigger-1",
        "candidate_id": "planned-gateway",
        "execution_id": "planned-gateway",
        "outcome": "approved",
        "operation": "proactive_extraction",
        "request_id": "actual-nano-request",
        "usage_status": "reported",
        "cost_status": "unknown",
        "attempt_ids": [],
    }
    connection.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", (json.dumps(input_json), "planned-run"))
    connection.commit()
    connection.close()
    plan = driver.build_producer_derived_pair_plan(
        fixture,
        database_path=database,
        producer_runs=[("planned", "planned-run"), ("ambient", "ambient-run")],
        owner_id=driver.QA_OWNER_UID,
    )
    receipt = tmp_path / "gateway.json"
    _write_gateway_receipt(receipt, run_id="planned-gateway")
    captured = driver.capture_agent_run(
        plan,
        database_path=database,
        agent_run_id="planned-run",
        comparison_run_id="comparison-pair",
        owner_id=driver.QA_OWNER_UID,
        case_id="planned",
        gateway_receipt_path=receipt,
    )
    assert captured["request_observations"] == [
        {
            "case_id": "planned",
            "architecture": "jit",
            "stage": "nano",
            "request_id": "actual-nano-request",
            "run_id": "comparison-pair",
            "evidence_sha256": plan["cases"][0]["matched_input"]["evidence_sha256"],
            "prompt_sha256": plan["cases"][0]["jit"]["nano"]["prompt_hashes"]["prompt_sha256"],
            "gateway_lane": plan["cases"][0]["jit"]["nano"]["route"]["gateway_lane"],
            "tool_rounds": 0,
            "receipt_origin": "actual",
        }
    ]


def test_capture_agent_run_rejects_wrong_owner_and_unknown_run(tmp_path: Path) -> None:
    database = _write_agent_db(tmp_path, owner_id="different-owner")
    receipt = tmp_path / "gateway.json"
    _write_gateway_receipt(receipt, run_id="gateway-run")
    with pytest.raises(driver.EvidenceError, match="owner"):
        driver.capture_agent_run(
            _plan_for_agent_db(),
            database_path=database,
            agent_run_id="agent-run",
            comparison_run_id="comparison-1",
            owner_id=driver.QA_OWNER_UID,
            case_id="actionable_deadline",
            gateway_receipt_path=receipt,
        )

    database = _write_agent_db(tmp_path / "unknown")
    with pytest.raises(driver.EvidenceError, match="unknown"):
        driver.capture_agent_run(
            _plan_for_agent_db(),
            database_path=database,
            agent_run_id="missing-run",
            comparison_run_id="comparison-1",
            owner_id=driver.QA_OWNER_UID,
            case_id="actionable_deadline",
            gateway_receipt_path=receipt,
        )


def test_capture_agent_run_rejects_unknown_cost_and_mismatched_gateway_run(tmp_path: Path) -> None:
    database = _write_agent_db(tmp_path, cost_status="unknown")
    receipt = tmp_path / "gateway.json"
    _write_gateway_receipt(receipt, run_id="gateway-run")
    with pytest.raises(driver.EvidenceError, match="cost status"):
        driver.capture_agent_run(
            _plan_for_agent_db(),
            database_path=database,
            agent_run_id="agent-run",
            comparison_run_id="comparison-1",
            owner_id=driver.QA_OWNER_UID,
            case_id="actionable_deadline",
            gateway_receipt_path=receipt,
        )

    database = _write_agent_db(tmp_path / "mismatch")
    _write_gateway_receipt(receipt, run_id="different-gateway-run")
    with pytest.raises(driver.EvidenceError, match="run_id"):
        driver.capture_agent_run(
            _plan_for_agent_db(),
            database_path=database,
            agent_run_id="agent-run",
            comparison_run_id="comparison-1",
            owner_id=driver.QA_OWNER_UID,
            case_id="actionable_deadline",
            gateway_receipt_path=receipt,
        )


def test_capture_agent_run_rejects_default_shared_agent_state(tmp_path: Path) -> None:
    shared_db = tmp_path / "agent" / driver.AGENT_DATABASE_FILENAME
    shared_db.parent.mkdir()
    shared_db.touch()
    receipt = tmp_path / "gateway.json"
    _write_gateway_receipt(receipt, run_id="gateway-run")

    with pytest.raises(driver.EvidenceError, match="agent database"):
        driver.capture_agent_run(
            _plan_for_agent_db(),
            database_path=shared_db,
            agent_run_id="agent-run",
            comparison_run_id="comparison-1",
            owner_id=driver.QA_OWNER_UID,
            case_id="actionable_deadline",
            gateway_receipt_path=receipt,
        )


def test_export_attempts_rejects_wrong_owner_and_unknown_request() -> None:
    class Document:
        def __init__(self, value: dict) -> None:
            self.value = value

        def to_dict(self) -> dict:
            return self.value

    class Query:
        def __init__(self, documents: list[Document]) -> None:
            self.documents = documents

        def where(self, *, filter: object) -> "Query":
            return self

        def limit(self, count: int) -> "Query":
            self.documents = self.documents[:count]
            return self

        def stream(self) -> list[Document]:
            return self.documents

    class Client:
        def __init__(self, documents: list[Document]) -> None:
            self.documents = documents

        def collection(self, name: str) -> Query:
            assert name == "llm_gateway_attempts"
            return Query(self.documents)

    row = Document({"request_id": "request-1", "attempt_id": "attempt-1", "user_uid": driver.QA_OWNER_UID})
    result = driver.export_durable_attempts(Client([row]), request_ids=["request-1"], owner_id=driver.QA_OWNER_UID)
    assert result["llm_gateway_attempts"] == [{"request_id": "request-1", "attempt_id": "attempt-1"}]

    with pytest.raises(driver.EvidenceError, match="no durable attempt"):
        driver.export_durable_attempts(Client([]), request_ids=["missing"], owner_id=driver.QA_OWNER_UID)
    with pytest.raises(driver.EvidenceError, match="owner"):
        driver.export_durable_attempts(
            Client([Document({"request_id": "request-1", "attempt_id": "attempt-1", "user_uid": "other"})]),
            request_ids=["request-1"],
            owner_id=driver.QA_OWNER_UID,
        )


def test_export_durable_jit_receipt_rebuilds_attempts_and_aggregate() -> None:
    class Document:
        def __init__(self, value: dict) -> None:
            self.value = value

        def to_dict(self) -> dict:
            return self.value

    class Query:
        def __init__(self, documents: list[Document]) -> None:
            self.documents = documents

        def where(self, *, filter: object) -> "Query":
            return self

        def limit(self, count: int) -> "Query":
            self.documents = self.documents[:count]
            return self

        def stream(self) -> list[Document]:
            return self.documents

    class Client:
        def __init__(self, documents: list[Document]) -> None:
            self.documents = documents

        def collection(self, name: str) -> Query:
            assert name == "llm_gateway_attempts"
            return Query(self.documents)

    def row(attempt_id: str, ordinal: int, cost: int) -> dict:
        return {
            "attempt_id": attempt_id,
            "retry_ordinal": ordinal,
            "jit_run_id": "gateway-run",
            "jit_contract_version": "jit-cloud-qa-v1",
            "user_uid": driver.QA_OWNER_UID,
            "provider": "openai",
            "configured_model": "gpt-5.6-luna",
            "actual_model_version": "gpt-5.6-luna-2026-01-01",
            "rate_card_id": "test-card",
            "cost_basis": "test",
            "usage_status": "confirmed",
            "cost_status": "estimated",
            "uncached_input_tokens": 100 + ordinal,
            "cached_input_tokens": 2,
            "cache_write_tokens": 3,
            "output_tokens": 20,
            "reasoning_tokens": 4 + ordinal,
            "estimated_cost_micro_usd": cost,
        }

    result = driver.export_durable_jit_receipt(
        Client([Document(row("attempt-2", 2, 200)), Document(row("attempt-1", 1, 100))]),
        execution_id="gateway-run",
        owner_id=driver.QA_OWNER_UID,
    )
    receipt = result["jit_gateway_receipts"][0]
    assert [item["attempt_id"] for item in receipt["attempts"]] == ["attempt-1", "attempt-2"]
    assert receipt["aggregate"] == {
        "attempt_count": 2,
        "normalized_uncached_input_tokens": 203,
        "cached_input_tokens": 4,
        "cache_write_tokens": 6,
        "output_tokens": 40,
        "reasoning_tokens": 11,
        "estimated_cost_micro_usd": 300,
        "cost_status": "estimated",
    }


def test_export_durable_jit_receipt_rejects_wrong_execution_or_owner() -> None:
    class Document:
        def __init__(self, value: dict) -> None:
            self.value = value

        def to_dict(self) -> dict:
            return self.value

    class Query:
        def where(self, *, filter: object) -> "Query":
            return self

        def limit(self, count: int) -> "Query":
            return self

        def stream(self) -> list[Document]:
            return [
                Document(
                    {
                        "attempt_id": "attempt",
                        "jit_run_id": "other-run",
                        "jit_contract_version": "jit-cloud-qa-v1",
                        "user_uid": driver.QA_OWNER_UID,
                    }
                )
            ]

    class Client:
        def collection(self, name: str) -> Query:
            return Query()

    with pytest.raises(driver.EvidenceError, match="different JIT execution"):
        driver.export_durable_jit_receipt(Client(), execution_id="gateway-run", owner_id=driver.QA_OWNER_UID)


def test_export_durable_jit_receipt_preserves_unknown_cost() -> None:
    class Document:
        def to_dict(self) -> dict:
            return {
                "attempt_id": "attempt",
                "jit_run_id": "gateway-run",
                "jit_contract_version": "jit-cloud-qa-v1",
                "user_uid": driver.QA_OWNER_UID,
                "provider": "openai",
                "configured_model": "gpt-5.6-luna",
                "actual_model_version": "gpt-5.6-luna-2026-01-01",
                "rate_card_id": "test-card",
                "cost_basis": "usage_unknown",
                "usage_status": "indeterminate",
                "cost_status": "indeterminate",
                "uncached_input_tokens": 10,
                "cached_input_tokens": 0,
                "cache_write_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_micro_usd": None,
            }

    class Query:
        def where(self, *, filter: object) -> "Query":
            return self

        def limit(self, count: int) -> "Query":
            return self

        def stream(self) -> list[Document]:
            return [Document()]

    class Client:
        def collection(self, name: str) -> Query:
            return Query()

    receipt = driver.export_durable_jit_receipt(Client(), execution_id="gateway-run", owner_id=driver.QA_OWNER_UID)[
        "jit_gateway_receipts"
    ][0]
    assert receipt["aggregate"]["estimated_cost_micro_usd"] is None
    assert receipt["aggregate"]["cost_status"] == "unknown"


def test_capture_endpoint_observation_joins_actual_header_and_input_hashes(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    plan = _plan()
    case = next(item for item in fixture["cases"] if item["case_id"] == "actionable_deadline")
    materialized = driver._materialized_prompts(case, "legacy", "full")
    headers = tmp_path / "response.headers"
    headers.write_text("HTTP/1.1 200 OK\r\nX-Omi-Request-ID: legacy-request-1\r\n\r\n", encoding="latin-1")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(case["shared_evidence"]), encoding="utf-8")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(materialized["prompt"], encoding="utf-8")

    result = driver.capture_endpoint_observation(
        plan,
        headers_path=headers,
        evidence_path=evidence,
        prompt_path=prompt,
        comparison_run_id="comparison-legacy-1",
        owner_id=driver.QA_OWNER_UID,
        case_id="actionable_deadline",
        architecture="legacy",
        stage="full",
    )

    observation = result["request_observations"][0]
    assert observation["request_id"] == "legacy-request-1"
    assert observation["run_id"] == "comparison-legacy-1"
    assert observation["evidence_sha256"] == plan["cases"][0]["matched_input"]["evidence_sha256"]
    assert observation["prompt_sha256"] == plan["cases"][0]["legacy"]["prompt_hashes"]["prompt_sha256"]

    headers.write_text("HTTP/1.1 200 OK\r\n\r\n", encoding="latin-1")
    with pytest.raises(driver.EvidenceError, match="X-Omi-Request-ID"):
        driver.capture_endpoint_observation(
            plan,
            headers_path=headers,
            evidence_path=evidence,
            prompt_path=prompt,
            comparison_run_id="comparison-legacy-2",
            owner_id=driver.QA_OWNER_UID,
            case_id="actionable_deadline",
            architecture="legacy",
            stage="full",
        )


def test_capture_endpoint_marks_actual_nano_only_for_source_request(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    plan = _plan()
    case = next(item for item in plan["cases"] if item["case_id"] == "actionable_deadline")
    actual_request_id = "actual-nano-request"
    case["jit"]["nano"]["actual_nano_billing"] = {
        "dispatch": "observed",
        "request_id": actual_request_id,
    }
    fixture_case = next(item for item in fixture["cases"] if item["case_id"] == "actionable_deadline")
    materialized = driver._materialized_prompts(fixture_case, "jit", "nano")
    headers = tmp_path / "nano.headers"
    headers.write_text(f"HTTP/1.1 200 OK\r\nX-Omi-Request-ID: {actual_request_id}\r\n\r\n", encoding="latin-1")
    evidence = tmp_path / "nano.evidence.json"
    evidence.write_text(json.dumps(fixture_case["shared_evidence"]), encoding="utf-8")
    prompt = tmp_path / "nano.prompt.txt"
    prompt.write_text(materialized["prompt"], encoding="utf-8")

    result = driver.capture_endpoint_observation(
        plan,
        headers_path=headers,
        evidence_path=evidence,
        prompt_path=prompt,
        comparison_run_id="comparison-actual-nano",
        owner_id=driver.QA_OWNER_UID,
        case_id="actionable_deadline",
        architecture="jit",
        stage="nano",
        receipt_origin="actual",
    )
    assert result["request_observations"][0]["receipt_origin"] == "actual"

    headers.write_text("HTTP/1.1 200 OK\r\nX-Omi-Request-ID: other-request\r\n\r\n", encoding="latin-1")
    with pytest.raises(driver.EvidenceError, match="differs from producer nano billing"):
        driver.capture_endpoint_observation(
            plan,
            headers_path=headers,
            evidence_path=evidence,
            prompt_path=prompt,
            comparison_run_id="comparison-actual-nano-2",
            owner_id=driver.QA_OWNER_UID,
            case_id="actionable_deadline",
            architecture="jit",
            stage="nano",
            receipt_origin="actual",
        )

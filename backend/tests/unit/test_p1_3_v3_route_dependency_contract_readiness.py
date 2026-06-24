import importlib.util
import json
from pathlib import Path

REQUIRED_CONTRACT_EVIDENCE = [
    "authenticated_subject_binding_required_before_any_read",
    "legacy_token_api_key_mcp_auth_behavior_inventory_required",
    "client_uid_override_rejected_before_read_source_selection",
    "non_enrolled_legacy_boundary_and_enrolled_memory_boundary_required",
    "rate_limit_or_backpressure_dependency_hook_required_for_get",
    "missing_invalid_auth_control_cursor_config_fail_closed_required",
    "real_testclient_scenarios_blocked_until_runtime_route_wiring_exists",
]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("p1_3_v3_route_dependency_contract_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(execute=False):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_route_dependency_contract_readiness.py")
    return module.build_report(execute=execute)


def test_route_dependency_contract_runner_exists_and_is_safe_by_default():
    report = _report(execute=False)

    assert report["artifact"] == "p1_3_v3_route_dependency_contract_readiness"
    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "NOT_RUN"
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["runtime_wiring_changed"] is False
    assert report["routers_memories_modified"] is False
    assert report["production_app_imported"] is False
    assert report["app_startup_executed"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["pinecone_calls_executed"] is False
    assert report["telemetry_sink_calls_executed"] is False
    assert report["approval_claimed"] is False


def test_route_dependency_contract_pins_required_auth_rate_limit_fail_closed_evidence():
    report = _report(execute=False)

    assert report["route"] == "GET /v3/memories"
    assert report["contract_evidence_count"] == len(REQUIRED_CONTRACT_EVIDENCE)
    assert [item["evidence_id"] for item in report["required_contract_evidence"]] == REQUIRED_CONTRACT_EVIDENCE
    assert all(item["status"] == "BLOCKED" for item in report["required_contract_evidence"])
    assert all(item["required_before_runtime_wiring"] is True for item in report["required_contract_evidence"])
    assert report["summary"]["blocked_contract_evidence_count"] == len(REQUIRED_CONTRACT_EVIDENCE)
    assert report["summary"]["real_testclient_scenario_count"] >= 8


def test_route_dependency_contract_defines_scenarios_without_claiming_execution():
    report = _report(execute=True)
    scenarios = {scenario["scenario_id"]: scenario for scenario in report["blocked_testclient_scenarios"]}

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "BLOCKED"
    assert scenarios["missing_auth"]["expected_behavior"] == "401_or_403_before_any_read"
    assert scenarios["invalid_auth"]["expected_behavior"] == "401_or_403_before_any_read"
    assert scenarios["client_uid_override"]["expected_behavior"] == "ignored_or_rejected_authenticated_uid_wins"
    assert (
        scenarios["non_enrolled_legacy_safe"]["expected_behavior"]
        == "legacy_primary_only_current_limit_offset_semantics"
    )
    assert scenarios["enrolled_control_missing"]["expected_behavior"] == "503_fail_closed_no_legacy_fallback"
    assert (
        scenarios["cursor_invalid_or_generation_mismatch"]["expected_behavior"]
        == "400_or_503_fail_closed_no_legacy_fallback"
    )
    assert scenarios["rate_limited_or_backpressured"]["expected_behavior"] == "429_or_retry_after_before_read"
    assert scenarios["config_missing_or_disabled"]["expected_behavior"] == "503_fail_closed_no_legacy_fallback"
    assert all(scenario["executed_now"] is False for scenario in scenarios.values())
    assert all(scenario["blocked_until_route_wiring"] is True for scenario in scenarios.values())


def test_route_dependency_contract_logging_and_side_effect_guards_are_explicit():
    report = json.loads(json.dumps(_report(execute=False), sort_keys=True))

    assert report["logging_contract"] == {
        "logs_secret_material": False,
        "logs_cursor_token": False,
        "logs_user_content": False,
        "logs_client_supplied_uid": False,
        "allowed_low_cardinality_fields": [
            "route",
            "auth_result",
            "rate_limit_result",
            "read_decision",
            "fail_closed_reason",
            "cohort",
            "projection_generation_match",
        ],
    }
    assert report["production_call_contract"] == {
        "firestore_reads_allowed_by_default": False,
        "firestore_writes_allowed": False,
        "provider_or_vector_calls_allowed": False,
        "network_calls_allowed": False,
        "telemetry_sink_calls_allowed": False,
        "mutating_routes_allowed": False,
    }
    assert (
        "No secret material, cursor token, client-supplied uid, or user memory content logging." in report["non_claims"]
    )


def test_route_dependency_contract_is_static_readiness_only_and_registered():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "p1_3_v3_route_dependency_contract_readiness.py"
    source = script_path.read_text(encoding="utf-8")
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    external_script = (root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")
    runtime_script = (root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text(encoding="utf-8")

    assert "backend.routers.memories" not in source
    assert "routers.memories" not in source
    assert "requests." not in source
    assert "TestClient(" not in source
    assert "telemetry" in source
    assert "test_p1_3_v3_route_dependency_contract_readiness.py" in test_sh
    assert "route_dependency_contract_readiness_proof" in external_script
    assert "route_dependency_contract_readiness_proof" in runtime_script
    assert "p1_3_v3_route_dependency_contract_readiness.py" in ticket_doc
    assert "route dependency auth/rate-limit/fail-closed readiness contract" in ticket_doc
    assert "p1_3_v3_route_dependency_contract_readiness.py" in oracle_doc
    assert "route dependency auth/rate-limit/fail-closed readiness contract" in oracle_doc

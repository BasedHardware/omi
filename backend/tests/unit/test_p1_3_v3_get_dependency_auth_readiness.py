import importlib.util
import json
from pathlib import Path

REQUIRED_COVERED_DEFAULTS = [
    "real_get_route_uses_auth_get_current_user_uid_dependency",
    "minimal_fastapi_app_can_override_get_auth_dependency_to_stub_uid",
    "get_without_auth_override_is_blocked_in_controlled_testclient_probe",
    "current_get_route_has_no_rate_limit_dependency",
    "get_with_auth_override_calls_stubbed_legacy_get_memories_for_non_enrolled_baseline",
    "no_v17_cohort_control_dependency_present_or_invoked",
    "no_main_app_startup_no_external_calls_no_mutations_no_runtime_cutover",
]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_get_dependency_auth_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(execute=True):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_get_dependency_auth_readiness.py")
    return module.build_report(execute=execute)


def test_get_dependency_auth_readiness_runner_exists_and_is_safe():
    report = _report(execute=False)

    assert report["artifact"] == "v17_p1_3_v3_get_dependency_auth_readiness"
    assert report["status"] in {"PARTIAL", "BLOCKED"}
    assert report["proof_status"] == "NOT_RUN"
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["production_app_imported"] is False
    assert report["app_startup_executed"] is False
    assert report["runtime_wiring_changed"] is False
    assert report["routers_memories_modified"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["pinecone_calls_executed"] is False
    assert report["approval_claimed"] is False


def test_get_dependency_auth_probe_pins_auth_override_and_blocked_without_override():
    report = _report(execute=True)
    probe = report["probe"]

    assert report["proof_status"] == "PARTIAL"
    assert probe["testclient_ok"] is True
    assert probe["minimal_fastapi_app_created"] is True
    assert probe["real_router_included_under_stubs"] is True
    assert probe["auth_dependency_overridden"] is True
    assert probe["without_auth_override"]["blocked"] is True
    assert probe["without_auth_override"]["status_code"] == 500
    assert probe["without_auth_override"]["stubbed_auth_call_count"] == 1
    assert probe["with_auth_override"]["status_code"] == 200
    assert probe["with_auth_override"]["observed_legacy_call"] == {
        "uid": "stubbed-auth-uid",
        "limit": 5000,
        "offset": 0,
    }
    assert probe["stubbed_legacy_get_memories_call_count"] == 1


def test_get_dependency_auth_probe_pins_route_dependencies_and_no_rate_limit():
    report = _report(execute=True)
    route = report["route_dependency_evidence"]
    probe = report["probe"]

    assert route["route"] == "GET /v3/memories"
    assert route["handler"] == "get_memories"
    assert route["auth_dependency"] == "utils.other.endpoints.get_current_user_uid"
    assert route["auth_dependency_equivalent"] == "routers.memories.auth.get_current_user_uid"
    assert route["uses_expected_auth_dependency"] is True
    assert route["rate_limit_dependency"] is None
    assert route["rate_limit_policy"] is None
    assert route["has_rate_limit_dependency"] is False
    assert probe["rate_limit_call_count"] == 0
    assert probe["dependency_calls"] == ["auth.get_current_user_uid"]


def test_get_dependency_auth_probe_preserves_non_enrolled_legacy_and_no_v17_control():
    report = _report(execute=True)
    probe = report["probe"]

    assert probe["with_auth_override"]["body"][0]["id"] == "legacy-auth-proof"
    assert probe["with_auth_override"]["body"][0]["uid"] == "stubbed-auth-uid"
    assert probe["with_auth_override"]["body"][0]["content"] == "legacy dependency/auth proof memory"
    assert probe["v17_control_dependency_present"] is False
    assert probe["v17_control_dependency_invoked"] is False
    assert probe["v17_adapter_modules_loaded"] == []
    assert report["v17_cohort_control_dependency_present"] is False
    assert report["v17_cohort_control_dependency_invoked"] is False
    assert report["stubbed_legacy_get_memories_executed"] is True
    assert report["non_enrolled_legacy_behavior_preserved_under_auth_override"] is True


def test_get_dependency_auth_non_claims_summary_and_json_are_stable():
    decoded = json.loads(json.dumps(_report(execute=True), sort_keys=True))

    assert decoded["summary"] == {
        "status": "PARTIAL",
        "proof_status": "PARTIAL",
        "testclient_ok": True,
        "expected_auth_dependency_present": True,
        "auth_override_works": True,
        "without_auth_override_blocked": True,
        "has_rate_limit_dependency": False,
        "stubbed_legacy_get_memories_call_count": 1,
        "v17_cohort_control_dependency_present": False,
        "v17_cohort_control_dependency_invoked": False,
        "runtime_cutover_claimed": False,
    }
    assert decoded["proof"]["covered_defaults"] == REQUIRED_COVERED_DEFAULTS
    assert "No backend/routers/memories.py runtime wiring changed." in decoded["non_claims"]
    assert (
        "No V17 cohort/control dependency is currently present or invoked by GET /v3/memories." in decoded["non_claims"]
    )


def test_get_dependency_auth_readiness_is_registered_and_linked():
    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    external_script = (root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")
    runtime_script = (root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")

    assert "test_p1_3_v3_get_dependency_auth_readiness.py" in test_sh
    assert "get_dependency_auth_readiness_proof" in external_script
    assert "get_dependency_auth_readiness_proof" in runtime_script
    assert "p1_3_v3_get_dependency_auth_readiness.py" in ticket_doc
    assert "GET dependency/auth/rate-limit TestClient proof" in ticket_doc
    assert "p1_3_v3_get_dependency_auth_readiness.py" in oracle_doc
    assert "GET dependency/auth/rate-limit TestClient proof" in oracle_doc

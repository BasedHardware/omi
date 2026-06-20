import importlib.util
import json
from pathlib import Path


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_account_generation_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(execute=False):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_account_generation_readiness.py")
    return module.build_report(execute=execute)


def test_account_generation_readiness_is_safe_and_blocked_by_default():
    report = _report(execute=False)

    assert report["artifact"] == "v17_p1_3_v3_account_generation_readiness"
    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "NOT_RUN"
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["runtime_wiring_changed"] is False
    assert report["routers_memories_modified"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["production_rollout_approved"] is False


def test_account_generation_readiness_identifies_independent_state_head_and_remaining_blocker():
    report = _report(execute=True)

    assert report["proof_status"] == "LOCAL_CONTRACT_PROVED_RUNTIME_BLOCKED"
    source = report["trusted_account_generation_source"]
    assert source["canonical_path"] == "users/{uid}/memory_state/head"
    assert source["reader_contract"] == "backend/utils/memory/v17_v3_account_generation_source.py"
    assert source["server_owned"] is True
    assert source["independent_from_control_doc"] is True
    assert source["independent_from_projection_doc"] is True
    assert source["client_supplied_generation_trusted"] is False
    assert source["used_for_runtime_expected_generation_now"] is False
    assert source["runtime_wired"] is False

    blocker = report["remaining_runtime_blocker"]
    assert blocker["status"] == "BLOCKED"
    assert "writer/emulator evidence" in blocker["required_before_runtime_change"]
    assert blocker["runtime_wired"] is False


def test_account_generation_readiness_requires_four_way_generation_equality_without_self_compare():
    report = _report(execute=True)
    equality = report["future_route_generation_requirements"]

    assert equality["expected_account_generation_source"] == "trusted_memory_state_head_reader"
    assert equality["must_equal"] == [
        "trusted_account_generation",
        "control_state.account_generation",
        "projection_state.account_generation",
        "cursor.account_generation_when_present",
    ]
    assert equality["forbidden_shortcuts"] == [
        "copy_control_state_account_generation_into_expected_account_generation",
        "copy_projection_state_account_generation_into_expected_account_generation",
        "trust_client_supplied_expected_account_generation",
    ]
    assert equality["fail_closed_reasons"] == [
        "missing_state_head",
        "malformed_state_head",
        "uid_mismatch",
        "source_mismatch",
        "unsupported_schema",
        "malformed_account_generation",
        "read_failed",
        "trusted_control_projection_cursor_generation_mismatch",
    ]


def test_account_generation_readiness_json_summary_and_docs_registration_are_stable():
    decoded = json.loads(json.dumps(_report(execute=True), sort_keys=True))
    assert decoded["summary"] == {
        "status": "BLOCKED",
        "proof_status": "LOCAL_CONTRACT_PROVED_RUNTIME_BLOCKED",
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "approval_claimed": False,
        "trusted_source_identified": True,
        "remaining_runtime_blocker_count": 1,
    }

    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    external = (root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")

    assert "test_v17_v3_account_generation_source.py" in test_sh
    assert "test_v17_p1_3_v3_account_generation_readiness.py" in test_sh
    assert "v17_p1_3_v3_account_generation_readiness.py" in ticket_doc
    assert "trusted account-generation source/readiness" in ticket_doc
    assert "v17_p1_3_v3_account_generation_readiness.py" in oracle_doc
    assert "trusted account-generation source/readiness" in oracle_doc
    assert "account_generation_readiness_proof" in external

import importlib.util
import json
from pathlib import Path

REQUIRED_REQUIREMENT_IDS = [
    "canonical_projection_path_api",
    "memorydb_materialization_fields",
    "generation_account_projection_freshness_fences",
    "source_commit_version_evidence_fences",
    "delete_tombstone_vector_cleanup_fences",
    "enabled_empty_representation",
    "archive_and_short_term_defaults",
    "pagination_cursor_compatibility",
    "fake_injectable_read_interface",
]

REQUIRED_PROOF_KEYS = {
    "projection_readiness_proof",
    "memory_read_service_proof",
    "request_adapter_proof",
    "response_adapter_proof",
    "route_planner_proof",
    "write_convergence_proof",
    "cursor_service_proof",
    "fastapi_route_contract_proof",
    "get_runtime_wiring_readiness_proof",
}


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("p1_3_v3_projection_store_readiness", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(execute=False):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_projection_store_readiness.py")
    return module.build_report(execute=execute)


def test_projection_store_readiness_runner_exists_and_is_safe_by_default():
    report = _report(execute=False)

    assert report["artifact"] == "p1_3_v3_projection_store_readiness"
    assert report["status"] == "BLOCKED"
    assert report["proof_status"] in {"NOT_RUN", "BLOCKED"}
    assert report["execute"] is False
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["runtime_wiring_changed"] is False
    assert report["production_store_writes_implemented"] is False
    assert report["projection_read_route_wired"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["cloud_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["pinecone_calls_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False


def test_projection_store_readiness_inventories_exact_store_api_requirements():
    report = _report(execute=True)

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "LOCAL_IMPLEMENTATION_PROVED"
    requirements = {item["requirement_id"]: item for item in report["store_api_requirements"]}
    assert list(requirements) == REQUIRED_REQUIREMENT_IDS

    for requirement_id, requirement in requirements.items():
        assert requirement["status"].startswith("LOCAL_"), requirement_id
        assert requirement["required_before_runtime_change"] is True
        assert requirement["runtime_wired"] is False
        assert requirement["approval_claimed"] is False
        assert requirement["missing_real_firestore_or_api_evidence"] is False
        assert requirement["evidence_sources"], requirement_id

    assert (
        requirements["canonical_projection_path_api"]["canonical_state_path"]
        == "users/{uid}/v3_compatibility_projection/state"
    )
    assert (
        requirements["canonical_projection_path_api"]["canonical_items_path"]
        == "users/{uid}/v3_compatibility_projection_items/{memory_id}"
    )
    assert requirements["canonical_projection_path_api"]["explicit_blocker"] is None
    assert "List[MemoryDB]" in requirements["memorydb_materialization_fields"]["required_contract"]
    assert requirements["memorydb_materialization_fields"]["memory_only_body_fields_forbidden"] == [
        "memory_item_id",
        "generation",
        "source_commit_id",
        "projection_version",
        "projection_freshness_fence",
        "archive_tier",
        "short_term_staleness_reason",
    ]
    assert "account_generation" in requirements["generation_account_projection_freshness_fences"]["required_fields"]
    assert "source_commit_id" in requirements["source_commit_version_evidence_fences"]["required_fields"]
    assert "vector_cleanup_fence" in requirements["delete_tombstone_vector_cleanup_fences"]["required_fields"]
    assert requirements["enabled_empty_representation"]["response_body"] == []
    assert requirements["enabled_empty_representation"]["legacy_fallback_allowed"] is False
    assert requirements["archive_and_short_term_defaults"]["archive_default_available"] is False
    assert requirements["archive_and_short_term_defaults"]["stale_short_term_default_visible"] is False
    assert requirements["pagination_cursor_compatibility"]["legacy_non_enrolled_offset_behavior_preserved"] is True
    assert requirements["pagination_cursor_compatibility"]["v3_cursor_required_before_cutover"] is True
    assert requirements["fake_injectable_read_interface"]["runtime_route_wiring_now"] is False


def test_projection_store_readiness_defines_fake_injectable_read_interface_without_implementation():
    report = _report(execute=True)
    interface = report["fake_injectable_read_interface"]

    assert interface == {
        "interface_name": "V3CompatibilityProjectionReader",
        "method": "read_projection_page",
        "input_fields": [
            "uid",
            "limit",
            "cursor",
            "expected_account_generation",
            "read_mode",
            "include_archive",
            "filter_hash",
        ],
        "output_fields": [
            "items_memorydb_compatible",
            "next_cursor",
            "projection_generation",
            "account_generation",
            "source_commit_id",
            "source_version",
            "projection_commit_id",
            "projection_version",
            "freshness_fence_generation",
            "tombstone_fence_generation",
            "vector_cleanup_fence_generation",
            "empty_projection",
        ],
        "fake_injectable": True,
        "production_firestore_reader_implemented": True,
        "implementation": "backend/database/v3_compatibility_projection.py",
        "contract": "backend/utils/memory/v3_projection_reader_contract.py",
        "emulator_proof": "backend/scripts/p1_3_v3_projection_reader_emulator_test.py",
        "runtime_route_wiring_now": False,
    }


def test_projection_store_readiness_links_existing_local_proofs_and_marks_real_evidence_missing():
    report = _report(execute=True)
    proofs = report["existing_local_proof_artifacts"]

    assert set(proofs) == REQUIRED_PROOF_KEYS
    for proof in proofs.values():
        assert proof["runtime_wired"] is False
        assert proof["production_rollout_approved"] is False
        assert proof["external_calls"] == []
        assert proof["missing_real_firestore_or_api_evidence"] is True

    assert proofs["projection_readiness_proof"]["service"] == "backend/utils/memory/v3_projection_readiness.py"
    assert proofs["memory_read_service_proof"]["service"] == "backend/utils/memory/v3_memory_read_service.py"
    assert proofs["request_adapter_proof"]["service"] == "backend/utils/memory/v3_request_adapter.py"
    assert proofs["response_adapter_proof"]["service"] == "backend/utils/memory/v3_response_adapter.py"
    assert proofs["route_planner_proof"]["service"] == "backend/utils/memory/v3_route_planner.py"


def test_projection_store_readiness_records_safe_next_steps_and_non_claims():
    report = _report(execute=True)

    assert [step["step_id"] for step in report["proposed_next_safe_steps"]] == [
        "choose_canonical_projection_path_and_schema",
        "add_fake_reader_contract_tests",
        "add_firestore_emulator_read_model_proof",
        "prove_projection_writer_convergence_separately",
        "wire_route_only_after_all_gates_pass",
    ]
    assert all(step["implements_runtime_wiring_now"] is False for step in report["proposed_next_safe_steps"])
    assert all(step["implements_production_writes_now"] is False for step in report["proposed_next_safe_steps"])
    assert "No production compatibility projection store writes implemented." in report["non_claims"]
    assert (
        "Local Firestore emulator evidence collected only by npm run test:memory-v3-projection-reader:emulator; no production cloud evidence collected."
        in report["non_claims"]
    )
    assert "No `/v3` route wiring changed." in report["non_claims"]
    assert report["local_implementation_evidence"]["reader"] == "backend/database/v3_compatibility_projection.py"
    assert report["local_implementation_evidence"]["npm_command"] == "npm run test:memory-v3-projection-reader:emulator"


def test_projection_store_readiness_json_summary_is_stable():
    decoded = json.loads(json.dumps(_report(execute=True), sort_keys=True))

    assert decoded["summary"] == {
        "status": "BLOCKED",
        "proof_status": "LOCAL_IMPLEMENTATION_PROVED",
        "requirement_count": 9,
        "blocked_requirement_count": 0,
        "local_implementation_requirement_count": 9,
        "existing_local_proof_count": 9,
        "missing_real_firestore_or_api_evidence_count": 0,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "production_store_writes_implemented": False,
        "approval_claimed": False,
        "safe_next_step_count": 5,
    }


def test_projection_store_readiness_is_registered_in_test_runner_docs_and_parent_readiness():
    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    runtime_readiness = (root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external_readiness = (root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")

    assert "test_p1_3_v3_projection_store_readiness.py" in test_sh
    assert "test_v3_compatibility_projection.py" in test_sh
    assert "p1_3_v3_projection_store_readiness.py" in ticket_doc
    assert "p1_3_v3_projection_reader_emulator_test.py" in ticket_doc
    assert "projection store/API readiness" in ticket_doc
    assert "p1_3_v3_projection_store_readiness.py" in oracle_doc
    assert "test:memory-v3-projection-reader:emulator" in oracle_doc
    assert "projection store/API readiness" in oracle_doc
    assert "projection_store_readiness_proof" in runtime_readiness
    assert "projection_store_readiness_proof" in external_readiness

import importlib.util
import json
from pathlib import Path

REQUIRED_ROUTE_REFERENCES = {
    "GET /v3/memories": "list_default_memories",
    "POST /v3/memories": "create_memory",
    "POST /v3/memories/batch": "batch_create_memory",
    "PATCH /v3/memories/{memory_id}": "edit_memory",
    "DELETE /v3/memories/{memory_id}": "delete_memory",
    "GET /v3/memories/{memory_id}": "missing_read_endpoint_gap",
    "GET /v3/memories/search": "missing_search_endpoint_gap",
}

REQUIRED_GAPS = {
    "disabled_malformed_no_grant_semantics",
    "enabled_empty_semantics",
    "response_shape_source_metadata",
    "archive_default_unavailable",
    "category_filter_compatibility",
    "unsafe_legacy_fallback_after_v17_writes",
    "cursor_pagination_stability",
}


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_external_compatibility_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v3_external_compatibility_runner_exists_and_is_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py"
    assert script_path.exists(), "missing safe /v3 external compatibility readiness runner"

    module = _load_module(script_path)
    report = module.build_report(execute=False)

    assert report["status"] == "BLOCKED"
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["benchmark_evidence_collected"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False
    assert report["execute"] is False


def test_v3_external_compatibility_inventory_pins_exact_route_gaps_and_non_claims():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py")
    report = module.build_report(execute=True)

    assert report["execute"] is True
    assert report["status"] == "BLOCKED"
    routes = {surface["route"]: surface for surface in report["v3_surfaces"]}
    for route, expected_id in REQUIRED_ROUTE_REFERENCES.items():
        assert route in routes
        assert routes[route]["surface_id"] == expected_id
        assert routes[route]["source_file"] == "backend/routers/memories.py"
        assert routes[route]["evidence"] == []

    gaps = {gap["gap_id"]: gap for gap in report["remaining_gaps"]}
    assert REQUIRED_GAPS.issubset(gaps)
    for gap in gaps.values():
        assert gap["status"] in {"BLOCKED", "NOT_RUN"}
        assert gap["evidence"] == []
        assert gap["approval_claimed"] is False


def test_v3_readiness_pins_code_route_evidence_for_runtime_decision_blockers():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py")
    report = module.build_report(execute=True)

    list_surface = {surface["surface_id"]: surface for surface in report["v3_surfaces"]}["list_default_memories"]
    assert (
        list_surface["route_decorator"]
        == "@router.get('/v3/memories', tags=['memories'], response_model=List[MemoryDB])"
    )
    assert list_surface["handler_signature"] == (
        "def get_memories(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):"
    )
    assert list_surface["db_call"] == "memories_db.get_memories(uid, limit, offset)"
    assert list_surface["first_page_limit_override"] == "if offset == 0: limit = 5000"
    assert list_surface["supported_query_params"] == ["limit", "offset"]
    assert list_surface["unsupported_query_params"] == ["category", "cursor", "include_archive", "source"]
    assert list_surface["response_model"] == "List[MemoryDB]"
    assert list_surface["source_metadata_contract"] == "absent"

    create_surface = {surface["surface_id"]: surface for surface in report["v3_surfaces"]}["create_memory"]
    assert create_surface["db_write_call"] == "memories_db.create_memory(uid, payload)"
    assert create_surface["vector_write_call"] == "upsert_memory_vector(...)"
    assert create_surface["v17_write_convergence"] == "absent"

    delete_surface = {surface["surface_id"]: surface for surface in report["v3_surfaces"]}["delete_memory"]
    assert delete_surface["validation_call"] == "_validate_memory(uid, memory_id)"
    assert delete_surface["db_write_call"] == "memories_db.delete_memory(uid, memory_id)"
    assert delete_surface["v17_tombstone_convergence"] == "absent"


def test_v3_readiness_pins_decision_matrix_and_product_dependencies():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py")
    report = module.build_report(execute=True)

    decisions = {decision["state"]: decision for decision in report["runtime_decision_matrix"]}
    for state in ["disabled", "malformed", "missing", "no_default_memory_grant"]:
        assert decisions[state]["required_behavior"] == "fail_closed_or_explicit_legacy_safe_product_decision"
        assert decisions[state]["unsafe_legacy_fallback_allowed"] is False
    assert decisions["enabled_empty"]["required_behavior"] == "return_empty_v17_result_without_legacy_fallback"
    assert decisions["enabled_empty"]["unsafe_legacy_fallback_allowed"] is False
    assert (
        decisions["archive_default"]["required_behavior"] == "default_unavailable_without_explicit_archive_capability"
    )
    assert (
        decisions["cursor_pagination"]["required_behavior"] == "stable_cursor_contract_required_before_runtime_cutover"
    )

    dependencies = {dependency["dependency_id"]: dependency for dependency in report["product_decision_dependencies"]}
    for dependency_id in [
        "v3_disabled_malformed_no_grant_policy",
        "v3_enabled_empty_policy",
        "v3_response_shape_source_metadata",
        "v3_cursor_pagination_contract",
        "v3_write_convergence_before_read_cutover",
    ]:
        assert dependencies[dependency_id]["status"] == "BLOCKED"
        assert dependencies[dependency_id]["approval_claimed"] is False


def test_v3_readiness_pins_prescriptive_oracle_defaults_and_escalations():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py")
    report = module.build_report(execute=True)

    oracle = report["oracle_prescriptive_recommendations"]
    assert oracle["session_slug"] == "v3-v17-compat-prescripti"
    assert oracle["production_approach"] == "additive_v3_compatibility_adapter_over_v17_authoritative_writes"
    assert oracle["default_body_contract"] == "List[MemoryDB]"
    assert oracle["archive_default"] == "not_launched_on_v3_default_reads"
    assert oracle["enabled_empty"] == "200_empty_list_no_legacy_fallback"
    assert oracle["cursor_default"] == "additive_opaque_hmac_keyset_cursor_created_at_desc_memory_id_desc"
    assert oracle["write_convergence"] == "v17_writes_and_compatibility_projection_before_v17_reads"

    defaults = {default["default_id"]: default for default in report["engineering_defaults_locked_now"]}
    assert defaults["non_enrolled_legacy_primary"]["product_escalation_required"] is False
    assert defaults["enrolled_malformed_missing_fail_closed"]["http_status"] == 503
    assert defaults["no_default_memory_grant_privacy_deny"]["http_status"] == 403
    assert defaults["source_metadata_additive_headers"]["body_shape_changed"] is False
    assert defaults["no_legacy_v17_merge_or_exception_fallback"]["unsafe_fallback_allowed"] is False

    escalations = {decision["decision_id"]: decision for decision in report["irreducible_product_api_decisions"]}
    assert set(escalations) == {"no_default_memory_grant_meaning", "legacy_no_cursor_compatibility_window"}
    assert escalations["no_default_memory_grant_meaning"]["recommended_default"] == "privacy_consent_returns_403"
    assert escalations["legacy_no_cursor_compatibility_window"]["recommended_default"] == (
        "preserve_offset_only_for_non_v17_clients_require_cursor_for_v17_cohort"
    )


def test_v3_readiness_pins_oracle_implementation_shape_and_unsafe_approaches():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py")
    report = module.build_report(execute=True)

    shape = report["oracle_implementation_shape"]
    assert shape["decision_service"] == "backend/utils/memory/v17_v3_compatibility.py"
    assert shape["request_adapter"] == "backend/utils/memory/v17_v3_request_adapter.py"
    assert shape["read_service"] == "backend/utils/memory/v17_v3_memory_read_service.py"
    assert shape["response_adapter"] == "backend/utils/memory/v17_v3_response_adapter.py"
    assert shape["projection_store"] == "users/{uid}/memories as V17-derived compatibility projection"
    assert shape["cursor_service"] == "backend/utils/memory/v17_v3_cursor.py"
    assert shape["external_write_service"] == "backend/utils/memory/v17_v3_write_convergence.py"
    assert shape["decision_order"] == [
        "global_emergency_gate",
        "server_side_cohort_membership",
        "versioned_per_user_control_document",
        "exact_uid_schema_validation",
        "default_memory_grant",
        "account_generation",
        "write_convergence_and_projection_readiness",
        "selected_read_path",
    ]

    unsafe = set(report["unsafe_approaches_to_avoid"])
    assert "missing_malformed_or_exception_as_use_legacy" in unsafe
    assert "legacy_v17_result_merge" in unsafe
    assert "fallback_because_v17_returned_zero_results" in unsafe
    assert "include_archive_true_as_authorization" in unsafe
    assert "invented_memorydb_field_defaults_from_memory_items" in unsafe
    assert "offset_based_or_unsigned_cursor" in unsafe
    assert "apply_5000_first_page_override_to_v17_cursor" in unsafe


def test_v3_readiness_links_pure_decision_and_cursor_service_proofs_without_rollout_claims():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py")
    report = module.build_report(execute=True)

    proof = report["decision_service_proof"]
    assert proof["service"] == "backend/utils/memory/v17_v3_compatibility.py"
    assert proof["test"] == "backend/tests/unit/test_v17_v3_compatibility.py"
    assert proof["runtime_wired"] is False
    assert proof["production_rollout_approved"] is False
    assert proof["external_calls"] == []
    assert proof["covered_defaults"] == [
        "non_enrolled_legacy_primary",
        "enrolled_missing_malformed_uid_mismatch_unsupported_timeout_fail_closed_503",
        "no_default_memory_grant_privacy_consent_deny_403_product_overridable",
        "enabled_empty_projection_returns_200_empty_list_no_legacy_fallback",
        "write_convergence_or_projection_not_ready_fail_closed",
        "archive_default_unavailable",
        "list_memorydb_body_header_only_metadata",
        "signed_opaque_keyset_generation_bound_cursor_no_offset_no_5000_override",
        "unsafe_legacy_fallback_after_enrolled_error_or_v17_write_state_not_exposed",
    ]

    cursor_proof = report["cursor_service_proof"]
    assert cursor_proof["service"] == "backend/utils/memory/v17_v3_cursor.py"
    assert cursor_proof["test"] == "backend/tests/unit/test_v17_v3_cursor.py"
    assert cursor_proof["runtime_wired"] is False
    assert cursor_proof["production_rollout_approved"] is False
    assert cursor_proof["external_calls"] == []
    assert cursor_proof["covered_defaults"] == [
        "opaque_hmac_signed_cursor",
        "created_at_desc_memory_id_desc_keyset",
        "uid_bound",
        "account_generation_bound",
        "projection_generation_bound",
        "filter_hash_bound",
        "source_bound",
        "read_mode_bound",
        "expiration_enforced",
        "tamper_rejected_fail_closed",
        "offset_disallowed_in_v17_cursor_mode",
        "legacy_first_page_5000_override_disallowed",
    ]

    projection_proof = report["projection_readiness_proof"]
    assert projection_proof["service"] == "backend/utils/memory/v17_v3_projection_readiness.py"
    assert projection_proof["test"] == "backend/tests/unit/test_v17_v3_projection_readiness.py"
    assert projection_proof["runtime_wired"] is False
    assert projection_proof["production_rollout_approved"] is False
    assert projection_proof["external_calls"] == []
    assert projection_proof["covered_defaults"] == [
        "external_create_update_delete_write_convergence_required",
        "account_generation_present_and_matching",
        "projection_generation_present_and_current",
        "source_v17_derived_compatibility_projection_only",
        "tombstone_delete_fence_present_and_current",
        "source_projection_commit_version_and_freshness_fences_required",
        "missing_stale_inconsistent_projection_fails_closed",
        "enabled_empty_returns_empty_list_only_when_projection_ready",
        "no_legacy_fallback_after_projection_failure",
        "archive_default_unavailable_no_stale_short_term_default_visible",
    ]

    read_service_proof = report["memory_read_service_proof"]
    assert read_service_proof["service"] == "backend/utils/memory/v17_v3_memory_read_service.py"
    assert read_service_proof["test"] == "backend/tests/unit/test_v17_v3_memory_read_service.py"
    assert read_service_proof["runtime_wired"] is False
    assert read_service_proof["production_rollout_approved"] is False
    assert read_service_proof["external_calls"] == []
    assert read_service_proof["covered_defaults"] == [
        "non_enrolled_legacy_primary_plan_marker_only_no_data_fetching",
        "enrolled_missing_malformed_fail_closed_no_legacy_fallback",
        "no_default_memory_grant_privacy_consent_deny_403",
        "projection_not_ready_or_write_convergence_not_ready_fail_closed",
        "enabled_projection_ready_empty_returns_200_empty_list_no_legacy_fallback",
        "projection_ready_page_preserves_caller_supplied_list_memorydb_body",
        "additive_headers_for_read_source_read_decision_next_cursor_link_only",
        "invalid_v17_cursor_offset_or_5000_override_fail_closed_no_downgrade",
        "offset_limit_5000_behavior_legacy_primary_only",
        "archive_default_unavailable_no_stale_short_term_default_visible",
    ]

    write_convergence_proof = report["write_convergence_proof"]
    assert write_convergence_proof["service"] == "backend/utils/memory/v17_v3_write_convergence.py"
    assert write_convergence_proof["test"] == "backend/tests/unit/test_v17_v3_write_convergence.py"
    assert write_convergence_proof["runtime_wired"] is False
    assert write_convergence_proof["production_rollout_approved"] is False
    assert write_convergence_proof["external_calls"] == []
    assert write_convergence_proof["covered_defaults"] == [
        "create_update_require_v17_authoritative_write_path_projection_update_commit_and_current_generation",
        "delete_requires_tombstone_projection_removal_vector_cleanup_outbox_fence",
        "missing_stale_partial_swallowed_failure_dual_write_without_durable_outbox_generation_mismatch_fail_closed",
        "external_writes_disabled_safe_only_when_reads_blocked_or_no_active_write_surfaces",
        "no_enrolled_v17_legacy_direct_write_fallback_knob",
        "archive_default_unavailable_no_stale_short_term_default_visible",
    ]

    response_adapter_proof = report["response_adapter_proof"]
    assert response_adapter_proof["service"] == "backend/utils/memory/v17_v3_response_adapter.py"
    assert response_adapter_proof["test"] == "backend/tests/unit/test_v17_v3_response_adapter.py"
    assert response_adapter_proof["runtime_wired"] is False
    assert response_adapter_proof["production_rollout_approved"] is False
    assert response_adapter_proof["external_calls"] == []
    assert response_adapter_proof["covered_defaults"] == [
        "pure_local_read_service_envelope_to_memorydb_response_adapter",
        "preserve_list_memorydb_body_no_source_policy_cursor_fields_in_body",
        "additive_headers_only_read_source_read_decision_next_cursor_link_rel_next",
        "enabled_empty_returns_empty_list_with_v17_headers_no_legacy_fallback_marker",
        "fail_closed_and_denied_have_no_body_data_no_legacy_fallback_marker",
        "reject_v17_only_body_source_policy_cursor_diagnostics_fields",
        "archive_default_unavailable_no_stale_short_term_default_visible_proof_fields_only",
    ]

    request_adapter_proof = report["request_adapter_proof"]
    assert request_adapter_proof["service"] == "backend/utils/memory/v17_v3_request_adapter.py"
    assert request_adapter_proof["test"] == "backend/tests/unit/test_v17_v3_request_adapter.py"
    assert request_adapter_proof["runtime_wired"] is False
    assert request_adapter_proof["production_rollout_approved"] is False
    assert request_adapter_proof["external_calls"] == []
    assert request_adapter_proof["covered_defaults"] == [
        "pure_local_query_parameter_to_read_service_request_contract",
        "legacy_limit_offset_preserved_as_legacy_primary_only",
        "v17_cursor_mode_disallows_offset_and_5000_first_page_override",
        "v17_limit_bounds_validated_without_expanding_to_5000",
        "category_filter_state_bound_into_filter_hash_and_cursor_binding",
        "unsupported_filters_fail_closed_no_silent_legacy_fallback",
        "include_archive_default_false_unavailable_explicit_archive_blocked_for_v3_default",
        "source_and_read_mode_bounded_to_v17_compatibility_projection",
        "no_fastapi_dependency_route_wiring_external_calls_or_mutations",
    ]

    route_planner_proof = report["route_planner_proof"]
    assert route_planner_proof["service"] == "backend/utils/memory/v17_v3_route_planner.py"
    assert route_planner_proof["test"] == "backend/tests/unit/test_v17_v3_route_planner.py"
    assert route_planner_proof["runtime_wired"] is False
    assert route_planner_proof["production_rollout_approved"] is False
    assert route_planner_proof["external_calls"] == []
    assert route_planner_proof["covered_defaults"] == [
        "pure_local_route_adjacent_composition_no_route_wiring_or_data_fetching",
        "composes_request_adapter_decision_write_projection_read_response_seams",
        "non_enrolled_legacy_primary_plan_marker_only_preserves_limit_offset",
        "enrolled_valid_request_returns_list_memorydb_response_with_additive_headers",
        "enrolled_invalid_request_cursor_filter_archive_fail_closed_no_legacy_fallback",
        "enrolled_malformed_no_grant_projection_not_ready_write_not_ready_fail_closed_or_deny",
        "enabled_empty_returns_200_empty_list_no_legacy_fallback",
        "archive_default_unavailable_no_stale_short_term_default_visible",
    ]


def test_v3_readiness_json_round_trips_and_command_summary_is_stable():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py")
    report = module.build_report(execute=True)
    encoded = json.dumps(report, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["summary"] == {
        "status": "BLOCKED",
        "surface_count": 7,
        "gap_count": 7,
        "decision_state_count": 8,
        "product_dependency_count": 5,
        "decision_service_proof_present": True,
        "cursor_service_proof_present": True,
        "projection_readiness_proof_present": True,
        "memory_read_service_proof_present": True,
        "write_convergence_proof_present": True,
        "response_adapter_proof_present": True,
        "request_adapter_proof_present": True,
        "route_planner_proof_present": True,
        "route_signature_integration_proof_present": True,
        "fastapi_route_contract_proof_present": True,
        "real_router_dependency_map_proof_present": True,
        "real_router_get_testclient_proof_present": True,
        "get_dependency_auth_readiness_proof_present": True,
        "projection_store_readiness_proof_present": True,
        "read_only": True,
        "mutation_allowed": False,
        "approval_claimed": False,
    }


def test_v3_readiness_is_registered_in_test_runner_and_oracle_docs():
    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")

    assert "test_v17_p1_3_v3_external_compatibility_readiness.py" in test_sh
    assert "test_v17_v3_compatibility.py" in test_sh
    assert "test_v17_v3_cursor.py" in test_sh
    assert "test_v17_v3_projection_readiness.py" in test_sh
    assert "test_v17_v3_memory_read_service.py" in test_sh
    assert "test_v17_v3_write_convergence.py" in test_sh
    assert "test_v17_v3_response_adapter.py" in test_sh
    assert "test_v17_v3_request_adapter.py" in test_sh
    assert "test_v17_v3_route_planner.py" in test_sh
    assert "test_v17_p1_3_v3_route_signature_integration.py" in test_sh
    assert "test_v17_p1_3_v3_real_router_dependency_map.py" in test_sh
    assert "test_v17_p1_3_v3_real_router_get_testclient.py" in test_sh
    assert "test_v17_p1_3_v3_get_dependency_auth_readiness.py" in test_sh
    assert "test_v17_p1_3_v3_projection_store_readiness.py" in test_sh
    assert "v17_p1_3_v3_external_compatibility_readiness.py" in ticket_doc
    assert "backend/utils/memory/v17_v3_compatibility.py" in ticket_doc
    assert "backend/utils/memory/v17_v3_cursor.py" in ticket_doc
    assert "backend/utils/memory/v17_v3_projection_readiness.py" in ticket_doc
    assert "backend/utils/memory/v17_v3_memory_read_service.py" in ticket_doc
    assert "backend/utils/memory/v17_v3_write_convergence.py" in ticket_doc
    assert "backend/utils/memory/v17_v3_response_adapter.py" in ticket_doc
    assert "backend/utils/memory/v17_v3_request_adapter.py" in ticket_doc
    assert "backend/utils/memory/v17_v3_route_planner.py" in ticket_doc
    assert "v17_p1_3_v3_route_signature_integration.py" in ticket_doc
    assert "v17_p1_3_v3_real_router_dependency_map.py" in ticket_doc
    assert "v17_p1_3_v3_real_router_get_testclient.py" in ticket_doc
    assert "v17_p1_3_v3_get_dependency_auth_readiness.py" in ticket_doc
    assert "v17_p1_3_v3_projection_store_readiness.py" in ticket_doc
    assert "Oracle P1-3 `/v3` external compatibility readiness slice" in ticket_doc
    assert "v17_p1_3_v3_external_compatibility_readiness.py" in oracle_doc
    assert "backend/utils/memory/v17_v3_compatibility.py" in oracle_doc
    assert "backend/utils/memory/v17_v3_cursor.py" in oracle_doc
    assert "backend/utils/memory/v17_v3_projection_readiness.py" in oracle_doc
    assert "backend/utils/memory/v17_v3_memory_read_service.py" in oracle_doc
    assert "backend/utils/memory/v17_v3_write_convergence.py" in oracle_doc
    assert "backend/utils/memory/v17_v3_response_adapter.py" in oracle_doc
    assert "backend/utils/memory/v17_v3_request_adapter.py" in oracle_doc
    assert "backend/utils/memory/v17_v3_route_planner.py" in oracle_doc
    assert "v17_p1_3_v3_route_signature_integration.py" in oracle_doc
    assert "v17_p1_3_v3_real_router_dependency_map.py" in oracle_doc
    assert "v17_p1_3_v3_real_router_get_testclient.py" in oracle_doc
    assert "v17_p1_3_v3_get_dependency_auth_readiness.py" in oracle_doc
    assert "v17_p1_3_v3_projection_store_readiness.py" in oracle_doc
    assert "local `/v3` external compatibility readiness slice" in oracle_doc

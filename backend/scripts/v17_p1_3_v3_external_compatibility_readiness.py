#!/usr/bin/env python3
"""Safe Oracle P1-3 `/v3` external compatibility readiness inventory.

This runner is intentionally proof-only. It does not import FastAPI routers, read
Firestore, call providers, mutate state, run production traffic, or claim approval.
It pins the exact `/v3` route surfaces and remaining compatibility gaps that must
be resolved before external V17 rollout can be approved.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

V3_SURFACES = [
    {
        "surface_id": "list_default_memories",
        "route": "GET /v3/memories",
        "source_file": "backend/routers/memories.py",
        "handler": "get_memories",
        "route_decorator": "@router.get('/v3/memories', tags=['memories'], response_model=List[MemoryDB])",
        "handler_signature": "def get_memories(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):",
        "db_call": "memories_db.get_memories(uid, limit, offset)",
        "first_page_limit_override": "if offset == 0: limit = 5000",
        "supported_query_params": ["limit", "offset"],
        "unsupported_query_params": ["category", "cursor", "include_archive", "source"],
        "response_model": "List[MemoryDB]",
        "source_metadata_contract": "absent",
        "current_read_source": "legacy users/{uid}/memories via database.memories.get_memories",
        "v17_gap": "No route-local V17 rollout decision/read seam or source metadata contract is wired here yet.",
        "status": "BLOCKED",
        "evidence": [],
    },
    {
        "surface_id": "create_memory",
        "route": "POST /v3/memories",
        "source_file": "backend/routers/memories.py",
        "handler": "create_memory",
        "db_write_call": "memories_db.create_memory(uid, payload)",
        "vector_write_call": "upsert_memory_vector(...) ".strip(),
        "v17_write_convergence": "absent",
        "current_read_source": "legacy users/{uid}/memories write plus vector upsert",
        "v17_gap": "External write convergence/dual-write semantics are not proven for V17 memory_items.",
        "status": "BLOCKED",
        "evidence": [],
    },
    {
        "surface_id": "batch_create_memory",
        "route": "POST /v3/memories/batch",
        "source_file": "backend/routers/memories.py",
        "handler": "create_memories_batch",
        "current_read_source": "legacy users/{uid}/memories batch write plus vector upsert",
        "v17_gap": "Batch write convergence and rollback semantics are not proven for V17 memory_items.",
        "status": "BLOCKED",
        "evidence": [],
    },
    {
        "surface_id": "edit_memory",
        "route": "PATCH /v3/memories/{memory_id}",
        "source_file": "backend/routers/memories.py",
        "handler": "edit_memory",
        "current_read_source": "legacy users/{uid}/memories validation/edit plus vector re-upsert",
        "v17_gap": "V17 edit/update convergence and no unsafe fallback after V17 writes are not proven.",
        "status": "BLOCKED",
        "evidence": [],
    },
    {
        "surface_id": "delete_memory",
        "route": "DELETE /v3/memories/{memory_id}",
        "source_file": "backend/routers/memories.py",
        "handler": "delete_memory",
        "validation_call": "_validate_memory(uid, memory_id)",
        "db_write_call": "memories_db.delete_memory(uid, memory_id)",
        "v17_tombstone_convergence": "absent",
        "current_read_source": "legacy users/{uid}/memories validation/delete plus vector delete",
        "v17_gap": "V17 tombstone/delete/account-generation convergence is not proven for external callers.",
        "status": "BLOCKED",
        "evidence": [],
    },
    {
        "surface_id": "missing_read_endpoint_gap",
        "route": "GET /v3/memories/{memory_id}",
        "source_file": "backend/routers/memories.py",
        "handler": None,
        "current_read_source": "not registered in backend/routers/memories.py",
        "v17_gap": "No single-memory external read route is available to prove read/list shape parity.",
        "status": "NOT_RUN",
        "evidence": [],
    },
    {
        "surface_id": "missing_search_endpoint_gap",
        "route": "GET /v3/memories/search",
        "source_file": "backend/routers/memories.py",
        "handler": None,
        "current_read_source": "not registered in backend/routers/memories.py",
        "v17_gap": "No `/v3` semantic search route is available to prove list/search shape parity.",
        "status": "NOT_RUN",
        "evidence": [],
    },
]

REMAINING_GAPS = [
    {
        "gap_id": "disabled_malformed_no_grant_semantics",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_proof": "Decide and test whether disabled, malformed, missing, or no-grant rollout returns legacy-safe, empty, or explicit denial for `/v3`; do not allow implicit unsafe legacy fallback after V17-write states.",
        "approval_claimed": False,
        "evidence": [],
    },
    {
        "gap_id": "enabled_empty_semantics",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_proof": "When V17 default reads are explicitly enabled and `memory_items` is empty, prove `/v3` returns an empty V17 result without falling back to stale legacy rows.",
        "approval_claimed": False,
        "evidence": [],
    },
    {
        "gap_id": "response_shape_source_metadata",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_proof": "Define and test additive V17/default policy and source metadata in the external MemoryDB-compatible response shape without silently fabricating category/review/manual/edit fields.",
        "approval_claimed": False,
        "evidence": [],
    },
    {
        "gap_id": "archive_default_unavailable",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_proof": "Prove Archive tier is default-unavailable for `/v3` unless an explicit Archive-capable product decision exists.",
        "approval_claimed": False,
        "evidence": [],
    },
    {
        "gap_id": "category_filter_compatibility",
        "status": "NOT_RUN",
        "route_refs": ["GET /v3/memories"],
        "required_proof": "`/v3` currently exposes limit/offset only; category/filter compatibility needs a product/API decision and fixtures before runtime changes.",
        "approval_claimed": False,
        "evidence": [],
    },
    {
        "gap_id": "unsafe_legacy_fallback_after_v17_writes",
        "status": "BLOCKED",
        "route_refs": [
            "POST /v3/memories",
            "POST /v3/memories/batch",
            "PATCH /v3/memories/{memory_id}",
            "DELETE /v3/memories/{memory_id}",
        ],
        "required_proof": "External create/edit/delete must have a durable V17 convergence plan before `/v3` read fallback semantics can be broadened.",
        "approval_claimed": False,
        "evidence": [],
    },
    {
        "gap_id": "cursor_pagination_stability",
        "status": "NOT_RUN",
        "route_refs": ["GET /v3/memories"],
        "required_proof": "Current `/v3` uses limit/offset with a first-page limit override; stable V17 cursor pagination remains unproven.",
        "approval_claimed": False,
        "evidence": [],
    },
]

RUNTIME_DECISION_MATRIX = [
    {
        "state": "disabled",
        "route_refs": ["GET /v3/memories"],
        "required_behavior": "fail_closed_or_explicit_legacy_safe_product_decision",
        "unsafe_legacy_fallback_allowed": False,
        "current_runtime_proof": "BLOCKED: route directly calls legacy memories_db.get_memories without a V17 read decision seam.",
    },
    {
        "state": "malformed",
        "route_refs": ["GET /v3/memories"],
        "required_behavior": "fail_closed_or_explicit_legacy_safe_product_decision",
        "unsafe_legacy_fallback_allowed": False,
        "current_runtime_proof": "BLOCKED: no route-local malformed rollout-state branch exists before legacy read.",
    },
    {
        "state": "missing",
        "route_refs": ["GET /v3/memories"],
        "required_behavior": "fail_closed_or_explicit_legacy_safe_product_decision",
        "unsafe_legacy_fallback_allowed": False,
        "current_runtime_proof": "BLOCKED: no route-local missing rollout-state branch exists before legacy read.",
    },
    {
        "state": "no_default_memory_grant",
        "route_refs": ["GET /v3/memories"],
        "required_behavior": "fail_closed_or_explicit_legacy_safe_product_decision",
        "unsafe_legacy_fallback_allowed": False,
        "current_runtime_proof": "BLOCKED: no /v3 app/key/default-memory grant is enforced before legacy read.",
    },
    {
        "state": "enabled_empty",
        "route_refs": ["GET /v3/memories"],
        "required_behavior": "return_empty_v17_result_without_legacy_fallback",
        "unsafe_legacy_fallback_allowed": False,
        "current_runtime_proof": "BLOCKED: no V17 memory_items read seam exists, so empty V17 state cannot be distinguished from legacy fallback.",
    },
    {
        "state": "archive_default",
        "route_refs": ["GET /v3/memories"],
        "required_behavior": "default_unavailable_without_explicit_archive_capability",
        "unsafe_legacy_fallback_allowed": False,
        "current_runtime_proof": "BLOCKED: /v3 has no Archive capability decision; readiness preserves Archive default-unavailable as a non-claim.",
    },
    {
        "state": "response_shape_source_metadata",
        "route_refs": ["GET /v3/memories"],
        "required_behavior": "additive_external_contract_required_before_exposing_v17_source_metadata",
        "unsafe_legacy_fallback_allowed": False,
        "current_runtime_proof": "BLOCKED: response_model=List[MemoryDB] has no source metadata fields or compatibility source contract.",
    },
    {
        "state": "cursor_pagination",
        "route_refs": ["GET /v3/memories"],
        "required_behavior": "stable_cursor_contract_required_before_runtime_cutover",
        "unsafe_legacy_fallback_allowed": False,
        "current_runtime_proof": "BLOCKED: /v3 supports limit/offset only and overrides first-page limit to 5000.",
    },
]

PRODUCT_DECISION_DEPENDENCIES = [
    {
        "dependency_id": "v3_disabled_malformed_no_grant_policy",
        "status": "BLOCKED",
        "approval_claimed": False,
        "needed_decision": "Whether external /v3 callers should receive explicit denial, empty safe response, or opt-in legacy-safe behavior for disabled/malformed/missing/no-grant state.",
    },
    {
        "dependency_id": "v3_enabled_empty_policy",
        "status": "BLOCKED",
        "approval_claimed": False,
        "needed_decision": "Confirm enabled-empty V17 memory_items returns [] and must not fall back to stale legacy memories.",
    },
    {
        "dependency_id": "v3_response_shape_source_metadata",
        "status": "BLOCKED",
        "approval_claimed": False,
        "needed_decision": "Define additive external source metadata and defaulted category/review/manual/edit provenance semantics for MemoryDB-compatible clients.",
    },
    {
        "dependency_id": "v3_cursor_pagination_contract",
        "status": "BLOCKED",
        "approval_claimed": False,
        "needed_decision": "Define stable cursor pagination semantics or explicitly retain legacy offset semantics for /v3 cutover.",
    },
    {
        "dependency_id": "v3_write_convergence_before_read_cutover",
        "status": "BLOCKED",
        "approval_claimed": False,
        "needed_decision": "Decide whether /v3 writes are dual-written/converged to V17 before reads can use V17 by default.",
    },
]

ORACLE_PRESCRIPTIVE_RECOMMENDATIONS = {
    "session_slug": "v3-v17-compat-prescripti",
    "oracle_cli": "consult-oracle 0.14.0",
    "model_selection_caveat": "gpt-5.5-pro browser returned guidance; model-selection evidence reported resolved unavailable/verified no.",
    "production_approach": "additive_v3_compatibility_adapter_over_v17_authoritative_writes",
    "default_body_contract": "List[MemoryDB]",
    "archive_default": "not_launched_on_v3_default_reads",
    "enabled_empty": "200_empty_list_no_legacy_fallback",
    "cursor_default": "additive_opaque_hmac_keyset_cursor_created_at_desc_memory_id_desc",
    "write_convergence": "v17_writes_and_compatibility_projection_before_v17_reads",
    "summary": (
        "Oracle recommends preserving /v3's default List[MemoryDB] body while adding a V17 compatibility "
        "adapter over V17-authoritative writes and a V17-derived users/{uid}/memories projection. Non-enrolled "
        "users stay legacy-primary; enrolled malformed/missing/control-timeout states fail closed; no-grant denies; "
        "enabled-empty returns [] without legacy fallback; Archive is not launched on default /v3; cursor mode is "
        "additive, signed, keyset, and generation/projection bound."
    ),
}

ENGINEERING_DEFAULTS_LOCKED_NOW = [
    {
        "default_id": "non_enrolled_legacy_primary",
        "behavior": "Users outside the V17 cohort keep current legacy /v3 behavior as the selected primary path.",
        "http_status": 200,
        "product_escalation_required": False,
    },
    {
        "default_id": "enrolled_malformed_missing_fail_closed",
        "behavior": "Enrolled users with missing, malformed, uid-mismatched, unsupported-schema, or timed-out control state fail closed before legacy reads.",
        "http_status": 503,
        "product_escalation_required": False,
    },
    {
        "default_id": "no_default_memory_grant_privacy_deny",
        "behavior": "Treat absent/revoked default-memory grant as privacy/consent denial unless product explicitly separates rollout from consent.",
        "http_status": 403,
        "product_escalation_required": True,
    },
    {
        "default_id": "enabled_empty_returns_empty",
        "behavior": "When V17 compatibility projection is enabled and empty, return [] and do not query legacy afterward.",
        "http_status": 200,
        "product_escalation_required": False,
    },
    {
        "default_id": "archive_not_launched_on_default_v3",
        "behavior": "Do not add include_archive=true or Archive vector behavior to the initial /v3 cutover.",
        "http_status": None,
        "product_escalation_required": False,
    },
    {
        "default_id": "source_metadata_additive_headers",
        "behavior": "Keep the JSON body MemoryDB-compatible; expose route-level read-source/read-decision/next-cursor diagnostics through additive headers.",
        "body_shape_changed": False,
        "product_escalation_required": False,
    },
    {
        "default_id": "cursor_additive_keyset_signed",
        "behavior": "Add opaque HMAC keyset cursor mode for V17 canaries while preserving offset behavior only for legacy-primary clients.",
        "product_escalation_required": False,
    },
    {
        "default_id": "no_legacy_v17_merge_or_exception_fallback",
        "behavior": "Do not merge legacy and V17 result pages and do not treat None/missing/exceptions as permission to use legacy.",
        "unsafe_fallback_allowed": False,
        "product_escalation_required": False,
    },
]

IRREDUCIBLE_PRODUCT_API_DECISIONS = [
    {
        "decision_id": "no_default_memory_grant_meaning",
        "recommended_default": "privacy_consent_returns_403",
        "escalation": "Escalate only if product states default-memory grant is merely rollout eligibility; then add a separate consent control.",
        "approval_claimed": False,
    },
    {
        "decision_id": "legacy_no_cursor_compatibility_window",
        "recommended_default": "preserve_offset_only_for_non_v17_clients_require_cursor_for_v17_cohort",
        "escalation": "Decide how long old clients retain offset/first-page behavior; do not reproduce the 5000-item override in V17 cursor mode.",
        "approval_claimed": False,
    },
]

ORACLE_IMPLEMENTATION_SHAPE = {
    "decision_service": "backend/utils/memory/v17_v3_compatibility.py",
    "request_adapter": "backend/utils/memory/v17_v3_request_adapter.py",
    "route_planner": "backend/utils/memory/v17_v3_route_planner.py",
    "read_service": "backend/utils/memory/v17_v3_memory_read_service.py",
    "response_adapter": "backend/utils/memory/v17_v3_response_adapter.py",
    "projection_service": "backend/database/v17_v3_compatibility_projection.py",
    "projection_store": "users/{uid}/memories as V17-derived compatibility projection",
    "cursor_service": "backend/utils/memory/v17_v3_cursor.py",
    "external_write_service": "backend/utils/memory/v17_v3_write_convergence.py",
    "decision_order": [
        "global_emergency_gate",
        "server_side_cohort_membership",
        "versioned_per_user_control_document",
        "exact_uid_schema_validation",
        "default_memory_grant",
        "account_generation",
        "write_convergence_and_projection_readiness",
        "selected_read_path",
    ],
    "required_headers": [
        "X-Omi-Memory-Read-Source",
        "X-Omi-Memory-Read-Decision",
        "X-Omi-Memory-Next-Cursor",
        "Link rel=next",
    ],
}

UNSAFE_APPROACHES_TO_AVOID = [
    "missing_malformed_or_exception_as_use_legacy",
    "legacy_v17_result_merge",
    "fallback_because_v17_returned_zero_results",
    "include_archive_true_as_authorization",
    "invented_memorydb_field_defaults_from_memory_items",
    "switch_reads_before_v3_mutations_converge",
    "direct_legacy_writes_for_enrolled_v17_account",
    "independent_firestore_pinecone_dual_writes_with_swallowed_failure",
    "delete_success_before_tombstone_projection_removal_vector_fence_and_cleanup_outbox",
    "offset_based_or_unsigned_cursor",
    "allow_pagination_source_generation_epoch_or_filter_change",
    "apply_5000_first_page_override_to_v17_cursor",
    "treat_readiness_scripts_or_unit_counts_as_production_evidence",
]

DECISION_SERVICE_PROOF = {
    "service": "backend/utils/memory/v17_v3_compatibility.py",
    "test": "backend/tests/unit/test_v17_v3_compatibility.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "non_enrolled_legacy_primary",
        "enrolled_missing_malformed_uid_mismatch_unsupported_timeout_fail_closed_503",
        "no_default_memory_grant_privacy_consent_deny_403_product_overridable",
        "enabled_empty_projection_returns_200_empty_list_no_legacy_fallback",
        "write_convergence_or_projection_not_ready_fail_closed",
        "archive_default_unavailable",
        "list_memorydb_body_header_only_metadata",
        "signed_opaque_keyset_generation_bound_cursor_no_offset_no_5000_override",
        "unsafe_legacy_fallback_after_enrolled_error_or_v17_write_state_not_exposed",
    ],
}

CURSOR_SERVICE_PROOF = {
    "service": "backend/utils/memory/v17_v3_cursor.py",
    "test": "backend/tests/unit/test_v17_v3_cursor.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
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
    ],
}

PROJECTION_READINESS_PROOF = {
    "service": "backend/utils/memory/v17_v3_projection_readiness.py",
    "test": "backend/tests/unit/test_v17_v3_projection_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
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
    ],
}

MEMORY_READ_SERVICE_PROOF = {
    "service": "backend/utils/memory/v17_v3_memory_read_service.py",
    "test": "backend/tests/unit/test_v17_v3_memory_read_service.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
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
    ],
}

WRITE_CONVERGENCE_PROOF = {
    "service": "backend/utils/memory/v17_v3_write_convergence.py",
    "test": "backend/tests/unit/test_v17_v3_write_convergence.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "create_update_require_v17_authoritative_write_path_projection_update_commit_and_current_generation",
        "delete_requires_tombstone_projection_removal_vector_cleanup_outbox_fence",
        "missing_stale_partial_swallowed_failure_dual_write_without_durable_outbox_generation_mismatch_fail_closed",
        "external_writes_disabled_safe_only_when_reads_blocked_or_no_active_write_surfaces",
        "no_enrolled_v17_legacy_direct_write_fallback_knob",
        "archive_default_unavailable_no_stale_short_term_default_visible",
    ],
}

RESPONSE_ADAPTER_PROOF = {
    "service": "backend/utils/memory/v17_v3_response_adapter.py",
    "test": "backend/tests/unit/test_v17_v3_response_adapter.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "pure_local_read_service_envelope_to_memorydb_response_adapter",
        "preserve_list_memorydb_body_no_source_policy_cursor_fields_in_body",
        "additive_headers_only_read_source_read_decision_next_cursor_link_rel_next",
        "enabled_empty_returns_empty_list_with_v17_headers_no_legacy_fallback_marker",
        "fail_closed_and_denied_have_no_body_data_no_legacy_fallback_marker",
        "reject_v17_only_body_source_policy_cursor_diagnostics_fields",
        "archive_default_unavailable_no_stale_short_term_default_visible_proof_fields_only",
    ],
}

REQUEST_ADAPTER_PROOF = {
    "service": "backend/utils/memory/v17_v3_request_adapter.py",
    "test": "backend/tests/unit/test_v17_v3_request_adapter.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "pure_local_query_parameter_to_read_service_request_contract",
        "legacy_limit_offset_preserved_as_legacy_primary_only",
        "v17_cursor_mode_disallows_offset_and_5000_first_page_override",
        "v17_limit_bounds_validated_without_expanding_to_5000",
        "category_filter_state_bound_into_filter_hash_and_cursor_binding",
        "unsupported_filters_fail_closed_no_silent_legacy_fallback",
        "include_archive_default_false_unavailable_explicit_archive_blocked_for_v3_default",
        "source_and_read_mode_bounded_to_v17_compatibility_projection",
        "no_fastapi_dependency_route_wiring_external_calls_or_mutations",
    ],
}

ROUTE_PLANNER_PROOF = {
    "service": "backend/utils/memory/v17_v3_route_planner.py",
    "test": "backend/tests/unit/test_v17_v3_route_planner.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "pure_local_route_adjacent_composition_no_route_wiring_or_data_fetching",
        "composes_request_adapter_decision_write_projection_read_response_seams",
        "non_enrolled_legacy_primary_plan_marker_only_preserves_limit_offset",
        "enrolled_valid_request_returns_list_memorydb_response_with_additive_headers",
        "enrolled_invalid_request_cursor_filter_archive_fail_closed_no_legacy_fallback",
        "enrolled_malformed_no_grant_projection_not_ready_write_not_ready_fail_closed_or_deny",
        "enabled_empty_returns_200_empty_list_no_legacy_fallback",
        "archive_default_unavailable_no_stale_short_term_default_visible",
    ],
}

ROUTE_SIGNATURE_INTEGRATION_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_route_signature_integration.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_route_signature_integration.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "static_ast_source_inspection_of_memories_router_no_fastapi_import",
        "pins_get_post_delete_v3_route_signatures_and_body_models",
        "pins_current_legacy_get_post_delete_db_vector_paths_no_cutover_claim",
        "maps_get_limit_offset_to_request_adapter_contract_with_offset_v17_blocked",
        "identifies_future_query_to_request_adapter_to_route_planner_to_response_adapter_seam",
        "archive_default_unavailable_no_stale_short_term_default_visible",
    ],
}

FASTAPI_ROUTE_CONTRACT_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_fastapi_route_contract.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_fastapi_route_contract.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "controlled_isolated_fastapi_app": True,
    "imports_real_router_or_app": False,
    "covered_defaults": [
        "list_memorydb_response_model_serializes_legacy_compatible_items",
        "additive_headers_permitted_without_body_mutation",
        "enabled_empty_returns_empty_list_no_legacy_fallback_marker",
        "fail_closed_denied_returns_no_body_data_no_legacy_fallback_marker",
        "v17_only_fields_filtered_from_list_memorydb_body",
        "archive_default_unavailable_no_stale_short_term_default_visible",
    ],
}

REAL_ROUTER_DEPENDENCY_MAP_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_real_router_dependency_map.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_real_router_dependency_map.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "imports_real_router_under_stubs": True,
    "covered_defaults": [
        "real_memories_router_imported_only_after_explicit_unsafe_dependency_stubs",
        "pins_import_side_effects_and_required_testclient_overrides_before_route_execution",
        "pins_get_post_delete_v3_route_functions_and_decorators_from_real_router",
        "future_get_seam_remains_request_adapter_to_route_planner_to_response_adapter",
        "no_main_app_startup_no_external_calls_no_mutations_no_runtime_cutover",
    ],
}

REAL_ROUTER_GET_TESTCLIENT_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_real_router_get_testclient.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_real_router_get_testclient.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "get_only_testclient_under_stubs": True,
    "post_delete_unexecuted": True,
    "covered_defaults": [
        "minimal_fastapi_app_includes_real_memories_router_under_explicit_stubs",
        "get_v3_memories_calls_stubbed_legacy_memories_db_get_memories",
        "default_first_page_observes_current_offset_zero_limit_5000_override",
        "explicit_limit_offset_reach_stubbed_legacy_get_memories_when_offset_nonzero",
        "list_memorydb_response_model_serializes_legacy_compatible_items",
        "post_delete_unexecuted_and_mutation_flags_remain_false",
        "v17_request_adapter_route_planner_response_adapter_not_invoked_yet",
        "no_main_app_startup_no_external_calls_no_mutations_no_runtime_cutover",
    ],
}

GET_DEPENDENCY_AUTH_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_get_dependency_auth_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_get_dependency_auth_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "controlled_testclient_under_stubs": True,
    "covered_defaults": [
        "real_get_route_uses_auth_get_current_user_uid_dependency",
        "minimal_fastapi_app_can_override_get_auth_dependency_to_stub_uid",
        "get_without_auth_override_is_blocked_in_controlled_testclient_probe",
        "current_get_route_has_no_rate_limit_dependency",
        "get_with_auth_override_calls_stubbed_legacy_get_memories_for_non_enrolled_baseline",
        "no_v17_cohort_control_dependency_present_or_invoked",
        "no_main_app_startup_no_external_calls_no_mutations_no_runtime_cutover",
    ],
}

PROJECTION_STORE_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_projection_store_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_projection_store_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "read_only_projection_store_api_requirements_inventory",
        "canonical_projection_path_api_blocked_until_chosen",
        "memorydb_materialization_without_v17_only_body_leakage",
        "account_projection_generation_freshness_source_commit_version_evidence_fences",
        "delete_tombstone_vector_cleanup_fences_required",
        "enabled_empty_returns_empty_list_no_legacy_fallback",
        "archive_default_unavailable_no_stale_short_term_default_visible",
        "pagination_cursor_contract_plus_non_enrolled_legacy_offset_compatibility",
        "fake_injectable_reader_interface_shape_without_route_wiring",
    ],
}

CONTROL_READER_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_control_reader_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_control_reader_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "read_only_server_side_control_reader_requirements_inventory",
        "canonical_control_source_path_api_blocked_until_chosen",
        "server_owned_control_reads_only_no_direct_client_control_reads",
        "fake_injectable_control_reader_interface_shape_without_route_wiring",
        "missing_control_doc_stale_generation_no_grant_fail_closed_or_denied",
        "projection_not_ready_write_convergence_not_ready_cursor_secret_fail_closed",
        "non_enrolled_legacy_offset_zero_limit_5000_preserved_only_for_legacy_primary",
        "enrolled_gate_failures_never_fallback_to_legacy",
        "archive_default_unavailable_no_stale_short_term_default_visible",
    ],
}

CONTROL_READER_CONTRACT_PROOF = {
    "service": "backend/utils/memory/v17_v3_control_reader_contract.py",
    "test": "backend/tests/unit/test_v17_v3_control_reader_contract.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "pure_fake_injectable_server_control_reader_protocol_and_decision_contract",
        "non_enrolled_legacy_primary_allowed_marker_without_route_wiring",
        "enrolled_all_gates_ready_allows_v17_projection_marker_without_legacy_fallback",
        "missing_control_doc_stale_generation_no_grant_projection_write_cursor_archive_short_term_fail_closed",
        "archive_default_unavailable_and_stale_short_term_default_hidden",
        "no_fastapi_firestore_pinecone_provider_cloud_network_imports_or_runtime_wiring",
    ],
}

CONTROL_READER_EMULATOR_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_control_reader_emulator_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_control_reader_emulator_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "safe_default_blocked_not_run_no_cloud_or_emulator_side_effects",
        "local_firestore_emulator_harness_config_inventory_without_starting_services",
        "canonical_server_control_source_path_api_still_blocked_until_chosen",
        "control_doc_fixture_schema_uid_generation_grant_projection_write_archive_short_term_fields",
        "security_iam_evidence_no_direct_client_control_reads_server_principal_allowed",
        "rules_static_emulator_and_cloud_iam_proof_separation",
        "contract_decision_case_inventory_matches_v17_v3_control_reader_contract",
        "non_enrolled_legacy_boundary_and_enrolled_no_legacy_fallback_constraints",
    ],
}

ACCOUNT_GENERATION_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_account_generation_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_account_generation_readiness.py",
    "contract": "backend/utils/memory/v17_v3_account_generation_source.py",
    "contract_test": "backend/tests/unit/test_v17_v3_account_generation_source.py",
    "writer": "backend/database/v17_memory_apply_store.py",
    "writer_unit_test": "backend/tests/unit/test_v17_firestore_apply_store.py",
    "emulator_test": "backend/scripts/v17_firestore_python_apply_emulator_test.py",
    "rules_emulator_test": "backend/scripts/v17_firestore_rules_emulator_test.mjs",
    "npm_emulator_command": "npm run test:v17-v3-state-head:emulator",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "trusted_server_owned_memory_state_head_reader_contract",
        "state_head_written_from_committed_v17_apply_control_state",
        "client_direct_read_write_denied_by_firestore_rules_emulator",
        "admin_emulator_write_read_and_trusted_reader_success",
        "expected_account_generation_not_copied_from_control_or_projection",
        "missing_malformed_uid_source_schema_generation_read_failures_fail_closed",
        "future_route_requires_trusted_control_projection_cursor_generation_equality",
        "runtime_blocked_until_route_wiring_remaining_gates_telemetry_and_approval",
    ],
}

REAL_ROUTER_FAIL_CLOSED_MATRIX_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_real_router_fail_closed_matrix.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_real_router_fail_closed_matrix.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "current_real_router_get_remains_legacy_only_under_stubs",
        "non_enrolled_legacy_preserves_limit_offset_and_offset_zero_limit_5000",
        "enrolled_projection_success_calls_projection_reader_only",
        "enrolled_fail_closed_states_call_no_reader_and_never_legacy_fallback",
        "no_grant_and_archive_denial_return_403_without_body_or_legacy_fallback",
        "projection_control_account_cursor_mismatch_fail_closed_without_legacy_fallback",
        "enabled_empty_returns_empty_list_with_no_legacy_fallback",
        "future_dispatcher_matrix_proven_only_at_pure_helper_route_planner_seam",
    ],
}

WRITE_CONVERGENCE_TOMBSTONE_MATRIX_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_write_convergence_tombstone_matrix.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_write_convergence_tombstone_matrix.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "create_update_delete_convergence_all_required_before_v17_projection_reads",
        "create_update_delete_convergence_false_fail_closed_without_legacy_fallback",
        "delete_tombstone_fence_missing_or_generation_mismatch_fail_closed",
        "account_projection_tombstone_freshness_generation_fences_must_match",
        "enabled_empty_allowed_only_when_all_write_projection_tombstone_fences_ready",
        "archive_default_unavailable_and_stale_short_term_default_hidden",
        "failures_never_allow_legacy_fallback_or_v17_legacy_merge",
        "future_dispatcher_matrix_proven_only_at_pure_helper_route_planner_write_projection_seam",
    ],
}

CURSOR_SECRET_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_cursor_secret_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_cursor_secret_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "status": "BLOCKED",
    "blocker": "No existing runtime-owned V17 /v3 cursor signing secret/config source is wired.",
    "client_supplied_secret_trusted": False,
    "covered_defaults": [
        "server_owned_cursor_secret_source_required_before_runtime_wiring",
        "client_supplied_cursor_secret_never_trusted",
        "first_page_no_cursor_does_not_require_client_secret_trust",
        "signed_cursor_preserves_account_projection_generation_source_and_keyset",
        "tamper_expiry_generation_source_wrong_secret_fail_closed_no_legacy_fallback",
        "no_fastapi_firestore_pinecone_provider_cloud_network_imports_or_runtime_wiring",
    ],
}

OBSERVABILITY_APPROVAL_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_observability_approval_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_observability_approval_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "status": "BLOCKED",
    "telemetry_sink_calls_executed": False,
    "approval_claimed": False,
    "blocker": "No V17 /v3 GET telemetry sink, runtime canary/rollback gate, or production approval artifact reader is runtime-wired; local canary approval schema and fake-injectable reader validation exist only as readiness seams.",
    "covered_defaults": [
        "read_source_route_decision_failure_reason_required_before_v3_get_cutover",
        "control_projection_account_generation_labels_required_and_bounded",
        "cursor_validation_result_reason_without_token_or_secret_logging",
        "canary_enrollment_and_rollback_read_disable_gate_required",
        "local_canary_approval_artifact_schema_validation_present_but_not_runtime_wired",
        "local_canary_approval_artifact_reader_validation_present_but_not_runtime_wired",
        "no_legacy_fallback_marker_required_for_v17_failures",
        "archive_default_unavailable_and_stale_short_term_hidden_markers_required",
        "product_privacy_operational_approval_artifact_missing",
        "no_pii_raw_memory_content_or_high_cardinality_labels",
    ],
}

CANARY_APPROVAL_SOURCE_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_canary_approval_source_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_canary_approval_source_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "status": "BLOCKED",
    "approval_claimed": False,
    "blocker": (
        "Server-owned approval artifact source/ownership/IAM contract is selected locally, but production artifact, "
        "direct-client-deny rules/IAM evidence, and backend service-principal read evidence are still missing/not-run."
    ),
    "covered_defaults": [
        "server_owned_route_scoped_approval_artifact_source_selected",
        "client_supplied_approval_artifacts_never_trusted",
        "bounded_product_privacy_ops_and_memory_platform_oncall_ownership_required",
        "direct_client_read_write_denied_or_emulator_iam_proof_required",
        "backend_service_principal_read_required_before_runtime_wiring",
        "no_uid_session_memory_cursor_token_secret_payload_or_high_cardinality_artifact_dimensions",
    ],
}

CANARY_APPROVAL_PRODUCTION_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_canary_approval_production_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_canary_approval_production_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "status": "BLOCKED",
    "proof_status": "NOT_RUN",
    "approval_claimed": False,
    "blocker": (
        "Production-safe backend service-principal artifact read proof remains optional/explicit and read-only; "
        "missing env gates produce NOT_RUN/BLOCKED rather than production failure."
    ),
    "covered_defaults": [
        "explicit_env_gates_required_before_any_production_read",
        "single_route_scoped_artifact_document_read_only",
        "schema_validation_reuses_v17_v3_canary_approval_artifact_semantics",
        "valid_artifact_does_not_claim_production_rollout_approval",
    ],
}

GET_RUNTIME_WIRING_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_get_runtime_wiring_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_get_runtime_wiring_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "remaining_real_service_runtime_gates_inventory_before_get_cutover",
        "current_real_router_get_legacy_behavior_is_baseline_not_cutover",
        "non_enrolled_legacy_primary_offset_zero_limit_5000_must_be_preserved",
        "enrolled_fail_closed_no_grant_projection_not_ready_write_not_ready_no_legacy_fallback",
        "real_cursor_secret_control_projection_write_convergence_auth_rate_limit_telemetry_approval_gates_missing",
        "observability_approval_readiness_matrix_present_but_blocked",
        "archive_default_unavailable_no_stale_short_term_default_visible",
        "safe_future_cutover_sequence_documented_without_runtime_wiring",
    ],
}


def build_report(*, execute: bool = False) -> dict[str, Any]:
    return {
        "artifact": "v17_p1_3_v3_external_compatibility_readiness",
        "status": "BLOCKED",
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "benchmark_evidence_collected": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "scope": "Oracle P1-3 `/v3` external compatibility readiness only; no runtime behavior changed.",
        "v3_surfaces": V3_SURFACES,
        "remaining_gaps": REMAINING_GAPS,
        "runtime_decision_matrix": RUNTIME_DECISION_MATRIX,
        "product_decision_dependencies": PRODUCT_DECISION_DEPENDENCIES,
        "oracle_prescriptive_recommendations": ORACLE_PRESCRIPTIVE_RECOMMENDATIONS,
        "engineering_defaults_locked_now": ENGINEERING_DEFAULTS_LOCKED_NOW,
        "irreducible_product_api_decisions": IRREDUCIBLE_PRODUCT_API_DECISIONS,
        "oracle_implementation_shape": ORACLE_IMPLEMENTATION_SHAPE,
        "unsafe_approaches_to_avoid": UNSAFE_APPROACHES_TO_AVOID,
        "decision_service_proof": DECISION_SERVICE_PROOF,
        "cursor_service_proof": CURSOR_SERVICE_PROOF,
        "projection_readiness_proof": PROJECTION_READINESS_PROOF,
        "memory_read_service_proof": MEMORY_READ_SERVICE_PROOF,
        "write_convergence_proof": WRITE_CONVERGENCE_PROOF,
        "response_adapter_proof": RESPONSE_ADAPTER_PROOF,
        "request_adapter_proof": REQUEST_ADAPTER_PROOF,
        "route_planner_proof": ROUTE_PLANNER_PROOF,
        "route_signature_integration_proof": ROUTE_SIGNATURE_INTEGRATION_PROOF,
        "fastapi_route_contract_proof": FASTAPI_ROUTE_CONTRACT_PROOF,
        "real_router_dependency_map_proof": REAL_ROUTER_DEPENDENCY_MAP_PROOF,
        "real_router_get_testclient_proof": REAL_ROUTER_GET_TESTCLIENT_PROOF,
        "get_dependency_auth_readiness_proof": GET_DEPENDENCY_AUTH_READINESS_PROOF,
        "projection_store_readiness_proof": PROJECTION_STORE_READINESS_PROOF,
        "control_reader_readiness_proof": CONTROL_READER_READINESS_PROOF,
        "control_reader_contract_proof": CONTROL_READER_CONTRACT_PROOF,
        "control_reader_emulator_readiness_proof": CONTROL_READER_EMULATOR_READINESS_PROOF,
        "account_generation_readiness_proof": ACCOUNT_GENERATION_READINESS_PROOF,
        "real_router_fail_closed_matrix_proof": REAL_ROUTER_FAIL_CLOSED_MATRIX_PROOF,
        "write_convergence_tombstone_matrix_proof": WRITE_CONVERGENCE_TOMBSTONE_MATRIX_PROOF,
        "cursor_secret_readiness_proof": CURSOR_SECRET_READINESS_PROOF,
        "observability_approval_readiness_proof": OBSERVABILITY_APPROVAL_READINESS_PROOF,
        "canary_approval_source_readiness_proof": CANARY_APPROVAL_SOURCE_READINESS_PROOF,
        "canary_approval_production_readiness_proof": CANARY_APPROVAL_PRODUCTION_READINESS_PROOF,
        "get_runtime_wiring_readiness_proof": GET_RUNTIME_WIRING_READINESS_PROOF,
        "non_claims": [
            "No production traffic executed.",
            "No Firestore, Pinecone, cloud, provider, or network calls executed.",
            "No Firestore reads or writes executed.",
            "No benchmark evidence collected.",
            "No telemetry sink integration claimed.",
            "No external rollout approval claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "surface_count": len(V3_SURFACES),
            "gap_count": len(REMAINING_GAPS),
            "decision_state_count": len(RUNTIME_DECISION_MATRIX),
            "product_dependency_count": len(PRODUCT_DECISION_DEPENDENCIES),
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
            "control_reader_readiness_proof_present": True,
            "control_reader_contract_proof_present": True,
            "account_generation_readiness_proof_present": True,
            "real_router_fail_closed_matrix_proof_present": True,
            "write_convergence_tombstone_matrix_proof_present": True,
            "cursor_secret_readiness_proof_present": True,
            "observability_approval_readiness_proof_present": True,
            "canary_approval_source_readiness_proof_present": True,
            "canary_approval_production_readiness_proof_present": True,
            "read_only": True,
            "mutation_allowed": False,
            "approval_claimed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Emit the same safe report with execute=true")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

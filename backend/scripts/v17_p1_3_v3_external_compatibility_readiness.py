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
    "read_service": "backend/utils/memory/v17_v3_memory_read_service.py",
    "projection_service": "backend/database/v17_v3_compatibility_projection.py",
    "projection_store": "users/{uid}/memories as V17-derived compatibility projection",
    "cursor_service": "backend/utils/memory/v17_v3_cursor.py",
    "external_write_service": "backend/utils/memory/v17_external_memory_write_service.py",
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

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

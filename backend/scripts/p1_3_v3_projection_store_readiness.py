#!/usr/bin/env python3
"""Safe `/v3` memory compatibility projection store/API readiness artifact.

This is a read-only local contract inventory for the future memory-derived
compatibility projection read API/store needed before `GET /v3/memories` can be
cut over. It intentionally does not import FastAPI routers, contact production
Firestore, call Pinecone/providers/cloud/network services, mutate state, implement
production store writes, wire runtime routes, or claim approval.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


def _load_external_readiness_module():
    spec = importlib.util.spec_from_file_location(
        "p1_3_v3_external_compatibility_readiness",
        Path(__file__).with_name("p1_3_v3_external_compatibility_readiness.py"),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load p1_3_v3_external_compatibility_readiness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_EXTERNAL = _load_external_readiness_module()

PROOF_CONSTANTS = {
    "projection_readiness_proof": _EXTERNAL.PROJECTION_READINESS_PROOF,
    "memory_read_service_proof": _EXTERNAL.MEMORY_READ_SERVICE_PROOF,
    "request_adapter_proof": _EXTERNAL.REQUEST_ADAPTER_PROOF,
    "response_adapter_proof": _EXTERNAL.RESPONSE_ADAPTER_PROOF,
    "route_planner_proof": _EXTERNAL.ROUTE_PLANNER_PROOF,
    "write_convergence_proof": _EXTERNAL.WRITE_CONVERGENCE_PROOF,
    "cursor_service_proof": _EXTERNAL.CURSOR_SERVICE_PROOF,
    "fastapi_route_contract_proof": _EXTERNAL.FASTAPI_ROUTE_CONTRACT_PROOF,
    "get_runtime_wiring_readiness_proof": _EXTERNAL.GET_RUNTIME_WIRING_READINESS_PROOF,
}

EXISTING_LOCAL_PROOF_ARTIFACTS = {
    key: {
        **proof,
        "missing_real_firestore_or_api_evidence": True,
    }
    for key, proof in PROOF_CONSTANTS.items()
}

STORE_API_REQUIREMENTS = [
    {
        "requirement_id": "canonical_projection_path_api",
        "status": "LOCAL_IMPLEMENTED",
        "required_contract": "Canonical server-owned memory-derived projection state/items paths exist for a future `/v3` reader.",
        "canonical_state_path": "users/{uid}/v3_compatibility_projection/state",
        "canonical_items_path": "users/{uid}/v3_compatibility_projection_items/{memory_id}",
        "canonical_path": "users/{uid}/v3_compatibility_projection_items/{memory_id}",
        "explicit_blocker": None,
        "candidate_paths": [],
        "evidence_sources": ["projection_readiness_proof", "get_runtime_wiring_readiness_proof"],
        "missing_real_firestore_or_api_evidence": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "memorydb_materialization_fields",
        "status": "LOCAL_IMPLEMENTED",
        "required_contract": "Projection records must materialize List[MemoryDB] without leaking memory-only body fields.",
        "required_fields": [
            "id",
            "uid",
            "content",
            "category",
            "visibility",
            "tags",
            "created_at",
            "updated_at",
            "reviewed",
            "user_review",
            "manually_added",
            "edited",
            "conversation_id",
            "data_protection_level",
        ],
        "memory_only_body_fields_forbidden": [
            "memory_item_id",
            "generation",
            "source_commit_id",
            "projection_version",
            "projection_freshness_fence",
            "archive_tier",
            "short_term_staleness_reason",
        ],
        "additive_metadata_allowed_only_outside_body": True,
        "evidence_sources": ["response_adapter_proof", "fastapi_route_contract_proof"],
        "missing_real_firestore_or_api_evidence": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "generation_account_projection_freshness_fences",
        "status": "LOCAL_IMPLEMENTED",
        "required_contract": "Read API must prove account/projection generation freshness before returning enrolled memory data.",
        "required_fields": [
            "uid",
            "account_generation",
            "expected_account_generation",
            "projection_generation",
            "freshness_fence_generation",
            "projection_generated_at",
        ],
        "blocked_states": [
            "account_generation_missing_or_mismatch",
            "projection_generation_missing_or_stale",
            "freshness_fence_missing_or_stale",
        ],
        "evidence_sources": ["projection_readiness_proof", "memory_read_service_proof"],
        "missing_real_firestore_or_api_evidence": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "source_commit_version_evidence_fences",
        "status": "LOCAL_IMPLEMENTED",
        "required_contract": "Projection reads must expose verifiable source and projection commit/version/evidence fences to server logic.",
        "required_fields": [
            "source_commit_id",
            "source_version",
            "projection_commit_id",
            "projection_version",
            "source_evidence_fence",
            "projection_evidence_fence",
        ],
        "body_leakage_allowed": False,
        "evidence_sources": ["projection_readiness_proof", "response_adapter_proof"],
        "missing_real_firestore_or_api_evidence": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "delete_tombstone_vector_cleanup_fences",
        "status": "LOCAL_READER_FENCED",
        "required_contract": "Deletes must prove tombstone, projection removal, and vector cleanup fences before success/read cutover.",
        "required_fields": [
            "tombstone_fence_generation",
            "delete_projection_commit_id",
            "vector_cleanup_fence",
            "vector_cleanup_fence_generation",
            "delete_outbox_fence",
        ],
        "unsafe_states": ["deleted_memory_visible", "vector_left_searchable", "tombstone_missing_or_stale"],
        "evidence_sources": ["write_convergence_proof", "projection_readiness_proof"],
        "missing_real_firestore_or_api_evidence": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "enabled_empty_representation",
        "status": "LOCAL_IMPLEMENTED",
        "required_contract": "Enabled empty memory projection returns HTTP 200 with [] and never falls back to stale legacy rows.",
        "response_body": [],
        "legacy_fallback_allowed": False,
        "empty_projection_flag_required": True,
        "evidence_sources": ["projection_readiness_proof", "memory_read_service_proof", "route_planner_proof"],
        "missing_real_firestore_or_api_evidence": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "archive_and_short_term_defaults",
        "status": "LOCAL_IMPLEMENTED",
        "required_contract": "Archive is default-unavailable and stale Short-term is not default-visible in `/v3` compatibility projection reads.",
        "archive_default_available": False,
        "stale_short_term_default_visible": False,
        "explicit_archive_product_decision_required": True,
        "short_term_freshness_filter_required": True,
        "evidence_sources": ["request_adapter_proof", "response_adapter_proof", "route_planner_proof"],
        "missing_real_firestore_or_api_evidence": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "pagination_cursor_compatibility",
        "status": "LOCAL_IMPLEMENTED",
        "required_contract": "memory projection reads need stable cursor inputs/outputs while preserving current non-enrolled legacy offset behavior.",
        "cursor_inputs": ["limit", "cursor", "filter_hash", "projection_generation", "account_generation"],
        "cursor_outputs": ["items", "next_cursor", "has_more", "projection_generation"],
        "legacy_non_enrolled_offset_behavior_preserved": True,
        "legacy_offset_zero_limit_5000_only_for_legacy_primary": True,
        "v3_cursor_required_before_cutover": True,
        "evidence_sources": ["cursor_service_proof", "request_adapter_proof", "memory_read_service_proof"],
        "missing_real_firestore_or_api_evidence": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "fake_injectable_read_interface",
        "status": "LOCAL_IMPLEMENTED",
        "required_contract": "Define a fake-injectable read interface shape for future route wiring, without wiring it now.",
        "runtime_route_wiring_now": False,
        "production_firestore_reader_implemented": True,
        "evidence_sources": ["memory_read_service_proof", "route_planner_proof", "get_runtime_wiring_readiness_proof"],
        "missing_real_firestore_or_api_evidence": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
]

FAKE_INJECTABLE_READ_INTERFACE = {
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

PROPOSED_NEXT_SAFE_STEPS = [
    {
        "step_id": "choose_canonical_projection_path_and_schema",
        "description": "Pick and document the canonical Firestore/API path and schema for memory-derived `/v3` compatibility projection records.",
        "implements_runtime_wiring_now": False,
        "implements_production_writes_now": False,
    },
    {
        "step_id": "add_fake_reader_contract_tests",
        "description": "Add pure fake-reader tests for pagination, empty, generation, source, tombstone, and vector cleanup fences.",
        "implements_runtime_wiring_now": False,
        "implements_production_writes_now": False,
    },
    {
        "step_id": "add_firestore_emulator_read_model_proof",
        "description": "Use Firestore emulator fixtures to prove real projection reads and MemoryDB materialization without cloud calls.",
        "implements_runtime_wiring_now": False,
        "implements_production_writes_now": False,
    },
    {
        "step_id": "prove_projection_writer_convergence_separately",
        "description": "Prove production writer/outbox/tombstone/vector cleanup convergence before any runtime read cutover.",
        "implements_runtime_wiring_now": False,
        "implements_production_writes_now": False,
    },
    {
        "step_id": "wire_route_only_after_all_gates_pass",
        "description": "Only wire `GET /v3/memories` after control, projection store, cursor, write convergence, auth/rate-limit, telemetry, and approval gates pass.",
        "implements_runtime_wiring_now": False,
        "implements_production_writes_now": False,
    },
]


def build_report(*, execute: bool = False) -> dict[str, Any]:
    blocked_requirement_count = sum(1 for item in STORE_API_REQUIREMENTS if item["status"] == "BLOCKED")
    local_implementation_count = sum(1 for item in STORE_API_REQUIREMENTS if str(item["status"]).startswith("LOCAL_"))
    missing_evidence_count = sum(1 for item in STORE_API_REQUIREMENTS if item["missing_real_firestore_or_api_evidence"])
    return {
        "artifact": "p1_3_v3_projection_store_readiness",
        "status": "BLOCKED",
        "proof_status": "LOCAL_IMPLEMENTATION_PROVED" if execute else "NOT_RUN",
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "production_store_writes_implemented": False,
        "projection_read_route_wired": False,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "cloud_calls_executed": False,
        "firestore_reads_executed": bool(execute),
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "scope": "Readiness/local implementation and emulator proof inventory for future memory-derived `/v3` compatibility projection read API/store.",
        "local_implementation_evidence": {
            "reader": "backend/database/v3_compatibility_projection.py",
            "contract": "backend/utils/memory/v3_projection_reader_contract.py",
            "unit_tests": "backend/tests/unit/test_v3_compatibility_projection.py",
            "emulator_test": "backend/scripts/p1_3_v3_projection_reader_emulator_test.py",
            "npm_command": "npm run test:memory-v3-projection-reader:emulator",
            "server_owned_state_path": "users/{uid}/v3_compatibility_projection/state",
            "server_owned_items_path": "users/{uid}/v3_compatibility_projection_items/{memory_id}",
        },
        "store_api_requirements": STORE_API_REQUIREMENTS,
        "fake_injectable_read_interface": FAKE_INJECTABLE_READ_INTERFACE,
        "existing_local_proof_artifacts": EXISTING_LOCAL_PROOF_ARTIFACTS,
        "proposed_next_safe_steps": PROPOSED_NEXT_SAFE_STEPS,
        "non_claims": [
            "No production compatibility projection store writes implemented.",
            "Local Firestore emulator evidence collected only by npm run test:memory-v3-projection-reader:emulator; no production cloud evidence collected.",
            "No Pinecone, provider, production cloud, or network calls executed by readiness artifact.",
            "No `/v3` route wiring changed.",
            "No Archive default visibility or stale Short-term default visibility introduced.",
            "No rollout approval claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "proof_status": "LOCAL_IMPLEMENTATION_PROVED" if execute else "NOT_RUN",
            "requirement_count": len(STORE_API_REQUIREMENTS),
            "blocked_requirement_count": blocked_requirement_count,
            "local_implementation_requirement_count": local_implementation_count,
            "existing_local_proof_count": len(EXISTING_LOCAL_PROOF_ARTIFACTS),
            "missing_real_firestore_or_api_evidence_count": missing_evidence_count,
            "read_only": True,
            "mutation_allowed": False,
            "runtime_wiring_changed": False,
            "production_store_writes_implemented": False,
            "approval_claimed": False,
            "safe_next_step_count": len(PROPOSED_NEXT_SAFE_STEPS),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Emit the same safe BLOCKED projection store report")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

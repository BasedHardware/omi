#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, Sequence

LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES = {
    "v3_memories_route": "backend/routers/memories.py GET /v3/memories",
    "legacy_memories_database_reader": "backend/database/memories.py get_memories",
    "product_v17_read_service": "backend/utils/memory/v17_product_memory_read_service.py",
    "developer_v17_adapter": "backend/utils/memory/v17_developer_memory_adapter.py",
    "mcp_v17_adapter": "backend/utils/memory/v17_mcp_memory_adapter.py",
    "chat_v17_adapter": "backend/utils/memory/v17_chat_memory_adapter.py",
    "mcp_rest_router": "backend/routers/mcp.py",
    "mcp_sse_router": "backend/routers/mcp_sse.py",
    "developer_router": "backend/routers/developer.py",
    "cutover_checklist": "backend/scripts/cutover_evidence_readiness.py",
    "ticket_source_of_truth": "docs/epics/v17_memory_implementation_tickets.md T21",
    "oracle_review": "docs/epics/v17_t20_oracle_milestone_review.md Oracle P0-8/T21",
    "existing_v17_read_tests": "backend/tests/unit/test_product_memory_read_service.py; backend/tests/unit/test_product_memory_router.py; backend/tests/unit/test_developer_memory_adapter.py; backend/tests/unit/test_v17_mcp_memory_adapter.py; backend/tests/unit/test_chat_memory_adapter.py",
    "legacy_memories_tests": "backend/tests/unit/test_memories_validation.py; backend/tests/unit/test_dev_api_memories_pagination.py; backend/tests/unit/test_mcp_memory_filters.py",
}

PROOF_MATRIX: Dict[str, Dict[str, Any]] = {
    "v3_endpoint_legacy_shape_compatibility": {
        "status": "NOT_RUN",
        "scope": "Inventory /v3 endpoint compatibility proof for legacy and V17-backed readers while preserving legacy response model and additive-only fields.",
        "required_artifacts": [
            "Static and runtime response-shape diff for backend/routers/memories.py GET /v3/memories versus any V17-backed replacement path, including existing List[MemoryDB] parse compatibility.",
            "Client/backward-compatibility artifact proving existing callers tolerate additive tier/provenance/cursor metadata and still parse legacy memory fields.",
            "Regression output for legacy /v3 create/list/delete/review routes proving no accidental default exposure of Short-term stale or Archive records.",
        ],
        "pass_fail_criteria": "PASS only when /v3 endpoint compatibility is demonstrated for legacy clients and any V17-read rollout remains additive, server-authorized, and rollback-safe.",
        "evidence": [],
    },
    "stable_cursor_pagination_and_ordering": {
        "status": "NOT_RUN",
        "scope": "Prove stable cursor pagination and stable ordering for legacy/V17 readers before high-volume imports become visible.",
        "required_artifacts": [
            "Cursor contract artifact defining cursor fields, tie-breakers, opaque encoding, max page size, and stable ordering across equal timestamps/scores and item IDs.",
            "A/B proof that legacy offset pagination from backend/database/memories.py get_memories and V17 cursor pagination do not duplicate, skip, or reorder records under inserts/deletes between pages.",
            "High-volume fixture regression covering first page, middle page, last page, invalid/expired cursor, limit bounds, and rollback to legacy read without cursor corruption.",
        ],
        "pass_fail_criteria": "PASS only when stable cursor pagination provides deterministic pages with no duplicate/skip behavior and stable ordering is documented and tested across legacy/V17 rollback.",
        "evidence": [],
    },
    "category_filters_and_developer_category_filtering": {
        "status": "NOT_RUN",
        "scope": "Prove category filters and developer category filtering behave compatibly across legacy /v3, V17 product reads, developer API, MCP, and chat callers.",
        "required_artifacts": [
            "Category-filter compatibility matrix for uncategorized, invalid category, multi-category, default categories, and tier-filter interactions.",
            "Developer category filtering proof that GET /v1/dev/user/memories category requests do not bypass required V17 authorization or expose legacy-only split-brain results during rollout.",
            "MCP/chat/product category semantics regression proving category filters do not make Archive default-visible and do not resurrect deleted/non-active records.",
        ],
        "pass_fail_criteria": "PASS only when category filters and developer category filtering are behaviorally compatible, authorized, deterministic, and safe across all supported callers.",
        "evidence": [],
    },
    "disabled_malformed_no_grant_behavior": {
        "status": "NOT_RUN",
        "scope": "Prove disabled/malformed/no-grant behavior is fail-closed and compatible across legacy/V17 readers and external callers.",
        "required_artifacts": [
            "Truth table for disabled/malformed/no-grant states covering product, developer, MCP REST, MCP SSE, chat, and /v3 readers, including explicit USE_V17/USE_LEGACY_SAFE/DENY_MEMORY decisions.",
            "Regression output proving revoked grants and malformed rollout state do not silently downgrade to unsafe legacy reads after V17 writes are enabled.",
            "Error/empty response-shape compatibility evidence for callers that currently expect 403, empty arrays, or legacy fallback under disabled states.",
        ],
        "pass_fail_criteria": "PASS only when disabled/malformed/no-grant behavior is explicitly authorized, consistent per caller contract, and never leaks memory through unsafe legacy fallback.",
        "evidence": [],
    },
    "enabled_but_empty_behavior": {
        "status": "NOT_RUN",
        "scope": "Prove enabled-but-empty behavior does not silently hide compatible legacy data or produce incompatible response shapes.",
        "required_artifacts": [
            "Enabled-but-empty fixture matrix for empty authoritative V17 store, empty-after-filtering, empty-after-hydration, and genuinely empty user account.",
            "Caller compatibility evidence showing product/developer/MCP/chat surfaces return documented empty shape/status without unsafe legacy fallback or silent data loss.",
            "Telemetry/decision evidence that empty-after-hydration is distinguishable from no matching memories and can block cutover when reconciliation is incomplete.",
        ],
        "pass_fail_criteria": "PASS only when enabled-but-empty behavior is intentional, observable, response-compatible, and cannot silently suppress still-authoritative legacy records.",
        "evidence": [],
    },
    "deleted_non_active_and_archive_default_unavailable": {
        "status": "NOT_RUN",
        "scope": "Prove deleted/non-active records remain excluded and Archive default-unavailable remains preserved across /v3 and V17 read compatibility paths.",
        "required_artifacts": [
            "Deleted/non-active records fixture covering deleted_at, invalidated, tombstoned, pending review, rejected review, expired Short-term, and purged-generation cases.",
            "Archive default-unavailable proof that default product/developer/MCP/chat and /v3 compatibility reads exclude Archive unless an explicit server-authorized Archive capability and explicit query are present.",
            "Rollback proof that non-active and Archive exclusions remain identical when switching between legacy and V17-compatible read paths.",
        ],
        "pass_fail_criteria": "PASS only when deleted/non-active records never return by default and Archive default-unavailable is enforced by server-side policy, not client-selected fields.",
        "evidence": [],
    },
    "external_response_shape_compatibility": {
        "status": "NOT_RUN",
        "scope": "Prove external response shape compatibility for product, developer API, MCP, chat/tool, and legacy /v3 callers.",
        "required_artifacts": [
            "Schema diff artifact for /v3, /v17 product, /v1/dev/user/memories, MCP REST, MCP SSE, and chat search memory tool responses.",
            "Golden fixtures proving old clients ignore unknown tier/provenance/cursor fields and new clients can consume cursor metadata without breaking legacy list shapes.",
            "Error-shape compatibility matrix for malformed cursor, invalid category, unauthorized grant, and empty page across all external callers.",
        ],
        "pass_fail_criteria": "PASS only when external response shape compatibility is demonstrated with golden fixtures and any new fields are additive, documented, and stable.",
        "evidence": [],
    },
    "mcp_rest_sse_shape_consistency": {
        "status": "NOT_RUN",
        "scope": "Prove MCP REST/SSE shape consistency for memory search/list responses, rollout decisions, cursor pagination, and empty/error behavior.",
        "required_artifacts": [
            "MCP REST versus MCP SSE response-shape and tool-result diff for identical memory search inputs, limits, offsets/cursors, categories, and disabled/no-grant states.",
            "Regression output from backend/routers/mcp.py and backend/routers/mcp_sse.py proving both transports enforce identical default-read grants and Archive default-unavailable policy.",
            "Compatibility evidence that cursor metadata, if exposed, has the same semantics and documented absence/presence across both MCP transports.",
        ],
        "pass_fail_criteria": "PASS only when MCP REST/SSE shape consistency is proven for success, empty, denied, malformed, category-filtered, and paginated cases.",
        "evidence": [],
    },
    "product_developer_mcp_chat_caller_regression": {
        "status": "NOT_RUN",
        "scope": "Collect product/developer/MCP/chat caller regression evidence for T21 /v3 compatibility and cursor pagination rollout safety.",
        "required_artifacts": [
            "Product route regression for /v3 compatibility and /v17 product reads, including stable cursor pagination, category filters, stable ordering, disabled/no-grant, enabled-but-empty, deleted/non-active, and Archive default-unavailable cases.",
            "Developer API regression for list/vector/category paths proving developer category filtering and response-shape compatibility across legacy/V17 rollout decisions.",
            "MCP REST/SSE and chat tool regression proving product/developer/MCP/chat caller regression coverage with no unsafe legacy fallback, no silent data loss, and compatible empty/error shapes.",
        ],
        "pass_fail_criteria": "PASS only when product/developer/MCP/chat caller regression outputs are attached and cover every T21 behavior before cutover approval.",
        "evidence": [],
    },
}

NON_CLAIMS = [
    "Oracle verdict remains BLOCK production rollout / NO-GO.",
    "This T21 `/v3` compatibility and cursor pagination readiness matrix is NOT_RUN/BLOCKED and does not claim production approval.",
    "Default and execute modes are read-only inventory only; no network/provider/cloud calls are executed and no mutations are planned.",
    "No production traffic, Firestore mutation, Pinecone mutation, benchmark run, telemetry sink integration, T21 completion, or cutover approval is performed by this artifact.",
    "Archive remains default-unavailable and stale Short-term remains not default-visible.",
]


@dataclass(frozen=True)
class T21V3CompatibilityCursorReadinessConfig:
    execute: bool


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe T21 /v3 compatibility and cursor pagination readiness/proof matrix. It inventories required evidence without production calls."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Emit the same read-only matrix; does not call providers or mutate state.",
    )
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> T21V3CompatibilityCursorReadinessConfig:
    return T21V3CompatibilityCursorReadinessConfig(execute=bool(args.execute))


def build_readiness_artifact(config: T21V3CompatibilityCursorReadinessConfig) -> Dict[str, Any]:
    return {
        "status": "BLOCKED",
        "read_only": True,
        "mutation_allowed": False,
        "execute_requested": config.execute,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "benchmark_evidence_collected": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "compatibility_surfaces": [
            "/v3/memories legacy list response",
            "/v17/memory/search product default read response",
            "/v1/dev/user/memories developer response",
            "MCP REST search_memories response",
            "MCP SSE search_memories response",
            "chat search_memories_tool response",
        ],
        "required_scope_summary": "/v3 endpoint compatibility; stable cursor pagination; category filters; stable ordering; disabled/malformed/no-grant; enabled-but-empty; deleted/non-active records; Archive default-unavailable; external response shape compatibility; developer category filtering; MCP REST/SSE shape consistency; product/developer/MCP/chat caller regression",
        "local_route_adapter_and_test_references": LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES,
        "proof_matrix": PROOF_MATRIX,
        "planned_safe_commands": [
            "python3 backend/scripts/t21_v3_compatibility_cursor_readiness.py",
            "python3 backend/scripts/t21_v3_compatibility_cursor_readiness.py --execute",
            "pytest tests/unit/test_t21_v3_compatibility_cursor_readiness.py -q",
            "pytest tests/unit/test_cutover_evidence_readiness.py -q",
            "pytest tests/unit/test_v17_*.py -q",
        ],
        "non_claims": NON_CLAIMS,
    }


def main(argv: Sequence[str] | None = None) -> int:
    config = config_from_args(parse_args(argv or sys.argv[1:]))
    print(json.dumps(build_readiness_artifact(config), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

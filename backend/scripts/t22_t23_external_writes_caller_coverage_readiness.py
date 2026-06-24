#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, Sequence

LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES = {
    "v3_memories_route": "backend/routers/memories.py POST/PATCH/DELETE/GET /v3/memories",
    "developer_memory_routes": "backend/routers/developer.py /v1/dev/user/memories create/edit/delete/list/vector/search",
    "mcp_rest_memory_routes": "backend/routers/mcp.py MCP REST create/edit/delete/list/search",
    "mcp_sse_memory_tools": "backend/routers/mcp_sse.py MCP streamable HTTP/SSE tools create_memory/edit_memory/delete_memory/get_memories/search_memories",
    "platform_tools_memory_routes": "backend/routers/tools.py /v1/tools/memories list/search",
    "agent_tool_execution": "backend/routers/agent_tools.py /v1/agent/execute-tool",
    "legacy_memory_database": "backend/database/memories.py create_memory/edit_memory/delete_memory/save_memories/get_memories",
    "legacy_write_guard": "backend/utils/memory/default_read_rollout.py assert_legacy_memory_write_allowed_for_default_read_decision",
    "external_default_read_authorization": "backend/utils/memory/product_authorization.py authorize_memory_external_default_memory_read",
    "developer_memory_adapter": "backend/utils/memory/developer_memory_adapter.py",
    "mcp_memory_adapter": "backend/utils/memory/mcp_memories.py",
    "chat_memory_adapter": "backend/utils/memory/chat_memory_adapter.py",
    "product_memory_read_service": "backend/utils/memory/product_memory_read_service.py",
    "cutover_checklist": "backend/scripts/cutover_evidence_readiness.py",
    "ticket_source_of_truth": "docs/epics/memory_implementation_tickets.md T22/T23",
    "oracle_review": "docs/epics/memory_t20_oracle_milestone_review.md Oracle P0-8/T22/T23",
    "existing_guard_and_caller_tests": "backend/tests/unit/test_developer_memory_adapter.py; backend/tests/unit/test_memory_mcp_memory_adapter.py; backend/tests/unit/test_chat_memory_adapter.py; backend/tests/unit/test_product_authorization.py; backend/tests/unit/test_app_key_memory_grant_assignment_readiness.py",
}

PROOF_MATRIX: Dict[str, Dict[str, Any]] = {
    "external_create_write_read_convergence": {
        "status": "NOT_RUN",
        "scope": "Inventory external create/edit/delete/list/search write/read convergence proof beginning with create paths before authoritative memory reads.",
        "required_artifacts": [
            "Create-path fixture proving /v3, Developer API, MCP REST, MCP SSE tool, platform tool, chat tool, and agent caller writes converge into the authoritative memory-visible projection or are blocked before memory authoritative reads.",
            "Read-after-create evidence from product, Developer API, MCP REST/SSE, chat, tool, and agent callers showing one canonical item identity, tier, category, visibility, provenance, ledger/outbox state, and no duplicate legacy/memory presentation.",
            "Negative create cases for non-whitelisted users, missing app/key/scope grants, invalid tiers, review/sensitive fields, Archive requests, malformed payloads, and disabled rollout state.",
        ],
        "pass_fail_criteria": "PASS only when every external create path either writes through the approved memory convergence mechanism or is blocked before authoritative memory reads can diverge from legacy writes.",
        "evidence": [],
    },
    "external_edit_write_read_convergence": {
        "status": "NOT_RUN",
        "scope": "Inventory external create/edit/delete/list/search write/read convergence proof for edit/update paths across memory content, category, tags, visibility, and vector/search projections.",
        "required_artifacts": [
            "Edit-path fixture covering /v3 PATCH, Developer API PATCH, MCP REST PATCH, MCP SSE edit_memory, and any tool/agent update-memory path with deterministic updated_at/item_revision/source_commit_id behavior.",
            "Read-after-edit proof that product default reads, Developer list/vector, MCP REST/SSE list/search, chat search, and platform tools return the edited memory-authoritative value and never stale legacy/vector content after write convergence is marked ready.",
            "Conflict proof for concurrent edits, stale revisions, malformed category/tier changes, review state changes, and rollback from memory edit handling to legacy-safe behavior before cutover.",
        ],
        "pass_fail_criteria": "PASS only when edits converge across item store, projections, vector metadata, and all callers without stale legacy unsafe fallback after memory writes.",
        "evidence": [],
    },
    "external_delete_write_read_convergence": {
        "status": "NOT_RUN",
        "scope": "Inventory external create/edit/delete/list/search write/read convergence proof for deletes, tombstones, vector removal, and no resurrection.",
        "required_artifacts": [
            "Delete-path fixture covering /v3 single/bulk delete, Developer API delete, MCP REST delete, MCP SSE delete_memory, and any tool/agent forget-memory path with tombstone and deletion-service proof.",
            "Read-after-delete proof that product, Developer API, MCP REST/SSE, chat, tool, and agent callers exclude deleted/non-active records from list/search and do not resurrect deleted records through legacy fallback or vector stale hits.",
            "Bulk delete/account purge/delete account compatibility evidence tying legacy memory deletes, memory memory_items, review records, import lineage, vectors, and repair outbox handling to one deletion outcome.",
        ],
        "pass_fail_criteria": "PASS only when deletes are durable, converged, visible to every caller as absence/tombstone per contract, and never bypass memory deletion/review/import compatibility requirements.",
        "evidence": [],
    },
    "external_list_search_read_convergence": {
        "status": "NOT_RUN",
        "scope": "Inventory external create/edit/delete/list/search write/read convergence proof for list and search after mixed external writes.",
        "required_artifacts": [
            "Mixed create/edit/delete fixture proving list/search convergence across /v3, Developer API list/vector, MCP REST list/search, MCP SSE get_memories/search_memories, chat search, platform tools, and agent execution paths.",
            "Ordering, pagination/cursor/offset, category-filter, reviewed/manual/sensitive, and semantic-search shape evidence after writes, edits, deletes, imports, and rollback/disable transitions.",
            "No-split-brain report proving legacy users remain legacy-only while memory-enabled users do not see inconsistent write/read results across external callers.",
        ],
        "pass_fail_criteria": "PASS only when external list/search callers agree on canonical write outcomes, authorization, default tiers, and empty/error response shapes after all write operations.",
        "evidence": [],
    },
    "developer_api_write_read_paths": {
        "status": "NOT_RUN",
        "scope": "Inventory Developer API write/read paths for create, batch create, edit, delete, list, category filters, and vector search before authoritative memory reads.",
        "required_artifacts": [
            "Developer API route matrix for POST /v1/dev/user/memories, batch create, PATCH, DELETE, GET list, category-filtered list, and vector search with app/key/scope grant enforcement evidence.",
            "Read-after-write regression proving Developer API writes cannot remain legacy-only after memory default reads are authoritative and category-filter compatibility no longer hides or resurrects records.",
            "Developer response-shape compatibility proof for MemoryResponse/CleanerMemory/vector response fields, errors, disabled/no-grant, enabled-empty, and rollback states.",
        ],
        "pass_fail_criteria": "PASS only when Developer API write/read paths are fully converged or explicitly blocked, authorized by app/key/scope grants, and response-compatible.",
        "evidence": [],
    },
    "mcp_rest_write_read_list_search_paths": {
        "status": "NOT_RUN",
        "scope": "Inventory MCP REST write/read/list/search paths for app/key/scope authorized external memory access.",
        "required_artifacts": [
            "MCP REST route matrix for POST /v1/mcp/memories, DELETE/PATCH /v1/mcp/memories/{memory_id}, GET /v1/mcp/memories, and GET /v1/mcp/memories/search with persisted MCP app_id/key_id/scopes and server-owned memory grants.",
            "Read-after-write proof showing MCP REST list/search converge after create/edit/delete without stale vector hits, unsafe legacy fallback, or Archive default exposure.",
            "MCP REST error/empty/rollback response-shape compatibility evidence for disabled rollout, malformed grant state, missing scopes, revoked grants, and memory enabled-but-empty states.",
        ],
        "pass_fail_criteria": "PASS only when MCP REST write/read/list/search paths enforce grants, converge after writes, and remain compatible across success, empty, denied, and rollback states.",
        "evidence": [],
    },
    "mcp_sse_tool_write_read_list_search_paths": {
        "status": "NOT_RUN",
        "scope": "Inventory MCP REST/SSE write/read/list/search paths, specifically streamable HTTP/SSE memory tools and tool-result contracts.",
        "required_artifacts": [
            "MCP SSE tool matrix for create_memory, edit_memory, delete_memory, get_memories, and search_memories, including session auth context propagation and persisted scope/grant enforcement.",
            "Tool-result read-after-write proof showing SSE tools match MCP REST semantics for canonical IDs, response shape, errors, empty states, list/search ordering, and deleted/non-active exclusion.",
            "Compatibility evidence that MCP tool advertisements/security schemes never grant memory access by themselves and that tool calls fail closed when app/key/scope state is absent or malformed.",
        ],
        "pass_fail_criteria": "PASS only when MCP streamable HTTP/SSE memory tools have the same authorized, converged write/read/list/search semantics as MCP REST.",
        "evidence": [],
    },
    "chat_tool_agent_caller_coverage": {
        "status": "NOT_RUN",
        "scope": "Inventory chat/tool/agent caller coverage for memory list/search/create/edit/delete/read-after-write behavior.",
        "required_artifacts": [
            "Chat search_memories_tool regression proving memory default reads after external writes, disabled/no-grant denial or safe legacy mode, Archive default-unavailable, and compatible tool output text/JSON shape.",
            "Platform tools route regression for /v1/tools/memories list/search and any memory write tools, proving they use the same policy/convergence decisions as product, Developer API, and MCP callers.",
            "Agent execution coverage for /v1/agent/execute-tool and agent remember/forget/update/search flows proving no direct legacy unsafe fallback after memory writes and no unscoped Archive exposure.",
        ],
        "pass_fail_criteria": "PASS only when chat/tool/agent caller coverage demonstrates the same authorization, convergence, response shape, rollback, and Archive default-unavailable behavior as product/external API callers.",
        "evidence": [],
    },
    "dual_write_outbox_or_memory_write_convergence_plan": {
        "status": "NOT_RUN",
        "scope": "Inventory dual-write/outbox or memory-write convergence plan required before authoritative external reads consume new write outcomes.",
        "required_artifacts": [
            "Design and tested implementation evidence choosing one convergence mechanism: durable memory write service, safe dual-write, or outbox-driven convergence from legacy writes into memory memory_items/projections/vectors.",
            "Idempotency, retry/dead-letter, lease/serialization, item_revision, source_commit_id, content_hash, vector projection, and no-silent-data-loss evidence for create/edit/delete operations.",
            "Cutover readiness proof that external writes cannot bypass the convergence mechanism once memory reads are authoritative and that convergence failures block rollout instead of falling back unsafely.",
        ],
        "pass_fail_criteria": "PASS only when a durable, tested write convergence plan prevents legacy/memory split-brain for all external write paths before authoritative memory reads.",
        "evidence": [],
    },
    "delete_review_import_compatibility": {
        "status": "NOT_RUN",
        "scope": "Inventory delete/review/import compatibility across external writes, old-memory imports, review queues, non-active states, and account deletion/export.",
        "required_artifacts": [
            "Compatibility matrix covering /v3 review queue/resolve/review routes, Developer/MCP write routes, import/backfill output, memory deletion service, account purge/export, and raw/source tombstone outcomes.",
            "Proof that pending review, rejected review, invalidated, tombstoned, imported, source-deleted, and purged records are excluded or exposed only under the correct server-authorized policy.",
            "Rollback evidence proving delete/review/import state is not lost when switching between legacy-safe and memory-authoritative readers after external writes.",
        ],
        "pass_fail_criteria": "PASS only when delete/review/import compatibility is proven end-to-end and no caller can resurrect non-active or source-tombstoned memories.",
        "evidence": [],
    },
    "no_legacy_unsafe_fallback_after_memory_writes": {
        "status": "NOT_RUN",
        "scope": "Inventory no legacy unsafe fallback after memory writes for disabled, malformed, no-grant, partial-outage, and rollback states.",
        "required_artifacts": [
            "Truth table identifying when USE_LEGACY_SAFE is still legal after memory writes, what fallback_projection_ready/reconciliation/generation proof is required, and when DENY_MEMORY must be returned instead.",
            "Regression output proving missing/malformed/revoked grants, disabled rollout, empty-after-hydration, vector/provider partial outage, and write-convergence lag do not silently downgrade to unsafe legacy reads.",
            "Audit/observability evidence that every fallback decision includes a bounded reason, consumer/surface, write convergence state, and approval blocker without leaking uid/query/memory IDs into high-cardinality telemetry.",
        ],
        "pass_fail_criteria": "PASS only when legacy fallback after memory writes is either proven reconciled and safe or denied consistently across product, Developer API, MCP, chat, tools, and agents.",
        "evidence": [],
    },
    "app_key_scope_grant_enforcement": {
        "status": "NOT_RUN",
        "scope": "Inventory app/key/scope grant enforcement for external writes and reads across Developer API, MCP REST/SSE, third-party tools, chat, and agent callers.",
        "required_artifacts": [
            "Grant matrix tying authenticated scopes and server-owned grants to memories.read, memories.write, memories.archive.read, default_read, write, and archive_read operations by consumer/surface.",
            "Regression output proving missing app_id/key_id, missing authenticated scope, missing persisted scope, disabled grant, malformed grant doc, unknown consumer, and revoked grants fail closed before read or write access.",
            "Proof that MCP tool advertisements, client request fields, category filters, and explicit Archive queries cannot self-grant access without server-owned app/key/scope state.",
        ],
        "pass_fail_criteria": "PASS only when app/key/scope grant enforcement is complete before external write/read/list/search/tool/agent access and Archive requires the stronger explicit server-owned grant.",
        "evidence": [],
    },
    "archive_default_unavailable": {
        "status": "NOT_RUN",
        "scope": "Inventory Archive default-unavailable proof across external writes and caller reads after create/edit/delete/import/review operations.",
        "required_artifacts": [
            "Fixture proof that external create/edit/import paths cannot make Archive default-visible and cannot write Archive-visible records without explicit server-authorized archive_write/archive_read policy.",
            "Product, Developer API, MCP REST/SSE, chat, tool, and agent list/search proof that Archive remains absent by default after all external writes, even when client/tool asks for category, include flags, or malformed Archive fields.",
            "Rollback/disable evidence proving Archive remains default-unavailable in legacy-safe mode, memory-authoritative mode, and denied states.",
        ],
        "pass_fail_criteria": "PASS only when Archive default-unavailable is enforced server-side for every write and read caller and cannot be made default-visible by request payloads or rollback state.",
        "evidence": [],
    },
    "response_shape_compatibility": {
        "status": "NOT_RUN",
        "scope": "Inventory response-shape compatibility for external create/edit/delete/list/search and chat/tool/agent outputs before authoritative memory reads.",
        "required_artifacts": [
            "Golden response fixtures for /v3, Developer API, MCP REST, MCP SSE tool results, chat memory tools, platform tools, and agent execution across create/edit/delete/list/search success states.",
            "Error/empty/denied/malformed/rollback fixtures proving new memory policy, convergence, cursor, tier, provenance, and grant fields are additive or intentionally mapped without breaking existing clients.",
            "Contract diff covering MemoryDB, MemoryResponse, CleanerMemory, MCP tool result JSON, ToolResponse text envelopes, and agent tool execution envelopes.",
        ],
        "pass_fail_criteria": "PASS only when response-shape compatibility is demonstrated with golden fixtures for all external write/read callers and any new fields are additive, documented, and stable.",
        "evidence": [],
    },
    "rollback_disable_behavior": {
        "status": "NOT_RUN",
        "scope": "Inventory rollback/disable behavior for T22/T23 external writes and caller coverage after partial rollout or failed write convergence.",
        "required_artifacts": [
            "Rollback drill proving global/user/consumer disable states stop new memory external writes or reads as required, preserve already-converged data, and avoid unsafe legacy fallback after memory writes.",
            "Disable behavior matrix for product, /v3, Developer API, MCP REST/SSE, chat, tools, and agent callers across legacy-only users, shadow-only users, memory-authoritative users, and write-convergence blocked users.",
            "Operational blocker evidence tying rollback to cutover checklist gates, central telemetry/alert requirements, write-convergence backlog, and explicit production owner approval before re-enable.",
        ],
        "pass_fail_criteria": "PASS only when rollback/disable behavior is deterministic, tested, does not lose or resurrect memories, and blocks cutover without explicit evidence and approval.",
        "evidence": [],
    },
}

NON_CLAIMS = [
    "Oracle verdict remains BLOCK production rollout / NO-GO.",
    "This T22/T23 external writes and caller coverage readiness matrix is NOT_RUN/BLOCKED and does not claim production approval.",
    "Default and execute modes are read-only inventory only; no network/provider/cloud calls are executed and no mutations are planned.",
    "No production traffic, Firestore mutation, Pinecone mutation, write convergence execution, benchmark run, telemetry sink integration, T22/T23 completion, or cutover approval is performed by this artifact.",
    "Archive remains default-unavailable and stale Short-term remains not default-visible.",
]


@dataclass(frozen=True)
class T22T23ExternalWritesCallerCoverageReadinessConfig:
    execute: bool


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe T22/T23 external writes and caller coverage readiness/proof matrix. It inventories required evidence without production calls."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Emit the same read-only matrix; does not call providers or mutate state.",
    )
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> T22T23ExternalWritesCallerCoverageReadinessConfig:
    return T22T23ExternalWritesCallerCoverageReadinessConfig(execute=bool(args.execute))


def build_readiness_artifact(config: T22T23ExternalWritesCallerCoverageReadinessConfig) -> Dict[str, Any]:
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
            "/v3/memories create/edit/delete/list/search compatibility",
            "/v1/dev/user/memories Developer API create/edit/delete/list/vector/search",
            "MCP REST create/edit/delete/list/search",
            "MCP streamable HTTP/SSE create_memory/edit_memory/delete_memory/get_memories/search_memories",
            "chat search_memories_tool and memory caller paths",
            "/v1/tools/memories platform tool list/search",
            "/v1/agent/execute-tool agent memory tool execution",
        ],
        "required_scope_summary": "external create/edit/delete/list/search write/read convergence; Developer API write/read paths; MCP REST/SSE write/read/list/search paths; chat/tool/agent caller coverage; dual-write/outbox or memory-write convergence plan; delete/review/import compatibility; no legacy unsafe fallback after memory writes; app/key/scope grant enforcement; Archive default-unavailable; response-shape compatibility; rollback/disable behavior",
        "local_route_adapter_and_test_references": LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES,
        "proof_matrix": PROOF_MATRIX,
        "planned_safe_commands": [
            "python3 backend/scripts/t22_t23_external_writes_caller_coverage_readiness.py",
            "python3 backend/scripts/t22_t23_external_writes_caller_coverage_readiness.py --execute",
            "pytest tests/unit/test_t22_t23_external_writes_caller_coverage_readiness.py -q",
            "pytest tests/unit/test_cutover_evidence_readiness.py -q",
            "pytest tests/unit/test_memory_*.py -q",
        ],
        "non_claims": NON_CLAIMS,
    }


def main(argv: Sequence[str] | None = None) -> int:
    config = config_from_args(parse_args(argv or sys.argv[1:]))
    print(json.dumps(build_readiness_artifact(config), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

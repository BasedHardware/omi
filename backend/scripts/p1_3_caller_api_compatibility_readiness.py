#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, Sequence

LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES = {
    "product_v17_default_search": "backend/routers/memory_product.py GET /memory/search",
    "product_v17_vector_search": "backend/routers/memory_product.py GET /memory/vector/search",
    "product_v17_archive_search": "backend/routers/memory_product.py GET /memory/archive/search",
    "v3_legacy_list": "backend/routers/memories.py GET /v3/memories",
    "developer_default_list": "backend/routers/developer.py GET /v1/dev/user/memories",
    "developer_vector_search": "backend/routers/developer.py GET /v1/dev/user/memories/vector/search",
    "mcp_rest_search": "backend/routers/mcp.py GET /v1/mcp/memories/search",
    "mcp_rest_get": "backend/routers/mcp.py GET /v1/mcp/memories",
    "mcp_sse_search": "backend/routers/mcp_sse.py search_memories tool",
    "mcp_sse_get": "backend/routers/mcp_sse.py get_memories tool",
    "chat_get_tool": "backend/utils/retrieval/tools/memory_tools.py get_memories_tool",
    "chat_search_tool": "backend/utils/retrieval/tools/memory_tools.py search_memories_tool",
    "tools_rest_get": "backend/routers/tools.py GET /v1/tools/memories",
    "tools_rest_search": "backend/routers/tools.py POST /v1/tools/memories/search",
    "agent_execute_tool": "backend/routers/agent_tools.py POST /v1/agent/execute-tool",
    "developer_adapter": "backend/utils/memory/v17_developer_memory_adapter.py",
    "mcp_adapter": "backend/utils/mcp_memories.py",
    "chat_adapter": "backend/utils/memory/v17_chat_memory_adapter.py",
    "product_read_service": "backend/utils/memory/v17_product_memory_read_service.py",
    "rollout_helper": "backend/utils/memory/v17_default_read_rollout.py",
    "existing_tests": "backend/tests/unit/test_product_memory_router.py; backend/tests/unit/test_developer_memory_adapter.py; backend/tests/unit/test_v17_mcp_memory_adapter.py; backend/tests/unit/test_chat_memory_adapter.py; backend/tests/unit/test_mcp_search_memories.py; backend/tests/unit/test_mcp_memory_filters.py; backend/tests/unit/test_dev_api_memories_pagination.py; backend/tests/unit/test_tools_router.py",
}

SURFACE_CONTRACT_MATRIX: Dict[str, Dict[str, Any]] = {
    "product_v17_routes": {
        "status": "NOT_RUN",
        "existing_references": [
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["product_v17_default_search"],
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["product_v17_vector_search"],
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["product_v17_archive_search"],
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["product_read_service"],
        ],
        "caller_operations": ["list/search default memory", "vector search", "explicit Archive search"],
        "disabled_malformed_no_grant_contract": "Fail closed with HTTP 403/deny observability for disabled, malformed, or no-grant states; no unsafe legacy downgrade from V17 product routes.",
        "enabled_but_empty_contract": "Return the documented empty product response shape with rollout observability; empty-after-hydration must be distinguishable before rollout approval.",
        "category_filter_contract": "No default Archive or stale Short-term exposure; any future category filters require the same server authorization and non-active filtering contract.",
        "response_shape_contract": "Keep product V17 response fields additive and stable; do not claim /v3 compatibility from product-only shapes.",
        "fallback_contract": "V17 product routes deny or return V17 results only; legacy fallback requires an explicit compatibility route decision, not an implicit downgrade.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "v3_legacy_external_api": {
        "status": "NOT_RUN",
        "existing_references": [LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["v3_legacy_list"]],
        "caller_operations": ["legacy external list"],
        "disabled_malformed_no_grant_contract": "Legacy /v3 remains legacy until a dedicated compatibility proof exists; any V17-backed replacement must define disabled rollout semantics per surface: 403, empty, or legacy-safe.",
        "enabled_but_empty_contract": "Must not silently hide legacy-authoritative data; enabled-but-empty semantics require fixture proof before any V17-backed /v3 read.",
        "category_filter_contract": "Preserve legacy category semantics or publish an additive migration contract with invalid-category behavior and ordering proof.",
        "response_shape_contract": "/v3 external compatibility requires legacy model parse compatibility and additive-only metadata.",
        "fallback_contract": "Rollback must not duplicate, skip, resurrect, or expose Archive by default.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "developer_api_default_list": {
        "status": "NOT_RUN",
        "existing_references": [
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["developer_default_list"],
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["developer_adapter"],
        ],
        "caller_operations": ["default list"],
        "disabled_malformed_no_grant_contract": "Developer default list should deny with a stable external error shape when app/key/scope/grant or rollout fails closed.",
        "enabled_but_empty_contract": "Return an empty List[CleanerMemory] only when V17 is authoritative and reconciliation proves no compatible legacy data is being hidden.",
        "category_filter_contract": "No category filter on this default path; see developer_api_category_filter for category-specific contract.",
        "response_shape_contract": "Developer response shape must not fabricate private/reviewed/edited/category defaults when V17 data lacks authoritative fields.",
        "fallback_contract": "Legacy-safe fallback is allowed only while V17 writes are not converged and the shared decision explicitly says USE_LEGACY_SAFE.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "developer_api_category_filter": {
        "status": "NOT_RUN",
        "existing_references": [LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["developer_default_list"]],
        "caller_operations": ["category-filtered list"],
        "disabled_malformed_no_grant_contract": "Developer category filtering must not force unsafe legacy; if V17 write/read convergence is active, category fallback must deny or use a proven safe compatibility path.",
        "enabled_but_empty_contract": "Empty category pages must distinguish no matching category from blocked split-brain category fallback.",
        "category_filter_contract": "Define valid/invalid category behavior, multi-category behavior, and no category=other fabrication before rollout.",
        "response_shape_contract": "Developer response shape must not fabricate private/reviewed/edited/category defaults on category-filtered records.",
        "fallback_contract": "Current explicit legacy-safe fallback remains BLOCKED for external rollout until category compatibility is proven.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "developer_api_vector_search": {
        "status": "NOT_RUN",
        "existing_references": [
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["developer_vector_search"],
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["developer_adapter"],
        ],
        "caller_operations": ["vector search"],
        "disabled_malformed_no_grant_contract": "Deny with stable 403 detail when app/key/scope/grant or rollout fails closed.",
        "enabled_but_empty_contract": "Return documented empty search list only when vector hydration/reconciliation proves no silent data loss.",
        "category_filter_contract": "No category filter accepted on current vector route; future filters require the category contract.",
        "response_shape_contract": "Search result shape must be documented against developer list shape and should not fabricate legacy-only fields.",
        "fallback_contract": "No unsafe legacy vector fallback after DENY_MEMORY or SHADOW_ONLY; USE_LEGACY_SAFE requires explicit bounded semantics.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "mcp_rest_search_memories": {
        "status": "NOT_RUN",
        "existing_references": [
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["mcp_rest_search"],
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["mcp_adapter"],
        ],
        "caller_operations": ["search_memories"],
        "disabled_malformed_no_grant_contract": "Deny app/key/scope/grant failures; V17 rollout DENY_MEMORY/SHADOW_ONLY returns documented empty or error consistently with SSE.",
        "enabled_but_empty_contract": "Empty search results must be identical in semantics to MCP SSE search_memories for the same input.",
        "category_filter_contract": "No category filter on REST search; category behavior must align if added.",
        "response_shape_contract": "MCP REST searched-memory list shape must be compared with MCP SSE tool-result shape before rollout.",
        "fallback_contract": "MCP search_memories vs get_memories consistency must be resolved; search cannot silently use V17 while get remains unsafe legacy.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "mcp_rest_get_memories": {
        "status": "NOT_RUN",
        "existing_references": [LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["mcp_rest_get"]],
        "caller_operations": ["get/list memories"],
        "disabled_malformed_no_grant_contract": "Define whether disabled rollout means 403, empty, or legacy-safe for MCP get_memories; current legacy path is not external-rollout proof.",
        "enabled_but_empty_contract": "List empty shape must match MCP SSE get_memories semantics and pagination/filter behavior.",
        "category_filter_contract": "Category/review/manual/date/sensitive filters need compatibility proof before any V17 default read promotion.",
        "response_shape_contract": "CleanerMemory list shape must be compared with REST search and SSE tool response shapes.",
        "fallback_contract": "MCP search_memories vs get_memories consistency is a blocking compatibility decision.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "mcp_sse_search_memories": {
        "status": "NOT_RUN",
        "existing_references": [LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["mcp_sse_search"]],
        "caller_operations": ["streamable HTTP/SSE search_memories tool"],
        "disabled_malformed_no_grant_contract": "MCP SSE disabled/no-grant behavior must match MCP REST search for equivalent authenticated app/key/scope context.",
        "enabled_but_empty_contract": "Tool result empty content must be stable and semantically equal to MCP REST search empty behavior.",
        "category_filter_contract": "No category filter on current search tool unless explicitly added and aligned with REST.",
        "response_shape_contract": "MCP REST vs SSE shape/fallback consistency must be proven with golden tool-result fixtures.",
        "fallback_contract": "Fallback chain must be identical to MCP REST search or explicitly documented as incompatible and BLOCKED.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "mcp_sse_get_memories": {
        "status": "NOT_RUN",
        "existing_references": [LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["mcp_sse_get"]],
        "caller_operations": ["streamable HTTP/SSE get_memories tool"],
        "disabled_malformed_no_grant_contract": "Define MCP SSE get_memories disabled/no-grant behavior and align it with MCP REST get_memories before external rollout.",
        "enabled_but_empty_contract": "Tool result empty content must be stable across REST/SSE list semantics.",
        "category_filter_contract": "List filters require REST/SSE parity fixtures.",
        "response_shape_contract": "MCP SSE get_memories text/tool shape must be compared with MCP REST CleanerMemory list response.",
        "fallback_contract": "MCP REST vs SSE shape/fallback consistency is required before V17 read promotion.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "chat_get_memories_tool": {
        "status": "NOT_RUN",
        "existing_references": [LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["chat_get_tool"]],
        "caller_operations": ["LLM get_memories_tool"],
        "disabled_malformed_no_grant_contract": "Define whether chat get memory remains legacy-safe or denies when rollout is disabled/malformed/no-grant.",
        "enabled_but_empty_contract": "Empty natural-language output must be compatible and distinguish real empty from denied/unsafe fallback.",
        "category_filter_contract": "No category filter; date filters must not make Archive or stale Short-term visible by default.",
        "response_shape_contract": "Text formatting must mark memory content as data before future P1-5 prompt-injection hardening.",
        "fallback_contract": "Chat get/search tools should not disagree on disabled rollout semantics.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "chat_search_memories_tool": {
        "status": "NOT_RUN",
        "existing_references": [
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["chat_search_tool"],
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["chat_adapter"],
        ],
        "caller_operations": ["LLM search_memories_tool"],
        "disabled_malformed_no_grant_contract": "Document whether disabled rollout returns legacy-safe text, empty text, or denial text; align with chat get_memories_tool.",
        "enabled_but_empty_contract": "Empty vector result text must distinguish no match from empty-after-hydration or denied state.",
        "category_filter_contract": "No category filter on current search tool.",
        "response_shape_contract": "Text response must remain compatible with LangChain tool consumers and avoid fabricated fields.",
        "fallback_contract": "Legacy-safe fallback only through explicit V17ReadDecision; no implicit None downgrade.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "tools_rest_memories": {
        "status": "NOT_RUN",
        "existing_references": [
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["tools_rest_get"],
            LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["tools_rest_search"],
        ],
        "caller_operations": ["tools REST get", "tools REST search"],
        "disabled_malformed_no_grant_contract": "tools and agent callers need explicit disabled rollout semantics; current tool service legacy reads are not V17 rollout proof.",
        "enabled_but_empty_contract": "ToolResponse empty/error text must be stable and not hide legacy-authoritative data.",
        "category_filter_contract": "No category filter on current tools REST memory endpoints.",
        "response_shape_contract": "ToolResponse wrapping must be compared with chat tool text and agent execute-tool results.",
        "fallback_contract": "Define if tools REST follows chat semantics, product semantics, or separate legacy-safe compatibility semantics.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
    "agent_execute_tool_memories": {
        "status": "NOT_RUN",
        "existing_references": [LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES["agent_execute_tool"]],
        "caller_operations": ["agent execute memory tools"],
        "disabled_malformed_no_grant_contract": "Agent execute-tool memory callers must inherit a documented tool contract instead of bypassing rollout through LangChain legacy reads.",
        "enabled_but_empty_contract": "Agent string result must distinguish empty, denied, and unsafe-fallback-blocked states.",
        "category_filter_contract": "No direct category filter; invoked tool parameters must still be constrained by the chosen memory-tool contract.",
        "response_shape_contract": "Agent result/error wrapper must be compatible with VM agent clients and documented against tools REST output.",
        "fallback_contract": "Agent callers must not get broader legacy fallback than chat/tools callers for equivalent operations.",
        "archive_default_unavailable": True,
        "evidence": [],
    },
}

BEHAVIOR_CONTRACT_MATRIX: Dict[str, Dict[str, Any]] = {
    "disabled_malformed_no_grant_semantics": {
        "status": "NOT_RUN",
        "required_decisions": [
            "For each surface, choose and document disabled rollout semantics per surface: 403, empty, or legacy-safe.",
            "Malformed rollout, missing schema, no app/key grant, missing scope, global gate denial, and read errors must fail closed or use only explicitly proven legacy-safe fallback.",
        ],
        "blocking_questions": ["Which external surfaces may retain legacy-safe fallback after V17 writes converge?"],
        "evidence": [],
    },
    "enabled_but_empty_semantics": {
        "status": "NOT_RUN",
        "required_decisions": [
            "Define enabled-but-empty semantics for empty authoritative store, empty after category filter, empty after vector hydration, and genuinely empty account.",
            "Require observability that distinguishes empty-after-hydration from no matching memories.",
        ],
        "blocking_questions": [
            "What response text/status should chat, tools, and MCP SSE use for denied versus genuinely empty?"
        ],
        "evidence": [],
    },
    "category_filter_semantics": {
        "status": "NOT_RUN",
        "required_decisions": [
            "Developer category filtering must not force unsafe legacy.",
            "Define valid, invalid, multi-category, no-category, and category=other behavior across Developer API, MCP list, and /v3.",
        ],
        "blocking_questions": ["Can category-filtered Developer API list deny while unfiltered default list uses V17?"],
        "evidence": [],
    },
    "get_list_search_consistency": {
        "status": "NOT_RUN",
        "required_decisions": [
            "MCP search_memories vs get_memories consistency must be resolved before external rollout.",
            "Chat get/search and tools REST get/search must publish aligned fallback and empty semantics.",
        ],
        "blocking_questions": [
            "Should get/list promote to V17 before search, or should search stay legacy-safe until get/list parity exists?"
        ],
        "evidence": [],
    },
    "response_shape_compatibility": {
        "status": "NOT_RUN",
        "required_decisions": [
            "MCP REST vs SSE shape/fallback consistency must be proven with golden fixtures.",
            "Product, /v3, Developer API, MCP REST, MCP SSE, chat text, tools REST, and agent wrappers need stable success/empty/error shapes.",
        ],
        "blocking_questions": ["Which fields are additive and which legacy fields are required by external clients?"],
        "evidence": [],
    },
    "archive_default_unavailable": {
        "status": "NOT_RUN",
        "required_decisions": [
            "Archive default-unavailable is mandatory on every default/list/search surface.",
            "Explicit Archive access requires separate server authorization and explicit caller intent; no client-provided category/filter should imply Archive default visibility.",
        ],
        "blocking_questions": ["Which non-product external surfaces, if any, will ever expose explicit Archive reads?"],
        "evidence": [],
    },
    "fallback_semantics": {
        "status": "NOT_RUN",
        "required_decisions": [
            "Every V17 attempt must return an explicit USE_V17, USE_LEGACY_SAFE, DENY_MEMORY, or SHADOW_ONLY-style outcome before fallback.",
            "No implicit None/exception fallback; no unsafe legacy fallback after write convergence or no-grant denial.",
        ],
        "blocking_questions": [
            "What is the abort threshold for legacy-safe fallback once reconciliation detects split-brain?"
        ],
        "evidence": [],
    },
    "mcp_rest_sse_parity": {
        "status": "NOT_RUN",
        "required_decisions": [
            "MCP REST vs SSE shape/fallback consistency must cover search, get/list, create/edit/delete denial, empty, invalid category, and auth failures.",
            "Both transports must use verified app/key/scope context and the same Archive default-unavailable policy.",
        ],
        "blocking_questions": [
            "Can SSE tool text differ from REST JSON while preserving a single compatibility contract?"
        ],
        "evidence": [],
    },
    "developer_non_fabrication_contract": {
        "status": "NOT_RUN",
        "required_decisions": [
            "Developer response shape must not fabricate private/reviewed/edited/category defaults.",
            "Missing authoritative V17 fields must be denied, omitted if optional, or explicitly marked as compatibility-derived with product approval.",
        ],
        "blocking_questions": [
            "Are current CleanerMemory required fields compatible with V17 authoritative item fields without fabrication?"
        ],
        "evidence": [],
    },
    "v3_external_compatibility": {
        "status": "NOT_RUN",
        "required_decisions": [
            "/v3 external compatibility requires legacy response model parse proof, stable pagination/order, invalid-record handling, and rollback proof.",
            "A V17-backed /v3 path must not make stale Short-term or Archive default-visible.",
        ],
        "blocking_questions": ["Should /v3 remain pure legacy until all P1/P0 blockers close?"],
        "evidence": [],
    },
    "tools_and_agent_callers": {
        "status": "NOT_RUN",
        "required_decisions": [
            "tools and agent callers must be included in disabled/no-grant, enabled-empty, response-shape, and fallback compatibility decisions.",
            "Agent execute-tool must not bypass V17 rollout policy by invoking legacy LangChain memory tools under a different wrapper.",
        ],
        "blocking_questions": [
            "Should tools REST and agent execute-tool follow chat semantics or external Developer/MCP semantics?"
        ],
        "evidence": [],
    },
}

NON_CLAIMS = [
    "Oracle verdict remains BLOCK production rollout / NO-GO.",
    "This Oracle P1-3 caller/API compatibility contract is NOT_RUN/BLOCKED and does not claim production approval.",
    "Default and execute modes are read-only inventory only; no network/provider/cloud calls are executed and no mutations are planned.",
    "No production traffic, Firestore read/write, Pinecone read/write, provider call, benchmark run, telemetry sink integration, runtime behavior change, or rollout approval is performed by this artifact.",
    "Archive remains default-unavailable and stale Short-term remains not default-visible.",
]


@dataclass(frozen=True)
class P13CallerApiCompatibilityReadinessConfig:
    execute: bool


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe Oracle P1-3 caller/API compatibility contract readiness artifact. It inventories required surface decisions without production calls."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Emit the same read-only P1-3 compatibility contract matrix; does not call providers or mutate state.",
    )
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> P13CallerApiCompatibilityReadinessConfig:
    return P13CallerApiCompatibilityReadinessConfig(execute=bool(args.execute))


def build_readiness_artifact(config: P13CallerApiCompatibilityReadinessConfig) -> Dict[str, Any]:
    return {
        "status": "BLOCKED",
        "read_only": True,
        "mutation_allowed": False,
        "execute_requested": config.execute,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "benchmark_evidence_collected": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "compatibility_contract_title": "Oracle P1-3 caller/API compatibility contract",
        "required_scope_summary": "Inventory Product, /v3, Developer API, MCP REST, MCP SSE, chat, tools, and agent callers across disabled/malformed/no-grant, enabled-but-empty, category filters, get/list/search, response shape, Archive default-unavailable, and fallback semantics. Required decisions include MCP search_memories vs get_memories consistency; MCP REST vs SSE shape/fallback consistency; Developer category filtering must not force unsafe legacy; Developer response shape must not fabricate private/reviewed/edited/category defaults; disabled rollout semantics per surface: 403, empty, or legacy-safe; enabled-but-empty semantics; Archive default-unavailable; /v3 external compatibility; tools and agent callers.",
        "local_route_adapter_and_test_references": LOCAL_ROUTE_ADAPTER_AND_TEST_REFERENCES,
        "surface_contract_matrix": SURFACE_CONTRACT_MATRIX,
        "behavior_contract_matrix": BEHAVIOR_CONTRACT_MATRIX,
        "planned_safe_commands": [
            "python3 backend/scripts/p1_3_caller_api_compatibility_readiness.py",
            "python3 backend/scripts/p1_3_caller_api_compatibility_readiness.py --execute",
            "pytest tests/unit/test_p1_3_caller_api_compatibility_readiness.py -q",
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

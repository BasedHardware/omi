import importlib.util
import sys
from pathlib import Path

REQUIRED_SURFACES = {
    "product_memory_routes",
    "v3_legacy_external_api",
    "developer_api_default_list",
    "developer_api_category_filter",
    "developer_api_vector_search",
    "mcp_rest_search_memories",
    "mcp_rest_get_memories",
    "mcp_sse_search_memories",
    "mcp_sse_get_memories",
    "chat_get_memories_tool",
    "chat_search_memories_tool",
    "tools_rest_memories",
    "agent_execute_tool_memories",
}

REQUIRED_CASE_KEYS = {
    "disabled_malformed_no_grant_semantics",
    "enabled_but_empty_semantics",
    "category_filter_semantics",
    "get_list_search_consistency",
    "response_shape_compatibility",
    "archive_default_unavailable",
    "fallback_semantics",
    "mcp_rest_sse_parity",
    "developer_non_fabrication_contract",
    "v3_external_compatibility",
    "tools_and_agent_callers",
}

REQUIRED_REFERENCE_TERMS = [
    "backend/routers/memory_product.py GET /memory/search",
    "backend/routers/memory_product.py GET /memory/vector/search",
    "backend/routers/memory_product.py GET /memory/archive/search",
    "backend/routers/memories.py GET /v3/memories",
    "backend/routers/developer.py GET /v1/dev/user/memories",
    "backend/routers/developer.py GET /v1/dev/user/memories/vector/search",
    "backend/routers/mcp.py GET /v1/mcp/memories/search",
    "backend/routers/mcp.py GET /v1/mcp/memories",
    "backend/routers/mcp_sse.py search_memories tool",
    "backend/routers/mcp_sse.py get_memories tool",
    "backend/utils/retrieval/tools/memory_tools.py get_memories_tool",
    "backend/utils/retrieval/tools/memory_tools.py search_memories_tool",
    "backend/routers/tools.py GET /v1/tools/memories",
    "backend/routers/tools.py POST /v1/tools/memories/search",
    "backend/routers/agent_tools.py POST /v1/agent/execute-tool",
    "backend/utils/memory/developer_memory_adapter.py",
    "backend/utils/mcp_memories.py",
]

REQUIRED_CONTRACT_TERMS = [
    "MCP search_memories vs get_memories consistency",
    "MCP REST vs SSE shape/fallback consistency",
    "Developer category filtering must not force unsafe legacy",
    "Developer response shape must not fabricate private/reviewed/edited/category defaults",
    "disabled rollout semantics per surface: 403, empty, or legacy-safe",
    "enabled-but-empty semantics",
    "Archive default-unavailable",
    "/v3 external compatibility",
    "tools and agent callers",
]

FORBIDDEN_MUTATION_TERMS = [
    ".upsert(",
    ".delete(",
    ".update(",
    ".set(",
    ".add(",
    "delete_all",
    "batch.commit",
    "commit()",
    "requests.",
    "httpx.",
    "pinecone.",
    "firestore.Client",
    "gcloud ",
    "firebase deploy",
]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("p1_3_caller_api_compatibility_readiness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _module():
    root = Path(__file__).resolve().parents[2]
    return _load_module(root / "scripts" / "p1_3_caller_api_compatibility_readiness.py")


def test_p1_3_runner_exists_and_is_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "p1_3_caller_api_compatibility_readiness.py"

    assert script_path.exists(), "missing safe Oracle P1-3 caller/API compatibility readiness runner"
    script = script_path.read_text()
    for term in REQUIRED_REFERENCE_TERMS + REQUIRED_CONTRACT_TERMS:
        assert term in script
    for term in FORBIDDEN_MUTATION_TERMS:
        assert term not in script

    module = _module()
    artifact = module.build_readiness_artifact(module.P13CallerApiCompatibilityReadinessConfig(execute=False))

    assert artifact["status"] == "BLOCKED"
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["network_or_provider_calls_executed"] is False
    assert artifact["provider_calls_executed"] is False
    assert artifact["firestore_reads_executed"] is False
    assert artifact["firestore_writes_executed"] is False
    assert artifact["benchmark_evidence_collected"] is False
    assert artifact["production_rollout_approved"] is False
    assert artifact["approval_claimed"] is False


def test_p1_3_surface_and_behavior_matrices_are_complete_and_not_run():
    module = _module()
    artifact = module.build_readiness_artifact(module.P13CallerApiCompatibilityReadinessConfig(execute=False))

    assert set(artifact["surface_contract_matrix"]) == REQUIRED_SURFACES
    for surface_key, surface in artifact["surface_contract_matrix"].items():
        assert surface_key in REQUIRED_SURFACES
        assert surface["status"] == "NOT_RUN"
        assert surface["evidence"] == []
        assert surface["existing_references"]
        assert surface["disabled_malformed_no_grant_contract"]
        assert surface["enabled_but_empty_contract"]
        assert surface["response_shape_contract"]
        assert surface["fallback_contract"]
        assert surface["archive_default_unavailable"] is True

    assert set(artifact["behavior_contract_matrix"]) == REQUIRED_CASE_KEYS
    for case_key, case in artifact["behavior_contract_matrix"].items():
        assert case_key in REQUIRED_CASE_KEYS
        assert case["status"] == "NOT_RUN"
        assert case["evidence"] == []
        assert case["required_decisions"]
        assert case["blocking_questions"]


def test_p1_3_execute_remains_read_only_blocked_without_evidence_or_calls():
    module = _module()
    artifact = module.build_readiness_artifact(module.P13CallerApiCompatibilityReadinessConfig(execute=True))

    assert artifact["status"] == "BLOCKED"
    assert artifact["execute_requested"] is True
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["network_or_provider_calls_executed"] is False
    assert artifact["provider_calls_executed"] is False
    assert artifact["firestore_reads_executed"] is False
    assert artifact["firestore_writes_executed"] is False
    assert artifact["production_rollout_approved"] is False
    assert all(surface["evidence"] == [] for surface in artifact["surface_contract_matrix"].values())
    assert all(case["evidence"] == [] for case in artifact["behavior_contract_matrix"].values())
    assert "no network/provider/cloud calls are executed" in " ".join(artifact["non_claims"])


def test_p1_3_readiness_is_linked_from_oracle_ticket_and_test_runner():
    repo = Path(__file__).resolve().parents[2].parent
    oracle = (repo / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text()
    tickets = (repo / "docs" / "epics" / "memory_implementation_tickets.md").read_text()
    test_sh = (repo / "backend" / "test.sh").read_text()

    for text in (oracle, tickets):
        assert "p1_3_caller_api_compatibility_readiness.py" in text
        assert "Oracle P1-3 caller/API compatibility contract" in text
        assert "MCP search_memories vs get_memories consistency" in text
        assert "Developer response shape must not fabricate" in text
        assert "tools and agent callers" in text

    assert "test_p1_3_caller_api_compatibility_readiness.py" in test_sh

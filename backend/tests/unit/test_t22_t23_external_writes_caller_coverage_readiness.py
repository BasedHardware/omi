import importlib.util
import sys
from pathlib import Path

REQUIRED_CASE_KEYS = {
    "external_create_write_read_convergence",
    "external_edit_write_read_convergence",
    "external_delete_write_read_convergence",
    "external_list_search_read_convergence",
    "developer_api_write_read_paths",
    "mcp_rest_write_read_list_search_paths",
    "mcp_sse_tool_write_read_list_search_paths",
    "chat_tool_agent_caller_coverage",
    "dual_write_outbox_or_memory_write_convergence_plan",
    "delete_review_import_compatibility",
    "no_legacy_unsafe_fallback_after_memory_writes",
    "app_key_scope_grant_enforcement",
    "archive_default_unavailable",
    "response_shape_compatibility",
    "rollback_disable_behavior",
}

REQUIRED_REFERENCE_TERMS = [
    "backend/routers/memories.py POST/PATCH/DELETE/GET /v3/memories",
    "backend/routers/developer.py /v1/dev/user/memories create/edit/delete/list/vector/search",
    "backend/routers/mcp.py MCP REST create/edit/delete/list/search",
    "backend/routers/mcp_sse.py MCP streamable HTTP/SSE tools create_memory/edit_memory/delete_memory/get_memories/search_memories",
    "backend/routers/tools.py /v1/tools/memories list/search",
    "backend/routers/agent_tools.py /v1/agent/execute-tool",
    "backend/database/memories.py create_memory/edit_memory/delete_memory/save_memories/get_memories",
    "backend/utils/memory/default_read_rollout.py assert_legacy_memory_write_allowed_for_default_read_decision",
    "backend/utils/memory/product_authorization.py authorize_memory_external_default_memory_read",
    "docs/epics/memory_implementation_tickets.md T22/T23",
    "cutover_evidence_readiness.py",
]

REQUIRED_SCOPE_TERMS = [
    "external create/edit/delete/list/search write/read convergence",
    "Developer API write/read paths",
    "MCP REST/SSE write/read/list/search paths",
    "chat/tool/agent caller coverage",
    "dual-write/outbox or memory-write convergence plan",
    "delete/review/import compatibility",
    "no legacy unsafe fallback after memory writes",
    "app/key/scope grant enforcement",
    "Archive default-unavailable",
    "response-shape compatibility",
    "rollback/disable behavior",
]

FORBIDDEN_MUTATION_TERMS = [
    ".upsert(",
    ".delete(",
    ".update(",
    ".set(",
    ".add(",
    "delete_all",
    "deleteAll",
    "batch.commit",
    "commit()",
    "requests.",
    "httpx.",
    "pinecone.",
    "gcloud run deploy",
    "firebase deploy",
]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("t22_t23_external_writes_caller_coverage_readiness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _module():
    root = Path(__file__).resolve().parents[2]
    return _load_module(root / "scripts" / "t22_t23_external_writes_caller_coverage_readiness.py")


def test_t22_t23_external_writes_caller_coverage_runner_exists_and_is_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "t22_t23_external_writes_caller_coverage_readiness.py"

    assert script_path.exists(), "missing safe T22/T23 external writes and caller coverage readiness matrix runner"
    script = script_path.read_text()
    for term in REQUIRED_REFERENCE_TERMS + REQUIRED_SCOPE_TERMS:
        assert term in script
    for term in FORBIDDEN_MUTATION_TERMS:
        assert term not in script

    module = _module()
    artifact = module.build_readiness_artifact(module.T22T23ExternalWritesCallerCoverageReadinessConfig(execute=False))

    assert artifact["status"] == "BLOCKED"
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["network_or_provider_calls_executed"] is False
    assert artifact["provider_calls_executed"] is False
    assert artifact["benchmark_evidence_collected"] is False
    assert artifact["production_rollout_approved"] is False
    assert artifact["approval_claimed"] is False


def test_t22_t23_readiness_matrix_contains_required_cases_with_empty_evidence():
    module = _module()
    artifact = module.build_readiness_artifact(module.T22T23ExternalWritesCallerCoverageReadinessConfig(execute=False))

    assert set(artifact["proof_matrix"]) == REQUIRED_CASE_KEYS
    for case_key, case in artifact["proof_matrix"].items():
        assert case_key in REQUIRED_CASE_KEYS
        assert case["status"] == "NOT_RUN"
        assert case["evidence"] == []
        assert case["required_artifacts"]
        assert case["pass_fail_criteria"]
        case_text = " ".join(case["required_artifacts"]) + " " + case["scope"]
        assert any(scope_term in case_text for scope_term in REQUIRED_SCOPE_TERMS)

    archive_case = artifact["proof_matrix"]["archive_default_unavailable"]
    assert "Archive default-unavailable" in archive_case["scope"]
    assert "default-visible" in " ".join(archive_case["required_artifacts"])


def test_t22_t23_execute_remains_read_only_blocked_and_not_run_without_calls():
    module = _module()
    artifact = module.build_readiness_artifact(module.T22T23ExternalWritesCallerCoverageReadinessConfig(execute=True))

    assert artifact["status"] == "BLOCKED"
    assert artifact["execute_requested"] is True
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["network_or_provider_calls_executed"] is False
    assert artifact["provider_calls_executed"] is False
    assert all(case["evidence"] == [] for case in artifact["proof_matrix"].values())
    assert "no network/provider/cloud calls are executed" in " ".join(artifact["non_claims"])


def test_t22_t23_readiness_is_linked_from_cutover_oracle_docs_and_ticket():
    repo = Path(__file__).resolve().parents[2].parent
    oracle = (repo / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text()
    tickets = (repo / "docs" / "epics" / "memory_implementation_tickets.md").read_text()
    cutover = (repo / "backend" / "scripts" / "cutover_evidence_readiness.py").read_text()

    for text in (oracle, tickets, cutover):
        assert "t22_t23_external_writes_caller_coverage_readiness.py" in text
        assert "T22/T23 external writes and caller coverage" in text
        assert "external create/edit/delete/list/search write/read convergence" in text
        assert "chat/tool/agent caller coverage" in text

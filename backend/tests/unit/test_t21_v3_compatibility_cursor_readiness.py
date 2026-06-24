import importlib.util
import sys
from pathlib import Path

REQUIRED_CASE_KEYS = {
    "v3_endpoint_legacy_shape_compatibility",
    "stable_cursor_pagination_and_ordering",
    "category_filters_and_developer_category_filtering",
    "disabled_malformed_no_grant_behavior",
    "enabled_but_empty_behavior",
    "deleted_non_active_and_archive_default_unavailable",
    "external_response_shape_compatibility",
    "mcp_rest_sse_shape_consistency",
    "product_developer_mcp_chat_caller_regression",
}

REQUIRED_REFERENCE_TERMS = [
    "backend/routers/memories.py GET /v3/memories",
    "backend/database/memories.py get_memories",
    "backend/utils/memory/product_memory_read_service.py",
    "backend/utils/memory/developer_memory_adapter.py",
    "backend/utils/memory/mcp_memories.py",
    "backend/utils/memory/chat_memory_adapter.py",
    "backend/routers/mcp.py",
    "backend/routers/mcp_sse.py",
    "backend/routers/developer.py",
    "docs/epics/memory_implementation_tickets.md T21",
    "cutover_evidence_readiness.py",
]

REQUIRED_SCOPE_TERMS = [
    "/v3 endpoint compatibility",
    "stable cursor pagination",
    "category filters",
    "stable ordering",
    "disabled/malformed/no-grant",
    "enabled-but-empty",
    "deleted/non-active records",
    "Archive default-unavailable",
    "external response shape compatibility",
    "developer category filtering",
    "MCP REST/SSE shape consistency",
    "product/developer/MCP/chat caller regression",
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
    spec = importlib.util.spec_from_file_location("t21_v3_compatibility_cursor_readiness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _module():
    root = Path(__file__).resolve().parents[2]
    return _load_module(root / "scripts" / "t21_v3_compatibility_cursor_readiness.py")


def test_t21_v3_compatibility_cursor_runner_exists_and_is_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "t21_v3_compatibility_cursor_readiness.py"

    assert script_path.exists(), "missing safe T21 /v3 compatibility cursor readiness matrix runner"
    script = script_path.read_text()
    for term in REQUIRED_REFERENCE_TERMS + REQUIRED_SCOPE_TERMS:
        assert term in script
    for term in FORBIDDEN_MUTATION_TERMS:
        assert term not in script

    module = _module()
    artifact = module.build_readiness_artifact(module.T21V3CompatibilityCursorReadinessConfig(execute=False))

    assert artifact["status"] == "BLOCKED"
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["network_or_provider_calls_executed"] is False
    assert artifact["provider_calls_executed"] is False
    assert artifact["benchmark_evidence_collected"] is False
    assert artifact["production_rollout_approved"] is False
    assert artifact["approval_claimed"] is False


def test_t21_readiness_matrix_contains_required_cases_with_empty_evidence():
    module = _module()
    artifact = module.build_readiness_artifact(module.T21V3CompatibilityCursorReadinessConfig(execute=False))

    assert set(artifact["proof_matrix"]) == REQUIRED_CASE_KEYS
    for case_key, case in artifact["proof_matrix"].items():
        assert case_key in REQUIRED_CASE_KEYS
        assert case["status"] == "NOT_RUN"
        assert case["evidence"] == []
        assert case["required_artifacts"]
        assert case["pass_fail_criteria"]
        case_text = " ".join(case["required_artifacts"]) + " " + case["scope"]
        assert any(scope_term in case_text for scope_term in REQUIRED_SCOPE_TERMS)

    no_archive = artifact["proof_matrix"]["deleted_non_active_and_archive_default_unavailable"]
    assert "Archive default-unavailable" in " ".join(no_archive["required_artifacts"])
    assert "deleted/non-active records" in no_archive["scope"]


def test_t21_execute_remains_read_only_blocked_and_not_run_without_calls():
    module = _module()
    artifact = module.build_readiness_artifact(module.T21V3CompatibilityCursorReadinessConfig(execute=True))

    assert artifact["status"] == "BLOCKED"
    assert artifact["execute_requested"] is True
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["network_or_provider_calls_executed"] is False
    assert artifact["provider_calls_executed"] is False
    assert all(case["evidence"] == [] for case in artifact["proof_matrix"].values())
    assert "no network/provider/cloud calls are executed" in " ".join(artifact["non_claims"])


def test_t21_readiness_is_linked_from_cutover_oracle_docs_and_ticket():
    repo = Path(__file__).resolve().parents[2].parent
    oracle = (repo / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text()
    tickets = (repo / "docs" / "epics" / "memory_implementation_tickets.md").read_text()
    cutover = (repo / "backend" / "scripts" / "cutover_evidence_readiness.py").read_text()

    for text in (oracle, tickets, cutover):
        assert "t21_v3_compatibility_cursor_readiness.py" in text
        assert "T21 `/v3` compatibility and cursor pagination" in text
        assert "stable cursor pagination" in text
        assert "product/developer/MCP/chat caller regression" in text

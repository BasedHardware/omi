import importlib.util
import sys
from pathlib import Path

REQUIRED_CASE_KEYS = {
    "projection_commit_id_parity",
    "account_generation_parity",
    "item_revision_source_commit_content_hash_parity",
    "tombstone_deleted_source_handling",
    "stale_physical_vector_detection",
    "duplicate_vector_detection",
    "repair_outbox_enqueue_dead_letter_backlog",
    "repair_worker_convergence",
    "shared_ns2_legacy_memory_isolation_under_stale_candidates",
    "no_silent_data_loss",
}

REQUIRED_REFERENCE_TERMS = [
    "vector_search_provider_readiness.py",
    "shared_ns2_legacy_isolation_readiness.py",
    "pinecone_repair_validation_readiness.py",
    "memory_vector_repair_outbox_telemetry.py",
    "projection_commit_id",
    "account_generation",
    "item_revision",
    "source_commit_id",
    "content_hash",
    "memory_items",
    "vector metadata",
    "vector repair outbox",
    "shared ns2",
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
    "gcloud run deploy",
    "firebase deploy",
]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("t20_repair_projection_consistency_readiness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _module():
    root = Path(__file__).resolve().parents[2]
    return _load_module(root / "scripts" / "t20_repair_projection_consistency_readiness.py")


def test_t20_repair_projection_consistency_runner_exists_and_is_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "t20_repair_projection_consistency_readiness.py"

    assert script_path.exists(), "missing safe T20 repair/projection-consistency readiness matrix runner"
    script = script_path.read_text()
    for term in REQUIRED_REFERENCE_TERMS:
        assert term in script
    for term in FORBIDDEN_MUTATION_TERMS:
        assert term not in script

    module = _module()
    artifact = module.build_readiness_artifact(module.T20RepairProjectionConsistencyReadinessConfig(execute=False))

    assert artifact["status"] == "BLOCKED"
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["network_or_provider_calls_executed"] is False
    assert artifact["provider_calls_executed"] is False
    assert artifact["benchmark_evidence_collected"] is False
    assert artifact["production_rollout_approved"] is False
    assert artifact["approval_claimed"] is False
    assert artifact["shared_namespace"] == "ns2"


def test_t20_readiness_matrix_contains_required_cases_with_empty_evidence():
    module = _module()
    artifact = module.build_readiness_artifact(module.T20RepairProjectionConsistencyReadinessConfig(execute=False))

    assert set(artifact["proof_matrix"]) == REQUIRED_CASE_KEYS
    for case_key, case in artifact["proof_matrix"].items():
        assert case_key in REQUIRED_CASE_KEYS
        assert case["status"] == "NOT_RUN"
        assert case["evidence"] == []
        assert case["required_artifacts"]
        assert case["pass_fail_criteria"]
        assert "No production approval" not in case["pass_fail_criteria"]

    no_data_loss = artifact["proof_matrix"]["no_silent_data_loss"]
    assert "Archive default-unavailable" in " ".join(no_data_loss["required_artifacts"])
    assert "stale Short-term" in " ".join(no_data_loss["required_artifacts"])


def test_t20_execute_remains_read_only_and_not_run_without_provider_calls():
    module = _module()
    artifact = module.build_readiness_artifact(module.T20RepairProjectionConsistencyReadinessConfig(execute=True))

    assert artifact["status"] == "BLOCKED"
    assert artifact["execute_requested"] is True
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["network_or_provider_calls_executed"] is False
    assert artifact["provider_calls_executed"] is False
    assert all(case["evidence"] == [] for case in artifact["proof_matrix"].values())
    assert "no network/provider/cloud calls are executed" in " ".join(artifact["non_claims"])


def test_t20_readiness_is_linked_from_cutover_oracle_docs_and_ticket():
    repo = Path(__file__).resolve().parents[2].parent
    oracle = (repo / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text()
    tickets = (repo / "docs" / "epics" / "memory_implementation_tickets.md").read_text()
    cutover = (repo / "backend" / "scripts" / "cutover_evidence_readiness.py").read_text()

    for text in (oracle, tickets, cutover):
        assert "t20_repair_projection_consistency_readiness.py" in text
        assert "projection_commit_id/account_generation/item_revision/source_commit_id/content_hash" in text
        assert "repair outbox enqueue/dead-letter/backlog" in text
        assert "shared ns2 legacy/memory isolation under stale candidates" in text

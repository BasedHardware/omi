import importlib.util
import sys
from pathlib import Path

REQUIRED_ARTIFACT_TERMS = [
    "NOT_RUN",
    "read_only",
    "mutation_allowed",
    "provider_pagination_refill_semantics",
    "provider_vector_query_timeout_behavior",
    "firestore_candidate_hydration_read_counts",
    "malformed_or_stale_metadata",
    "cross_user_hits",
    "expired_short_term",
    "archive_default_unavailable",
    "deleted_or_tombstoned_sources",
    "duplicate_revisions",
    "partial_outages",
    "high_volume_account_candidate_budgets",
    "load_recall_latency_criteria",
    "PINECONE_API_KEY",
    "PINECONE_INDEX_NAME",
    "PINECONE_INDEX_HOST",
    "MEMORY_PROVIDER_PROOF_FIRESTORE_PROJECT",
    "MEMORY_PROVIDER_PROOF_UID",
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
]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("vector_search_provider_readiness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_provider_readiness_runner_exists_and_defaults_not_run_read_only():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "vector_search_provider_readiness.py"

    assert script_path.exists(), "missing safe memory vector search provider proof/readiness runner"
    script = script_path.read_text()
    for term in REQUIRED_ARTIFACT_TERMS:
        assert term in script
    for term in FORBIDDEN_MUTATION_TERMS:
        assert term not in script

    module = _load_module(script_path)
    config = module.VectorSearchProviderReadinessConfig(
        execute=False,
        pinecone_api_key="",
        pinecone_index_name="",
        pinecone_index_host="",
        firestore_project="",
        proof_uid="",
        proof_namespace="ns2",
    )
    artifact = module.build_readiness_artifact(config)

    assert artifact["status"] == "NOT_RUN"
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["provider_calls_executed"] is False
    assert artifact["shared_namespace"] == "ns2"
    assert artifact["proof_cases"]["provider_pagination_refill_semantics"]
    assert artifact["proof_cases"]["load_recall_latency_criteria"]
    assert "no real Pinecone/Firestore provider proof was executed" in " ".join(artifact["non_claims"])


def test_provider_readiness_execute_requires_prerequisites_and_remains_read_only():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "vector_search_provider_readiness.py")

    missing = module.VectorSearchProviderReadinessConfig(
        execute=True,
        pinecone_api_key="",
        pinecone_index_name="",
        pinecone_index_host="",
        firestore_project="",
        proof_uid="",
        proof_namespace="ns2",
    )
    prerequisites = module.evaluate_prerequisites(missing)

    assert "PINECONE_API_KEY is required" in prerequisites
    assert "PINECONE_INDEX_NAME is required" in prerequisites
    assert "PINECONE_INDEX_HOST is required" in prerequisites
    assert "MEMORY_PROVIDER_PROOF_FIRESTORE_PROJECT or --firestore-project is required" in prerequisites
    assert "MEMORY_PROVIDER_PROOF_UID or --proof-uid is required" in prerequisites
    artifact = module.build_readiness_artifact(missing)
    assert artifact["status"] == "NOT_RUN"
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["planned_provider_actions"] == [
        "read-only Pinecone query/inventory only; no upsert/delete/update",
        "read-only Firestore document get/query accounting only; no create/set/update/delete",
    ]

    ready = module.VectorSearchProviderReadinessConfig(
        execute=True,
        pinecone_api_key="key",
        pinecone_index_name="index",
        pinecone_index_host="host",
        firestore_project="project",
        proof_uid="uid",
        proof_namespace="ns2-readonly-shadow",
    )
    assert module.evaluate_prerequisites(ready) == []
    ready_artifact = module.build_readiness_artifact(ready)
    assert ready_artifact["status"] == "NOT_RUN"
    assert ready_artifact["provider_ready_for_readonly_execution"] is True
    assert ready_artifact["provider_calls_executed"] is False


def test_provider_readiness_proof_cases_cover_oracle_p0_7_matrix_without_claiming_evidence():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "vector_search_provider_readiness.py")
    artifact = module.build_readiness_artifact(
        module.VectorSearchProviderReadinessConfig(
            execute=False,
            pinecone_api_key="",
            pinecone_index_name="",
            pinecone_index_host="",
            firestore_project="",
            proof_uid="",
            proof_namespace="ns2",
        )
    )

    expected_cases = {
        "provider_pagination_refill_semantics",
        "provider_vector_query_timeout_behavior",
        "firestore_candidate_hydration_read_counts",
        "malformed_or_stale_metadata",
        "cross_user_hits",
        "expired_short_term",
        "archive_default_unavailable",
        "deleted_or_tombstoned_sources",
        "duplicate_revisions",
        "partial_outages",
        "high_volume_account_candidate_budgets",
        "load_recall_latency_criteria",
    }
    assert expected_cases.issubset(set(artifact["proof_cases"]))
    for case in expected_cases:
        assert artifact["proof_cases"][case]["status"] == "NOT_RUN"
        assert artifact["proof_cases"][case]["evidence"] == []
    assert artifact["production_rollout_approved"] is False
    assert artifact["benchmark_evidence_collected"] is False


def test_provider_readiness_docs_reference_non_claims_and_runner():
    root = Path(__file__).resolve().parents[2].parent
    evidence_markers = (root / "docs" / "operational" / "memory_readiness_evidence_markers.md").read_text()

    assert "vector_search_provider_readiness.py" in evidence_markers
    assert "provider pagination/refill" in evidence_markers
    assert "No real Pinecone/Firestore provider proof" in evidence_markers
    assert "load/recall/latency" in evidence_markers

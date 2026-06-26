import importlib.util
import sys
import types
from pathlib import Path

REQUIRED_ARTIFACT_TERMS = [
    "NOT_RUN",
    "read_only",
    "mutation_allowed",
    "ns2",
    "find_similar_memories",
    "search_memories_by_vector",
    "memory_schema_version",
    "memory_tier",
    "source_state",
    "restricted_sensitivity",
    "uid",
    "stale_or_deleted_physical_ids",
    "overfetch_refill",
]

FORBIDDEN_MUTATION_TERMS = [
    ".upsert(",
    ".delete(",
    "delete_all",
    "deleteAll",
    "update(",
]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("shared_ns2_legacy_isolation_readiness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_shared_ns2_readiness_runner_exists_and_defaults_not_run_read_only():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "shared_ns2_legacy_isolation_readiness.py"

    assert script_path.exists(), "missing safe shared ns2 legacy/memory isolation readiness runner"
    script = script_path.read_text()
    for term in REQUIRED_ARTIFACT_TERMS:
        assert term in script
    for term in FORBIDDEN_MUTATION_TERMS:
        assert term not in script

    module = _load_module(script_path)
    config = module.SharedNs2LegacyIsolationConfig(execute=False, api_key="", index_name="", index_host="")
    artifact = module.build_readiness_artifact(config)

    assert artifact["status"] == "NOT_RUN"
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["shared_namespace"] == "ns2"
    assert "PINECONE_API_KEY is required" in artifact["prerequisites"]
    assert artifact["legacy_search_inventory"]
    assert artifact["required_barriers"]["legacy_queries_exclude_memory_schema"]
    assert artifact["non_claims"]


def test_shared_ns2_readiness_execute_is_read_only_and_requires_provider_config():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "shared_ns2_legacy_isolation_readiness.py")

    missing = module.SharedNs2LegacyIsolationConfig(execute=True, api_key="", index_name="", index_host="")
    prerequisites = module.evaluate_prerequisites(missing)

    assert "PINECONE_API_KEY is required" in prerequisites
    assert "PINECONE_INDEX_NAME is required" in prerequisites
    assert "PINECONE_INDEX_HOST is required" in prerequisites
    artifact = module.build_readiness_artifact(missing)
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["planned_provider_actions"] == ["read-only query/inventory only; no upsert/delete/update"]

    ready = module.SharedNs2LegacyIsolationConfig(execute=True, api_key="key", index_name="idx", index_host="host")
    assert module.evaluate_prerequisites(ready) == []
    ready_artifact = module.build_readiness_artifact(ready)
    assert ready_artifact["status"] == "NOT_RUN"
    assert ready_artifact["read_only"] is True
    assert ready_artifact["mutation_allowed"] is False


def test_legacy_memory_vector_filters_exclude_memory_schema_records():
    pinecone_module = types.ModuleType("pinecone")
    setattr(pinecone_module, "Pinecone", lambda api_key: None)
    sys.modules["pinecone"] = pinecone_module
    clients_module = types.ModuleType("utils.llm.clients")
    setattr(clients_module, "embeddings", object())
    sys.modules["utils.llm.clients"] = clients_module
    projection_repair_module = types.ModuleType("database.projection_repair")
    setattr(projection_repair_module, "projection_metadata_for_fact", lambda memory, source_commit_id=None: {})
    sys.modules["database.projection_repair"] = projection_repair_module

    from database import vector_db

    legacy_filter = vector_db.build_legacy_memory_vector_filter("uid-1")
    subject_filter = vector_db.build_legacy_memory_vector_filter("uid-1", subject_entity_id="person-1")

    assert {"uid": {"$eq": "uid-1"}} in legacy_filter["$and"]
    assert {"memory_schema_version": {"$exists": False}} in legacy_filter["$and"]
    assert {"subject_entity_id": {"$eq": "person-1"}} in subject_filter["$and"]


def test_shared_ns2_docs_reference_non_claims_and_remaining_provider_proof():
    root = Path(__file__).resolve().parents[2].parent
    evidence_markers = (root / "docs" / "operational" / "memory_readiness_evidence_markers.md").read_text()

    assert "shared_ns2_legacy_isolation_readiness.py" in evidence_markers
    assert "legacy queries exclude memory schema" in evidence_markers
    assert "No real Pinecone shared `ns2` proof" in evidence_markers

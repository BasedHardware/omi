import importlib.util
import sys
from pathlib import Path

REQUIRED_STATIC_TERMS = [
    "PINECONE_API_KEY",
    "PINECONE_INDEX_NAME",
    "PINECONE_INDEX_HOST",
    "duplicate_stale_physical_ids",
    "tombstone_precedence_delete",
    "live_stale_item_repair_upsert",
    "retry_dead_letter_behavior",
    "shared_ns2_isolation",
    "legacy_vectors_not_touched",
    "throwaway vector id prefix",
    "--execute",
    "--allow-throwaway-mutation",
    "--test-namespace",
    "--throwaway-prefix",
    "--confirm-throwaway-prefix",
    "--shared-ns2-readonly",
    "NOT_RUN",
]

FORBIDDEN_BROAD_MUTATION_TERMS = [
    "delete_all",
    "deleteAll",
    "delete_all=True",
    "deleteAll=True",
    "namespace=\"ns2\" # mutation",
    "ids=None",
]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("pinecone_repair_validation_readiness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_memory_pinecone_validation_readiness_runner_exists_and_is_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "pinecone_repair_validation_readiness.py"

    assert script_path.exists(), "missing safe Pinecone validation readiness runner"
    script = script_path.read_text()

    for required in REQUIRED_STATIC_TERMS:
        assert required in script
    for forbidden in FORBIDDEN_BROAD_MUTATION_TERMS:
        assert forbidden not in script

    module = _load_module(script_path)
    config = module.PineconeRepairValidationConfig(
        execute=False,
        allow_throwaway_mutation=False,
        api_key="",
        index_name="",
        index_host="",
        test_namespace="",
        throwaway_prefix="",
        confirm_throwaway_prefix="",
        shared_ns2_readonly=False,
    )
    artifact = module.build_readiness_artifact(config)

    assert artifact["status"] == "NOT_RUN"
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["namespace"] == ""
    assert artifact["pass_fail_criteria"]["duplicate_stale_physical_ids"]
    assert artifact["pass_fail_criteria"]["shared_ns2_isolation"]
    assert artifact["non_claims"]


def test_memory_pinecone_validation_execute_requires_namespace_prefix_and_confirmation():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "pinecone_repair_validation_readiness.py")

    missing = module.PineconeRepairValidationConfig(
        execute=True,
        allow_throwaway_mutation=False,
        api_key="key",
        index_name="idx",
        index_host="host",
        test_namespace="",
        throwaway_prefix="",
        confirm_throwaway_prefix="",
        shared_ns2_readonly=False,
    )
    prerequisites = module.evaluate_prerequisites(missing)
    assert "--allow-throwaway-mutation is required for execute mode" in prerequisites
    assert "--test-namespace is required for execute mode" in prerequisites
    assert "--throwaway-prefix is required for execute mode" in prerequisites

    ns2_mutation = module.PineconeRepairValidationConfig(
        execute=True,
        allow_throwaway_mutation=True,
        api_key="key",
        index_name="idx",
        index_host="host",
        test_namespace="ns2",
        throwaway_prefix="memory-proof-test-",
        confirm_throwaway_prefix="memory-proof-test-",
        shared_ns2_readonly=False,
    )
    assert "execute mode cannot mutate shared production namespace ns2" in module.evaluate_prerequisites(ns2_mutation)

    ready = module.PineconeRepairValidationConfig(
        execute=True,
        allow_throwaway_mutation=True,
        api_key="key",
        index_name="idx",
        index_host="host",
        test_namespace="memory-proof-ns",
        throwaway_prefix="memory-proof-test-",
        confirm_throwaway_prefix="memory-proof-test-",
        shared_ns2_readonly=True,
    )
    assert module.evaluate_prerequisites(ready) == []
    artifact = module.build_readiness_artifact(ready)
    assert artifact["mutation_allowed"] is True
    assert artifact["read_only"] is False
    assert artifact["namespace"] == "memory-proof-ns"
    assert artifact["shared_ns2_mode"] == "read_only_inventory_only"


def test_memory_pinecone_validation_docs_reference_commands_and_non_claims():
    root = Path(__file__).resolve().parents[2].parent
    doc = (root / "docs" / "epics" / "memory_firestore_iam_deployment.md").read_text()

    assert "python3 backend/scripts/pinecone_repair_validation_readiness.py" in doc
    assert "--allow-throwaway-mutation" in doc
    assert "--test-namespace" in doc
    assert "--throwaway-prefix" in doc
    assert "duplicate stale physical IDs" in doc
    assert "tombstone precedence" in doc
    assert "retry/dead-letter" in doc
    assert "shared `ns2` isolation" in doc
    assert "not production approval" in doc

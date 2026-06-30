import importlib.util
import sys
from pathlib import Path

from config.memory_rollout import PASSED, MemoryRolloutMode, MemoryRolloutStageGate
from utils.memory.default_read_rollout import (
    DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
    MemoryReadDecision,
    normalize_archive_read_rollout_decision,
    normalize_default_read_rollout_decision,
)

CANONICAL_CONSUMERS = {"mcp", "developer_api", "omi_chat"}
FORBIDDEN_LEGACY_ALIASES = {
    "mcp_default_memory_grant",
    "developer_default_memory_grant",
    "developer_api_default_memory_grant",
    "chat_default_memory_grant",
    "omi_chat_default_memory_grant",
}


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("rollout_schema_readiness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _valid_schema_v1_rollout_doc(uid="u1"):
    return {
        "uid": uid,
        "schema_version": DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
        "mode": MemoryRolloutMode.read.value,
        "mode_epoch": 7,
        "cutover_epoch": 7,
        "account_generation": 3,
        "fallback_projection_ready": True,
        "persistent_memory_writes_started": True,
        "writes_blocked": False,
        "stage_gates": {
            MemoryRolloutStageGate.shadow.value: PASSED,
            MemoryRolloutStageGate.write.value: PASSED,
            MemoryRolloutStageGate.read.value: PASSED,
        },
        "grants": {
            "mcp": {"default_memory": True},
            "developer_api": {"default_memory": True},
            "omi_chat": {"default_memory": True, "archive": True},
        },
        "vector_projection_commit_id": "projection-commit-1",
        "vector_repair_outbox_enabled": True,
    }


def test_rollout_schema_readiness_runner_exists_and_is_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "rollout_schema_readiness.py"

    assert script_path.exists(), "missing safe rollout schema_version=1 readiness runner"
    script = script_path.read_text()
    for term in [
        "schema_version",
        "DEFAULT_READ_ROLLOUT_SCHEMA_VERSION",
        "grants.mcp.default_memory",
        "grants.developer_api.default_memory",
        "grants.omi_chat.default_memory",
        "rejected_legacy_shapes",
    ]:
        assert term in script
    for forbidden in [".set(", ".update(", ".delete(", ".add(", "batch.commit", "gcloud ", "firebase deploy"]:
        assert forbidden not in script

    module = _load_module(script_path)
    artifact = module.build_readiness_artifact(module.RolloutSchemaReadinessConfig(execute=False))

    assert artifact["status"] == "NOT_RUN"
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["network_or_provider_calls_executed"] is False
    assert artifact["canonical_schema_version"] == DEFAULT_READ_ROLLOUT_SCHEMA_VERSION
    assert set(artifact["canonical_consumers"]) == CANONICAL_CONSUMERS
    assert artifact["canonical_shape"]["required"] == ["uid", "schema_version", "grants"]
    assert all(shape["expected_decision"] == "USE_MEMORY" for shape in artifact["valid_examples"])
    assert {shape["reason"] for shape in artifact["rejected_legacy_shapes"]} >= {
        "unsupported_rollout_schema",
        "uid_mismatch",
        "missing_mcp_default_memory_grant",
        "missing_developer_default_memory_grant",
        "missing_chat_default_memory_grant",
    }


def test_rollout_schema_readiness_examples_parse_with_shared_rollout_normalizer():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "rollout_schema_readiness.py")
    artifact = module.build_readiness_artifact(module.RolloutSchemaReadinessConfig(execute=False))

    for example in artifact["valid_examples"]:
        decision = normalize_default_read_rollout_decision(
            uid=example["uid"],
            source_path=f"users/{example['uid']}/memory_control/state",
            consumer=example["consumer"],
            data=example["document"],
        )
        assert decision.read_decision == MemoryReadDecision.USE_MEMORY
        assert decision.app_has_default_memory_grant is True
        assert decision.archive_capability is False
        assert decision.vector_projection_commit_id == "projection-commit-1"

    chat_archive_example = next(example for example in artifact["valid_examples"] if example["consumer"] == "omi_chat")
    archive_decision = normalize_archive_read_rollout_decision(
        uid=chat_archive_example["uid"],
        source_path=f"users/{chat_archive_example['uid']}/memory_control/state",
        consumer="omi_chat",
        data=chat_archive_example["document"],
    )
    assert archive_decision.read_decision == MemoryReadDecision.USE_MEMORY
    assert archive_decision.archive_capability is True


def test_rollout_schema_readiness_rejected_legacy_shapes_fail_closed():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "rollout_schema_readiness.py")
    artifact = module.build_readiness_artifact(module.RolloutSchemaReadinessConfig(execute=False))

    for shape in artifact["rejected_legacy_shapes"]:
        decision = normalize_default_read_rollout_decision(
            uid=shape["uid"],
            source_path=f"users/{shape['uid']}/memory_control/state",
            consumer=shape["consumer"],
            data=shape["document"],
        )
        assert decision.read_decision == MemoryReadDecision.DENY_MEMORY
        assert decision.fallback_reason == shape["reason"]


def test_rollout_schema_docs_use_canonical_v1_shape_and_label_legacy_aliases_as_rejected():
    root = Path(__file__).resolve().parents[2].parent
    rollout_doc = root / "docs" / "epics" / "memory_rollout_schema_migration.md"
    assert rollout_doc.exists(), "missing rollout schema migration/compatibility note"
    text = rollout_doc.read_text()

    for required in [
        "schema_version: 1",
        "uid:",
        "grants.mcp.default_memory",
        "grants.developer_api.default_memory",
        "grants.omi_chat.default_memory",
        "grants.omi_chat.archive",
        "Rejected legacy shapes",
        "unsupported_rollout_schema",
        "uid_mismatch",
    ]:
        assert required in text

    canonical_section = text.split("## Rejected legacy shapes", 1)[0]
    for legacy_alias in FORBIDDEN_LEGACY_ALIASES:
        assert legacy_alias not in canonical_section

    evidence_markers = (root / "docs" / "operational" / "memory_readiness_evidence_markers.md").read_text()
    assert "rollout_schema_readiness.py" in evidence_markers
    assert "schema_version=1" in evidence_markers
    assert "canonical nested `grants.<consumer>.default_memory`" in evidence_markers
    assert "production_rollout_approved=false" in evidence_markers

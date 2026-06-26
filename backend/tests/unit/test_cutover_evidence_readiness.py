import importlib.util
import sys
from pathlib import Path

REQUIRED_GATE_KEYS = {
    "milestone_oracle_final_approval",
    "real_pinecone_validation",
    "real_firestore_cloud_iam_rules_validation",
    "recall_precision_latency_no_silent_data_loss_benchmarks",
    "production_metrics_aggregation_central_telemetry",
    "t20_repair_projection_consistency",
    "t21_v3_compatibility_cursor_pagination",
    "t22_t23_external_writes_and_caller_coverage",
    "production_cutover_approval",
}

REQUIRED_SCRIPT_TERMS = [
    "BLOCKED",
    "NOT_RUN",
    "production_rollout_approved",
    "final approval",
    "real Pinecone validation",
    "Firestore/cloud IAM",
    "recall/precision/latency/no-silent-data-loss",
    "central telemetry",
    "T20 repair/projection-consistency",
    "T21 /v3 compatibility and cursor pagination",
    "T22/T23 external writes and caller coverage",
    "production cutover approval",
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
    spec = importlib.util.spec_from_file_location("cutover_evidence_readiness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _default_artifact():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "cutover_evidence_readiness.py")
    return module.build_readiness_artifact(module.CutoverEvidenceReadinessConfig(execute=False))


def test_cutover_evidence_runner_exists_and_defaults_blocked_without_approval():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "cutover_evidence_readiness.py"

    assert script_path.exists(), "missing safe memory cutover evidence readiness/checklist runner"
    script = script_path.read_text()
    for term in REQUIRED_SCRIPT_TERMS:
        assert term in script
    for term in FORBIDDEN_MUTATION_TERMS:
        assert term not in script

    artifact = _default_artifact()
    assert artifact["status"] == "BLOCKED"
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["network_or_provider_calls_executed"] is False
    assert artifact["benchmark_evidence_collected"] is False
    assert artifact["production_rollout_approved"] is False
    assert artifact["approval_claimed"] is False
    assert set(artifact["gates"]) == REQUIRED_GATE_KEYS


def test_cutover_evidence_gates_are_blocked_or_not_run_with_required_proof_artifacts():
    artifact = _default_artifact()

    for gate_key, gate in artifact["gates"].items():
        assert gate_key in REQUIRED_GATE_KEYS
        assert gate["status"] in {"BLOCKED", "NOT_RUN"}
        assert gate["evidence"] == []
        assert gate["approval_claimed"] is False
        assert gate["required_proof_commands_or_artifacts"]
        assert gate["blockers"]

    assert artifact["gates"]["production_cutover_approval"]["status"] == "BLOCKED"
    assert "BLOCK production rollout" in " ".join(artifact["non_claims"])


def test_cutover_evidence_execute_does_not_change_state_or_run_network_calls():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "cutover_evidence_readiness.py")

    artifact = module.build_readiness_artifact(module.CutoverEvidenceReadinessConfig(execute=True))

    assert artifact["status"] == "BLOCKED"
    assert artifact["read_only"] is True
    assert artifact["mutation_allowed"] is False
    assert artifact["network_or_provider_calls_executed"] is False
    assert artifact["production_rollout_approved"] is False
    assert all(gate["evidence"] == [] for gate in artifact["gates"].values())
    assert "no network/provider/cloud calls are executed" in " ".join(artifact["non_claims"])


def test_cutover_evidence_docs_and_ticket_reference_runner_and_non_claims():
    root = Path(__file__).resolve().parents[2].parent
    evidence_markers = (root / "docs" / "operational" / "memory_readiness_evidence_markers.md").read_text()

    assert "cutover_evidence_readiness.py" in evidence_markers
    assert "Oracle P0-8" in evidence_markers
    assert "production_rollout_approved=false" in evidence_markers
    assert "T20 repair/projection-consistency" in evidence_markers
    assert "T21 `/v3` compatibility and cursor pagination" in evidence_markers
    assert "T22/T23 external writes and caller coverage" in evidence_markers

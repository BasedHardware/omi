import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_script():
    path = ROOT / "scripts" / "v3_f5_real_service_evidence_readiness.py"
    spec = importlib.util.spec_from_file_location("v3_f5_real_service_evidence_readiness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_utils():
    from testing.memory import v3_f5_evidence

    return v3_f5_evidence


class RecordingFactory:
    def __init__(self, client=None):
        self.calls = 0
        self.client = client

    def __call__(self):
        self.calls += 1
        return self.client


def _approved_config(module, **overrides):
    kwargs = dict(
        execute=True,
        environment="shared-nonprod",
        project_id="omi-memory-evidence-nonprod",
        project_number="123456789012",
        expected_principal="serviceAccount:memory-v3-f5-evidence@omi-memory-evidence-nonprod.iam.gserviceaccount.com",
        approval_subject="memory-V3-F5 real-service read-only evidence shared-nonprod 2026-06-20",
        approval_artifact_path="docs/approvals/memory-v3-f5-shared-nonprod-oracle-review.md",
        approved_paths=(
            "control/config metadata",
            "cursor secret metadata",
            "projection state metadata",
            "canary approval metadata",
            "iam policy",
            "firestore index state",
            "audit read log metadata",
        ),
        oracle_review_artifact="docs/operational/memory_readiness_evidence_markers.md#f4-before-f5-real-service-evidence-2026-06-20",
    )
    kwargs.update(overrides)
    return module.EvidenceRunConfig(**kwargs)


def test_cli_default_is_not_run_and_constructs_no_client():
    module = _load_script()
    result = module.main([], client_factory=RecordingFactory())
    assert result["status"] == "NOT_RUN"
    assert result["summary"]["cloud_client_constructed"] is False
    assert result["runtime_readiness"] == {"status": "BLOCKED", "decision": "NO_GO"}
    assert result["external_readiness"] == {"status": "BLOCKED", "decision": "NO_GO"}
    assert result["aggregate_readiness"] == {"status": "BLOCKED", "decision": "NO_GO"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("environment", "prod"),
        ("project_id", "other-project"),
        ("project_number", "999"),
        ("expected_principal", "serviceAccount:wrong@example.iam.gserviceaccount.com"),
        ("approval_subject", "wrong subject"),
        ("approval_artifact_path", "docs/approvals/missing.md"),
        ("approved_paths", ("control/config metadata",)),
        ("oracle_review_artifact", ""),
    ],
)
def test_execute_blocks_on_any_exact_gate_mismatch_without_constructing_client(field, value):
    utils = _load_utils()
    factory = RecordingFactory()
    report = utils.build_evidence_report(_approved_config(utils, **{field: value}), client_factory=factory)
    assert report["status"] == "BLOCKED"
    assert factory.calls == 0
    assert report["summary"]["cloud_client_constructed"] is False
    assert field in report["gate_failures"]


def test_identity_iam_contract_rejects_broad_roles_and_write_permissions():
    utils = _load_utils()
    client = utils.FakeEvidenceClient(
        principal="serviceAccount:memory-v3-f5-evidence@omi-memory-evidence-nonprod.iam.gserviceaccount.com",
        permissions=utils.REQUIRED_READ_PERMISSIONS | {"datastore.entities.create"},
        roles={"roles/viewer", "roles/editor"},
    )
    report = utils.build_evidence_report(_approved_config(utils), client_factory=RecordingFactory(client))
    assert report["status"] == "BLOCKED"
    assert report["identity_iam"]["status"] == "BLOCKED"
    assert report["identity_iam"]["owner_editor_present"] is True
    assert report["identity_iam"]["write_permission_intersection"] == ["datastore.entities.create"]


def test_fake_execute_uses_only_bounded_metadata_reads_and_no_route_or_app_imports():
    utils = _load_utils()
    client = utils.FakeEvidenceClient(
        principal="serviceAccount:memory-v3-f5-evidence@omi-memory-evidence-nonprod.iam.gserviceaccount.com",
        permissions=utils.REQUIRED_READ_PERMISSIONS,
        roles={"roles/omi.MemoryEvidenceReader"},
    )
    report = utils.build_evidence_report(_approved_config(utils), client_factory=RecordingFactory(client))
    assert report["status"] == "INCONCLUSIVE"
    assert report["summary"]["cloud_client_constructed"] is True
    assert client.calls == [
        "effective_principal",
        "iam_policy",
        "control_config_metadata",
        "cursor_secret_metadata",
        "projection_state_metadata",
        "canary_approval_metadata",
        "index_state",
        "audit_log_metadata",
    ]
    assert client.mutator_attempts == []
    assert report["scope"]["raw_memory_content_read"] is False
    assert report["scope"]["route_calls"] == []
    assert report["scope"]["production_app_imported"] is False
    assert report["cursor_secret_metadata"]["payload_bytes_read"] is False


def test_missing_audit_zero_write_proof_is_inconclusive_not_pass():
    utils = _load_utils()
    client = utils.FakeEvidenceClient(
        principal="serviceAccount:memory-v3-f5-evidence@omi-memory-evidence-nonprod.iam.gserviceaccount.com",
        permissions=utils.REQUIRED_READ_PERMISSIONS,
        roles={"roles/omi.MemoryEvidenceReader"},
        audit_zero_write_methods=None,
    )
    report = utils.build_evidence_report(_approved_config(utils), client_factory=RecordingFactory(client))
    assert report["zero_write_proof"]["status"] == "INCONCLUSIVE"
    assert report["status"] == "INCONCLUSIVE"


def test_deadline_timeout_or_partial_failure_blocks_without_fallback():
    utils = _load_utils()
    client = utils.FakeEvidenceClient(
        principal="serviceAccount:memory-v3-f5-evidence@omi-memory-evidence-nonprod.iam.gserviceaccount.com",
        permissions=utils.REQUIRED_READ_PERMISSIONS,
        roles={"roles/omi.MemoryEvidenceReader"},
        fail_call="projection_state_metadata",
    )
    report = utils.build_evidence_report(_approved_config(utils), client_factory=RecordingFactory(client))
    assert report["status"] == "BLOCKED"
    assert report["deadlines"]["fallback_attempted"] is False
    assert report["deadlines"]["bounded_retries"] == {"max_attempts": 2, "backoff_seconds": [0.05]}
    assert report["deadlines"]["overall_deadline_seconds"] == 30


def test_index_and_schema_validation_blocks_missing_required_index():
    utils = _load_utils()
    client = utils.FakeEvidenceClient(
        principal="serviceAccount:memory-v3-f5-evidence@omi-memory-evidence-nonprod.iam.gserviceaccount.com",
        permissions=utils.REQUIRED_READ_PERMISSIONS,
        roles={"roles/omi.MemoryEvidenceReader"},
        indexes=[],
    )
    report = utils.build_evidence_report(_approved_config(utils), client_factory=RecordingFactory(client))
    assert report["indexes_schema"]["status"] == "BLOCKED"
    assert "memory_items_by_uid_generation_updated_at" in report["indexes_schema"]["missing_indexes"]


def test_redaction_fail_closed_allowlist_and_sensitive_sentinel_removal():
    utils = _load_utils()
    client = utils.FakeEvidenceClient(
        principal="serviceAccount:memory-v3-f5-evidence@omi-memory-evidence-nonprod.iam.gserviceaccount.com",
        permissions=utils.REQUIRED_READ_PERMISSIONS,
        roles={"roles/omi.MemoryEvidenceReader"},
        inject_sensitive=True,
    )
    report = utils.build_evidence_report(_approved_config(utils), client_factory=RecordingFactory(client))
    rendered = utils.render_redacted_json(report)
    for sentinel in [
        "omi-memory-evidence-nonprod",
        "memory-v3-f5-evidence@",
        "secret-name",
        "secret-value",
        "cursor-token",
        "Authorization",
        "https://",
        "raw memory content",
    ]:
        assert sentinel not in rendered
    with pytest.raises(ValueError, match="not explicitly allowlisted"):
        utils.render_redacted_json({"unexpected": "field"})


def test_static_mutation_guard_and_runtime_readonly_wrapper_raise_before_rpc(tmp_path):
    utils = _load_utils()
    bad = tmp_path / "bad.py"
    bad.write_text("client.collection('x').document('y').set({'a': 1})\n", encoding="utf-8")
    assert utils.static_mutation_guard([bad])["status"] == "BLOCKED"
    client = utils.FakeEvidenceClient(
        principal="serviceAccount:memory-v3-f5-evidence@omi-memory-evidence-nonprod.iam.gserviceaccount.com",
        permissions=utils.REQUIRED_READ_PERMISSIONS,
    )
    wrapped = utils.ReadOnlyEvidenceClient(client)
    with pytest.raises(RuntimeError, match="mutator blocked before RPC"):
        wrapped.set({"a": 1})
    assert client.mutator_attempts == ["set"]


def test_f4_risk_confirmations_are_required_before_any_real_read():
    utils = _load_utils()
    client = utils.FakeEvidenceClient(
        principal="serviceAccount:memory-v3-f5-evidence@omi-memory-evidence-nonprod.iam.gserviceaccount.com",
        permissions=utils.REQUIRED_READ_PERMISSIONS,
        roles={"roles/omi.MemoryEvidenceReader"},
        structural_disable=False,
    )
    report = utils.build_evidence_report(_approved_config(utils), client_factory=RecordingFactory(client))
    assert report["status"] == "BLOCKED"
    assert report["f4_risk_confirmations"]["structural_disable_repository_assertion"] is False
    assert report["f4_risk_confirmations"]["pagination_branch_order_proof"] is True
    assert report["f4_risk_confirmations"]["read_only_f4_to_f3_call_graph_proof"] is True


def test_docs_test_runner_and_parent_readiness_link_f5_preparation():
    root = ROOT.parent
    test_sh = (ROOT / "test.sh").read_text(encoding="utf-8")
    selected_tests = subprocess.check_output(
        [sys.executable, str(ROOT / "scripts" / "select_backend_unit_tests.py"), "--all"],
        text=True,
        cwd=ROOT,
    ).splitlines()
    assert "scripts/select_backend_unit_tests.py --all" in test_sh
    assert "tests/unit/test_v3_f5_real_service_evidence_readiness.py" in selected_tests
    f5_script = (ROOT / "scripts" / "v3_f5_real_service_evidence_readiness.py").read_text(encoding="utf-8")
    f5_utils = (ROOT / "testing" / "memory" / "v3_f5_evidence.py").read_text(encoding="utf-8")
    assert "memory-V3-F5 real-service read-only evidence preparation" in f5_script
    assert "build_evidence_report" in f5_utils
    assert "default-NOT_RUN" in f5_script
    evidence_markers = (root / "docs" / "operational" / "memory_readiness_evidence_markers.md").read_text(
        encoding="utf-8"
    )
    assert "memory-V3-F5 real-service read-only evidence preparation" in evidence_markers

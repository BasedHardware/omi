from __future__ import annotations

import ast
import copy
import importlib
import socket
from pathlib import Path
from typing import Any

from utils.memory.v3_f6.aggregate import F6_LOCAL_GATE_IDS, build_pre_gcp_aggregate_report
from utils.memory.v3_f6.fingerprints import fingerprint
from utils.memory.v3_f6.redaction import render_redacted_evidence_json

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _import_names(module: Path) -> set[str]:
    tree = ast.parse(module.read_text(), filename=str(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or ""))
    return names


def _all_passed_local_proofs() -> dict[str, dict[str, Any]]:
    return {gate_id: {"status": "PASS", "evidence": f"{gate_id} proof"} for gate_id in F6_LOCAL_GATE_IDS}


def test_canonical_config_run_record_redaction_and_fingerprint_exports_are_old_new_identity():
    old_config = importlib.import_module("utils.memory.v3_gcp_evidence_config")
    new_config = importlib.import_module("utils.memory.v3_f6.config")
    for name in (
        "AuditSettings",
        "EvidenceLimits",
        "EvidenceTarget",
        "EvidenceTargetRegistry",
        "ValidationError",
    ):
        assert getattr(new_config, name) is getattr(old_config, name)

    old_run_record = importlib.import_module("utils.memory.v3_gcp_evidence_run_record")
    new_run_record = importlib.import_module("utils.memory.v3_f6.run_record")
    for name in (
        "ExecutionWindow",
        "RunRecordValidationError",
        "ValidatedRunRecord",
        "validate_run_record",
        "RUN_RECORD_FIELDS",
    ):
        assert getattr(new_run_record, name) is getattr(old_run_record, name)

    old_redaction = importlib.import_module("utils.memory.v3_gcp_evidence_redaction")
    new_redaction = importlib.import_module("utils.memory.v3_f6.redaction")
    new_fingerprint = importlib.import_module("utils.memory.v3_f6.fingerprints")
    for name in (
        "RedactionContractError",
        "render_redacted_evidence_json",
        "validate_redacted_evidence",
        "TOP_LEVEL_FIELDS",
        "FINGERPRINT_RE",
    ):
        assert getattr(new_redaction, name) is getattr(old_redaction, name)
    assert new_fingerprint.fingerprint is old_redaction.fingerprint


def test_f6_fingerprint_known_vector_is_stable_characterization():
    assert fingerprint("known-vector-input", key_id="project") == "hmac:project:6aa41691c2dc485103d0652f24c303ff"
    assert (
        fingerprint(
            "serviceAccount:PLACEHOLDER-v17-evidence@PLACEHOLDER-dev-project-id.iam.gserviceaccount.com",
            key_id="principal",
        )
        == "hmac:principal:d4b425000d609f503e45e2ca7ba09507"
    )


def test_redacted_evidence_json_rendering_is_byte_for_byte_stable():
    report = {
        "artifact_version": "V17-V3-F6F",
        "status": "PASS",
        "target": "dev",
        "project_fingerprint": "hmac:project:60957b7e8c7186dae0dabea5c9989e2a",
        "principal_fingerprint": "hmac:principal:d4b425000d609f503e45e2ca7ba09507",
        "run_fingerprint": "hmac:run:fec078406f7de8652eb25bfdc43f6e86",
        "approved_metadata_paths": ["control/config metadata", "iam policy"],
        "read_bounds": {"max_documents_per_path": 25, "max_paths": 7, "allow_collection_scans": False},
        "index_expectations": {"memory_items_by_uid_generation_updated_at": {"state": "READY"}},
        "audit": {"enabled": True, "zero_write_methods": True},
        "observations": [{"name": "schema", "status": "PASS", "metadata": {"checked": True}}],
        "non_claims": ["no raw memory content included"],
    }

    assert (
        render_redacted_evidence_json(report)
        == '''{
  "approved_metadata_paths": [
    "control/config metadata",
    "iam policy"
  ],
  "artifact_version": "V17-V3-F6F",
  "audit": {
    "enabled": true,
    "zero_write_methods": true
  },
  "index_expectations": {
    "memory_items_by_uid_generation_updated_at": {
      "state": "READY"
    }
  },
  "non_claims": [
    "no raw memory content included"
  ],
  "observations": [
    {
      "metadata": {
        "checked": true
      },
      "name": "schema",
      "status": "PASS"
    }
  ],
  "principal_fingerprint": "hmac:principal:d4b425000d609f503e45e2ca7ba09507",
  "project_fingerprint": "hmac:project:60957b7e8c7186dae0dabea5c9989e2a",
  "read_bounds": {
    "allow_collection_scans": false,
    "max_documents_per_path": 25,
    "max_paths": 7
  },
  "run_fingerprint": "hmac:run:fec078406f7de8652eb25bfdc43f6e86",
  "status": "PASS",
  "target": "dev"
}'''
    )


def test_pre_gcp_aggregate_report_does_not_mutate_local_proofs_input():
    local_proofs = _all_passed_local_proofs()
    local_proofs["f6f_redaction_output_contract"]["nested"] = {"items": ["preserve"]}
    before = copy.deepcopy(local_proofs)

    report = build_pre_gcp_aggregate_report(local_proofs=local_proofs)

    assert report["status"] == "PRE_GCP_READY"
    assert local_proofs == before


def test_canonical_config_run_record_redaction_and_fingerprint_import_without_network_or_provider_side_effects(
    monkeypatch,
):
    def fail_socket(*args, **kwargs):
        raise AssertionError("network/socket use is forbidden during F6 characterization imports")

    monkeypatch.setattr(socket, "create_connection", fail_socket)
    monkeypatch.setattr(socket.socket, "connect", fail_socket)

    for module_name in (
        "utils.memory.v3_f6.config",
        "utils.memory.v3_f6.run_record",
        "utils.memory.v3_f6.redaction",
        "utils.memory.v3_f6.fingerprints",
        "utils.memory.v3_f6.aggregate",
        "utils.memory.v3_f6.pre_gcp_aggregate",
    ):
        importlib.import_module(module_name)


def test_canonical_config_run_record_redaction_fingerprint_and_aggregate_static_import_boundaries():
    modules = [
        BACKEND_DIR / "utils/memory/v3_f6/config.py",
        BACKEND_DIR / "utils/memory/v3_f6/run_record.py",
        BACKEND_DIR / "utils/memory/v3_f6/redaction.py",
        BACKEND_DIR / "utils/memory/v3_f6/fingerprints.py",
        BACKEND_DIR / "utils/memory/v3_f6/aggregate.py",
        BACKEND_DIR / "utils/memory/v3_gcp_evidence_config.py",
        BACKEND_DIR / "utils/memory/v3_gcp_evidence_run_record.py",
        BACKEND_DIR / "utils/memory/v3_gcp_evidence_redaction.py",
    ]
    forbidden_roots = {
        "aiohttp",
        "anthropic",
        "firebase_admin",
        "google",
        "grpc",
        "httpx",
        "openai",
        "pinecone",
        "requests",
        "socket",
        "urllib",
    }
    offenders: list[str] = []
    for module_path in modules:
        for imported in _import_names(module_path):
            root = imported.lstrip(".").split(".", 1)[0]
            if root in forbidden_roots:
                offenders.append(f"{module_path.relative_to(BACKEND_DIR)} imports {imported}")

    assert offenders == []


def test_local_smoke_supplies_explicit_deterministic_run_record_clock(monkeypatch):
    from utils.memory.v3_f6 import local_smoke
    from utils.memory.v3_f6 import local_smoke as canonical_local_smoke

    observed: dict[str, object] = {}
    real_validate = local_smoke.validate_run_record

    def spy_validate_run_record(raw, registry, *, now=None):
        observed["now"] = now
        return real_validate(raw, registry, now=now)

    monkeypatch.setattr(canonical_local_smoke, "validate_run_record", spy_validate_run_record)

    report = local_smoke.build_report_from_current_local_contracts()

    assert report["status"] == "PRE_GCP_READY"
    assert observed["now"] == local_smoke._LOCAL_SMOKE_NOW

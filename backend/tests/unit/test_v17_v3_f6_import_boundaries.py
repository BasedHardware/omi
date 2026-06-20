from __future__ import annotations

import ast
import importlib
import json
import runpy
import socket
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _import_names(module: Path) -> set[str]:
    tree = ast.parse(module.read_text(), filename=str(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            names.add(base)
    return names


def test_old_f6_facade_exports_are_identical_to_canonical_exports():
    old_contracts = importlib.import_module("utils.memory.v17_v3_f6_readonly_contracts")
    canonical_contracts = importlib.import_module("utils.memory.v17_v3_f6.readonly_contracts")
    canonical_run_context = importlib.import_module("utils.memory.v17_v3_f6.run_context")

    for name in (
        "IdentityIamTarget",
        "RunRecord",
        "FakeIdentityIamSource",
        "EvidenceClientConfig",
        "ReadEvidenceRequest",
        "FakeReadEvidenceTransport",
        "ReadOnlyEvidenceClient",
        "AuditLogEvent",
        "AuditQuery",
        "FakeAuditLogClient",
        "verify_identity_iam",
        "assess_audit_correlation",
    ):
        assert getattr(old_contracts, name) is getattr(canonical_contracts, name)

    assert old_contracts.RunRecord is canonical_run_context.RunRecord


def test_old_pre_gcp_aggregate_facade_exports_are_identical_to_canonical_exports():
    old_aggregate = importlib.import_module("utils.memory.v17_v3_f6_pre_gcp_aggregate")
    canonical_aggregate = importlib.import_module("utils.memory.v17_v3_f6.pre_gcp_aggregate")

    for name in (
        "F6_LOCAL_GATE_IDS",
        "GCP_ACCESS_GATE_IDS",
        "NON_CLAIMS",
        "build_pre_gcp_aggregate_report",
        "build_report_from_current_local_contracts",
    ):
        assert getattr(old_aggregate, name) is getattr(canonical_aggregate, name)


def test_canonical_aggregate_module_does_not_import_local_smoke_doubles_config_or_redaction():
    aggregate_path = BACKEND_DIR / "utils/memory/v17_v3_f6/aggregate.py"
    imported = _import_names(aggregate_path)

    forbidden_substrings = (
        "gcp_evidence_config",
        "gcp_evidence_redaction",
        "local_doubles",
        "smoke",
        "Fake",
    )
    offenders = sorted(name for name in imported if any(token in name for token in forbidden_substrings))
    assert offenders == []


def test_core_contract_modules_do_not_import_provider_sdks_network_or_local_doubles():
    core_modules = [
        BACKEND_DIR / "utils/memory/v17_v3_f6/identity_iam.py",
        BACKEND_DIR / "utils/memory/v17_v3_f6/read_evidence.py",
        BACKEND_DIR / "utils/memory/v17_v3_f6/audit.py",
        BACKEND_DIR / "utils/memory/v17_v3_f6/run_context.py",
        BACKEND_DIR / "utils/memory/v17_v3_gcp_evidence_run_record.py",
    ]
    forbidden_roots = {
        "google",
        "firebase_admin",
        "requests",
        "httpx",
        "urllib",
        "grpc",
        "socket",
        "aiohttp",
        "pinecone",
        "openai",
        "anthropic",
    }
    forbidden_substrings = ("local_doubles", "testing.e2e.fakes")

    offenders: list[str] = []
    for module_path in core_modules:
        for imported in _import_names(module_path):
            root = imported.lstrip(".").split(".", 1)[0]
            if root in forbidden_roots or any(token in imported for token in forbidden_substrings):
                offenders.append(f"{module_path.relative_to(BACKEND_DIR)} imports {imported}")

    assert offenders == []


def test_pre_gcp_cli_emits_parseable_ready_json_when_socket_connections_fail(monkeypatch, capsys):
    def fail_socket(*args, **kwargs):
        raise AssertionError("network/socket use is forbidden in pre-GCP readiness CLI")

    monkeypatch.setattr(socket, "create_connection", fail_socket)
    monkeypatch.setattr(socket.socket, "connect", fail_socket)

    script_path = BACKEND_DIR / "scripts/v17_v3_f6_pre_gcp_aggregate_readiness.py"
    runpy.run_path(str(script_path), run_name="__main__")

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert captured.err == ""
    assert report["artifact_version"] == "V17-V3-F6H"
    assert report["status"] == "PRE_GCP_READY"
    assert report["decision"] == "BLOCKED_ON_GCP_ACCESS"
    assert report["remaining_blockers"] == ["gcp_access"]


@pytest.mark.parametrize(
    "module_name",
    [
        "utils.memory.v17_v3_f6.readonly_contracts",
        "utils.memory.v17_v3_f6.run_context",
        "utils.memory.v17_v3_f6.pre_gcp_aggregate",
    ],
)
def test_canonical_f6_modules_import_without_network_or_provider_side_effects(monkeypatch, module_name):
    def fail_socket(*args, **kwargs):
        raise AssertionError("network/socket use is forbidden during canonical F6 imports")

    monkeypatch.setattr(socket, "create_connection", fail_socket)
    monkeypatch.setattr(socket.socket, "connect", fail_socket)

    importlib.import_module(module_name)

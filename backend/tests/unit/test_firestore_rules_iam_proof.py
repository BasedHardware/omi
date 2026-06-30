import importlib.util
import sys
from pathlib import Path

REQUIRED_STATIC_TERMS = [
    "gcloud firestore databases describe",
    "gcloud projects get-iam-policy",
    "gcloud iam service-accounts get-iam-policy",
    "firebase firestore:rules:get",
    "users/{uid}/memory_outbox/{record_id}",
    "users/{uid}/memory_control/state",
    "users/{uid}/memory_control/app_key_memory_grants",
    "mcp_api_keys/{key_id}",
    "vector_repair_outbox_enabled",
    "client_denial.memory_outbox",
    "client_denial.app_key_memory_grants",
    "mcp_api_key_inventory",
    "worker_firestore_iam",
    "memory_control.server_owned",
    "app_key_grants.server_owned",
    "no_client_vector_repair_enablement",
    "no_broad_public_access",
    "NOT_RUN",
    "--execute",
]


FORBIDDEN_MUTATING_TERMS = [
    " firebase deploy",
    " gcloud firestore databases update",
    " gcloud firestore databases create",
    " gcloud firestore databases delete",
    " gcloud projects set-iam-policy",
    " gcloud iam service-accounts set-iam-policy",
    " add-iam-policy-binding",
    " remove-iam-policy-binding",
    " set-iam-policy",
    " deploy ",
]


def test_memory_firestore_rules_iam_proof_runner_exists_and_is_read_only():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "firestore_rules_iam_proof.py"

    assert script_path.exists(), "missing read-only Firestore IAM/deployed rules proof runner"
    script = script_path.read_text()

    for required in REQUIRED_STATIC_TERMS:
        assert required in script

    spec = importlib.util.spec_from_file_location("firestore_rules_iam_proof", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    config = module.FirestoreRulesIamProofConfig(
        project="proof-project",
        database="(default)",
        worker_sa="worker@proof-project.iam.gserviceaccount.com",
        backend_sa="backend@proof-project.iam.gserviceaccount.com",
    )
    commands = "\n".join(
        module.command_to_string(command) for command in module.build_read_only_commands(config).values()
    )
    for forbidden in FORBIDDEN_MUTATING_TERMS:
        assert forbidden not in commands


def test_memory_firestore_rules_iam_doc_references_proof_runner_and_pass_fail_gates():
    root = Path(__file__).resolve().parents[2].parent
    doc_path = root / "docs" / "epics" / "memory_firestore_iam_deployment.md"
    doc = doc_path.read_text()

    assert "python3 backend/scripts/firestore_rules_iam_proof.py" in doc
    assert "users/{uid}/memory_outbox/{record_id}" in doc
    assert "users/{uid}/memory_control/state" in doc
    assert "users/{uid}/memory_control/app_key_memory_grants" in doc
    assert "mcp_api_keys/{key_id}" in doc
    assert "vector_repair_outbox_enabled" in doc
    assert "client denial" in doc
    assert "MCP API-key" in doc
    assert "app/key memory grant" in doc
    assert "Admin worker service account" in doc
    assert "no client enablement of `vector_repair_outbox_enabled`" in doc
    assert "no broad public access" in doc
    assert "not production approval" in doc

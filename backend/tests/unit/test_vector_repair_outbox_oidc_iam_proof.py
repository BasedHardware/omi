from pathlib import Path


def test_v17_vector_repair_outbox_oidc_iam_proof_runner_exists_and_is_read_only():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "vector_repair_outbox_oidc_iam_proof.py"

    assert script_path.exists(), "missing read-only OIDC/IAM proof runner"
    script = script_path.read_text()

    required_targets = [
        "gcloud run services describe",
        "gcloud run services get-iam-policy",
        "gcloud scheduler jobs describe",
        "gcloud tasks queues describe",
        "gcloud projects get-iam-policy",
        "gcloud iam service-accounts get-iam-policy",
        "V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED",
        "roles/run.invoker",
        "roles/datastore.user",
        "roles/iam.serviceAccountTokenCreator",
        "oidcToken.serviceAccountEmail",
        "oidcToken.audience",
        "state == PAUSED",
        "NOT_RUN",
        "--execute",
    ]
    for target in required_targets:
        assert target in script

    forbidden_mutating_terms = [
        " add-iam-policy-binding",
        " set-iam-policy",
        " run deploy",
        " services update",
        " scheduler jobs create",
        " scheduler jobs update",
        " scheduler jobs resume",
        " tasks queues create",
        " tasks queues update",
        " firebase deploy",
        " gcloud firestore",
        " delete ",
    ]
    for forbidden in forbidden_mutating_terms:
        assert forbidden not in script


def test_v17_vector_repair_outbox_deployment_contract_references_oidc_iam_proof_runner():
    root = Path(__file__).resolve().parents[2].parent
    contract_path = root / "docs" / "epics" / "v17_vector_repair_outbox_cloud_deployment_contract.yaml"
    contract = contract_path.read_text()

    assert "python3 backend/scripts/vector_repair_outbox_oidc_iam_proof.py" in contract
    assert "read-only" in contract
    assert "--execute" in contract
    assert "production Firestore IAM/deployed rules validation gates remain open" in contract
    assert "real Pinecone duplicate stale physical ID delete/repair validation remains open" in contract

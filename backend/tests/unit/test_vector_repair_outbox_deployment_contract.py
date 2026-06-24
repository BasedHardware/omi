from pathlib import Path

REQUIRED_CONTRACT_TERMS = [
    "apiVersion: serving.knative.dev/v1",
    "kind: Service",
    "memory-vector-repair-outbox-worker",
    "uvicorn",
    "scripts.vector_repair_outbox_worker_entrypoint:app",
    "POST /memory-vector-repair-outbox-worker/tick",
    "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED",
    "value: \"false\"",
    "MEMORY_VECTOR_REPAIR_OUTBOX_UID",
    "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID",
    "PINECONE_API_KEY",
    "PINECONE_INDEX_NAME",
    "OPENAI_API_KEY",
    "VECTOR_REPAIR_PINECONE_NAMESPACE",
    "ns2",
    "Cloud Scheduler",
    "Cloud Tasks",
    "oidcToken",
    "audience",
    "serviceAccountEmail",
    "maxRetryDuration",
    "maxAttempts",
    "dead-letter",
    "roles/run.invoker",
    "roles/cloudtasks.enqueuer",
    "roles/iam.serviceAccountTokenCreator",
    "roles/datastore.user",
    "disabled-by-default",
    "not applied",
    "Cloud Run IAM (roles/run.invoker)",
    "no app-level bearer token",
]

FORBIDDEN_CLAIMS = [
    "production IAM validated",
    "deployed to production",
    "Pinecone deletion verified",
    "Cloud Scheduler created",
    "Cloud Tasks queue created",
]


def test_memory_vector_repair_outbox_cloud_deployment_contract_is_disabled_and_oidc_ready():
    root = Path(__file__).resolve().parents[2].parent
    contract_path = root / "docs" / "epics" / "memory_vector_repair_outbox_cloud_deployment_contract.yaml"

    assert contract_path.exists(), "missing checked-in Cloud Run/Tasks/Scheduler contract artifact"
    contract = contract_path.read_text()

    for required_term in REQUIRED_CONTRACT_TERMS:
        assert required_term in contract
    for forbidden_claim in FORBIDDEN_CLAIMS:
        assert forbidden_claim not in contract

    assert "run.googleapis.com/ingress: internal-and-cloud-load-balancing" in contract
    assert "run.googleapis.com/invoker-iam-disabled: \"false\"" in contract
    assert "state: PAUSED" in contract
    assert "schedule: \"*/15 * * * *\"" in contract
    assert "uri: https://REGION-PROJECT_ID.run.app/memory-vector-repair-outbox-worker/tick" in contract
    assert "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=true" in contract
    assert "Do not set the true value until all production gates pass" in contract
    assert "CLI one-tick entrypoint" not in contract
    assert "must exist before applying the Service/Tasks shape" not in contract

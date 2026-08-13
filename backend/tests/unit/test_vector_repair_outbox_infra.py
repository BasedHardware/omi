from datetime import datetime, timezone
from pathlib import Path
import json

from database.memory_vector_repair_outbox_telemetry import (
    VectorRepairOutboxTelemetryConfig,
    emit_vector_repair_outbox_worker_telemetry,
)
from database.memory_vector_repair_outbox_worker import (
    VectorRepairOutboxWorkerTickConfig,
    run_vector_repair_outbox_worker_tick,
)
from tests.unit.test_vector_repair_outbox_worker import _FakeFirestore, _live_item, _record

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend" / "scripts" / "vector_repair_outbox_emulator_test.py"
PACKAGE_JSON = ROOT / "package.json"

REQUIRED_CONTRACT_TERMS = [
    "apiVersion: serving.knative.dev/v1",
    "kind: Service",
    "memory-vector-repair-outbox-worker",
    "uvicorn",
    "scripts.vector_repair_outbox_worker_entrypoint:app",
    "POST /memory-vector-repair-outbox-worker/tick",
    "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED",
    'value: "false"',
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


def _summary(**overrides):
    data = {
        "enabled": True,
        "worker_id": "worker-a",
        "uid": "user-secret",
        "leased_count": 3,
        "processed_count": 1,
        "skipped_count": 1,
        "failed_count": 1,
        "ack_failed_count": 1,
        "actions": [
            {"record_id": "rec-delete", "idempotency_key": "idem-delete", "action": "delete"},
            {"record_id": "rec-repair", "idempotency_key": "idem-repair", "action": "repair"},
        ],
        "errors": [
            {"stage": "ack", "record_id": "rec-secret", "error": "Pinecone timeout for vector vec-secret"},
            {"stage": "process", "error": "deadline exceeded"},
        ],
    }
    data.update(overrides)
    return data


class TestTelemetry:
    def test_telemetry_emits_low_cardinality_metrics_and_events_without_identifiers(self):
        emitted = []

        result = emit_vector_repair_outbox_worker_telemetry(
            tick_summary=_summary(),
            backlog={"pending_count": 12, "dead_letter_count": 2, "oldest_pending_age_seconds": 901},
            duration_ms=1234,
            emitter=lambda payload: emitted.append(payload),
            config=VectorRepairOutboxTelemetryConfig(enabled=True),
        )

        assert result == {"enabled": True, "emitted_count": len(emitted), "failed_count": 0, "errors": []}
        metric_names = {payload["name"] for payload in emitted if payload["kind"] == "metric"}
        assert {
            "vector_repair_outbox_worker_records_total",
            "vector_repair_outbox_worker_action_total",
            "vector_repair_outbox_worker_retry_total",
            "vector_repair_outbox_worker_dead_letter_total",
            "vector_repair_outbox_worker_ack_failure_total",
            "vector_repair_outbox_worker_backlog_count",
            "vector_repair_outbox_worker_oldest_pending_age_seconds",
            "vector_repair_outbox_worker_duration_ms",
        }.issubset(metric_names)
        event_names = {payload["name"] for payload in emitted if payload["kind"] == "event"}
        assert {"vector_repair_outbox_worker_ack_failure", "vector_repair_outbox_worker_dead_letter"}.issubset(
            event_names
        )

        forbidden_values = {
            "user-secret",
            "worker-a",
            "rec-delete",
            "rec-repair",
            "rec-secret",
            "idem-delete",
            "vec-secret",
        }
        rendered = repr(emitted)
        for forbidden in forbidden_values:
            assert forbidden not in rendered
        for payload in emitted:
            assert set(payload["labels"]).issubset({"worker_component", "status", "action", "reason", "event_type"})

    def test_telemetry_disabled_is_noop_even_with_emitter(self):
        emitted = []

        result = emit_vector_repair_outbox_worker_telemetry(
            tick_summary=_summary(),
            emitter=lambda payload: emitted.append(payload),
            config=VectorRepairOutboxTelemetryConfig(enabled=False),
        )

        assert result == {"enabled": False, "emitted_count": 0, "failed_count": 0, "errors": []}
        assert emitted == []

    def test_telemetry_emitter_failures_are_recorded_without_raising(self):
        def failing_emitter(payload):
            raise RuntimeError(f"telemetry sink unavailable for {payload['name']}")

        result = emit_vector_repair_outbox_worker_telemetry(
            tick_summary=_summary(),
            emitter=failing_emitter,
            config=VectorRepairOutboxTelemetryConfig(enabled=True),
        )

        assert result["enabled"] is True
        assert result["emitted_count"] == 0
        assert result["failed_count"] > 0
        assert result["errors"][0] == {
            "stage": "telemetry",
            "name": "vector_repair_outbox_worker_records_total",
            "error": "telemetry sink unavailable for vector_repair_outbox_worker_records_total",
        }

    def test_worker_tick_telemetry_failure_does_not_mask_worker_cleanup_result(self):
        now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
        db = _FakeFirestore(
            {
                "users/u1/memory_outbox/repair": _record(
                    record_id="repair",
                    idempotency_key="repair-key",
                    outbox_path="users/u1/memory_outbox/repair",
                    available_at=now.isoformat(),
                )
            }
        )

        result = run_vector_repair_outbox_worker_tick(
            db_client=db,
            uid="u1",
            config=VectorRepairOutboxWorkerTickConfig(enabled=True, worker_id="worker-a", limit=10),
            authoritative_item_loader=lambda record: _live_item(memory_id=record["memory_id"]),
            vector_deleter=lambda record: None,
            vector_repairer=lambda record, item: None,
            now=now,
            telemetry_emitter=lambda payload: (_ for _ in ()).throw(RuntimeError("central metrics outage")),
            telemetry_config=VectorRepairOutboxTelemetryConfig(enabled=True),
        )

        assert db.store["users/u1/memory_outbox/repair"]["status"] == "completed"
        assert result["processed_count"] == 1
        assert result["failed_count"] == 0
        assert result["telemetry"]["failed_count"] > 0
        assert result["errors"] == []


class TestDeploymentContract:
    def test_memory_vector_repair_outbox_cloud_deployment_contract_is_disabled_and_oidc_ready(self):
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


class TestEmulatorHarness:
    def test_vector_repair_outbox_emulator_harness_is_wired_to_real_writer_and_rules_gate(self):
        assert SCRIPT.exists(), "missing memory vector repair outbox emulator harness"
        script = SCRIPT.read_text()
        assert "write_vector_repair_purge_outbox_records" in script
        assert "build_vector_repair_purge_outbox_records" in script
        assert "FIRESTORE_EMULATOR_HOST" in script
        assert "google.cloud.firestore" in script
        assert "users/{uid}/memory_outbox/{record_id}" in script
        assert "idempotent" in script
        assert "write failure propagated" in script

        package = json.loads(PACKAGE_JSON.read_text())
        assert package["scripts"]["test:memory-vector-repair-outbox:emulator"] == (
            "firebase emulators:exec --only firestore --project demo-memory "
            '"python3 backend/scripts/vector_repair_outbox_emulator_test.py"'
        )
        assert package["scripts"]["test:memory-vector-repair-outbox-rules:emulator"] == (
            "firebase emulators:exec --only firestore --project demo-memory "
            '"node backend/scripts/firestore_rules_emulator_test.mjs"'
        )
        assert package["scripts"]["test:memory-vector-repair-outbox-lease:emulator"] == (
            "firebase emulators:exec --only firestore --project demo-memory "
            '"python3 backend/scripts/vector_repair_outbox_lease_emulator_test.py"'
        )

    def test_vector_repair_outbox_lease_emulator_harness_is_wired_to_transactional_reader(self):
        script = ROOT / "backend" / "scripts" / "vector_repair_outbox_lease_emulator_test.py"

        assert script.exists(), "missing memory vector repair outbox lease contention emulator harness"
        content = script.read_text()
        assert "lease_vector_repair_purge_outbox_records" in content
        assert "ThreadPoolExecutor" in content
        assert "FIRESTORE_EMULATOR_HOST" in content
        assert "at most one" in content
        assert "PASS: memory vector repair/purge outbox transactional lease contention" in content


class TestOidcIamProof:
    def test_memory_vector_repair_outbox_oidc_iam_proof_runner_exists_and_is_read_only(self):
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
            "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED",
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

    def test_memory_vector_repair_outbox_deployment_contract_references_oidc_iam_proof_runner(self):
        root = Path(__file__).resolve().parents[2].parent
        contract_path = root / "docs" / "epics" / "memory_vector_repair_outbox_cloud_deployment_contract.yaml"
        contract = contract_path.read_text()

        assert "python3 backend/scripts/vector_repair_outbox_oidc_iam_proof.py" in contract
        assert "read-only" in contract
        assert "--execute" in contract
        assert "production Firestore IAM/deployed rules validation gates remain open" in contract
        assert "real Pinecone duplicate stale physical ID delete/repair validation remains open" in contract

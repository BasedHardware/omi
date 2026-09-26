import importlib.util
import json
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / "scripts" / "jit_qa_manual_operator.py"


def _load_operator():
    spec = importlib.util.spec_from_file_location("jit_qa_manual_operator_for_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OPERATOR = _load_operator()
SOURCE_SHA = "a" * 40
IMAGE = "gcr.io/based-hardware-dev/knowledge-ledger-drain-qa-job@sha256:" + "b" * 64


def _resource(**changes):
    values = {
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": OPERATOR.PROJECT,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": OPERATOR.PROJECT,
        "FIRESTORE_DATABASE_ID": OPERATOR.DATABASE,
        "FIREBASE_AUTH_PROJECT_ID": "based-hardware",
        "MEMORY_ENABLED": "on",
        "KNOWLEDGE_LEDGER_DRAIN_ENABLED": "false",
        "KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST": OPERATOR.UID,
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": OPERATOR.UID,
    }
    values.update(changes)
    env = [{"name": name, "value": value} for name, value in values.items()]
    env.extend(
        {"name": name, "valueSource": {"secretKeyRef": {"secret": name, "version": "latest"}}}
        for name in ("ENCRYPTION_SECRET", "POSTHOG_PROJECT_API_KEY")
    )
    return {
        "metadata": {"name": OPERATOR.JOB, "labels": {"jit-qa": "true", "source-sha": SOURCE_SHA}},
        "spec": {
            "template": {
                "spec": {
                    "template": {
                        "spec": {
                            "serviceAccountName": OPERATOR.RUNTIME_SERVICE_ACCOUNT,
                            "containers": [{"image": IMAGE, "env": env}],
                        }
                    }
                }
            }
        },
    }


def _firestore_document(**fields):
    def typed(value):
        if isinstance(value, bool):
            return {"booleanValue": value}
        if isinstance(value, int):
            return {"integerValue": str(value)}
        return {"stringValue": value}

    return {"fields": {key: typed(value) for key, value in fields.items()}}


def _execution_payload(**changes):
    values = {
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": OPERATOR.PROJECT,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": OPERATOR.PROJECT,
        "FIRESTORE_DATABASE_ID": OPERATOR.DATABASE,
        "FIREBASE_AUTH_PROJECT_ID": "based-hardware",
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": OPERATOR.UID,
        "MEMORY_ENABLED": "on",
        "KNOWLEDGE_LEDGER_DRAIN_ENABLED": "true",
        "KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST": OPERATOR.UID,
    }
    values.update(changes)
    env = [{"name": name, "value": value} for name, value in values.items()]
    env.extend(
        {"name": name, "valueFrom": {"secretKeyRef": {"name": name, "key": "latest"}}}
        for name in ("ENCRYPTION_SECRET", "POSTHOG_PROJECT_API_KEY")
    )
    return {
        "apiVersion": "run.googleapis.com/v1",
        "kind": "Execution",
        "metadata": {
            "name": OPERATOR.JOB + "-abc123",
            "labels": {
                "jit-qa": "true",
                "source-sha": SOURCE_SHA,
                "run.googleapis.com/job": OPERATOR.JOB,
            },
            "ownerReferences": [{"controller": True, "kind": "Job", "name": OPERATOR.JOB}],
        },
        "spec": {
            "template": {
                "spec": {
                    "serviceAccountName": OPERATOR.RUNTIME_SERVICE_ACCOUNT,
                    "containers": [{"image": IMAGE, "env": env}],
                }
            }
        },
    }


def test_job_contract_requires_immutable_source_admitted_qa_resource():
    result = OPERATOR.validate_job_resource(_resource(), source_sha=SOURCE_SHA, expected_image=IMAGE)
    assert result == {
        "job": OPERATOR.JOB,
        "image": IMAGE,
        "source_sha": SOURCE_SHA,
        "database": OPERATOR.DATABASE,
        "uid": OPERATOR.UID,
    }


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"GOOGLE_CLOUD_PROJECT": "based-hardware"}, "unexpected value"),
        ({"KNOWLEDGE_LEDGER_DRAIN_ENABLED": "true"}, "unexpected value"),
    ],
)
def test_job_contract_rejects_wrong_environment(changes, message):
    with pytest.raises(OPERATOR.OperatorError, match=message):
        OPERATOR.validate_job_resource(_resource(**changes), source_sha=SOURCE_SHA, expected_image=IMAGE)


def test_job_contract_rejects_tagged_image_stale_source_and_customer_binding():
    resource = _resource()
    resource["spec"]["template"]["spec"]["template"]["spec"]["containers"][0]["image"] = IMAGE.replace("@sha256:", ":")
    with pytest.raises(OPERATOR.OperatorError, match="immutable"):
        OPERATOR.validate_job_resource(resource, source_sha=SOURCE_SHA, expected_image=IMAGE)

    resource = _resource()
    resource["metadata"]["labels"]["source-sha"] = "c" * 40
    with pytest.raises(OPERATOR.OperatorError, match="source admission"):
        OPERATOR.validate_job_resource(resource, source_sha=SOURCE_SHA, expected_image=IMAGE)

    resource = _resource()
    resource["spec"]["template"]["spec"]["template"]["spec"]["containers"][0]["env"].append(
        {"name": "GOOGLE_APPLICATION_CREDENTIALS", "value": "/customer/key.json"}
    )
    with pytest.raises(OPERATOR.OperatorError, match="forbidden credential"):
        OPERATOR.validate_job_resource(resource, source_sha=SOURCE_SHA, expected_image=IMAGE)


def test_job_contract_rejects_live_digest_that_does_not_match_admitted_source_tag():
    with pytest.raises(OPERATOR.OperatorError, match="does not match"):
        OPERATOR.validate_job_resource(
            _resource(), source_sha=SOURCE_SHA, expected_image=IMAGE.replace("b" * 64, "c" * 64)
        )


def test_execution_name_and_state_are_fail_closed():
    assert OPERATOR.execution_name({"metadata": {"name": OPERATOR.JOB + "-abc123"}}) == OPERATOR.JOB + "-abc123"
    with pytest.raises(OPERATOR.OperatorError):
        OPERATOR.execution_name({"metadata": {"name": "knowledge-ledger-drain-job-abc123"}})
    assert OPERATOR.execution_state({}) == "running"
    assert (
        OPERATOR.execution_state({"status": {"conditions": [{"type": "Completed", "status": "True"}]}}) == "succeeded"
    )
    assert OPERATOR.execution_state({"status": {"conditions": [{"type": "Completed", "status": "False"}]}}) == "failed"


def test_execution_contract_proves_source_image_identity_and_drain_override():
    result = OPERATOR.validate_execution_payload(_execution_payload(), source_sha=SOURCE_SHA, expected_image=IMAGE)
    assert result == {
        "execution": OPERATOR.JOB + "-abc123",
        "job": OPERATOR.JOB,
        "image": IMAGE,
        "source_sha": SOURCE_SHA,
        "database": OPERATOR.DATABASE,
        "uid": OPERATOR.UID,
        "service_account": OPERATOR.RUNTIME_SERVICE_ACCOUNT,
        "drain_enabled": "true",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"KNOWLEDGE_LEDGER_DRAIN_ENABLED": "false"},
        {"KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST": "other-uid"},
    ],
)
def test_execution_contract_rejects_foreign_or_non_drain_override(changes):
    with pytest.raises(OPERATOR.OperatorError, match="override"):
        OPERATOR.validate_execution_payload(_execution_payload(**changes), source_sha=SOURCE_SHA, expected_image=IMAGE)


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "GOOGLE_APPLICATION_CREDENTIALS", "value": "/customer/key.json"},
        {"name": "UNREVIEWED_RUNTIME_SETTING", "value": "true"},
        {"name": "UNREVIEWED_RUNTIME_SETTING", "valueFrom": {}},
        {"name": "MEMORY_ENABLED", "value": "on"},
        {"name": "MEMORY_ENABLED", "value": "on", "valueFrom": {}},
        {"name": "ENCRYPTION_SECRET", "value": "unapproved"},
    ],
)
def test_execution_contract_rejects_unknown_duplicate_and_ambiguous_environment(entry):
    payload = _execution_payload()
    payload["spec"]["template"]["spec"]["containers"][0]["env"].append(entry)
    with pytest.raises(OPERATOR.OperatorError, match="environment"):
        OPERATOR.validate_execution_payload(payload, source_sha=SOURCE_SHA, expected_image=IMAGE)


def test_execution_contract_rejects_stale_job_source_and_service_account():
    payload = _execution_payload()
    payload["metadata"]["labels"]["source-sha"] = "c" * 40
    with pytest.raises(OPERATOR.OperatorError, match="source admission"):
        OPERATOR.validate_execution_payload(payload, source_sha=SOURCE_SHA, expected_image=IMAGE)

    payload = _execution_payload()
    payload["metadata"]["labels"]["run.googleapis.com/job"] = "other-job"
    with pytest.raises(OPERATOR.OperatorError, match="unexpected Cloud Run job"):
        OPERATOR.validate_execution_payload(payload, source_sha=SOURCE_SHA, expected_image=IMAGE)

    payload = _execution_payload()
    payload["spec"]["template"]["spec"]["serviceAccountName"] = "customer@based-hardware.iam.gserviceaccount.com"
    with pytest.raises(OPERATOR.OperatorError, match="service account"):
        OPERATOR.validate_execution_payload(payload, source_sha=SOURCE_SHA, expected_image=IMAGE)


def test_summary_parser_maps_content_free_cloud_log_line():
    logs = {
        "entries": [
            {
                "resource": {"type": "cloud_run_job"},
                "jsonPayload": {
                    "message": (
                        "knowledge_ledger_drain: scanned=1 inventoried=1 attempted=1 allowlist_blocked=0 "
                        "blocked=0 revoked=0 remaining=1 cutover=0 migrated_rows=100 errors=0"
                    )
                },
            }
        ]
    }
    assert OPERATOR.summary_from_logs(logs) == {
        "inventoried_users": 1,
        "scanned_documents": 1,
        "attempted_users": 1,
        "allowlist_blocked_users": 0,
        "rollout_blocked_users": 0,
        "authorization_revoked_users": 0,
        "remaining_users": 1,
        "cutover_users": 0,
        "migrated_rows": 100,
        "errors": [],
    }
    with pytest.raises(OPERATOR.OperatorError, match="found 0"):
        OPERATOR.summary_from_logs({"entries": []})
    list_payload = [logs["entries"][0]]
    assert OPERATOR.summary_from_logs(list_payload)["migrated_rows"] == 100


def test_summary_validation_requires_phase_specific_rollforward_counters():
    first = OPERATOR.summary_from_logs(
        {
            "message": (
                "knowledge_ledger_drain: scanned=1 inventoried=1 attempted=1 allowlist_blocked=0 "
                "blocked=0 revoked=0 remaining=1 cutover=0 migrated_rows=100 errors=0"
            )
        }
    )
    assert OPERATOR.validate_summary(first, phase="first")["migrated_rows"] == 100
    rollforward = dict(first)
    rollforward.update(remaining_users=0, cutover_users=1, migrated_rows=0)
    assert OPERATOR.validate_summary(rollforward, phase="rollforward")["cutover_users"] == 1
    with pytest.raises(OPERATOR.OperatorError, match="rollforward drain"):
        OPERATOR.validate_summary(first, phase="rollforward")


def test_durable_state_requires_matching_fences_and_nonempty_projection():
    control = _firestore_document(
        uid=OPERATOR.UID,
        writer_mode="ledger",
        head_commit_id="head",
        account_generation=3,
        source_generation=4,
        writer_epoch=2,
    )
    completion = _firestore_document(
        schema_version="knowledge_ledger.v1",
        status="complete",
        blocking_row_count=0,
        source_head_commit_id="head",
        writer_epoch=2,
    )
    projection = _firestore_document(
        schema_version="knowledge_ledger_prompt_projection.v1",
        status="complete",
        uid=OPERATOR.UID,
        source_head_commit_id="head",
        account_generation=3,
        source_generation=4,
        writer_epoch=2,
        legacy_row_count=0,
        blocking_row_count=0,
        scanned_row_count=101,
    )
    assert OPERATOR.validate_durable_state(control, completion, projection)["scanned_row_count"] == 101
    with pytest.raises(OPERATOR.OperatorError, match="head fence"):
        OPERATOR.validate_durable_state(
            control,
            _firestore_document(
                schema_version="knowledge_ledger.v1",
                status="complete",
                blocking_row_count=0,
                source_head_commit_id="other",
                writer_epoch=2,
            ),
            projection,
        )
    with pytest.raises(OPERATOR.OperatorError, match="missing non-empty head_commit_id"):
        OPERATOR.validate_durable_state(
            _firestore_document(
                uid=OPERATOR.UID,
                writer_mode="ledger",
                head_commit_id="",
                account_generation=3,
                source_generation=4,
                writer_epoch=2,
            ),
            completion,
            projection,
        )
    with pytest.raises(OPERATOR.OperatorError, match="account generation"):
        OPERATOR.validate_durable_state(
            control,
            completion,
            {**projection, "fields": {**projection["fields"], "account_generation": {"integerValue": "9"}}},
        )

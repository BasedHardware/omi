import importlib.util
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / "scripts" / "jit_qa_sweep_operator.py"


def _load_operator():
    spec = importlib.util.spec_from_file_location("jit_qa_sweep_operator_for_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OPERATOR = _load_operator()
RUN_ID = "qa-sweep-run-1"
SOURCE_SHA = "a" * 40
IMAGE = "gcr.io/based-hardware-dev/daily-memory-sweep-qa-job@sha256:" + "b" * 64


class _Snapshot:
    def __init__(self, payload):
        self.exists = payload is not None
        self._payload = payload

    def to_dict(self):
        return self._payload


class _Ref:
    def __init__(self, payload):
        self.payload = payload

    def get(self):
        return _Snapshot(self.payload)


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.fields = None

    def select(self, fields):
        self.fields = tuple(fields)
        return self

    def where(self, *args, **kwargs):
        return self

    def limit(self, count):
        return _Query(self.rows[:count])

    def stream(self):
        return iter(self.rows)


class _Collection:
    def __init__(self, rows, *, projectable=True):
        self.rows = rows
        self.projectable = projectable

    def select(self, fields):
        if not self.projectable:
            return None
        query = _Query(self.rows)
        return query.select(fields)


class _Db:
    def __init__(self, documents, rows, *, projectable=True):
        self.documents = documents
        self.rows = rows
        self.projectable = projectable

    def document(self, path):
        return _Ref(self.documents.get(path))

    def collection(self, _path):
        return _Collection(self.rows, projectable=self.projectable)


def _source_row(**changes):
    row = {
        "uid": OPERATOR.QA_SWEEP_UID,
        "qa_run_id": RUN_ID,
        "receipt_state": "committed",
        "outcome": "committed",
        "memory_id": "memory-qa-1",
        "candidate_digest": "digest-qa-1",
        "source_key": "daily_summary:conversation:chat-1:candidate-1",
        "source_id": "conversation:chat-1",
        "source_type": "daily_summary",
        "source_version": "daily-memory-agent.v1",
        "source_refs": ["conversation:chat-1"],
    }
    row.update(changes)
    return row


def _db(*rows):
    output_path = (
        f"{OPERATOR.QA_SWEEP_RUN_COLLECTION}/{RUN_ID}/{OPERATOR.QA_SWEEP_OUTPUT_SUBCOLLECTION}/{OPERATOR.QA_SWEEP_UID}"
    )
    run_path = f"{OPERATOR.QA_SWEEP_RUN_COLLECTION}/{RUN_ID}"
    policy = {
        "model_name": "gpt-5.6-luna",
        "max_model_candidates": 1,
        "max_model_cost_usd": 0.05,
        "provider_calls_allowed": 1,
    }
    output = {
        "schema_version": OPERATOR.QA_SWEEP_OUTPUT_SCHEMA_VERSION,
        "run_id": RUN_ID,
        "uid": OPERATOR.QA_SWEEP_UID,
        "project": OPERATOR.QA_SWEEP_PROJECT,
        "database": OPERATOR.QA_SWEEP_DATABASE,
        "status": "completed",
        "committed_candidates": len(rows),
        "model_policy": policy,
        "candidate_receipt_collection": OPERATOR.OUTPUT_COLLECTION,
        "candidate_receipt_join_field": "qa_run_id",
    }
    run = {
        "schema_version": OPERATOR.QA_SWEEP_RECEIPT_SCHEMA_VERSION,
        "run_id": RUN_ID,
        "uid": OPERATOR.QA_SWEEP_UID,
        "project": OPERATOR.QA_SWEEP_PROJECT,
        "database": OPERATOR.QA_SWEEP_DATABASE,
        "status": "completed",
        "model_policy": policy,
    }
    return _Db({run_path: run, output_path: output}, list(map(_Snapshot, rows)))


def _job_resource(*, source_sha=SOURCE_SHA, image=IMAGE):
    return {
        "metadata": {"name": "daily-memory-sweep-qa-job", "labels": {"jit-qa": "true", "source-sha": source_sha}},
        "spec": {"template": {"spec": {"template": {"spec": {"containers": [{"image": image}]}}}}},
    }


def test_consumer_requires_joined_current_chat_backed_output():
    result = OPERATOR.verify_qa_sweep_run(_db(_source_row()), run_id=RUN_ID)

    assert result["status"] == "PASS"
    assert result["input_evidence"] == {"chat_backed_rows": 1, "source_types": ["daily_summary"]}


def test_job_source_admission_ties_live_digest_to_reviewed_sha():
    assert OPERATOR.validate_job_resource(_job_resource(), source_sha=SOURCE_SHA, expected_image=IMAGE) == {
        "job": "daily-memory-sweep-qa-job",
        "image": IMAGE,
        "source_sha": SOURCE_SHA,
    }
    with pytest.raises(OPERATOR.JITQASweepOperatorError, match="source admission"):
        OPERATOR.validate_job_resource(_job_resource(source_sha="c" * 40), source_sha=SOURCE_SHA, expected_image=IMAGE)
    with pytest.raises(OPERATOR.JITQASweepOperatorError, match="does not match"):
        OPERATOR.validate_job_resource(
            _job_resource(), source_sha=SOURCE_SHA, expected_image=IMAGE.replace("b" * 64, "c" * 64)
        )


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"source_type": "legacy_migration"}, "legacy_migration"),
        ({"source_id": "jitqa-qa-sweep-run-1-legacy-001"}, "legacy_migration"),
        ({"source_type": "agent_conclusion", "source_refs": ["memory:standing-trigger-1"]}, "conversation-backed"),
    ],
)
def test_consumer_does_not_promote_historical_or_unrelated_rows(changes, message):
    with pytest.raises(OPERATOR.JITQASweepOperatorError, match=message):
        OPERATOR.verify_qa_sweep_run(_db(_source_row(**changes)), run_id=RUN_ID)


def test_consumer_requires_projection_and_bounded_inventory():
    db = _db(_source_row())
    db.projectable = False
    with pytest.raises(OPERATOR.JITQASweepOperatorError, match="projection"):
        OPERATOR.verify_qa_sweep_run(db, run_id=RUN_ID)

    rows = [_source_row(memory_id=f"memory-{index}") for index in range(9)]
    with pytest.raises(OPERATOR.JITQASweepOperatorError, match="more than eight"):
        OPERATOR.verify_qa_sweep_run(_db(*rows), run_id=RUN_ID, minimum_output_rows=1)


def test_qa_environment_validation_uses_explicit_mapping_and_fixed_policy():
    environment = {
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": OPERATOR.QA_SWEEP_PROJECT,
        "GCLOUD_PROJECT": OPERATOR.QA_SWEEP_PROJECT,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": OPERATOR.QA_SWEEP_PROJECT,
        "FIRESTORE_DATABASE_ID": OPERATOR.QA_SWEEP_DATABASE,
        "FIREBASE_AUTH_PROJECT_ID": "based-hardware",
        "MEMORY_ENABLED": "on",
        "OMI_JIT_QA_SWEEP_RUN_ID": RUN_ID,
        "OMI_JIT_QA_SWEEP_ADMISSION": "true",
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": OPERATOR.QA_SWEEP_UID,
        "MEMORY_DAILY_MEMORY_SWEEP_ENABLED": "true",
        "MEMORY_DAILY_MEMORY_SWEEP_KILL_SWITCH": "false",
        "MEMORY_DAILY_MEMORY_SWEEP_MODEL_ENABLED": "true",
        "MEMORY_DAILY_MEMORY_SWEEP_MODEL_NAME": "gpt-5.6-luna",
        "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES": "1",
        "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD": "0.05",
        "MEMORY_DAILY_MEMORY_SWEEP_COHORT_ENABLED": "true",
        "MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG": "jit-qa-sweep-v1",
        "MEMORY_DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENABLED": "false",
    }
    assert OPERATOR.validate_qa_sweep_environment(environment) == RUN_ID
    with pytest.raises(ValueError, match="OMI_ENV_STAGE"):
        OPERATOR.validate_qa_sweep_environment({"OMI_JIT_QA_SWEEP_RUN_ID": RUN_ID})

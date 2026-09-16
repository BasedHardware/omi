import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / "scripts" / "jit_qa_sweep_repair.py"
UID = "user-1"


def _load_operator():
    spec = importlib.util.spec_from_file_location("jit_qa_sweep_repair_for_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OPERATOR = _load_operator()

QA_ENV = {
    "OMI_ENV_STAGE": "dev",
    "GOOGLE_CLOUD_PROJECT": "based-hardware-dev",
    "FIRESTORE_DATABASE_ID": "jit-qa",
    "OMI_JIT_QA_AUTH_ONLY": "true",
    "OMI_JIT_QA_UID_ALLOWLIST": OPERATOR.QA_SWEEP_UID,
}


class _Snapshot:
    def __init__(self, payload):
        self.exists = payload is not None
        self._payload = payload

    def to_dict(self):
        return self._payload


class _Ref:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def get(self, **_kwargs):
        return _Snapshot(self.store.get(self.path))

    def set(self, value, merge=False):
        if merge and self.path in self.store:
            current = dict(self.store[self.path])
            current.update(value)
            self.store[self.path] = current
        else:
            self.store[self.path] = dict(value)

    def create(self, value):
        if self.path in self.store:
            raise RuntimeError("already exists")
        self.store[self.path] = dict(value)


class _AttemptQuery:
    def __init__(self, rows, date_value):
        self.rows, self.date_value = rows, date_value
        self.expected_date = None

    def where(self, *args, **kwargs):
        field_filter = kwargs.get("filter")
        assert field_filter is not None
        assert getattr(field_filter, "field_path", None) == "date"
        self.expected_date = getattr(field_filter, "value", None)
        return self

    def limit(self, _count):
        return self

    def stream(self):
        assert self.expected_date == self.date_value
        for row in self.rows:
            yield _Snapshot(row)


class _InvocationQuery:
    def __init__(self, store, prefix):
        self.store, self.prefix = store, prefix

    def limit(self, _count):
        return self

    def stream(self):
        for path, payload in sorted(self.store.items()):
            if path.startswith(self.prefix):
                yield _SnapshotWithPath(path.rsplit("/", 1)[-1], payload)


class _SnapshotWithPath(_Snapshot):
    def __init__(self, doc_id, payload):
        super().__init__(payload)
        self.id = doc_id


TODAY = datetime.now(timezone.utc).date().isoformat()


class _Db:
    def __init__(self, attempts=(), attempt_date=None):
        self.store = {}
        self.attempts = tuple(attempts)
        self.attempt_date = attempt_date or TODAY

    def document(self, path):
        return _Ref(self.store, path)

    def collection(self, path):
        if path == "llm_gateway_attempts":
            return _AttemptQuery(self.attempts, self.attempt_date)
        if path.startswith("users/") and path.endswith("/daily_memory_sweep_model_invocations"):
            return _InvocationQuery(self.store, f"{path}/")
        raise AssertionError(f"unexpected collection {path}")


def _tombstoned_invocation(store, *, state="payload_expired", claimed_minutes_ago=60):
    claimed_at = datetime.now(timezone.utc) - timedelta(minutes=claimed_minutes_ago)
    store[f"users/{UID}/daily_memory_sweep_model_invocations/inv-1"] = {
        "uid": UID,
        "invocation_id": "inv-1",
        "account_generation": 1,
        "source_generation": 4,
        "sweep_generation": 1,
        "window_id": "window-a",
        "state": state,
        "claimed_at": claimed_at,
        "lease_expires_at": claimed_at + timedelta(minutes=15),
    }
    store[f"daily_memory_sweep_model_invocation_fences/inv-1"] = {
        "uid": UID,
        "invocation_id": "inv-1",
        "account_generation": 1,
        "source_generation": 4,
        "sweep_generation": 1,
        "window_id": "window-a",
        "state": "pending",
        "claimed_at": claimed_at,
    }
    return claimed_at


def test_environment_fence_fails_closed(monkeypatch):
    for name in QA_ENV:
        env = dict(QA_ENV)
        env.pop(name)
        monkeypatch.setattr(OPERATOR.os, "environ", env)
        with pytest.raises(OPERATOR.JITQASweepRepairError, match=name):
            OPERATOR.validate_repair_environment()


def test_list_reports_tombstones_with_repair_state():
    db = _Db()
    _tombstoned_invocation(db.store)
    db.store[f"users/{UID}/daily_memory_sweep_model_invocations/inv-2"] = {"state": "returned"}
    rows = OPERATOR.list_tombstones(db, uid=UID)
    assert [row["invocation_id"] for row in rows] == ["inv-1"]
    assert rows[0]["state"] == "payload_expired"
    assert rows[0]["lease_expired"] is True
    assert rows[0]["repair_receipt"] is False


def test_repair_joins_gateway_accounting_and_writes_single_receipt():
    db = _Db(
        attempts=[
            {
                "date": TODAY,
                "user_uid": UID,
                "feature": "memories",
                "request_id": "req-1",
                "outcome": "success",
                "total_tokens": 2730,
                "estimated_cost_micro_usd": 926,
                "occurred_at": datetime.now(timezone.utc) - timedelta(minutes=59),
                "jit_run_id": "qa-sweep-34933918999-1",
            },
            {
                "date": TODAY,
                "user_uid": UID,
                "feature": "desktop_proactivity",
                "request_id": "req-2",
                "outcome": "success",
                "total_tokens": 10,
                "occurred_at": datetime.now(timezone.utc) - timedelta(minutes=59),
            },
        ]
    )
    _tombstoned_invocation(db.store)
    receipt = OPERATOR.repair_tombstone(
        db,
        invocation_id="inv-1",
        repair_authority="operator:qa-run-1",
        uid=UID,
    )
    assert receipt["provider_outcome_summary"] == "success_usage_recorded"
    stored = db.store[f"users/{UID}/daily_memory_sweep_model_invocation_repairs/inv-1"]
    assert stored["provider_outcome_evidence"]["jit_run_id"] == "qa-sweep-34933918999-1"
    attempts = stored["provider_outcome_evidence"]["attempts"]
    assert len(attempts) == 1 and attempts[0]["request_id"] == "req-1"
    assert "desktop_proactivity" not in str(attempts)


def test_repair_without_a_joinable_sweep_run_fails_closed():
    db = _Db(
        attempts=[
            {
                "date": TODAY,
                "user_uid": UID,
                "feature": "memories",
                "request_id": "req-1",
                "outcome": "error",
                "total_tokens": 0,
                "occurred_at": datetime.now(timezone.utc) - timedelta(minutes=59),
            },
        ]
    )
    _tombstoned_invocation(db.store)
    with pytest.raises(OPERATOR.JITQASweepRepairError, match="sweep run id"):
        OPERATOR.repair_tombstone(db, invocation_id="inv-1", repair_authority="operator:qa-run-1", uid=UID)

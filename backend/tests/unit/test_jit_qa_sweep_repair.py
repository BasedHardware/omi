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
        self.count = 50
        self.offset = 0

    def where(self, *args, **kwargs):
        field_filter = kwargs.get("filter")
        assert field_filter is not None
        assert getattr(field_filter, "field_path", None) == "date"
        self.expected_date = getattr(field_filter, "value", None)
        return self

    def order_by(self, field):
        assert field == "__name__"
        return self

    def start_after(self, snapshot):
        self.offset = int(snapshot.id) + 1
        return self

    def limit(self, count):
        self.count = count
        return self

    def stream(self):
        rows = [row for row in self.rows if row.get("date") == self.expected_date]
        for index in range(self.offset, min(len(rows), self.offset + self.count)):
            yield _SnapshotWithPath(f"{index:06d}", rows[index])


class _InvocationQuery:
    def __init__(self, store, prefix):
        self.store, self.prefix = store, prefix
        self.uid = None

    def where(self, *, filter):
        assert filter.field_path == "uid"
        self.uid = filter.value
        return self

    def limit(self, _count):
        return self

    def stream(self):
        for path, payload in sorted(self.store.items()):
            if path.startswith(self.prefix) and (self.uid is None or payload.get("uid") == self.uid):
                yield _SnapshotWithPath(path.rsplit("/", 1)[-1], payload)


class _SnapshotWithPath(_Snapshot):
    def __init__(self, doc_id, payload):
        super().__init__(payload)
        self.id = doc_id


NOW = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
TODAY = NOW.date().isoformat()


@pytest.fixture(autouse=True)
def _transactions(monkeypatch):
    monkeypatch.setattr(OPERATOR.firestore, "transactional", lambda fn: lambda transaction: fn(transaction))


class _Db:
    def __init__(self, attempts=(), attempt_date=None):
        self.store = {}
        self.attempts = tuple(attempts)
        self.attempt_date = attempt_date or TODAY

    def transaction(self):
        return self

    def set(self, ref, value):
        ref.set(value)

    def document(self, path):
        return _Ref(self.store, path)

    def collection(self, path):
        if path == "llm_gateway_attempts":
            return _AttemptQuery(self.attempts, self.attempt_date)
        if path == "daily_memory_sweep_model_invocation_fences":
            return _InvocationQuery(self.store, f"{path}/")
        if path.startswith("users/") and path.endswith("/daily_memory_sweep_model_invocations"):
            return _InvocationQuery(self.store, f"{path}/")
        raise AssertionError(f"unexpected collection {path}")


def _tombstoned_invocation(store, *, state="payload_expired", claimed_minutes_ago=60):
    claimed_at = NOW - timedelta(minutes=claimed_minutes_ago)
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
        "state": state,
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
    db.store["daily_memory_sweep_model_invocation_fences/inv-2"] = {"uid": UID, "state": "returned"}
    db.store[f"users/{UID}/daily_memory_sweep_model_invocations/inv-1"]["lease_expires_at"] = datetime.now(
        timezone.utc
    ) - timedelta(minutes=1)
    rows = OPERATOR.list_tombstones(db, uid=UID)
    assert [row["invocation_id"] for row in rows] == ["inv-1", "inv-2"]
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
                "occurred_at": NOW - timedelta(minutes=59),
                "jit_run_id": "qa-sweep-34933918999-1",
            },
            {
                "date": TODAY,
                "user_uid": UID,
                "feature": "desktop_proactivity",
                "request_id": "req-2",
                "outcome": "success",
                "total_tokens": 10,
                "occurred_at": NOW - timedelta(minutes=59),
            },
        ]
    )
    _tombstoned_invocation(db.store)
    receipt = OPERATOR.repair_tombstone(
        db,
        invocation_id="inv-1",
        repair_authority="operator:qa-run-1",
        uid=UID,
        now=NOW,
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
                "occurred_at": NOW - timedelta(minutes=59),
            },
        ]
    )
    _tombstoned_invocation(db.store)
    with pytest.raises(OPERATOR.JITQASweepRepairError, match="sweep run id"):
        OPERATOR.repair_tombstone(db, invocation_id="inv-1", repair_authority="operator:qa-run-1", uid=UID, now=NOW)


@pytest.mark.parametrize("reservation_exists", [False, True])
def test_missing_accounting_never_authorizes_repair(reservation_exists):
    db = _Db()
    _tombstoned_invocation(db.store)
    if reservation_exists:
        # Provider consumed after reservation, but its post-provider ledger write
        # was dropped. A window scan is indistinguishable from no dispatch.
        db.store["jit_cloud_qa_budgets_v1/opaque-owner-run-key"] = {
            "owner_uid": UID,
            "run_id": "actual-run",
            "reserved_attempts": 1,
            "active_reservation": {"ordinal": 1},
        }
    with pytest.raises(OPERATOR.JITQASweepRepairError, match="accounting absence is not proof"):
        OPERATOR.repair_tombstone(db, invocation_id="inv-1", repair_authority="operator:test", uid=UID, now=NOW)
    assert not any("repairs/" in key for key in db.store)


def test_legacy_claim_requires_explicit_attributed_attestation():
    db = _Db()
    _tombstoned_invocation(db.store)
    receipt = OPERATOR.repair_tombstone(
        db,
        invocation_id="inv-1",
        repair_authority="operator:test",
        uid=UID,
        now=NOW,
        attestation_confirmation=OPERATOR.NO_DISPATCH_ATTESTATION_CONFIRMATION,
        attestation_reference="incident:verified-worker-exit",
    )
    assert receipt["provider_outcome_summary"] == "operator_attested_no_dispatch"
    evidence = receipt["provider_outcome_evidence"]
    assert evidence["attested_by"] == "operator:test"
    assert evidence["claim_id"] is None
    assert evidence["evidence_reference"] == "incident:verified-worker-exit"
    assert "jit_run_id" not in evidence and "accounting_read_complete" not in evidence


@pytest.mark.parametrize(
    "confirmation,reference",
    [(None, "incident:1"), ("yes", "incident:1"), (OPERATOR.NO_DISPATCH_ATTESTATION_CONFIRMATION, None)],
)
def test_attestation_requires_exact_assertion_and_reference(confirmation, reference):
    db = _Db()
    _tombstoned_invocation(db.store)
    with pytest.raises(OPERATOR.JITQASweepRepairError, match="attestation and evidence reference"):
        OPERATOR.repair_tombstone(
            db,
            invocation_id="inv-1",
            repair_authority="operator:test",
            uid=UID,
            now=NOW,
            attestation_confirmation=confirmation,
            attestation_reference=reference,
        )


@pytest.mark.parametrize("age", [1, 16, 17])
def test_zero_attempt_repair_requires_lease_and_margin_expired(age):
    db = _Db()
    _tombstoned_invocation(db.store, claimed_minutes_ago=age)
    with pytest.raises(OPERATOR.JITQASweepRepairError, match="expired invocation lease"):
        OPERATOR.repair_tombstone(db, invocation_id="inv-1", repair_authority="operator:test", uid=UID, now=NOW)


def _foreign_rows(count):
    return [{"date": TODAY, "user_uid": "foreign", "feature": "memories"} for _ in range(count)]


def test_accounting_pages_past_fifty_foreign_rows_to_matching_attempt():
    db = _Db(
        attempts=_foreign_rows(55)
        + [
            {
                "date": TODAY,
                "user_uid": UID,
                "feature": "memories",
                "request_id": "matching",
                "outcome": "error",
                "jit_run_id": "actual-run",
                "occurred_at": NOW - timedelta(minutes=59),
            }
        ]
    )
    claimed = _tombstoned_invocation(db.store)
    evidence = OPERATOR.collect_provider_outcome_evidence(db, uid=UID, claimed_at=claimed, now=NOW)
    assert evidence["jit_run_id"] == "actual-run"
    assert [a["request_id"] for a in evidence["attempts"]] == ["matching"]


def test_incomplete_accounting_page_budget_refuses_absence(monkeypatch):
    monkeypatch.setattr(OPERATOR, "GATEWAY_ATTEMPT_MAX_PAGES", 1)
    db = _Db(attempts=_foreign_rows(50))
    _tombstoned_invocation(db.store)
    with pytest.raises(OPERATOR.JITQASweepRepairError, match="incomplete"):
        OPERATOR.repair_tombstone(db, invocation_id="inv-1", repair_authority="operator:test", uid=UID, now=NOW)
    assert not any("repairs/" in key for key in db.store)


def test_accounting_stream_failure_refuses_absence(monkeypatch):
    def broken(_self):
        yield _SnapshotWithPath("000001", {"user_uid": "foreign"})
        raise RuntimeError("incomplete stream")

    monkeypatch.setattr(_AttemptQuery, "stream", broken)
    db = _Db()
    _tombstoned_invocation(db.store)
    with pytest.raises(OPERATOR.JITQASweepRepairError, match="incomplete"):
        OPERATOR.repair_tombstone(db, invocation_id="inv-1", repair_authority="operator:test", uid=UID, now=NOW)


def test_accounting_reads_intermediate_days():
    occurred = NOW - timedelta(days=1)
    db = _Db(
        attempts=[
            {
                "date": occurred.date().isoformat(),
                "user_uid": UID,
                "feature": "memories",
                "request_id": "middle",
                "jit_run_id": "actual-run",
                "occurred_at": occurred,
            }
        ]
    )
    evidence = OPERATOR.collect_provider_outcome_evidence(db, uid=UID, claimed_at=NOW - timedelta(days=2), now=NOW)
    assert evidence["attempts"][0]["request_id"] == "middle"


def test_late_accounting_insert_before_cursor_never_becomes_absence_proof(monkeypatch):
    inserted = []
    original_stream = _AttemptQuery.stream

    def late_insert(query):
        if query.offset == 0:
            yield from original_stream(query)
            # This page has already been returned; the next query starts after
            # its cursor and cannot see a newly inserted lower document id.
            inserted.append({"user_uid": UID, "feature": "memories", "request_id": "late"})
        else:
            return

    monkeypatch.setattr(_AttemptQuery, "stream", late_insert)
    db = _Db(attempts=_foreign_rows(50))
    _tombstoned_invocation(db.store)
    with pytest.raises(OPERATOR.JITQASweepRepairError, match="accounting absence is not proof"):
        OPERATOR.repair_tombstone(db, invocation_id="inv-1", repair_authority="operator:test", uid=UID, now=NOW)
    assert inserted
    assert not any("repairs/" in key for key in db.store)


def test_recorded_attempt_conflicts_with_no_dispatch_attestation():
    db = _Db(
        attempts=[
            {
                "date": TODAY,
                "user_uid": UID,
                "feature": "memories",
                "request_id": "actual-request",
                "jit_run_id": "actual-run",
                "occurred_at": NOW - timedelta(minutes=59),
            }
        ]
    )
    _tombstoned_invocation(db.store)
    with pytest.raises(OPERATOR.JITQASweepRepairError, match="conflict"):
        OPERATOR.repair_tombstone(
            db,
            invocation_id="inv-1",
            repair_authority="operator:test",
            uid=UID,
            now=NOW,
            attestation_confirmation=OPERATOR.NO_DISPATCH_ATTESTATION_CONFIRMATION,
            attestation_reference="incident:wrong-assertion",
        )
    assert not any("repairs/" in key for key in db.store)


def test_operator_skip_returned_claim_does_not_require_lost_accounting(monkeypatch):
    db = _Db()
    _tombstoned_invocation(db.store, state="returned")
    db.store["daily_memory_sweep_model_invocation_fences/inv-1"].update(state="returned", claim_id="returned-claim")
    monkeypatch.setattr(
        OPERATOR,
        "collect_provider_outcome_evidence",
        lambda *_args, **_kwargs: pytest.fail("skip must not require reconstructing lost accounting"),
    )
    receipt = OPERATOR.repair_tombstone(
        db,
        invocation_id="inv-1",
        repair_authority="operator:test",
        uid=UID,
        now=NOW,
        attestation_confirmation=OPERATOR.SKIP_WINDOW_ATTESTATION_CONFIRMATION,
        attestation_reference="incident:stage-gap",
    )
    assert receipt["provider_outcome_summary"] == "operator_attested_skip_window"
    assert receipt["window_disposition"] == "abandoned"
    assert receipt["provider_dispatch_status"] == "not_attested"
    assert receipt["accounting_checked"] is False
    assert "attempts" not in receipt["provider_outcome_evidence"]
    assert receipt["provider_outcome_evidence"]["confirmation"] == "ATTEST_WORKER_TERMINATED_AND_ABANDON_WINDOW"
    assert receipt["consumed"] is False


@pytest.mark.parametrize("confirmation", ["ATTEST_SKIP_WINDOW_WITHOUT_DISPATCH_AND_WORKER_TERMINATED"])
def test_obsolete_skip_assertion_cannot_attest_no_dispatch_for_returned_claim(confirmation):
    db = _Db()
    _tombstoned_invocation(db.store, state="returned")
    with pytest.raises(OPERATOR.JITQASweepRepairError, match="attestation and evidence reference"):
        OPERATOR.repair_tombstone(
            db,
            invocation_id="inv-1",
            repair_authority="operator:test",
            uid=UID,
            now=NOW,
            attestation_confirmation=confirmation,
            attestation_reference="incident:stage-gap",
        )

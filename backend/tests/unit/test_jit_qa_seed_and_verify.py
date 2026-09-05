from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

# The migration import is intentionally top-level in the operator, matching
# backend import rules. Unit tests provide only the minimum synthetic key; no
# network or Firestore credential is used.
os.environ.setdefault("ENCRYPTION_SECRET", "x" * 32)

from scripts import jit_qa_seed_and_verify as operator


class _Snapshot:
    def __init__(self, payload: dict | None, *, document_id: str = ""):
        self.exists = payload is not None
        self._payload = dict(payload or {})
        self.id = document_id

    def to_dict(self):
        return dict(self._payload)


class _Ref:
    def __init__(self, db: "_DB", path: str):
        self.db = db
        self.path = path

    def select(self, _fields):
        return self

    def get(self):
        return _Snapshot(self.db.docs.get(self.path), document_id=self.path.rsplit("/", 1)[-1])

    def set(self, payload, merge=False):
        if merge and self.path in self.db.docs:
            self.db.docs[self.path].update(payload)
        else:
            self.db.docs[self.path] = dict(payload)

    def create(self, payload):
        if self.path in self.db.docs:
            raise RuntimeError("already exists")
        self.db.docs[self.path] = dict(payload)


class _Collection:
    def __init__(self, db: "_DB", path: str):
        self.db = db
        self.path = path.strip("/")
        self._limit = None

    @property
    def id(self):
        return self.path.rsplit("/", 1)[-1]

    def select(self, _fields):
        return self

    def limit(self, value):
        self._limit = value
        return self

    def stream(self):
        prefix_parts = self.path.split("/")
        rows = []
        for path, payload in self.db.docs.items():
            parts = path.split("/")
            if len(parts) == len(prefix_parts) + 1 and parts[: len(prefix_parts)] == prefix_parts:
                rows.append(_Snapshot(payload, document_id=parts[-1]))
        return rows[: self._limit]


class _DB:
    def __init__(self, *, include_control=True):
        self.docs = (
            {
                f"users/{operator.QA_UID}/memory_state/apply_control": {
                    "uid": operator.QA_UID,
                    "writer_mode": "compatibility",
                    "writer_epoch": 1,
                    "head_commit_id": "qa-head",
                    "account_generation": 1,
                    "source_generation": 1,
                    "commit_sequence": 0,
                }
            }
            if include_control
            else {}
        )

    def document(self, path):
        return _Ref(self, path)

    def collection(self, path):
        return _Collection(self, path)

    def collections(self):
        ids = {path.split("/", 1)[0] for path in self.docs}
        return [_Collection(self, collection_id) for collection_id in sorted(ids)]


def _summary(**overrides):
    value = {
        "inventoried_users": 1,
        "scanned_documents": 1,
        "attempted_users": 1,
        "allowlist_blocked_users": 0,
        "rollout_blocked_users": 0,
        "authorization_revoked_users": 0,
        "remaining_users": 0,
        "cutover_users": 1,
        "migrated_rows": 1,
        "errors": [],
    }
    value.update(overrides)
    return value


def test_target_and_environment_are_fail_closed(monkeypatch):
    with pytest.raises(operator.JITQAVerificationError, match="based-hardware-dev"):
        operator.validate_target(project="based-hardware")
    with pytest.raises(operator.JITQAVerificationError, match="jit-qa"):
        operator.validate_target(database="(default)")
    with pytest.raises(operator.JITQAVerificationError, match="fixed isolated"):
        operator.validate_target(uid="other-user")

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware")
    with pytest.raises(operator.JITQAVerificationError, match="GOOGLE_CLOUD_PROJECT"):
        operator.validate_environment()


def test_firestore_client_selects_named_qa_database(monkeypatch):
    calls = {}

    class FakeFirestoreClient:
        def __init__(self, **kwargs):
            calls.update(kwargs)

    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCLOUD_PROJECT", raising=False)
    monkeypatch.delenv("FIRESTORE_DATABASE_ID", raising=False)
    monkeypatch.setattr(operator.firestore, "Client", FakeFirestoreClient)
    operator.build_firestore_client()
    assert calls == {"project": "based-hardware-dev", "database": "jit-qa"}


def test_seed_is_idempotent_and_writes_only_owned_rows():
    db = _DB()
    first = operator.seed_fixture(db, run_id="proof-20260905")
    assert first["created_rows"] == operator.ROW_COUNT
    assert first["existing_rows"] == 0
    assert len(db.docs) == 1 + (operator.ROW_COUNT * 2)

    second = operator.seed_fixture(db, run_id="proof-20260905")
    assert second["created_rows"] == 0
    assert second["existing_rows"] == operator.ROW_COUNT
    assert len(db.docs) == 1 + (operator.ROW_COUNT * 2)

    state = operator.inspect_fixture(db, run_id="proof-20260905")
    assert state.retained_rows == operator.ROW_COUNT
    assert state.retained_evidence == operator.ROW_COUNT
    assert state.legacy_rows == operator.ROW_COUNT
    assert state.ledger_rows == 0
    assert state.missing_rows == ()
    assert state.writer_mode == "compatibility"
    assert not state.cursor_present


def test_seed_refuses_foreign_document_without_overwriting_it():
    db = _DB()
    path = operator._memory_path("proof-20260905", 0)
    db.docs[path] = {
        "memory_id": "customer-row",
        "uid": "customer-uid",
        "jit_qa_fixture": "someone-else",
    }
    with pytest.raises(operator.JITQAVerificationError, match="non-owned QA row"):
        operator.seed_fixture(db, run_id="proof-20260905")
    assert db.docs[path]["uid"] == "customer-uid"
    assert operator._evidence_path("proof-20260905", 0) not in db.docs


def test_fixture_exclusivity_fails_closed_without_a_queryable_collection():
    class PointOnlyDB:
        def document(self, path):
            return _Ref(_DB(), path)

    with pytest.raises(operator.JITQAVerificationError, match="cannot prove fixture exclusivity"):
        operator._assert_fixture_exclusive(PointOnlyDB(), run_id="proof-20260905")


def test_fixture_exclusivity_fails_closed_without_metadata_projection():
    class NoProjectionCollection:
        def limit(self, _value):
            return self

        def stream(self):
            return []

    class NoProjectionDB:
        def collection(self, _path):
            return NoProjectionCollection()

    with pytest.raises(operator.JITQAVerificationError, match="project fixture ownership metadata"):
        operator._assert_fixture_exclusive(NoProjectionDB(), run_id="proof-20260905")


def test_bootstrap_empty_inventory_rejects_any_present_collection():
    class UnboundedCollection:
        id = "users"

    class UnboundedDB:
        def collections(self):
            return [UnboundedCollection()]

    with pytest.raises(operator.JITQAVerificationError, match="truly empty"):
        operator._assert_named_database_empty(UnboundedDB())


def test_bootstrap_empty_inventory_accepts_no_collections():
    class EmptyDB:
        def collections(self):
            return []

    operator._assert_named_database_empty(EmptyDB())


def test_evidence_ownership_requires_full_source_metadata():
    db = _DB()
    operator.seed_fixture(db, run_id="proof-20260905")
    evidence = db.docs[operator._evidence_path("proof-20260905", 0)]
    evidence.pop("source_version")
    with pytest.raises(operator.JITQAVerificationError, match="foreign or malformed"):
        operator.inspect_fixture(db, run_id="proof-20260905")


def test_bootstrap_is_create_only_and_idempotent(monkeypatch):
    db = _DB(include_control=False)

    def ensure_control(uid, *, db_client):
        assert uid == operator.QA_UID
        control_ref = db_client.document(operator._control_path())
        if not control_ref.get().exists:
            control_ref.create(
                {
                    "uid": uid,
                    "writer_mode": "compatibility",
                    "writer_epoch": 0,
                    "head_commit_id": "head0",
                    "account_generation": 1,
                    "source_generation": 1,
                    "commit_sequence": 0,
                }
            )
        registry_ref = db_client.document(f"canonical_memory_maintenance_registry/{uid}")
        if not registry_ref.get().exists:
            registry_ref.create({"uid": uid, "schema_version": 1})
        return SimpleNamespace(uid=uid, writer_mode=SimpleNamespace(value="compatibility"))

    monkeypatch.setattr(operator, "ensure_canonical_apply_control_state", ensure_control)
    monkeypatch.setattr(operator, "validate_environment", lambda: None)

    first = operator.bootstrap_qa_account(db)
    assert first["profile"] == "created"
    assert first["tester"] == "created"
    assert db.docs[f"users/{operator.QA_UID}"]["time_zone"] == operator.QA_TIME_ZONE
    assert db.docs[f"users/{operator.QA_UID}"]["subscription"]["plan"] == operator.QA_ENTITLEMENT_PLAN
    assert db.docs[operator.TESTER_PATH]["test_account"] is True
    assert db.docs[operator.BOOTSTRAP_PATH]["status"] == "complete"

    before = {path: dict(payload) for path, payload in db.docs.items()}
    second = operator.bootstrap_qa_account(db)
    assert second["profile"] == "existing"
    assert second["tester"] == "existing"
    assert db.docs == before


def test_bootstrap_refuses_unowned_document_before_any_write(monkeypatch):
    db = _DB(include_control=False)
    db.docs["users/another-uid"] = {"uid": "another-uid"}
    monkeypatch.setattr(operator, "validate_environment", lambda: None)
    with pytest.raises(operator.JITQAVerificationError, match="truly empty"):
        operator.bootstrap_qa_account(db)
    assert operator.BOOTSTRAP_PATH not in db.docs


def test_summary_parser_accepts_workflow_envelope_and_rejects_missing_fields(tmp_path: Path):
    path = tmp_path / "drain.json"
    path.write_text(json.dumps({"execution": "knowledge-ledger-drain-qa-job-1", "summary": _summary()}))
    parsed = operator.load_summary(path)
    assert parsed["migrated_rows"] == 1

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"summary": {"errors": []}}))
    with pytest.raises(operator.JITQAVerificationError, match="missing fields"):
        operator.load_summary(bad)


def test_verify_requires_exact_bounded_page_shape():
    db = _DB()
    operator.seed_fixture(db, run_id="proof-20260905")
    run_id = "proof-20260905"
    for index in range(operator.ROW_COUNT):
        payload = db.docs[operator._memory_path(run_id, index)]
        payload.update(
            {
                "ledger_schema_version": operator.LEDGER_SCHEMA_VERSION,
                "write_reason": "legacy_migration",
                "status": "active",
                "item_revision": 2,
                "ledger_sequence": index + 1,
                "content_hash": f"hash-{index}",
            }
        )
    db.docs[operator._control_path()]["writer_mode"] = "ledger"
    db.docs[operator._completion_path()] = {
        "schema_version": "knowledge_ledger.v1",
        "status": "complete",
        "blocking_row_count": 0,
        "source_head_commit_id": "qa-head",
        "writer_epoch": 1,
    }
    db.docs[operator._projection_path()] = {
        "schema_version": "knowledge_ledger_prompt_projection.v1",
        "status": "complete",
        "uid": operator.QA_UID,
        "source_head_commit_id": "qa-head",
        "writer_epoch": 1,
        "legacy_row_count": 0,
        "blocking_row_count": 0,
        "scanned_row_count": operator.ROW_COUNT,
    }

    result = operator.verify_bounded_progress(
        db,
        run_id=run_id,
        first_summary=_summary(remaining_users=1, cutover_users=0, migrated_rows=100),
        second_summary=_summary(migrated_rows=1),
        retry_summary=_summary(
            inventoried_users=0,
            scanned_documents=1,
            attempted_users=0,
            cutover_users=0,
            migrated_rows=0,
        ),
    )
    assert result["result"] == "PASS"
    assert result["bounded_pages"] == [100, 1]
    assert result["retained_rows"] == operator.ROW_COUNT

    bad = _summary(remaining_users=1, cutover_users=0, migrated_rows=99)
    with pytest.raises(operator.JITQAVerificationError, match="first drain migrated_rows"):
        operator.verify_bounded_progress(
            db,
            run_id=run_id,
            first_summary=bad,
            second_summary=_summary(migrated_rows=1),
            retry_summary=_summary(
                inventoried_users=0,
                scanned_documents=1,
                attempted_users=0,
                cutover_users=0,
                migrated_rows=0,
            ),
        )

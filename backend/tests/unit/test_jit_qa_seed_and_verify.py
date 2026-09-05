from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# The migration import is intentionally top-level in the operator, matching
# backend import rules. Unit tests provide only the minimum synthetic key; no
# network or Firestore credential is used.
os.environ.setdefault("ENCRYPTION_SECRET", "x" * 32)

from scripts import jit_qa_seed_and_verify as operator


class _Snapshot:
    def __init__(self, payload: dict | None):
        self.exists = payload is not None
        self._payload = dict(payload or {})

    def to_dict(self):
        return dict(self._payload)


class _Ref:
    def __init__(self, db: "_DB", path: str):
        self.db = db
        self.path = path

    def select(self, _fields):
        return self

    def get(self):
        return _Snapshot(self.db.docs.get(self.path))

    def set(self, payload, merge=False):
        if merge and self.path in self.db.docs:
            self.db.docs[self.path].update(payload)
        else:
            self.db.docs[self.path] = dict(payload)


class _DB:
    def __init__(self):
        self.docs = {
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

    def document(self, path):
        return _Ref(self, path)


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

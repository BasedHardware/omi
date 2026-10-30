"""Operator-tool tests for the stale-planner archive restore (2026-10 incident).

Covers the contract from the remediation plan: dry-run is read-only and
payload-free, the selector matches the incident shape and excludes edited,
held, gated and deleted rows, apply goes through the canonical ledger with the
audit marker and is idempotent, and revert re-archives only marked rows.
"""

from __future__ import annotations

import copy
import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (
    CONSOLIDATION_APPLY_STUB_MODULE_NAMES,
    ensure_utils_memory_packages_importable,
    install_consolidation_apply_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)


@pytest.fixture(scope="module", autouse=True)
def _restore_tool_import_isolation():
    saved = snapshot_sys_modules(CONSOLIDATION_APPLY_STUB_MODULE_NAMES)
    touched = install_consolidation_apply_stubs()
    saved.update(snapshot_sys_modules(touched))
    ensure_utils_memory_packages_importable()
    for stale_module in ("database.memory_apply_store", "utils.memory.memory_system"):
        sys.modules.pop(stale_module, None)
    module = importlib.import_module("scripts.restore_stale_planner_archives")
    globals()["restore_tool"] = module
    yield
    restore_sys_modules(saved)


from models.memory_apply import MemoryControlState
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryTier, ProcessingState

WINDOW_FROM = datetime(2026, 10, 18, 23, 0, tzinfo=timezone.utc)
WINDOW_TO = datetime(2026, 10, 22, 18, 30, tzinfo=timezone.utc)
PROCESSED_AT = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
RETRY_RATIONALE = "Automatic consolidation exhausted its bounded retry budget; manual review is required."
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
MARKER = "stale-planner-2026-10-22"


class _Snapshot:
    def __init__(self, data=None, *, exists=True, doc_id=None, reference=None):
        self._data = data
        self.exists = exists
        self.id = doc_id
        self.reference = reference

    def to_dict(self):
        return self._data


class _Document:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self, transaction=None):
        if self.path not in self.db.docs:
            return _Snapshot(None, exists=False, doc_id=self.path.rsplit("/", 1)[-1], reference=self)
        return _Snapshot(self.db.docs[self.path], doc_id=self.path.rsplit("/", 1)[-1], reference=self)

    def set(self, data, merge=False):
        if merge and self.path in self.db.docs:
            self.db.docs[self.path] = {**self.db.docs[self.path], **data}
        else:
            self.db.docs[self.path] = data

    def update(self, data):
        if self.path not in self.db.docs:
            raise LookupError(self.path)
        self.db.docs[self.path] = {**self.db.docs[self.path], **data}

    def delete(self):
        self.db.docs.pop(self.path, None)

    def collection(self, name):
        return _ScanCollection(self.db, f"{self.path}/{name}")


class _Transaction:
    """Records sets/deletes; reads see committed state (single-writer tests)."""

    def __init__(self, db):
        self.db = db
        self.sets = []
        self.deletes = []
        self._read_only = False
        self._max_attempts = 1
        self._id = None

    def set(self, ref, data):
        self.sets.append((ref.path, data))

    def delete(self, ref):
        self.deletes.append(ref.path)

    def _begin(self, retry_id=None):
        self.sets = []
        self.deletes = []
        self._id = retry_id or "txn-1"

    def _commit(self):
        for path, data in self.sets:
            self.db.docs[path] = data
        for path in self.deletes:
            self.db.docs.pop(path, None)

    def _rollback(self):
        self.sets = []
        self.deletes = []

    def _clean_up(self):
        self._id = None


def _comparable(value: Any, reference: Any):
    """ISO-string payloads must compare against datetime query values."""
    if isinstance(value, str) and isinstance(reference, datetime):
        return datetime.fromisoformat(value)
    return value


def _norm_sort_value(value: Any) -> Any:
    """Normalize ISO strings to datetimes so sort keys and cursors line up."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


class _ScanCollection:
    def __init__(self, db, path, filters=None, orders=None, limit_count=None, cursor=None):
        self.db = db
        self.path = path
        self.filters = list(filters or [])
        self.orders = list(orders or [])
        self.limit_count = limit_count
        self.cursor = cursor

    def where(self, field_path=None, op_string=None, value=None, *, filter=None):
        if filter is not None:
            field_path, op_string, value = filter.field_path, filter.op_string, filter.value
        assert field_path is not None
        assert op_string in {"==", "in", ">=", "<=", "<", ">"}
        return _ScanCollection(
            self.db,
            self.path,
            [*self.filters, (field_path, op_string, value)],
            self.orders,
            self.limit_count,
            self.cursor,
        )

    def order_by(self, field_path):
        return _ScanCollection(
            self.db, self.path, self.filters, [*self.orders, field_path], self.limit_count, self.cursor
        )

    def start_after(self, cursor):
        return _ScanCollection(self.db, self.path, self.filters, self.orders, self.limit_count, cursor)

    def limit(self, limit_count):
        return _ScanCollection(self.db, self.path, self.filters, self.orders, limit_count, self.cursor)

    def document(self, doc_id):
        return _Document(self.db, f"{self.path}/{doc_id}")

    def stream(self):
        prefix = f"{self.path}/"
        rows = []
        for path, data in sorted(self.db.docs.items()):
            if not path.startswith(prefix) or "/" in path[len(prefix) :]:
                continue
            if all(self._matches(data, field, operator, value) for field, operator, value in self.filters):
                doc_id = path[len(prefix) :]
                rows.append((self._sort_key(data, doc_id), doc_id, data))
        rows.sort(key=lambda row: row[0])
        if self.cursor is not None:
            rows = self._apply_cursor(rows)
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return [
            _Snapshot(data, doc_id=doc_id, reference=_Document(self.db, f"{self.path}/{doc_id}"))
            for _sort_key, doc_id, data in rows
        ]

    def _apply_cursor(self, rows):
        """start_after: strictly after the first row matching a dict cursor's
        values (Firestore index-order semantics; the order-by tail makes the
        match unique), or strictly after a snapshot cursor's full key."""
        if isinstance(self.cursor, dict):
            cursor_values = tuple(
                _norm_sort_value(self.cursor[field_path]) for field_path in self.orders if field_path in self.cursor
            )
            if not cursor_values:
                raise AssertionError("cursor dict must key the order-by fields")
            width = len(cursor_values)
            for index, (key, _doc_id, _data) in enumerate(rows):
                if tuple(_norm_sort_value(value) for value in key[:width]) == cursor_values:
                    return rows[index + 1 :]
            return [row for row in rows if tuple(_norm_sort_value(value) for value in row[0][:width]) > cursor_values]
        payload = self.cursor.to_dict() or {}
        cursor_key = self._sort_key(payload, self.cursor.id)
        return [row for row in rows if row[0] > cursor_key]

    @staticmethod
    def _nested_value(data, field_path):
        current = data
        for part in str(field_path).split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @classmethod
    def _matches(cls, data, field_path, operator, expected):
        actual = cls._nested_value(data, field_path)
        if operator == "==":
            return actual == expected
        if operator == "in":
            return actual in expected
        comparable = _comparable(actual, expected)
        if comparable is None:
            return False
        if operator == ">=":
            return comparable >= expected
        if operator == "<=":
            return comparable <= expected
        if operator == "<":
            return comparable < expected
        if operator == ">":
            return comparable > expected
        raise AssertionError(f"unexpected operator {operator}")

    def _sort_key(self, data, doc_id):
        values = [
            doc_id if field_path == "__name__" else self._nested_value(data, field_path) for field_path in self.orders
        ]
        key = tuple([*values, doc_id] if "__name__" not in self.orders else values)
        return tuple(_norm_sort_value(value) for value in key)


class _ScanDb:
    def __init__(self, docs=None):
        self.docs: Dict[str, Any] = dict(docs or {})
        self.transaction_obj = _Transaction(self)

    def transaction(self):
        return self.transaction_obj

    def document(self, path):
        return _Document(self, path)

    def collection(self, path):
        return _ScanCollection(self, path)


def _evidence(evidence_id: str) -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id=evidence_id,
        source_type="conversation",
        source_id=f"conv-{evidence_id}",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _incident_item(
    uid: str,
    memory_id: str,
    *,
    processed_at: datetime = PROCESSED_AT,
    updated_at: Optional[datetime] = None,
    route: str = "review",
    rationale: str = RETRY_RATIONALE,
    processed_by: str = "canonical_batched_consolidation",
    user_review: Any = None,
    tier: MemoryTier = MemoryTier.archive,
    status: MemoryItemStatus = MemoryItemStatus.active,
    remediation: Optional[Dict[str, Any]] = None,
) -> MemoryItem:
    promotion: Dict[str, Any] = {
        "route": route,
        "reconciliation": "create",
        "rationale": rationale,
        "processing_status": "processed",
        "processed_at": processed_at,
        "processed_by": processed_by,
        "confidence": "low",
    }
    if user_review is not None:
        promotion["user_review"] = user_review
    if remediation is not None:
        promotion["remediation"] = remediation
    evidence = _evidence(f"ev_{memory_id}")
    return MemoryItem(
        memory_id=memory_id,
        uid=uid,
        version=1,
        tier=tier,
        status=status,
        processing_state=ProcessingState.processed,
        content=f"content-{memory_id}",
        evidence=[evidence],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=processed_at - timedelta(hours=6),
        updated_at=updated_at if updated_at is not None else processed_at,
        ledger_commit_id=f"commit_{memory_id}",
        ledger_sequence=1,
        source_commit_id=f"commit_{memory_id}",
        source_commit_sequence=1,
        content_hash=f"hash_{memory_id}",
        account_generation=1,
        promotion=promotion,
        expires_at=processed_at + timedelta(days=2) if tier == MemoryTier.short_term else None,
    )


def _seed_item(db: _ScanDb, item: MemoryItem) -> None:
    db.docs[f"users/{item.uid}/memory_items/{item.memory_id}"] = item.model_dump(mode="json")
    for evidence in item.evidence:
        db.docs[f"users/{item.uid}/memory_evidence/{evidence.evidence_id}"] = evidence.model_dump(mode="json")


def _seed_db(users: List[str]) -> _ScanDb:
    docs: Dict[str, Any] = {}
    for uid in users:
        docs[f"users/{uid}"] = {"uid": uid}
        docs[f"users/{uid}/memory_state/apply_control"] = MemoryControlState(
            uid=uid, head_commit_id="head0", account_generation=1, source_generation=1
        ).model_dump(mode="json")
    return _ScanDb(docs)


def _run(db: _ScanDb, mode: str = "dry-run", **overrides):
    tool = restore_tool
    kwargs: Dict[str, Any] = dict(
        db_client=db,
        mode=mode,
        project="based-hardware",
        window_from=WINDOW_FROM,
        window_to=WINDOW_TO,
        uid=None,
        users_from=None,
        page_size=3,
        max_reads=10_000,
        max_writes=50,
        run_id="test_run",
        now=NOW,
    )
    kwargs.update(overrides)
    return tool.run(**kwargs)


def test_dry_run_is_read_only_and_reports_counts():
    db = _seed_db(["uid-leak-canary", "uid-leak-held", "uid-leak-deleted"])
    _seed_item(db, _incident_item("uid-leak-canary", "mem-leak-1", processed_at=PROCESSED_AT))
    _seed_item(
        db,
        _incident_item("uid-leak-canary", "mem-leak-2", processed_at=PROCESSED_AT + timedelta(days=1)),
    )
    _seed_item(db, _incident_item("uid-leak-canary", "mem-edited", updated_at=PROCESSED_AT + timedelta(hours=1)))
    _seed_item(db, _incident_item("uid-leak-held", "mem-held-1"))
    _seed_item(db, _incident_item("uid-leak-deleted", "mem-deleted-1"))
    db.docs["legal_holds/uid-leak-held"] = {
        "schema_version": "legal_hold.v1",
        "issuer": "admin",
        "active": True,
        "updated_at": NOW,
    }
    db.docs["account_deletions/uid-leak-deleted"] = {"wipe_status": "running"}
    before = copy.deepcopy(db.docs)

    report = _run(db, mode="dry-run")

    assert db.docs == before, "dry run must not write anything"
    payload = report.to_json()
    assert payload["rows"]["matched"] == 2
    assert payload["users"]["excluded"] == {"deleted_user": 1, "legal_hold": 1}
    assert payload["rows"]["excluded_by_reason"] == {"edited_after_processing": 1}
    assert payload["matched_per_day"] == {"2026-10-20": 1, "2026-10-21": 1}
    assert payload["per_user_buckets"] == {"1": 0, "2-4": 1, "5-20": 0, "21-100": 0, ">100": 0}
    assert payload["writes"]["committed"] == 0 and payload["writes"]["attempted"] == 0
    assert payload["reads"]["documents"] > 0
    assert payload["mode"] == "dry-run"
    rendered = json.dumps(payload)
    for token in ("uid-leak", "mem-leak", "mem-edited", "mem-held", "mem-deleted", "content-"):
        assert token not in rendered, f"dry-run output must not contain {token}"
    assert len(payload["samples"]) == 2
    assert set(payload["samples"][0]) == {
        "route",
        "reconciliation",
        "processing_status",
        "confidence",
        "evidence_count",
        "sensitivity_label_count",
        "user_asserted",
        "captured_to_processed_hours",
    }


def test_selector_matches_incident_shapes_and_excludes_others():
    db = _seed_db(["uid-sel"])
    matched = [
        _incident_item("uid-sel", "mem-review", route="review"),
        _incident_item("uid-sel", "mem-archive-rationale", route="archive"),
    ]
    for item in matched:
        _seed_item(db, item)
    _seed_item(db, _incident_item("uid-sel", "mem-benign-archive", route="archive", rationale="Not interesting"))
    _seed_item(db, _incident_item("uid-sel", "mem-other-processor", processed_by="dream_agent"))
    _seed_item(db, _incident_item("uid-sel", "mem-user-reviewed", user_review=False))
    _seed_item(db, _incident_item("uid-sel", "mem-hidden", status=MemoryItemStatus.hidden))
    _seed_item(db, _incident_item("uid-sel", "mem-still-short-term", tier=MemoryTier.short_term))

    report = _run(db, mode="dry-run")

    assert report.rows_matched == 2
    assert dict(report.row_exclusions) == {"route_not_incident": 1, "processed_by_mismatch": 1, "user_reviewed": 1}
    # tier/status filters are served by the query itself, so those rows never surface.


def test_dry_run_excludes_accounts_under_destructive_gate():
    db = _seed_db(["uid-gated"])
    _seed_item(db, _incident_item("uid-gated", "mem-gated-1"))
    db.docs["legal_hold_deletion_gates/uid-gated"] = {
        "schema_version": "legal_hold_deletion_gate.v1",
        "uid": "uid-gated",
        "kind": "explicit_memory_deletion",
        "token": "tok",
        "state": "running",
        "started_at": NOW - timedelta(minutes=5),
        "finished_at": None,
    }

    report = _run(db, mode="dry-run")

    assert report.rows_matched == 0
    assert dict(report.users_excluded) == {"destructive_gate": 1}


def test_apply_restores_through_the_ledger_with_marker_and_is_idempotent():
    uid = "uid-apply"
    db = _seed_db([uid])
    items = [
        _incident_item(uid, "mem-restore-1", processed_at=PROCESSED_AT),
        _incident_item(uid, "mem-restore-2", processed_at=PROCESSED_AT + timedelta(days=1)),
    ]
    for item in items:
        _seed_item(db, item)

    report = _run(db, mode="apply")

    assert report.errors == []
    assert report.writes_attempted == 2
    assert report.writes_committed == 2
    assert report.writes_idempotent == 0
    assert report.outbox_events_enqueued > 0
    assert any(path.startswith(f"users/{uid}/memory_commits/") for path in db.docs), "must use the apply ledger"
    for item in items:
        restored = MemoryItem.model_validate(db.docs[f"users/{uid}/memory_items/{item.memory_id}"])
        assert restored.tier == MemoryTier.short_term
        assert restored.status == MemoryItemStatus.active
        assert restored.item_revision == item.item_revision + 1
        remediation = restored.promotion["remediation"]
        assert remediation["marker"] == MARKER
        assert remediation["action"] == "restore"
        assert remediation["previous_tier"] == "archive"
        assert remediation["restored_at"] == NOW
        # The historical incident audit stays intact next to the marker.
        assert restored.promotion["route"] == "review"
        assert restored.promotion["processed_by"] == "canonical_batched_consolidation"

    second = _run(db, mode="apply")
    assert second.rows_matched == 0, "restored rows leave the archive selector"
    assert second.writes_attempted == 0


def test_apply_respects_the_write_budget_and_reports_stopped_early():
    uid = "uid-budget"
    db = _seed_db([uid])
    for index in range(3):
        _seed_item(db, _incident_item(uid, f"mem-budget-{index}", processed_at=PROCESSED_AT))

    report = _run(db, mode="apply", max_writes=2)

    assert report.writes_committed == 2
    assert report.writes_stopped_early is True
    assert report.scan_truncated is True
    remaining = sum(
        1
        for path, data in db.docs.items()
        if path.startswith(f"users/{uid}/memory_items/") and MemoryItem.model_validate(data).tier == MemoryTier.archive
    )
    assert remaining == 1


def test_read_budget_stops_the_scan_and_reports_it():
    db = _seed_db(["uid-reads"])
    _seed_item(db, _incident_item("uid-reads", "mem-reads-1"))

    report = _run(db, mode="dry-run", max_reads=2)

    assert report.reads_exhausted is True
    assert report.scan_truncated is True
    assert report.reads_used > 2


def test_revert_re_archives_only_rows_carrying_the_marker():
    uid = "uid-revert"
    db = _seed_db([uid])
    restored = _incident_item(
        uid,
        "mem-revert-1",
        tier=MemoryTier.short_term,
        remediation={"marker": MARKER, "action": "restore", "restored_at": NOW - timedelta(hours=1)},
    )
    unmarked = _incident_item(uid, "mem-revert-unmarked", tier=MemoryTier.short_term)
    for item in (restored, unmarked):
        _seed_item(db, item)

    report = _run(db, mode="revert")

    assert report.errors == []
    assert report.rows_matched == 1
    assert report.writes_committed == 1
    reverted = MemoryItem.model_validate(db.docs[f"users/{uid}/memory_items/{restored.memory_id}"])
    assert reverted.tier == MemoryTier.archive
    assert reverted.status == MemoryItemStatus.active
    assert reverted.promotion["remediation"]["marker"] == MARKER
    assert reverted.promotion["remediation"]["action"] == "revert"
    assert reverted.promotion["remediation"]["reverted_at"] == NOW
    untouched = MemoryItem.model_validate(db.docs[f"users/{uid}/memory_items/{unmarked.memory_id}"])
    assert untouched.tier == MemoryTier.short_term
    assert untouched.item_revision == unmarked.item_revision


def test_apply_and_revert_round_trip_through_both_scans():
    uid = "uid-roundtrip"
    db = _seed_db([uid])
    original = _incident_item(uid, "mem-roundtrip-1")
    _seed_item(db, original)

    applied = _run(db, mode="apply")
    assert applied.writes_committed == 1
    reverted = _run(db, mode="revert")
    assert reverted.writes_committed == 1
    final = MemoryItem.model_validate(db.docs[f"users/{uid}/memory_items/{original.memory_id}"])
    assert final.tier == MemoryTier.archive
    assert final.promotion["remediation"]["action"] == "revert"
    # The reverted row still matches the incident selector but carries the marker.
    redry = _run(db, mode="dry-run")
    assert redry.rows_matched == 0
    assert dict(redry.row_exclusions) == {"already_marked": 1}


def test_no_output_identifies_a_user_in_any_mode():
    uid = "uid-privacy-check"
    db = _seed_db([uid])
    _seed_item(db, _incident_item(uid, "mem-privacy-1"))

    for mode in ("dry-run", "apply", "revert"):
        report = _run(db, mode=mode)
        rendered = json.dumps(report.to_json())
        assert "uid-privacy" not in rendered
        assert "mem-privacy" not in rendered
        assert "content-" not in rendered

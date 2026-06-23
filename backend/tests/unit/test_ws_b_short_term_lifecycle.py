"""WS-B canonical short-term promotion + TTL lifecycle tests."""

from __future__ import annotations

import hashlib
import os
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_db_client_mod = types.ModuleType("database._client")
_db_client_mod.db = MagicMock()


def _document_id_from_seed(seed: str) -> str:
    seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=seed_hash[:16], version=4))


_db_client_mod.document_id_from_seed = _document_id_from_seed
sys.modules.setdefault("database._client", _db_client_mod)

from models.memory_domain import MemoryLayer, MemoryProcessingState, MemoryRecordStatus
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_memory_apply import MemoryControlState
from models.v17_product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.canonical_memory_adapter import read_canonical_memories, write_canonical_extraction_memory
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from utils.memory.short_term_promotion import (
    DEFAULT_PROMOTION_BATCH_THRESHOLD,
    promotion_batch_threshold,
    promotion_trigger_reason,
    run_canonical_short_term_promotion,
    run_canonical_short_term_ttl_lifecycle,
)
from tests.unit.test_ws_i_write_convergence import (
    _FakeDb,
    _sample_memory_payload,
    _trusted_account_generation,
)


NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _DocRef:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def get(self, transaction=None):
        if self.path not in self._db.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self._db.docs[self.path], exists=True)

    def set(self, data, merge=False):
        self._db.docs[self.path] = data


class _CollectionRef:
    def __init__(self, db, path, filters=None, limit_count=None):
        self._db = db
        self.path = path
        self._filters = list(filters or [])
        self._limit_count = limit_count

    def where(self, field_path, op_string, value):
        return _CollectionRef(
            self._db,
            self.path,
            [*self._filters, (field_path, op_string, value)],
            limit_count=self._limit_count,
        )

    def limit(self, limit_count):
        return _CollectionRef(self._db, self.path, self._filters, limit_count=limit_count)

    def stream(self):
        prefix = f"{self.path}/"
        snapshots = []
        for path, data in sorted(self._db.docs.items()):
            if not path.startswith(prefix) or "/" in path[len(prefix) :]:
                continue
            if all(self._matches(data, field_path, op_string, value) for field_path, op_string, value in self._filters):
                snapshots.append(_Snapshot(data, exists=True))
        if self._limit_count is not None:
            snapshots = snapshots[: self._limit_count]
        for snapshot in snapshots:
            yield snapshot

    def _matches(self, data, field_path, op_string, value):
        if op_string != "==":
            raise AssertionError(f"unexpected query operator {op_string}")
        return data.get(field_path) == value


class _FakeTransaction:
    def __init__(self, db):
        self._db = db
        self.sets = []
        self._read_only = False
        self._max_attempts = 1
        self._id = None

    def set(self, ref, data):
        path = ref.path if hasattr(ref, "path") else ref
        self.sets.append((path, data))

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self.sets = []
        self._id = retry_id or "txn-1"

    def _commit(self):
        for path, data in self.sets:
            self._db.docs[path] = data

    def _rollback(self):
        self._id = None


class _PromotionFakeDb(_FakeDb):
    def __init__(self, docs=None):
        super().__init__(docs)
        self.transaction_obj = _FakeTransaction(self)

    def collection(self, path):
        return _CollectionRef(self, path)


def _canonical_db_with_control(uid: str = "uid-canonical") -> _PromotionFakeDb:
    return _PromotionFakeDb(
        {
            f"users/{uid}/memory_control/state": MemoryControlState(
                uid=uid,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json"),
        }
    )


def _seed_canonical_short_term(
    db: _PromotionFakeDb,
    *,
    uid: str,
    conversation_id: str,
    content: str,
    monkeypatch,
) -> str:
    evidence_id = f"ev_{conversation_id}"
    db.docs[f"users/{uid}/memory_evidence/{evidence_id}"] = MemoryEvidence(
        evidence_id=evidence_id,
        source_type="conversation",
        source_id=conversation_id,
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    ).model_dump(mode="json")
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_v17_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    payload["evidence"][0]["evidence_id"] = evidence_id
    return write_canonical_extraction_memory(uid, payload, db_client=db)


def _set_canonical_cohort(monkeypatch, uid: str) -> None:
    monkeypatch.setenv("MEMORY_CANONICAL_USERS", uid)


@pytest.fixture(autouse=True)
def _clear_canonical_env(monkeypatch):
    monkeypatch.delenv("MEMORY_CANONICAL_USERS", raising=False)


def test_promotion_fires_on_batch_threshold_via_apply(monkeypatch):
    uid = "uid-canonical-batch"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    threshold = promotion_batch_threshold()
    memory_ids = []
    for index in range(threshold):
        memory_ids.append(
            _seed_canonical_short_term(
                db,
                uid=uid,
                conversation_id=f"conv-batch-{index}",
                content=f"Fact number {index}",
                monkeypatch=monkeypatch,
            )
        )

    report = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-batch-1")

    assert report.skipped_reason is None
    assert report.trigger_reason == "batch_threshold"
    assert report.promoted_count == threshold
    for memory_id in memory_ids:
        stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
        assert stored["tier"] == MemoryTier.long_term.value
        assert stored["status"] == MemoryItemStatus.active.value
        assert stored["processing_state"] == ProcessingState.processed.value
        assert stored.get("expires_at") is None
        assert stored.get("promotion", {}).get("from_layer") == MemoryTier.short_term.value
        assert stored.get("promotion", {}).get("to_layer") == MemoryTier.long_term.value
        transitions = [path for path in db.docs if path.startswith(f"users/{uid}/short_term_lifecycle_transitions/")]
        assert transitions, "expected lifecycle transition audit"
        assert any(db.docs[path]["outcome"] == "promote_to_long_term" for path in transitions)


def test_promotion_fires_on_daily_elapsed_below_batch_threshold(monkeypatch):
    uid = "uid-canonical-daily"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        last_promotion_run_at=NOW - timedelta(hours=25),
    )
    db.docs[f"users/{uid}/memory_control/state"] = control.model_dump(mode="json")

    memory_id = _seed_canonical_short_term(
        db,
        uid=uid,
        conversation_id="conv-daily",
        content="User lives in Seattle",
        monkeypatch=monkeypatch,
    )

    report = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-daily-1")

    assert report.trigger_reason == "daily_elapsed"
    assert report.promoted_count == 1
    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert stored["tier"] == MemoryTier.long_term.value


def test_promotion_does_not_fire_when_neither_condition_met(monkeypatch):
    uid = "uid-canonical-hold"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        last_promotion_run_at=NOW - timedelta(hours=1),
    )
    db.docs[f"users/{uid}/memory_control/state"] = control.model_dump(mode="json")
    memory_id = _seed_canonical_short_term(
        db,
        uid=uid,
        conversation_id="conv-hold",
        content="User likes tea",
        monkeypatch=monkeypatch,
    )

    report = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-hold-1")

    assert report.skipped_reason == "promotion_not_due"
    assert report.promoted_count == 0
    assert db.docs[f"users/{uid}/memory_items/{memory_id}"]["tier"] == MemoryTier.short_term.value


def test_promoted_item_readable_and_idempotent_on_second_run(monkeypatch):
    uid = "uid-canonical-idem"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    threshold = promotion_batch_threshold()
    for index in range(threshold):
        _seed_canonical_short_term(
            db,
            uid=uid,
            conversation_id=f"conv-idem-{index}",
            content=f"Readable fact {index}",
            monkeypatch=monkeypatch,
        )

    first = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-idem-1")
    assert first.promoted_count == threshold
    memories = read_canonical_memories(uid, db_client=db)
    assert len(memories) == threshold
    assert all(memory.memory_tier == MemoryTier.long_term for memory in memories)

    second = run_canonical_short_term_promotion(uid, db_client=db, now=NOW + timedelta(hours=1), run_id="promo-idem-2")
    assert second.promoted_count == 0
    assert len(read_canonical_memories(uid, db_client=db)) == threshold


def test_expired_short_term_hidden_from_default_reads(monkeypatch):
    uid = "uid-canonical-ttl"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    memory_id = _seed_canonical_short_term(
        db,
        uid=uid,
        conversation_id="conv-ttl",
        content="Ephemeral note",
        monkeypatch=monkeypatch,
    )
    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    captured_at = NOW - timedelta(days=2)
    stored["captured_at"] = captured_at.isoformat()
    stored["updated_at"] = captured_at.isoformat()
    stored["expires_at"] = (NOW - timedelta(days=1)).isoformat()
    db.docs[f"users/{uid}/memory_items/{memory_id}"] = stored

    ttl_report = run_canonical_short_term_ttl_lifecycle(uid, db_client=db, now=NOW, run_id="ttl-1")
    assert ttl_report.skipped_reason is None
    assert ttl_report.lifecycle_created_count >= 1
    assert read_canonical_memories(uid, db_client=db) == []


def test_legacy_uid_promotion_and_lifecycle_are_noop(monkeypatch):
    uid = "uid-legacy"
    assert resolve_memory_system(uid, db_client=_PromotionFakeDb()) == MemorySystem.LEGACY
    db = _canonical_db_with_control(uid)
    promotion = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="legacy-promo")
    lifecycle = run_canonical_short_term_ttl_lifecycle(uid, db_client=db, now=NOW, run_id="legacy-ttl")
    assert promotion.skipped_reason == "not_canonical_cohort"
    assert lifecycle.skipped_reason == "not_canonical_cohort"


def test_promotion_trigger_reason_batch_default():
    assert promotion_batch_threshold() == DEFAULT_PROMOTION_BATCH_THRESHOLD
    assert promotion_trigger_reason(promotable_count=25, last_promotion_run_at=NOW, now=NOW) == "batch_threshold"
    assert (
        promotion_trigger_reason(
            promotable_count=1,
            last_promotion_run_at=NOW - timedelta(hours=25),
            now=NOW,
        )
        == "daily_elapsed"
    )
    assert (
        promotion_trigger_reason(
            promotable_count=1,
            last_promotion_run_at=NOW - timedelta(hours=1),
            now=NOW,
        )
        is None
    )


def test_memory_control_state_coerces_naive_firestore_timestamps():
    naive = datetime(2026, 6, 1, 12, 0, 0)
    control = MemoryControlState(
        uid="uid-canonical",
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        last_promotion_run_at=naive,
        updated_at=naive,
    )
    assert control.last_promotion_run_at is not None
    assert control.last_promotion_run_at.tzinfo == timezone.utc
    assert control.updated_at.tzinfo == timezone.utc
    assert control.last_promotion_run_at == datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_expired_and_pending_short_term_not_promoted_when_batch_threshold_met(monkeypatch):
    uid = "uid-canonical-negative"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    threshold = promotion_batch_threshold()

    eligible_ids = []
    for index in range(threshold):
        eligible_ids.append(
            _seed_canonical_short_term(
                db,
                uid=uid,
                conversation_id=f"conv-eligible-{index}",
                content=f"Eligible fact {index}",
                monkeypatch=monkeypatch,
            )
        )

    expired_id = _seed_canonical_short_term(
        db,
        uid=uid,
        conversation_id="conv-expired",
        content="Expired fact",
        monkeypatch=monkeypatch,
    )
    expired_stored = db.docs[f"users/{uid}/memory_items/{expired_id}"]
    captured_at = NOW - timedelta(days=2)
    expired_stored["captured_at"] = captured_at.isoformat()
    expired_stored["updated_at"] = captured_at.isoformat()
    expired_stored["expires_at"] = (NOW - timedelta(days=1)).isoformat()
    db.docs[f"users/{uid}/memory_items/{expired_id}"] = expired_stored

    pending_id = _seed_canonical_short_term(
        db,
        uid=uid,
        conversation_id="conv-pending",
        content="Pending fact",
        monkeypatch=monkeypatch,
    )
    pending_stored = db.docs[f"users/{uid}/memory_items/{pending_id}"]
    pending_stored["processing_state"] = ProcessingState.pending.value
    db.docs[f"users/{uid}/memory_items/{pending_id}"] = pending_stored

    report = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-negative-1")

    assert report.trigger_reason == "batch_threshold"
    assert report.promoted_count == threshold
    assert set(report.promoted_memory_ids) == set(eligible_ids)
    assert expired_id not in report.promoted_memory_ids
    assert pending_id not in report.promoted_memory_ids
    assert db.docs[f"users/{uid}/memory_items/{expired_id}"]["tier"] == MemoryTier.short_term.value
    assert db.docs[f"users/{uid}/memory_items/{pending_id}"]["tier"] == MemoryTier.short_term.value
    for memory_id in eligible_ids:
        assert db.docs[f"users/{uid}/memory_items/{memory_id}"]["tier"] == MemoryTier.long_term.value

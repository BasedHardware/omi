"""WS-B canonical short-term promotion + TTL lifecycle tests."""

from __future__ import annotations

import os
import sys
import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import NotFound

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (
    WS_B_STUB_MODULE_NAMES,
    ensure_utils_memory_packages_importable,
    install_ws_b_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

read_canonical_memories = None
write_canonical_extraction_memory = None
required_promotion_payload = None
ProcessedRequiredMemory = None
process_required_memory_item = None
update_canonical_memory_content = None
update_canonical_memory_review = None
MemorySystem = None
resolve_memory_system = None
CanonicalKgPromotionResult = None
DEFAULT_PROMOTION_BATCH_THRESHOLD = None
promotion_batch_threshold = None
promotion_trigger_reason = None
run_canonical_short_term_promotion = None
run_canonical_short_term_ttl_lifecycle = None
promote_short_term_item_via_apply = None


def _load_ws_b_runtime_modules() -> None:
    ensure_utils_memory_packages_importable()
    canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    short_term_promotion = importlib.import_module("utils.memory.short_term_promotion")
    required_promotion = importlib.import_module("utils.memory.required_promotion")
    required_processing = importlib.import_module("utils.memory.canonical_required_processing")
    memory_system = importlib.import_module("utils.memory.memory_system")
    canonical_kg_promotion = importlib.import_module("utils.memory.canonical_kg_promotion")

    g = globals()
    g["read_canonical_memories"] = canonical_adapter.read_canonical_memories
    g["write_canonical_extraction_memory"] = canonical_adapter.write_canonical_extraction_memory
    g["required_promotion_payload"] = required_promotion.required_promotion_payload
    g["ProcessedRequiredMemory"] = required_processing.ProcessedRequiredMemory
    g["process_required_memory_item"] = required_processing.process_required_memory_item
    g["update_canonical_memory_content"] = canonical_adapter.update_canonical_memory_content
    g["update_canonical_memory_review"] = canonical_adapter.update_canonical_memory_review
    g["MemorySystem"] = memory_system.MemorySystem
    g["resolve_memory_system"] = memory_system.resolve_memory_system
    g["CanonicalKgPromotionResult"] = canonical_kg_promotion.CanonicalKgPromotionResult
    g["DEFAULT_PROMOTION_BATCH_THRESHOLD"] = short_term_promotion.DEFAULT_PROMOTION_BATCH_THRESHOLD
    g["promotion_batch_threshold"] = short_term_promotion.promotion_batch_threshold
    g["promotion_trigger_reason"] = short_term_promotion.promotion_trigger_reason
    g["run_canonical_short_term_promotion"] = short_term_promotion.run_canonical_short_term_promotion
    g["run_canonical_short_term_ttl_lifecycle"] = short_term_promotion.run_canonical_short_term_ttl_lifecycle
    g["promote_short_term_item_via_apply"] = short_term_promotion.promote_short_term_item_via_apply


def _clear_ws_b_runtime_modules() -> None:
    g = globals()
    for name in (
        "read_canonical_memories",
        "write_canonical_extraction_memory",
        "required_promotion_payload",
        "ProcessedRequiredMemory",
        "process_required_memory_item",
        "update_canonical_memory_content",
        "update_canonical_memory_review",
        "MemorySystem",
        "resolve_memory_system",
        "CanonicalKgPromotionResult",
        "DEFAULT_PROMOTION_BATCH_THRESHOLD",
        "promotion_batch_threshold",
        "promotion_trigger_reason",
        "run_canonical_short_term_promotion",
        "run_canonical_short_term_ttl_lifecycle",
        "promote_short_term_item_via_apply",
    ):
        g[name] = None


@pytest.fixture(scope="module", autouse=True)
def _ws_b_import_isolation():
    saved = snapshot_sys_modules((*WS_B_STUB_MODULE_NAMES, *_WS_B_RUNTIME_MODULE_NAMES))
    touched = install_ws_b_import_stubs()
    saved.update(snapshot_sys_modules(touched))
    ensure_utils_memory_packages_importable()

    for stale_module in _WS_B_RUNTIME_MODULE_NAMES:
        sys.modules.pop(stale_module, None)

    _load_ws_b_runtime_modules()

    yield
    restore_sys_modules(saved)
    _clear_ws_b_runtime_modules()


from models.memory_domain import MemoryLayer, MemoryProcessingState, MemoryRecordStatus
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from tests.unit.test_ws_i_write_convergence import (
    _FakeDb,
    _sample_memory_payload,
    _trusted_account_generation,
)

# Anchored to the real clock rather than a fixed calendar date. Several cases persist an
# item through write_canonical_extraction_memory, which has no clock parameter and stamps
# captured_at from the real clock, and then drive processing with now=NOW. A fixed NOW
# meant expires_at (NOW + DEFAULT_SHORT_TERM_TTL_DAYS) eventually fell behind real
# captured_at, and the short_term "expires_at must be after captured_at" invariant started
# failing on its own — with no code change — once the wall clock passed that date.
NOW = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

_WS_B_RUNTIME_MODULE_NAMES = (
    "database.memory_apply_store",
    "utils.memory.canonical_memory_adapter",
    "utils.memory.short_term_promotion",
    "utils.memory.required_promotion",
    "utils.memory.canonical_required_processing",
    "utils.memory.memory_system",
    "utils.memory.canonical_kg_promotion",
)


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
        if merge and self.path in self._db.docs:
            self._db.docs[self.path] = self._db.docs[self.path] | data
            return
        self._db.docs[self.path] = data

    def update(self, data):
        if self.path not in self._db.docs:
            raise NotFound(f"Document {self.path} not found")
        self._db.docs[self.path] = self._db.docs[self.path] | data


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
            f"users/{uid}/memory_state/apply_control": MemoryControlState(
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
    _load_ws_b_runtime_modules()
    evidence_id = f"ev_{conversation_id}"
    db.docs[f"users/{uid}/memory_evidence/{evidence_id}"] = MemoryEvidence(
        evidence_id=evidence_id,
        source_type="conversation",
        source_id=conversation_id,
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    ).model_dump(mode="json")
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    payload["evidence"][0]["evidence_id"] = evidence_id
    return write_canonical_extraction_memory(uid, payload, db_client=db)


def _set_canonical_cohort(monkeypatch, *uids: str) -> None:
    from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort

    set_canonical_cohort(monkeypatch, *uids)


def _process_required(db: _PromotionFakeDb, uid: str, memory_id: str, *, content: str) -> None:
    result = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=lambda _item: ProcessedRequiredMemory(
            content=content,
            subject_entity_id="user",
            predicate="remembered_preference",
            arguments={"statement": content},
            rationale="test normalization",
        ),
        now=NOW,
    )
    assert result.processed is True


def _make_existing_long_term(db: _PromotionFakeDb, uid: str, memory_id: str) -> None:
    path = f"users/{uid}/memory_items/{memory_id}"
    db.docs[path]["tier"] = MemoryTier.long_term.value
    db.docs[path]["expires_at"] = None
    db.docs[path]["subject_entity_id"] = "user"
    db.docs[path]["predicate"] = "remembered_preference"
    db.docs[path]["arguments"] = {"statement": db.docs[path]["content"]}


@pytest.fixture(autouse=True)
def _clear_canonical_cohort_fixture(monkeypatch):
    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    _load_ws_b_runtime_modules()
    clear_canonical_cohort(monkeypatch)
    monkeypatch.setattr(
        "utils.memory.short_term_promotion.extract_kg_for_promoted_memory",
        lambda *_, **__: CanonicalKgPromotionResult(attempted=True, success=True),
    )


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
    db.docs[f"users/{uid}/memory_state/apply_control"] = control.model_dump(mode="json")

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
    db.docs[f"users/{uid}/memory_state/apply_control"] = control.model_dump(mode="json")
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
    assert promotion_trigger_reason(promotable_count=25, last_promotion_run_at=None, now=NOW) == "batch_threshold"
    assert (
        promotion_trigger_reason(
            promotable_count=1,
            last_promotion_run_at=None,
            now=NOW,
            required_promotion_count=1,
        )
        == "required_promotion"
    )
    assert (
        promotion_trigger_reason(
            promotable_count=1,
            last_promotion_run_at=None,
            now=NOW,
        )
        is None
    )
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


def test_promotion_does_not_fire_on_first_run_below_batch_threshold(monkeypatch):
    uid = "uid-canonical-first-tick"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    memory_id = _seed_canonical_short_term(
        db,
        uid=uid,
        conversation_id="conv-first-tick",
        content="User enjoys hiking",
        monkeypatch=monkeypatch,
    )

    report = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-first-tick")

    assert report.skipped_reason == "promotion_not_due"
    assert report.promoted_count == 0
    assert db.docs[f"users/{uid}/memory_items/{memory_id}"]["tier"] == MemoryTier.short_term.value


def test_required_promotion_manual_write_starts_short_term(monkeypatch):
    uid = "uid-canonical-required-manual"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    payload = required_promotion_payload(
        {
            "id": "manual-required-1",
            "content": "User prefers concise launch checklists",
            "manually_added": True,
        },
        source_surface="mcp",
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)
    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]

    assert stored["tier"] == MemoryTier.short_term.value
    assert stored["processing_state"] == ProcessingState.pending.value
    assert stored["user_asserted"] is True
    assert stored["promotion"]["required"] is True
    assert stored["promotion"]["status"] == "pending"
    assert stored["promotion"]["processing_status"] == "pending_processing"
    assert stored["promotion"]["source_surface"] == "mcp"
    assert not any(path.startswith(f"users/{uid}/memory_outbox/") for path in db.docs)
    assert read_canonical_memories(uid, db_client=db) == []
    visible = read_canonical_memories(uid, db_client=db, include_pending_processing=True)
    assert [memory.id for memory in visible] == [memory_id]
    assert visible[0].memory_tier == MemoryTier.short_term


def test_required_processing_preserves_non_manual_integration_classification():
    payload = required_promotion_payload(
        {
            "id": "integration-required-1",
            "content": "The account uses a weekly planning ritual",
            "manually_added": False,
        },
        source_surface="integration:planner",
    )

    assert payload["manually_added"] is False
    assert payload["user_asserted"] is False
    assert payload["promotion"]["required"] is True
    assert payload["promotion"]["processing_status"] == "pending_processing"


def test_required_promotion_waits_for_processing_receipt(monkeypatch):
    uid = "uid-canonical-required-promotion"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    monkeypatch.setattr("utils.memory.short_term_promotion.sync_canonical_memory_vector", lambda *_, **__: None)
    monkeypatch.setattr(
        "utils.memory.short_term_promotion.extract_kg_for_promoted_memory",
        lambda *_, **__: CanonicalKgPromotionResult(attempted=True, success=True),
    )
    payload = required_promotion_payload(
        {
            "id": "manual-required-2",
            "content": "User wants MCP memories promoted after review",
            "manually_added": True,
        },
        source_surface="developer_api",
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)

    report = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-required-1")
    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]

    assert report.skipped_reason == "promotion_not_due"
    assert report.promoted_memory_ids == []
    assert stored["tier"] == MemoryTier.short_term.value
    assert stored["processing_state"] == ProcessingState.pending.value
    assert stored["promotion"]["required"] is True
    assert stored["promotion"]["processing_status"] == "pending_processing"
    assert stored["promotion"]["source_surface"] == "developer_api"


def test_required_processing_receipt_unlocks_durable_promotion(monkeypatch):
    uid = "uid-canonical-required-processed"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    payload = required_promotion_payload(
        {"id": "manual-required-processed", "content": "remember that I like tea", "manually_added": True},
        source_surface="plugin:notes",
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)

    _process_required(db, uid, memory_id, content="The user prefers tea.")
    processed = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert processed["processing_state"] == ProcessingState.processed.value
    assert processed["promotion"]["processing_status"] == "processed"
    assert processed["promotion"]["processing_receipt"]["source_submission_id"] == "manual-required-processed"

    report = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-required-processed")
    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert report.promoted_memory_ids == [memory_id]
    assert stored["tier"] == MemoryTier.long_term.value
    assert stored["promotion"]["processing_receipt"]["processor_id"] == "canonical_required_memory"


def test_required_processing_receipt_is_bound_to_current_content_and_revision(monkeypatch):
    uid = "uid-canonical-required-stale-receipt"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    payload = required_promotion_payload(
        {"id": "manual-stale-receipt", "content": "Remember tea", "manually_added": True},
        source_surface="mcp",
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)
    _process_required(db, uid, memory_id, content="The user prefers tea.")
    item_path = f"users/{uid}/memory_items/{memory_id}"
    db.docs[item_path]["content"] = "Tampered content"

    report = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-stale-receipt")

    assert report.promoted_memory_ids == []
    assert report.skipped_reason == "promotion_not_due"
    assert db.docs[item_path]["tier"] == MemoryTier.short_term.value


def test_inflight_processor_cannot_overwrite_newer_user_edit(monkeypatch):
    uid = "uid-canonical-required-edit-race"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    payload = required_promotion_payload(
        {"id": "manual-edit-race", "content": "Old preference", "manually_added": True},
        source_surface="mcp",
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)

    def edit_then_return(_item):
        update_canonical_memory_content(uid, memory_id, "New preference", db_client=db)
        return ProcessedRequiredMemory(
            content="Old normalized preference",
            subject_entity_id="user",
            predicate="remembered_preference",
            arguments={"statement": "Old normalized preference"},
        )

    result = process_required_memory_item(uid, memory_id, db_client=db, processor=edit_then_return, now=NOW)
    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]

    assert result.processed is False
    assert result.skipped_reason == "newer_revision_pending"
    assert stored["content"] == "New preference"
    assert stored["processing_state"] == ProcessingState.pending.value


def test_negative_user_review_blocks_processing_and_promotion(monkeypatch):
    uid = "uid-canonical-required-rejected"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    payload = required_promotion_payload(
        {"id": "manual-rejected", "content": "Do not keep this", "manually_added": True},
        source_surface="mcp",
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    initial_revision = db.docs[item_path]["item_revision"]
    rejected = update_canonical_memory_review(uid, memory_id, False, db_client=db)

    assert rejected.item_revision == initial_revision + 1
    assert rejected.processing_state == ProcessingState.pending
    restored = update_canonical_memory_review(uid, memory_id, True, db_client=db)
    assert restored.processing_state == ProcessingState.pending
    assert restored.promotion["processing_status"] == "pending_processing"
    update_canonical_memory_review(uid, memory_id, False, db_client=db)

    processed = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=lambda _item: ProcessedRequiredMemory(content="Should not run"),
        now=NOW,
    )
    promotion = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-rejected")

    assert processed.skipped_reason == "not_pending_required_processing"
    assert promotion.promoted_memory_ids == []
    assert db.docs[item_path]["tier"] == MemoryTier.short_term.value


def test_inflight_processor_cannot_overwrite_negative_user_review(monkeypatch):
    uid = "uid-canonical-required-review-race"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    payload = required_promotion_payload(
        {"id": "manual-review-race", "content": "Stale preference", "manually_added": True},
        source_surface="mcp",
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)

    def reject_then_return(_item):
        update_canonical_memory_review(uid, memory_id, False, db_client=db)
        return ProcessedRequiredMemory(
            content="Stale normalized preference",
            subject_entity_id="user",
            predicate="remembered_preference",
            arguments={"statement": "Stale normalized preference"},
        )

    result = process_required_memory_item(uid, memory_id, db_client=db, processor=reject_then_return, now=NOW)
    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]

    assert result.processed is False
    assert result.skipped_reason == "newer_revision_pending"
    assert stored["promotion"]["user_review"] is False
    assert stored["processing_state"] == ProcessingState.pending.value


def test_required_processor_retry_rebases_operation_after_unrelated_head_advance(monkeypatch):
    uid = "uid-canonical-required-head-retry"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    payload = required_promotion_payload(
        {"id": "manual-head-retry", "content": "Remember the retry", "manually_added": True},
        source_surface="mcp",
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)
    processor = lambda _item: ProcessedRequiredMemory(
        content="The user remembers the retry.",
        subject_entity_id="user",
        predicate="remembers",
        arguments={"topic": "retry"},
    )
    processor_globals = process_required_memory_item.__globals__
    real_apply = processor_globals["apply_long_term_patch_firestore"]
    call_count = {"value": 0}

    def advance_head_once(**kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            control_path = f"users/{uid}/memory_state/apply_control"
            control = MemoryControlState(**db.docs[control_path])
            db.docs[control_path] = control.advance_head("commit_unrelated_processor").model_dump(mode="json")
        return real_apply(**kwargs)

    with patch.dict(processor_globals, {"apply_long_term_patch_firestore": advance_head_once}):
        first = process_required_memory_item(uid, memory_id, db_client=db, processor=processor, now=NOW)
        second = process_required_memory_item(uid, memory_id, db_client=db, processor=processor, now=NOW)

    assert first.error_code == "apply_retryable_head_mismatch"
    assert second.processed is True
    assert call_count["value"] == 2


def test_user_review_retry_rebases_operation_after_unrelated_head_advance(monkeypatch):
    uid = "uid-canonical-review-head-retry"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    payload = required_promotion_payload(
        {"id": "manual-review-head-retry", "content": "Review this", "manually_added": True},
        source_surface="mcp",
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)
    review_globals = update_canonical_memory_review.__globals__
    real_apply = review_globals["apply_long_term_patch_firestore"]
    call_count = {"value": 0}

    def advance_head_once(**kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            control_path = f"users/{uid}/memory_state/apply_control"
            control = MemoryControlState(**db.docs[control_path])
            db.docs[control_path] = control.advance_head("commit_unrelated_review").model_dump(mode="json")
        return real_apply(**kwargs)

    with patch.dict(review_globals, {"apply_long_term_patch_firestore": advance_head_once}):
        reviewed = update_canonical_memory_review(uid, memory_id, False, db_client=db)

    assert reviewed.promotion["user_review"] is False
    assert reviewed.processing_state == ProcessingState.pending
    assert call_count["value"] == 2


def test_inflight_promotion_cannot_overwrite_negative_user_review(monkeypatch):
    uid = "uid-canonical-required-promotion-review-race"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    payload = required_promotion_payload(
        {"id": "manual-promotion-review-race", "content": "Keep a preference", "manually_added": True},
        source_surface="mcp",
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)
    _process_required(db, uid, memory_id, content="The user keeps a preference.")
    item_path = f"users/{uid}/memory_items/{memory_id}"
    stale_item = MemoryItem(**db.docs[item_path])

    update_canonical_memory_review(uid, memory_id, False, db_client=db)
    control = MemoryControlState(**db.docs[f"users/{uid}/memory_state/apply_control"])

    with pytest.raises(RuntimeError, match="promotion apply failed"):
        promote_short_term_item_via_apply(
            uid,
            stale_item,
            control=control,
            run_id="stale-promotion-review",
            trigger_reason="required_user_assertion",
            now=NOW,
            db_client=db,
        )

    stored = db.docs[item_path]
    assert stored["tier"] == MemoryTier.short_term.value
    assert stored["promotion"]["user_review"] is False


def test_required_promotion_merges_exact_existing_long_term(monkeypatch):
    uid = "uid-canonical-required-merge"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    monkeypatch.setattr("utils.memory.short_term_promotion.sync_canonical_memory_vector", lambda *_, **__: None)
    monkeypatch.setattr(
        "utils.memory.short_term_promotion.extract_kg_for_promoted_memory",
        lambda *_, **__: CanonicalKgPromotionResult(attempted=True, success=True),
    )

    existing_payload = {
        "id": "existing-long-term",
        "content": "User prefers launch checklists",
        "manually_added": False,
        "memory_tier": MemoryTier.long_term.value,
    }
    existing_id = write_canonical_extraction_memory(uid, existing_payload, db_client=db)
    _make_existing_long_term(db, uid, existing_id)
    required_payload = required_promotion_payload(
        {
            "id": "manual-required-merge",
            "content": "  user   prefers launch CHECKLISTS ",
            "manually_added": True,
        },
        source_surface="mcp",
    )
    short_id = write_canonical_extraction_memory(uid, required_payload, db_client=db)
    _process_required(db, uid, short_id, content="User prefers launch checklists")
    initial_existing_commit = db.docs[f"users/{uid}/memory_items/{existing_id}"]["ledger_commit_id"]
    initial_short_commit = db.docs[f"users/{uid}/memory_items/{short_id}"]["ledger_commit_id"]

    report = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-required-merge")
    existing_stored = db.docs[f"users/{uid}/memory_items/{existing_id}"]
    short_stored = db.docs[f"users/{uid}/memory_items/{short_id}"]

    assert report.trigger_reason == "required_promotion"
    assert report.promoted_memory_ids == [existing_id]
    assert existing_stored["tier"] == MemoryTier.long_term.value
    assert existing_stored["corroboration_count"] == 1
    assert existing_stored["ledger_commit_id"] != initial_existing_commit
    assert short_stored["tier"] == MemoryTier.short_term.value
    assert short_stored["status"] == MemoryItemStatus.superseded.value
    assert short_stored["superseded_by"] == existing_id
    assert short_stored["ledger_commit_id"] != initial_short_commit
    assert short_stored["promotion"]["status"] == "merged"
    assert short_stored["promotion"]["target_memory_id"] == existing_id


def test_required_promotion_merges_multiple_sources_in_same_run(monkeypatch):
    uid = "uid-canonical-required-merge-multiple"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    monkeypatch.setattr("utils.memory.short_term_promotion.sync_canonical_memory_vector", lambda *_, **__: None)

    existing_id = write_canonical_extraction_memory(
        uid,
        {
            "id": "existing-long-term-multi",
            "content": "User prefers launch checklists",
            "memory_tier": MemoryTier.long_term.value,
        },
        db_client=db,
    )
    _make_existing_long_term(db, uid, existing_id)
    short_ids = []
    for source_id in ["manual-required-multi-a", "manual-required-multi-b"]:
        payload = required_promotion_payload(
            {
                "id": source_id,
                "content": "User prefers launch checklists",
                "manually_added": True,
            },
            source_surface="mcp",
        )
        short_id = write_canonical_extraction_memory(uid, payload, db_client=db)
        _process_required(db, uid, short_id, content="User prefers launch checklists")
        short_ids.append(short_id)

    report = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-required-multi")
    existing_stored = db.docs[f"users/{uid}/memory_items/{existing_id}"]

    assert report.trigger_reason == "required_promotion"
    assert report.promoted_memory_ids == [existing_id, existing_id]
    assert existing_stored["corroboration_count"] == 2
    for short_id in short_ids:
        short_stored = db.docs[f"users/{uid}/memory_items/{short_id}"]
        assert short_stored["status"] == MemoryItemStatus.superseded.value
        assert short_stored["promotion"]["status"] == "merged"
        assert short_stored["promotion"]["target_memory_id"] == existing_id


def test_required_promotion_retry_after_supersede_failure_is_idempotent_across_run_ids(monkeypatch):
    uid = "uid-canonical-required-merge-retry"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    monkeypatch.setattr("utils.memory.short_term_promotion.sync_canonical_memory_vector", lambda *_, **__: None)

    existing_id = write_canonical_extraction_memory(
        uid,
        {
            "id": "existing-long-term-retry",
            "content": "User prefers launch checklists",
            "memory_tier": MemoryTier.long_term.value,
        },
        db_client=db,
    )
    _make_existing_long_term(db, uid, existing_id)
    required_payload = required_promotion_payload(
        {
            "id": "manual-required-retry",
            "content": "User prefers launch checklists",
            "manually_added": True,
        },
        source_surface="mcp",
    )
    short_id = write_canonical_extraction_memory(uid, required_payload, db_client=db)
    _process_required(db, uid, short_id, content="User prefers launch checklists")

    promotion_globals = run_canonical_short_term_promotion.__globals__
    real_apply = promotion_globals["apply_long_term_patch_firestore"]
    failed_once = False

    def flaky_apply(**kwargs):
        nonlocal failed_once
        patch_payload = kwargs.get("patch_payload") or {}
        if (
            not failed_once
            and patch_payload.get("target_memory_id") == short_id
            and patch_payload.get("result_status") == "superseded"
        ):
            failed_once = True
            raise RuntimeError("injected supersede failure")
        return real_apply(**kwargs)

    with patch.dict(promotion_globals, {"apply_long_term_patch_firestore": flaky_apply}):
        with pytest.raises(RuntimeError, match="injected supersede failure"):
            run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-required-retry-1")

    existing_after_failure = db.docs[f"users/{uid}/memory_items/{existing_id}"]
    short_after_failure = db.docs[f"users/{uid}/memory_items/{short_id}"]
    assert existing_after_failure["corroboration_count"] == 1
    assert short_after_failure["status"] == MemoryItemStatus.active.value

    retry = run_canonical_short_term_promotion(
        uid,
        db_client=db,
        now=NOW + timedelta(hours=1),
        run_id="promo-required-retry-2",
    )
    existing_after_retry = db.docs[f"users/{uid}/memory_items/{existing_id}"]
    short_after_retry = db.docs[f"users/{uid}/memory_items/{short_id}"]

    assert retry.promoted_memory_ids == [existing_id]
    assert existing_after_retry["corroboration_count"] == 1
    assert existing_after_retry["ledger_commit_id"] == existing_after_failure["ledger_commit_id"]
    assert short_after_retry["status"] == MemoryItemStatus.superseded.value
    assert short_after_retry["promotion"]["status"] == "merged"


def test_promotion_daily_cadence_applies_after_first_successful_run(monkeypatch):
    uid = "uid-canonical-after-first-run"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    threshold = promotion_batch_threshold()
    for index in range(threshold):
        _seed_canonical_short_term(
            db,
            uid=uid,
            conversation_id=f"conv-first-run-{index}",
            content=f"Batch fact {index}",
            monkeypatch=monkeypatch,
        )

    first = run_canonical_short_term_promotion(uid, db_client=db, now=NOW, run_id="promo-first-run")
    assert first.trigger_reason == "batch_threshold"
    assert first.promoted_count == threshold
    assert db.docs[f"users/{uid}/memory_state/apply_control"]["last_promotion_run_at"] is not None

    daily_memory_id = _seed_canonical_short_term(
        db,
        uid=uid,
        conversation_id="conv-daily-after-first",
        content="New fact after first promotion run",
        monkeypatch=monkeypatch,
    )

    hold = run_canonical_short_term_promotion(
        uid,
        db_client=db,
        now=NOW + timedelta(hours=1),
        run_id="promo-hold-after-first",
    )
    assert hold.skipped_reason == "promotion_not_due"
    assert db.docs[f"users/{uid}/memory_items/{daily_memory_id}"]["tier"] == MemoryTier.short_term.value

    daily = run_canonical_short_term_promotion(
        uid,
        db_client=db,
        now=NOW + timedelta(hours=25),
        run_id="promo-daily-after-first",
    )
    assert daily.trigger_reason == "daily_elapsed"
    assert daily.promoted_count == 1
    assert daily_memory_id in daily.promoted_memory_ids


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

"""Canonical Short-term intake, required normalization, and TTL contracts."""

from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timedelta, timezone

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
update_canonical_memory_content = None
update_canonical_memory_review = None
required_processing_payload = None
ProcessedRequiredMemory = None
process_required_memory_item = None
run_required_memory_processing = None
run_canonical_short_term_ttl_lifecycle = None

_RUNTIME_MODULES = (
    "database.memory_apply_store",
    "utils.memory.canonical_memory_adapter",
    "utils.memory.required_promotion",
    "utils.memory.canonical_required_processing",
    "utils.memory.short_term_promotion",
)


def _load_runtime() -> None:
    ensure_utils_memory_packages_importable()
    adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    required = importlib.import_module("utils.memory.required_promotion")
    processor = importlib.import_module("utils.memory.canonical_required_processing")
    maintenance = importlib.import_module("utils.memory.short_term_promotion")
    globals().update(
        {
            "read_canonical_memories": adapter.read_canonical_memories,
            "write_canonical_extraction_memory": adapter.write_canonical_extraction_memory,
            "update_canonical_memory_content": adapter.update_canonical_memory_content,
            "update_canonical_memory_review": adapter.update_canonical_memory_review,
            "required_processing_payload": required.required_processing_payload,
            "ProcessedRequiredMemory": processor.ProcessedRequiredMemory,
            "process_required_memory_item": processor.process_required_memory_item,
            "run_required_memory_processing": processor.run_required_memory_processing,
            "run_canonical_short_term_ttl_lifecycle": maintenance.run_canonical_short_term_ttl_lifecycle,
        }
    )


@pytest.fixture(scope="module", autouse=True)
def _import_isolation():
    saved = snapshot_sys_modules((*WS_B_STUB_MODULE_NAMES, *_RUNTIME_MODULES))
    touched = install_ws_b_import_stubs()
    saved.update(snapshot_sys_modules(touched))
    ensure_utils_memory_packages_importable()
    for module_name in _RUNTIME_MODULES:
        sys.modules.pop(module_name, None)
    _load_runtime()
    yield
    restore_sys_modules(saved)


from models.memory_apply import MemoryControlState, memory_content_hash
from models.memory_evidence import (
    ArtifactPreservationState,
    MemoryEvidence,
    SourceState,
)
from models.product_memory import (
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    MemoryItem,
)
from tests.unit.fixtures.canonical_memory_fakes import (
    _sample_memory_payload,
    _trusted_account_generation,
)
from utils.memory.memory_system import MemorySystem

# Anchored to the real clock rather than a fixed calendar date. Several cases persist an
# item through write_canonical_extraction_memory, which has no clock parameter and stamps
# captured_at from the real clock, and then drive processing with now=NOW. A fixed NOW
# meant expires_at (NOW + DEFAULT_SHORT_TERM_TTL_DAYS) eventually fell behind real
# captured_at, and the short_term "expires_at must be after captured_at" invariant started
# failing on its own — with no code change — once the wall clock passed that date.
NOW = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _Document:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self, transaction=None):
        if self.path not in self.db.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self.db.docs[self.path])

    def set(self, data, merge=False):
        if merge and self.path in self.db.docs:
            self.db.docs[self.path] = {**self.db.docs[self.path], **data}
        else:
            self.db.docs[self.path] = data

    def update(self, data):
        if self.path not in self.db.docs:
            raise NotFound(self.path)
        self.db.docs[self.path] = {**self.db.docs[self.path], **data}


class _Collection:
    def __init__(self, db, path, filters=None, order_fields=None, limit_count=None):
        self.db = db
        self.path = path
        self.filters = list(filters or [])
        self.order_fields = list(order_fields or [])
        self.limit_count = limit_count

    def where(self, field_path=None, op_string=None, value=None, *, filter=None):
        if filter is not None:
            field_path = filter.field_path
            op_string = filter.op_string
            value = filter.value
        assert field_path is not None
        assert op_string in {"==", "in", "<="}
        return _Collection(
            self.db,
            self.path,
            [*self.filters, (field_path, op_string, value)],
            self.order_fields,
            self.limit_count,
        )

    def order_by(self, field_path):
        return _Collection(
            self.db,
            self.path,
            self.filters,
            [*self.order_fields, field_path],
            self.limit_count,
        )

    def limit(self, limit_count):
        return _Collection(self.db, self.path, self.filters, self.order_fields, limit_count)

    def stream(self):
        prefix = self.path + "/"
        snapshots = []
        for path, data in sorted(self.db.docs.items()):
            if not path.startswith(prefix) or "/" in path[len(prefix) :]:
                continue
            if all(self._matches(data, field, operator, value) for field, operator, value in self.filters):
                snapshots.append(_Snapshot(data))
        for field_path in reversed(self.order_fields):
            snapshots.sort(key=lambda snapshot: self._nested_value(snapshot.to_dict(), field_path))
        if self.limit_count is not None:
            snapshots = snapshots[: self.limit_count]
        return snapshots

    @staticmethod
    def _nested_value(data, field_path):
        value = data
        for part in field_path.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    @classmethod
    def _matches(cls, data, field_path, operator, expected):
        actual = cls._nested_value(data, field_path)
        if operator == "==":
            return actual == expected
        if operator == "in":
            return actual in expected
        if operator == "<=":
            if isinstance(actual, str) and isinstance(expected, datetime):
                expected = expected.isoformat()
            return actual is not None and actual <= expected
        raise AssertionError(f"unexpected query operator {operator}")


class _Transaction:
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


class _Db:
    def __init__(self, uid):
        self.docs = {
            f"users/{uid}/memory_state/apply_control": MemoryControlState(
                uid=uid,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json")
        }
        self.transaction_obj = _Transaction(self)

    def document(self, path):
        return _Document(self, path)

    def collection(self, path):
        return _Collection(self, path)

    def transaction(self):
        return self.transaction_obj


class _PromotionFakeDb(_Db):
    """Shared canonical Firestore fake used by adjacent backfill contract tests."""

    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.transaction_obj = _Transaction(self)


def _canonical_db_with_control(uid: str = "uid-canonical") -> _PromotionFakeDb:
    return _PromotionFakeDb(
        {
            f"users/{uid}/memory_state/apply_control": MemoryControlState(
                uid=uid,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json")
        }
    )


def _configure_universal_memory(monkeypatch, *uids: str) -> None:
    from tests.unit.universal_memory_test_helpers import configure_universal_memory

    configure_universal_memory(monkeypatch, *uids)


def _seed_canonical_short_term(
    db: _PromotionFakeDb,
    *,
    uid: str,
    conversation_id: str,
    content: str,
    monkeypatch,
) -> str:
    _load_runtime()
    _set_canonical(monkeypatch, uid)
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    payload["evidence"][0]["evidence_id"] = f"ev_{conversation_id}"
    return write_canonical_extraction_memory(uid, payload, db_client=db)


def _set_canonical(monkeypatch, uid: str) -> None:
    from tests.unit.universal_memory_test_helpers import configure_universal_memory

    configure_universal_memory(monkeypatch, uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )


def _required_payload(memory_id: str, content: str, *, manually_added=True):
    return required_processing_payload(
        {
            "id": memory_id,
            "content": content,
            "manually_added": manually_added,
        },
        source_surface="mcp",
    )


def _write_required(monkeypatch, uid: str, db: _Db, memory_id: str, content: str) -> str:
    _set_canonical(monkeypatch, uid)
    return write_canonical_extraction_memory(
        uid,
        _required_payload(memory_id, content),
        db_client=db,
    )


def _process(uid: str, memory_id: str, db: _Db, *, content: str):
    return process_required_memory_item(
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


@pytest.fixture(autouse=True)
def _reset_universal_memory(monkeypatch):
    from tests.unit.universal_memory_test_helpers import reset_universal_memory_fixture

    _load_runtime()
    reset_universal_memory_fixture(monkeypatch)


def test_required_submission_is_visible_pending_short_term_but_not_default_memory(
    monkeypatch,
):
    uid = "uid-required"
    db = _Db(uid)
    memory_id = _write_required(
        monkeypatch,
        uid,
        db,
        "manual-required",
        "Remember that I prefer concise launch checklists.",
    )

    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert stored["tier"] == MemoryTier.short_term.value
    assert stored["processing_state"] == ProcessingState.pending.value
    assert stored["promotion"]["required"] is True
    assert stored["promotion"]["processing_status"] == "pending_processing"
    outbox = [doc for path, doc in db.docs.items() if path.startswith(f"users/{uid}/memory_outbox/")]
    assert {doc["event_type"]: doc["payload"]["action"] for doc in outbox} == {
        "projection_sync": "delete",
        "vector_sync": "delete",
    }
    assert all(doc["payload"]["item_revision"] == stored["item_revision"] for doc in outbox)
    assert all(doc["payload"]["content_hash"] == stored["content_hash"] for doc in outbox)
    assert read_canonical_memories(uid, db_client=db) == []
    pending = read_canonical_memories(uid, db_client=db, include_pending_processing=True)
    assert [memory.id for memory in pending] == [memory_id]


def test_required_processing_preserves_integration_attribution():
    payload = _required_payload(
        "integration-required",
        "The account uses a weekly planning ritual.",
        manually_added=False,
    )
    assert payload["manually_added"] is False
    assert payload["user_asserted"] is False
    assert payload["promotion"]["required"] is True
    assert payload["promotion"]["source_surface"] == "mcp"


def test_required_processor_resolves_unknown_api_subject_and_infers_person_kind(
    monkeypatch,
):
    uid = "uid-api-required-subject"
    db = _Db(uid)
    _set_canonical(monkeypatch, uid)
    payload = _required_payload(
        "integration-required-subject",
        "Sarah prefers early flights.",
        manually_added=False,
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)

    result = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=lambda _item: ProcessedRequiredMemory(
            content="Sarah prefers early flights.",
            subject_entity_id="person:sarah",
            predicate="prefers",
            arguments={"thing": "early flights"},
        ),
        now=NOW,
    )

    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert result.processed is True
    assert stored["user_asserted"] is False
    assert stored["subject_entity_id"] == "person:sarah"
    assert stored["promotion"]["source_attribution"] == {
        "subject_entity_id": "person:sarah",
        "subject_attribution": "third_party",
        "subject_kind": "person",
    }


def test_required_processor_normalizes_but_does_not_bypass_l2(monkeypatch):
    uid = "uid-processed"
    db = _Db(uid)
    memory_id = _write_required(monkeypatch, uid, db, "manual-processed", "remember tea")

    result = _process(uid, memory_id, db, content="The user prefers tea.")

    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    receipt = stored["promotion"]["processing_receipt"]
    assert result.processed is True
    assert stored["tier"] == MemoryTier.short_term.value
    assert stored["processing_state"] == ProcessingState.processed.value
    assert stored["subject_entity_id"] == "user"
    assert stored["predicate"] == "remembered_preference"
    assert stored["arguments"] == {"statement": "The user prefers tea."}
    assert receipt["output_item_revision"] == stored["item_revision"]
    assert receipt["source_submission_id"] == "manual-processed"


def test_required_processor_cannot_replace_known_manual_third_party_subject(
    monkeypatch,
):
    uid = "uid-known-third-party"
    db = _Db(uid)
    _set_canonical(monkeypatch, uid)
    payload = _required_payload("manual-third-party", "Sarah prefers early flights.")
    payload.update(
        {
            "subject_entity_id": "person:sarah",
            "subject_attribution": "third_party",
            "subject_kind": "person",
        }
    )
    memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)
    before = dict(db.docs[f"users/{uid}/memory_items/{memory_id}"])

    result = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=lambda _item: ProcessedRequiredMemory(
            content="The user prefers early flights.",
            subject_entity_id="user",
            predicate="prefers",
            arguments={"thing": "early flights"},
        ),
        now=NOW,
    )

    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert result.error_code == "RequiredProcessingSubjectContradiction"
    assert stored == before
    assert stored["processing_state"] == ProcessingState.pending.value
    assert stored["subject_entity_id"] == "person:sarah"


def test_required_processing_failures_back_off_then_quarantine_and_new_revision_escapes(
    monkeypatch,
):
    uid = "uid-required-retry"
    db = _Db(uid)
    memory_id = _write_required(monkeypatch, uid, db, "manual-poison", "remember tea")
    calls = 0

    def poison(_item):
        nonlocal calls
        calls += 1
        raise ValueError("invalid model output")

    first = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=poison,
        now=NOW,
    )
    deferred = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=poison,
        now=NOW + timedelta(minutes=1),
    )
    second = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=poison,
        now=NOW + timedelta(minutes=5),
    )
    terminal = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=poison,
        now=NOW + timedelta(minutes=15),
    )

    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert first.attempted is True
    assert first.retryable is True
    assert deferred.skipped_reason == "retry_backoff"
    assert deferred.attempted is False
    assert second.retryable is True
    assert terminal.quarantined is True
    assert stored["processing_state"] == ProcessingState.blocked.value
    assert stored["promotion"]["processing_status"] == "processing_blocked"
    assert stored["promotion"]["attempt_count"] == 3
    assert calls == 3

    update_canonical_memory_content(uid, memory_id, "Remember coffee instead.", db_client=db)
    recovered = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=lambda _item: ProcessedRequiredMemory(content="The user prefers coffee."),
        now=NOW + timedelta(days=100),
    )

    assert recovered.processed is True
    assert recovered.attempted is True
    assert db.docs[f"users/{uid}/memory_items/{memory_id}"]["processing_state"] == ProcessingState.processed.value


def test_required_processing_flex_deferral_releases_lease_without_spending_quality_attempt(monkeypatch):
    from utils.memory.promotion_flex import PromotionFlexDeferred

    uid = "uid-required-flex-deferred"
    db = _Db(uid)
    memory_id = _write_required(monkeypatch, uid, db, "manual-flex", "remember tea")

    deferred = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=lambda _item: (_ for _ in ()).throw(PromotionFlexDeferred("capacity")),
        now=NOW,
        attempt_lease_seconds=1_200,
    )
    recovered = _process(uid, memory_id, db, content="User prefers tea")

    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert deferred.attempted is True
    assert deferred.retryable is True
    assert deferred.error_code == "flex_deferred"
    assert recovered.processed is True
    assert stored["promotion"]["attempt_count"] == 1


def test_required_processing_scan_skips_backoff_rows_without_exceeding_call_budget(
    monkeypatch,
):
    uid = "uid-required-scan"
    db = _Db(uid)
    poison_ids = [
        _write_required(monkeypatch, uid, db, f"poison-{index:02d}", f"poison {index}") for index in range(25)
    ]
    fresh_id = _write_required(monkeypatch, uid, db, "z-fresh", "remember coffee")
    first_calls = 0

    def poison(_item):
        nonlocal first_calls
        first_calls += 1
        raise ValueError("invalid model output")

    first_report = run_required_memory_processing(
        uid,
        db_client=db,
        processor=poison,
        now=NOW,
    )
    processed_ids: list[str] = []

    def normalize(item):
        processed_ids.append(item.memory_id)
        return ProcessedRequiredMemory(content=f"Normalized {item.content}")

    second_report = run_required_memory_processing(
        uid,
        db_client=db,
        processor=normalize,
        now=NOW + timedelta(minutes=1),
    )

    assert first_report.attempted_count == 25
    assert len(first_report.retryable_memory_ids) == 25
    assert first_calls == 25
    assert second_report.attempted_count == 1
    assert second_report.processed_memory_ids == [fresh_id]
    assert processed_ids == [fresh_id]
    assert all(memory_id in second_report.skipped_memory_ids for memory_id in poison_ids)


def test_required_processing_lease_blocks_overlapping_llm_invocation(monkeypatch):
    uid = "uid-required-lease"
    db = _Db(uid)
    memory_id = _write_required(monkeypatch, uid, db, "manual-lease", "remember tea")
    nested_processor = pytest.fail
    nested_result = None

    def outer_processor(_item):
        nonlocal nested_result
        nested_result = process_required_memory_item(
            uid,
            memory_id,
            db_client=db,
            processor=nested_processor,
            now=NOW,
        )
        return ProcessedRequiredMemory(content="The user prefers tea.")

    result = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=outer_processor,
        now=NOW,
    )

    assert result.processed is True
    assert nested_result is not None
    assert nested_result.skipped_reason == "attempt_leased"
    assert nested_result.attempted is False


def test_required_processing_preserves_original_expiry_and_receipt_time(monkeypatch):
    uid = "uid-expiry"
    db = _Db(uid)
    memory_id = _write_required(monkeypatch, uid, db, "manual-expiry", "remember tea")
    path = f"users/{uid}/memory_items/{memory_id}"
    captured_value = db.docs[path]["captured_at"]
    captured_at = captured_value if isinstance(captured_value, datetime) else datetime.fromisoformat(captured_value)
    original_expiry = db.docs[path]["expires_at"]

    result = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=lambda _item: ProcessedRequiredMemory(content="The user prefers tea."),
        now=captured_at - timedelta(days=10),
    )

    assert result.processed is True
    assert db.docs[path]["expires_at"] == original_expiry
    processed_value = db.docs[path]["promotion"]["processing_receipt"]["processed_at"]
    processed_at = processed_value if isinstance(processed_value, datetime) else datetime.fromisoformat(processed_value)
    assert processed_at == captured_at


def test_inflight_processor_cannot_overwrite_newer_user_edit(monkeypatch):
    uid = "uid-edit-race"
    db = _Db(uid)
    memory_id = _write_required(monkeypatch, uid, db, "manual-edit", "Old preference")

    def edit_then_return(_item):
        update_canonical_memory_content(uid, memory_id, "New preference", db_client=db)
        return ProcessedRequiredMemory(content="Stale normalized preference")

    result = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=edit_then_return,
        now=NOW,
    )

    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert result.skipped_reason == "newer_revision_pending"
    assert stored["content"] == "New preference"
    assert stored["processing_state"] == ProcessingState.pending.value


def test_negative_user_review_is_authoritative_during_processing_race(monkeypatch):
    uid = "uid-review-race"
    db = _Db(uid)
    memory_id = _write_required(monkeypatch, uid, db, "manual-review", "Do not keep this")

    def reject_then_return(_item):
        update_canonical_memory_review(uid, memory_id, False, db_client=db)
        return ProcessedRequiredMemory(content="Stale normalized preference")

    result = process_required_memory_item(
        uid,
        memory_id,
        db_client=db,
        processor=reject_then_return,
        now=NOW,
    )

    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert result.skipped_reason == "newer_revision_pending"
    assert stored["promotion"]["user_review"] is False
    assert stored["promotion"]["processing_status"] == "processing_rejected"
    assert stored["tier"] == MemoryTier.short_term.value
    review_events = [
        doc
        for path, doc in db.docs.items()
        if path.startswith(f"users/{uid}/memory_outbox/")
        and doc["payload"].get("item_revision") == stored["item_revision"]
    ]
    assert {doc["event_type"]: doc["payload"]["action"] for doc in review_events} == {
        "projection_sync": "delete",
        "vector_sync": "delete",
    }
    assert all(doc["payload"]["content_hash"] == stored["content_hash"] for doc in review_events)


def test_expired_short_term_is_default_hidden_and_ttl_audited(monkeypatch):
    uid = "uid-expired"
    _set_canonical(monkeypatch, uid)
    db = _Db(uid)
    evidence = MemoryEvidence(
        evidence_id="ev-expired",
        source_type="conversation",
        source_id="conv-expired",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    item = MemoryItem(
        memory_id="mem-expired",
        uid=uid,
        version=1,
        tier=MemoryTier.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="Expired context",
        evidence=[evidence],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=NOW - timedelta(days=31),
        updated_at=NOW - timedelta(days=31),
        expires_at=NOW - timedelta(days=1),
        ledger_commit_id="head0",
        ledger_sequence=0,
        item_revision=1,
        content_hash=memory_content_hash(content="Expired context", evidence_ids=[evidence.evidence_id]),
        account_generation=1,
    )
    db.docs[f"users/{uid}/memory_items/{item.memory_id}"] = item.model_dump(mode="json")
    db.docs[f"users/{uid}/memory_evidence/{evidence.evidence_id}"] = evidence.model_dump(mode="json")

    with pytest.MonkeyPatch.context() as local_patch:
        local_patch.setattr(
            "utils.memory.short_term_promotion.resolve_memory_system",
            lambda *args, **kwargs: MemorySystem.CANONICAL,
        )
        report = run_canonical_short_term_ttl_lifecycle(
            uid,
            db_client=db,
            now=NOW,
            run_id="run-expiry",
        )

    assert read_canonical_memories(uid, db_client=db, now=NOW) == []
    assert report.lifecycle_created_count == 1
    assert report.lifecycle_terminal_count == 1
    settled = db.docs[f"users/{uid}/memory_items/{item.memory_id}"]
    assert settled["tier"] == MemoryTier.archive.value
    assert settled["status"] == MemoryItemStatus.hidden.value
    delete_events = [
        payload
        for path, payload in db.docs.items()
        if path.startswith(f"users/{uid}/memory_outbox/") and payload.get("memory_id") == item.memory_id
    ]
    assert {event["event_type"]: event["payload"]["action"] for event in delete_events} == {
        "projection_sync": "delete",
        "vector_sync": "delete",
    }

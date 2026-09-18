from datetime import datetime, timedelta, timezone
import copy
import hashlib

import pytest

from database import jit_proactivity_store as store
from models.jit_proactivity import JITProactivityEventReceipt
from models.memory_apply import MemoryControlState
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
    ProcessingState,
)
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)


class _Snapshot:
    def __init__(self, payload=None):
        self.payload = payload
        self.exists = payload is not None

    def to_dict(self):
        return copy.deepcopy(self.payload)


class _Ref:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self, transaction=None):
        return _Snapshot(self.db.docs.get(self.path))


class _Transaction:
    def __init__(self, db):
        self.db = db

    def set(self, ref, payload):
        self.db.docs[ref.path] = payload


class _Db:
    def __init__(self):
        control = MemoryControlState(
            uid="u1",
            head_commit_id="head-1",
            account_generation=1,
            source_generation=1,
        )
        self.docs = {
            "users/u1": {"time_zone": "UTC"},
            "users/u1/memory_state/apply_control": control.model_dump(mode="python"),
        }

    def document(self, path):
        return _Ref(self, path)


def _trigger(identifier="trigger-1"):
    return MemoryItem(
        memory_id=identifier,
        uid="u1",
        version=1,
        tier=MemoryLayer.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="Release trigger",
        evidence=[
            MemoryEvidence(
                evidence_id="evidence-1",
                source_type="chat_turn",
                source_id="turn-1",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=True,
        captured_at=NOW,
        updated_at=NOW,
        ledger_commit_id="head-1",
        ledger_sequence=1,
        account_generation=1,
        ledger_schema_version="knowledge_ledger.v1",
        kind=MemoryKind.trigger,
        subject_scope=MemorySubjectScope.primary_user,
        trigger_condition={
            "keywords": ["release"],
            "action": {"type": "agent_prompt", "prompt": "Find the next release step."},
        },
        arguments={"wakeup_budget_per_day": 1},
        intent_backed=True,
        write_reason=LedgerWriteReason.standing_trigger,
    )


def _digest(value):
    return (
        value
        if len(value) == 64 and all(character in "0123456789abcdef" for character in value)
        else hashlib.sha256(value.encode()).hexdigest()
    )


def _receipt(event_id, operation, *, candidate_id=None, device_id="mac", trigger=None, parent_event_id=None):
    event_id = _digest(event_id)
    return JITProactivityEventReceipt(
        uid="u1",
        event_id=event_id,
        candidate_id=_digest(candidate_id or event_id),
        operation=operation,
        account_generation=1,
        trigger_memory_id=trigger.memory_id if trigger else None,
        trigger_revision=trigger.item_revision if trigger else None,
        budget_day="2026-08-24",
        parent_event_id=_digest(parent_event_id) if parent_event_id else None,
        device_id=_digest(device_id),
        created_at=NOW,
        request_hash=(event_id.encode().hex() + "0" * 64)[:64],
    )


def _reserve(db, receipt):
    transaction = _Transaction(db)
    wrapped = getattr(store._reserve_transaction, "to_wrap", store._reserve_transaction)
    return wrapped(transaction, db, receipt)


def test_notifications_share_one_atomic_cross_device_total_and_per_trigger_budget():
    db = _Db()
    trigger = _trigger()
    db.docs["users/u1/memory_items/trigger-1"] = trigger.model_dump(mode="python")

    first, applied = _reserve(db, _receipt("planned-1", "planned_notification", trigger=trigger))
    assert applied is True and first.event_id == _digest("planned-1")
    replay, replayed = _reserve(db, _receipt("planned-1", "planned_notification", trigger=trigger))
    assert replayed is False and replay.event_id == _digest("planned-1")
    with pytest.raises(store.JITProactivityReservationError, match="per-trigger"):
        _reserve(
            db,
            _receipt("planned-2", "planned_notification", device_id="windows", trigger=trigger),
        )

    _reserve(db, _receipt("ambient-1", "ambient_notification", device_id="windows"))
    _reserve(db, _receipt("ambient-2", "ambient_notification"))
    with pytest.raises(store.JITProactivityReservationError, match="notification budget exhausted"):
        _reserve(db, _receipt("ambient-3", "ambient_notification"))


def test_nano_triage_and_full_turn_candidate_caps_are_atomic():
    db = _Db()
    for index in range(8):
        _reserve(db, _receipt(f"triage-{index}", "nano_triage", device_id="windows" if index % 2 else "mac"))
    with pytest.raises(store.JITProactivityReservationError, match="nano-triage budget exhausted"):
        _reserve(db, _receipt("triage-8", "nano_triage"))

    parent = _receipt("admit-1", "ambient_notification", candidate_id="candidate-1")
    _reserve(db, parent)
    _reserve(
        db,
        _receipt(
            "turn-1",
            "full_turn",
            candidate_id="candidate-1",
            parent_event_id=parent.event_id,
        ),
    )
    with pytest.raises(store.JITProactivityReservationError, match="full-turn budget exhausted"):
        _reserve(
            db,
            _receipt(
                "turn-2",
                "full_turn",
                candidate_id="candidate-1",
                parent_event_id=parent.event_id,
            ),
        )

    forged_parent = _receipt("forged-admit", "ambient_notification", candidate_id="candidate-4")
    with pytest.raises(store.JITProactivityReservationError, match="required JIT authority"):
        _reserve(
            db,
            _receipt(
                "turn-4",
                "full_turn",
                candidate_id="candidate-4",
                parent_event_id=forged_parent.event_id,
            ),
        )


def test_account_deletion_fence_blocks_every_reservation():
    db = _Db()
    db.docs["account_deletions/u1"] = {"wipe_status": "accepted"}

    with pytest.raises(store.JITProactivityReservationError, match="account deletion"):
        _reserve(db, _receipt("ambient", "ambient_notification"))


def test_new_account_generation_resets_same_day_budget_but_rejects_future_generation():
    db = _Db()
    receipt = _receipt("ambient-1", "ambient_notification")
    day_path = "users/u1/jit_proactivity_daily_budgets/2026-08-24"
    db.docs[day_path] = {
        "schema_version": "jit_proactivity_daily_budget.v1",
        "uid": "u1",
        "account_generation": 0,
        "budget_day": "2026-08-24",
        "budget_timezone": "UTC",
        "total_notifications": 3,
        "nano_triages": 8,
        "planned_by_trigger": {},
    }

    _, applied = _reserve(db, receipt)
    assert applied is True
    assert db.docs[day_path]["account_generation"] == 1
    assert db.docs[day_path]["total_notifications"] == 1

    db.docs.pop(f"users/u1/jit_proactivity_events/{_digest('ambient-1')}")
    db.docs[day_path]["account_generation"] = 2
    with pytest.raises(store.JITProactivityReservationError, match="malformed"):
        _reserve(db, _receipt("ambient-2", "ambient_notification"))


def test_per_trigger_budget_map_is_bounded_before_adding_a_new_trigger():
    db = _Db()
    trigger = _trigger("new-trigger")
    db.docs["users/u1/memory_items/new-trigger"] = trigger.model_dump(mode="python")
    db.docs["users/u1/jit_proactivity_daily_budgets/2026-08-24"] = {
        "schema_version": "jit_proactivity_daily_budget.v1",
        "uid": "u1",
        "account_generation": 1,
        "budget_day": "2026-08-24",
        "budget_timezone": "UTC",
        "total_notifications": 0,
        "nano_triages": 0,
        "planned_by_trigger": {f"trigger-{index}": 0 for index in range(500)},
    }

    with pytest.raises(store.JITProactivityReservationError, match="per-trigger budget is malformed"):
        _reserve(db, _receipt("planned-new", "planned_notification", trigger=trigger))


def test_full_turn_requires_notification_admission_and_has_a_daily_hard_cap():
    db = _Db()
    with pytest.raises(ValueError, match="notification-admission parent"):
        _receipt("orphan-turn", "full_turn", candidate_id="orphan")

    for index in range(3):
        parent = _receipt(f"admit-{index}", "ambient_notification", candidate_id=f"candidate-{index}")
        _reserve(db, parent)
        _reserve(
            db,
            _receipt(
                f"turn-{index}",
                "full_turn",
                candidate_id=f"candidate-{index}",
                parent_event_id=parent.event_id,
            ),
        )


def test_full_turn_is_rejected_after_parent_receives_feedback():
    db = _Db()
    parent = _receipt("feedback-parent", "ambient_notification", candidate_id="candidate-feedback")
    _reserve(db, parent)
    db.docs[f"users/u1/jit_proactivity_events/{parent.event_id}"]["feedback_id"] = _digest("feedback")

    with pytest.raises(store.JITProactivityReservationError, match="authority is stale"):
        _reserve(
            db,
            _receipt(
                "turn-after-feedback",
                "full_turn",
                candidate_id="candidate-feedback",
                parent_event_id=parent.event_id,
            ),
        )


@pytest.mark.parametrize(
    ("instant", "expected_day"),
    [
        (datetime(2026, 11, 1, 3, 59, tzinfo=timezone.utc), "2026-10-31"),
        (datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc), "2026-11-01"),
        (datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc), "2026-11-01"),
        (datetime(2026, 3, 8, 6, 59, tzinfo=timezone.utc), "2026-03-08"),
        (datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc), "2026-03-08"),
    ],
)
def test_budget_day_uses_server_authoritative_local_timezone_across_dst(instant, expected_day):
    assert store._budget_day_for_timezone(instant, "America/New_York") == expected_day


def test_budget_day_fails_closed_for_missing_or_invalid_timezone():
    with pytest.raises(store.JITProactivityReservationError, match="unavailable"):
        store._budget_day_for_timezone(NOW, "")
    with pytest.raises(store.JITProactivityReservationError, match="invalid"):
        store._budget_day_for_timezone(NOW, "Mars/Olympus_Mons")


def test_timezone_change_cannot_split_an_active_daily_budget_window():
    db = _Db()
    _reserve(db, _receipt("utc-window", "ambient_notification"))

    db.docs["users/u1"]["time_zone"] = "America/Los_Angeles"
    changed = _receipt("pacific-window", "ambient_notification").model_copy(
        update={"budget_timezone": "America/Los_Angeles"}
    )

    with pytest.raises(store.JITProactivityReservationError, match="split an active budget window"):
        _reserve(db, changed)


def test_transaction_rejects_timezone_changed_after_client_proposal():
    db = _Db()
    proposed = _receipt("stale-timezone", "ambient_notification")
    db.docs["users/u1"]["time_zone"] = "America/New_York"

    with pytest.raises(store.JITProactivityReservationError, match="authority changed"):
        _reserve(db, proposed)


def test_purged_or_evidence_less_trigger_cannot_reserve_paid_work():
    db = _Db()
    trigger = _trigger()
    db.docs["users/u1/memory_items/trigger-1"] = trigger.model_copy(
        update={"source_state": SourceState.purged}
    ).model_dump(mode="python")
    with pytest.raises(store.JITProactivityReservationError, match="trigger authority is stale"):
        _reserve(db, _receipt("planned-purged", "planned_notification", trigger=trigger))

    db.docs["users/u1/memory_items/trigger-1"] = trigger.model_copy(update={"evidence": []}).model_dump(mode="python")
    with pytest.raises(store.JITProactivityReservationError, match="trigger authority is stale"):
        _reserve(db, _receipt("planned-no-evidence", "planned_notification", trigger=trigger))


def test_snoozed_trigger_cannot_reserve_paid_work_until_exact_expiry():
    db = _Db()
    snoozed_until = NOW + timedelta(hours=1)
    base_trigger = _trigger()
    trigger = base_trigger.model_copy(
        update={
            "arguments": {
                **base_trigger.arguments,
                "jit_trigger_feedback": {
                    "snoozed_until": snoozed_until.isoformat(),
                },
            }
        }
    )
    db.docs["users/u1/memory_items/trigger-1"] = trigger.model_dump(mode="python")

    with pytest.raises(store.JITProactivityReservationError, match="trigger authority is stale"):
        _reserve(db, _receipt("planned-snoozed", "planned_notification", trigger=trigger))

    after_expiry = _receipt("planned-awake", "planned_notification", trigger=trigger).model_copy(
        update={"created_at": snoozed_until}
    )
    persisted, applied = _reserve(db, after_expiry)
    assert applied is True
    assert persisted.event_id == after_expiry.event_id


@pytest.mark.parametrize(
    "trigger_update",
    [
        {"arguments": {}},
        {
            "trigger_condition": {
                "keywords": ["release"],
                "embedding": {
                    "prototype_id": "release-prototype",
                    "prototype_revision": "1",
                    "model_id": "local-model",
                    "model_version": "1",
                    "language": "en",
                    "min_similarity": 0.82,
                },
                "action": {"type": "agent_prompt", "prompt": "Find the next release step."},
            }
        },
        {"trigger_condition": {"action": {"type": "agent_prompt", "prompt": "Find the next release step."}}},
    ],
)
def test_snapshot_invalid_trigger_cannot_reserve_paid_work(trigger_update):
    db = _Db()
    trigger = _trigger()
    db.docs["users/u1/memory_items/trigger-1"] = trigger.model_copy(update=trigger_update).model_dump(mode="python")

    with pytest.raises(store.JITProactivityReservationError, match="trigger authority is stale"):
        _reserve(db, _receipt("planned-invalid", "planned_notification", trigger=trigger))


def test_reservation_obeys_strict_firestore_read_before_write_ordering():
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head-1",
        account_generation=1,
        source_generation=1,
    )
    trigger = _trigger()
    database = StrictFirestore(
        {
            ("users", "u1"): {"time_zone": "UTC"},
            ("users", "u1", "memory_state", "apply_control"): control.model_dump(mode="python"),
            ("users", "u1", "memory_items", "trigger-1"): trigger.model_dump(mode="python"),
        }
    )
    receipt = _receipt("strict-planned", "planned_notification", trigger=trigger)
    wrapped = getattr(store._reserve_transaction, "to_wrap", store._reserve_transaction)

    persisted, applied = wrapped(database.transaction(), database, receipt)

    assert applied is True
    assert persisted.event_id == receipt.event_id
    assert database.transactions[-1].has_written is True

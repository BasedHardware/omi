from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models.memory_apply import MemoryControlState, WriterMode
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.memory.knowledge_ledger_writer_transition import (
    CompleteUnionProofReceipt,
    MemoryWriterClass,
    WriterAdmissionError,
    WriterTransitionConflict,
    WriterTransitionConflictCode,
    abort_writer_transition,
    begin_writer_transition,
    complete_writer_transition,
    require_writer_admitted,
)

UID = "writer-user"
OWNER = "migration-run-1"
CONTROL_PATH = ("users", UID, "memory_state", "apply_control")
RECEIPT_PATH = ("users", UID, "memory_control", "knowledge_ledger_writer_transition_receipt")


def _control(**updates):
    values = {
        "uid": UID,
        "head_commit_id": "head-7",
        "account_generation": 3,
        "source_generation": 9,
        "commit_sequence": 11,
        "updated_at": datetime(2026, 8, 24, tzinfo=timezone.utc),
    }
    values.update(updates)
    return MemoryControlState.model_validate(values)


def _database(control):
    return StrictFirestore({CONTROL_PATH: control.model_dump(mode="python")})


def _receipt(control, **updates):
    target = {
        WriterMode.transitioning_to_ledger: WriterMode.ledger,
        WriterMode.transitioning_to_compatibility: WriterMode.compatibility,
    }[control.writer_mode]
    values = {
        "uid": control.uid,
        "transition_owner": control.writer_transition_owner,
        "writer_mode": control.writer_mode,
        "target_mode": target,
        "writer_epoch": control.writer_epoch,
        "head_commit_id": control.head_commit_id,
        "account_generation": control.account_generation,
        "source_generation": control.source_generation,
        "commit_sequence": control.commit_sequence,
        "complete_union_digest": "a" * 64,
        "complete_union_count": 17,
        "generated_at": datetime(2026, 8, 24, 1, tzinfo=timezone.utc),
    }
    values.update(updates)
    return CompleteUnionProofReceipt.model_validate(values)


def test_legacy_control_fields_decode_to_compatibility_epoch_zero_and_malformed_values_fail_closed():
    legacy = _control()
    assert legacy.writer_mode == WriterMode.compatibility
    assert legacy.writer_epoch == 0
    assert legacy.writer_transition_owner is None

    with pytest.raises(ValidationError, match="writer_mode"):
        _control(writer_mode="surprise")
    with pytest.raises(ValidationError, match="writer_epoch must be an integer"):
        _control(writer_epoch="1")
    with pytest.raises(ValidationError, match="requires an owner"):
        _control(writer_mode=WriterMode.transitioning_to_ledger, writer_epoch=1)
    with pytest.raises(ValidationError, match="cannot retain"):
        _control(writer_transition_owner=OWNER)


def test_writer_admission_blocks_ordinary_writers_during_transitions_but_preserves_internal_migration():
    compatibility = _control()
    ledger = _control(writer_mode=WriterMode.ledger, writer_epoch=2)
    transitioning = _control(
        writer_mode=WriterMode.transitioning_to_ledger,
        writer_epoch=1,
        writer_transition_owner=OWNER,
    )

    require_writer_admitted(compatibility, MemoryWriterClass.compatibility)
    require_writer_admitted(compatibility, MemoryWriterClass.user)
    require_writer_admitted(compatibility, MemoryWriterClass.ledger, allow_ledger_migration=True)
    require_writer_admitted(ledger, MemoryWriterClass.ledger)
    require_writer_admitted(ledger, MemoryWriterClass.user)
    require_writer_admitted(transitioning, MemoryWriterClass.ledger, allow_ledger_migration=True)
    with pytest.raises(WriterAdmissionError):
        require_writer_admitted(compatibility, MemoryWriterClass.ledger)
    with pytest.raises(WriterAdmissionError):
        require_writer_admitted(ledger, MemoryWriterClass.compatibility)
    with pytest.raises(WriterAdmissionError):
        require_writer_admitted(transitioning, MemoryWriterClass.compatibility)
    with pytest.raises(WriterAdmissionError):
        require_writer_admitted(transitioning, MemoryWriterClass.ledger)
    with pytest.raises(WriterAdmissionError):
        require_writer_admitted(transitioning, MemoryWriterClass.user)


@pytest.mark.parametrize(
    ("source_mode", "target_mode", "transition_mode"),
    [
        (WriterMode.compatibility, WriterMode.ledger, WriterMode.transitioning_to_ledger),
        (WriterMode.ledger, WriterMode.compatibility, WriterMode.transitioning_to_compatibility),
    ],
)
def test_begin_writer_transition_supports_only_the_two_legal_directions_and_advances_fences(
    source_mode, target_mode, transition_mode
):
    observed = _control(writer_mode=source_mode, writer_epoch=4)
    database = _database(observed)

    transitioned = begin_writer_transition(
        UID,
        target_mode=target_mode,
        transition_owner=OWNER,
        expected_control=observed,
        db_client=database,
    )

    assert transitioned.writer_mode == transition_mode
    assert transitioned.writer_epoch == 5
    assert transitioned.source_generation == observed.source_generation + 1
    assert transitioned.writer_transition_owner == OWNER
    assert database.rows[CONTROL_PATH]["writer_epoch"] == 5


def test_begin_replay_is_idempotent_and_cross_owner_or_illegal_entry_fails():
    observed = _control()
    database = _database(observed)
    first = begin_writer_transition(
        UID,
        target_mode=WriterMode.ledger,
        transition_owner=OWNER,
        expected_control=observed,
        db_client=database,
    )
    replay = begin_writer_transition(
        UID,
        target_mode=WriterMode.ledger,
        transition_owner=OWNER,
        expected_control=observed,
        db_client=database,
    )
    assert replay == first
    assert database.transactions[-1].sets == []

    with pytest.raises(WriterTransitionConflict) as cross_owner:
        begin_writer_transition(
            UID,
            target_mode=WriterMode.ledger,
            transition_owner="migration-run-2",
            expected_control=observed,
            db_client=database,
        )
    assert cross_owner.value.code == WriterTransitionConflictCode.cross_owner

    with pytest.raises(WriterTransitionConflict) as illegal:
        begin_writer_transition(
            UID,
            target_mode=WriterMode.compatibility,
            transition_owner=OWNER,
            expected_control=observed,
            db_client=database,
        )
    assert illegal.value.code == WriterTransitionConflictCode.illegal_transition


@pytest.mark.parametrize(
    ("rows", "expected_code"),
    [
        ({}, WriterTransitionConflictCode.missing_control),
        (
            {
                CONTROL_PATH: {
                    "uid": UID,
                    "head_commit_id": "head-7",
                    "account_generation": 3,
                    "source_generation": 9,
                    "writer_mode": "not-a-mode",
                }
            },
            WriterTransitionConflictCode.malformed_control,
        ),
    ],
)
def test_transition_entry_fails_closed_on_missing_or_malformed_persisted_control(rows, expected_code):
    database = StrictFirestore(rows)
    with pytest.raises(WriterTransitionConflict) as conflict:
        begin_writer_transition(
            UID,
            target_mode=WriterMode.ledger,
            transition_owner=OWNER,
            expected_control=_control(),
            db_client=database,
        )
    assert conflict.value.code == expected_code


def test_complete_requires_exact_epoch_and_fence_and_persists_only_content_free_proof():
    observed = _control()
    database = _database(observed)
    transitioned = begin_writer_transition(
        UID,
        target_mode=WriterMode.ledger,
        transition_owner=OWNER,
        expected_control=observed,
        db_client=database,
    )

    stale = transitioned.model_copy(update={"writer_epoch": transitioned.writer_epoch + 1})
    with pytest.raises(WriterTransitionConflict) as stale_conflict:
        complete_writer_transition(
            UID,
            transition_owner=OWNER,
            expected_control=stale,
            receipt=_receipt(stale),
            db_client=database,
        )
    assert stale_conflict.value.code == WriterTransitionConflictCode.stale_fence

    receipt = _receipt(transitioned)
    completed = complete_writer_transition(
        UID,
        transition_owner=OWNER,
        expected_control=transitioned,
        receipt=receipt,
        db_client=database,
    )
    assert completed.writer_mode == WriterMode.ledger
    assert completed.writer_epoch == transitioned.writer_epoch
    assert completed.source_generation == transitioned.source_generation
    assert completed.writer_transition_owner is None
    assert set(database.rows) == {CONTROL_PATH, RECEIPT_PATH}
    persisted = database.rows[RECEIPT_PATH]
    assert persisted["complete_union_count"] == 17
    assert persisted["complete_union_digest"] == "a" * 64
    assert not ({"content", "body", "rows", "memories", "memory_items"} & set(persisted))


def test_complete_replay_is_idempotent_and_cross_owner_fails_closed():
    observed = _control()
    database = _database(observed)
    transitioned = begin_writer_transition(
        UID,
        target_mode=WriterMode.ledger,
        transition_owner=OWNER,
        expected_control=observed,
        db_client=database,
    )
    receipt = _receipt(transitioned)
    first = complete_writer_transition(
        UID,
        transition_owner=OWNER,
        expected_control=transitioned,
        receipt=receipt,
        db_client=database,
    )
    replay = complete_writer_transition(
        UID,
        transition_owner=OWNER,
        expected_control=transitioned,
        receipt=receipt,
        db_client=database,
    )
    assert replay == first
    assert database.transactions[-1].sets == []

    other_database = _database(transitioned)
    with pytest.raises(WriterTransitionConflict) as cross_owner:
        complete_writer_transition(
            UID,
            transition_owner="migration-run-2",
            expected_control=transitioned,
            receipt=_receipt(transitioned, transition_owner="migration-run-2"),
            db_client=other_database,
        )
    assert cross_owner.value.code == WriterTransitionConflictCode.cross_owner


def test_abort_returns_only_to_prior_stable_mode_and_replay_is_idempotent():
    observed = _control(writer_mode=WriterMode.ledger, writer_epoch=8)
    database = _database(observed)
    transitioning = begin_writer_transition(
        UID,
        target_mode=WriterMode.compatibility,
        transition_owner=OWNER,
        expected_control=observed,
        db_client=database,
    )
    aborted = abort_writer_transition(
        UID,
        transition_owner=OWNER,
        expected_control=transitioning,
        db_client=database,
    )
    replay = abort_writer_transition(
        UID,
        transition_owner=OWNER,
        expected_control=transitioning,
        db_client=database,
    )

    assert aborted.writer_mode == WriterMode.ledger
    assert aborted.writer_epoch == transitioning.writer_epoch
    assert aborted.source_generation == transitioning.source_generation
    assert replay == aborted
    assert database.transactions[-1].sets == []


def test_content_bearing_proof_and_cross_user_fence_are_rejected():
    transitioned = _control(
        writer_mode=WriterMode.transitioning_to_ledger,
        writer_epoch=1,
        writer_transition_owner=OWNER,
    )
    payload = _receipt(transitioned).model_dump(mode="python")
    payload["content"] = "must never enter a control-plane receipt"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CompleteUnionProofReceipt.model_validate(payload)

    database = _database(transitioned)
    foreign = transitioned.model_copy(update={"uid": "another-user"})
    with pytest.raises(WriterTransitionConflict) as cross_owner:
        abort_writer_transition(
            UID,
            transition_owner=OWNER,
            expected_control=foreign,
            db_client=database,
        )
    assert cross_owner.value.code == WriterTransitionConflictCode.cross_owner

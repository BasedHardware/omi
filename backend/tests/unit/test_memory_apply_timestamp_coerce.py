"""Regression: a malformed stored timestamp string must not abort a long-term memory patch.

apply_long_term_patch_transaction coerces four optional timestamp fields
(last_corroborated_at, captured_at, updated_at, expires_at) from ISO strings via
datetime.fromisoformat. A single drifted value (a non-ISO string left by an older writer)
used to raise ValueError and abort the whole patch apply for that item. The guard drops just
the malformed field, so the item keeps its existing (update path) or materialized (create
path) value and the patch still commits.
"""

from datetime import datetime, timezone

from models.memory_apply import (
    ApplyStatus,
    MemoryControlState,
    apply_long_term_patch_transaction,
    _coerce_iso_timestamp,
)
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.memory_contracts import DurablePatchDecision, LifecycleState


def _operation(**overrides):
    base = dict(
        uid="u1",
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id="pkt1",
        target_memory_id=None,
        evidence_ids=["ev1"],
        logical_payload={"decision": "add", "memory_text": "User prefers concise updates.", "result_status": "active"},
        account_generation=1,
        source_generation=2,
        observed_head_commit_id="head0",
    )
    base.update(overrides)
    return MemoryOperation.new(**base)


def _patch(**overrides):
    payload = dict(
        patch_id="patch1",
        packet_id="pkt1",
        run_id="run1",
        observed_head_commit_id="head0",
        idempotency_key="idem1",
        decision=DurablePatchDecision.add,
        result_status=LifecycleState.active,
        evidence_ids=["ev1"],
        memory_text="User prefers concise updates.",
        confidence="medium",
        relationship_to_user="self",
        subject_entity_id="user",
        subject_label="the user",
        aboutness="primary_user",
    )
    payload.update(overrides)
    return payload


def _control():
    return MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)


def test_coerce_iso_timestamp_parses_valid_z_suffix():
    parsed = _coerce_iso_timestamp("2026-07-14T12:00:00Z", field="updated_at")
    assert parsed == datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def test_coerce_iso_timestamp_returns_none_on_malformed():
    assert _coerce_iso_timestamp("not-a-timestamp", field="captured_at") is None


def test_malformed_timestamp_field_is_dropped_and_patch_still_commits():
    # Before the guard, a non-ISO captured_at raised ValueError out of the whole apply.
    result = apply_long_term_patch_transaction(
        control_state=_control(),
        operation=_operation(),
        patch_payload=_patch(captured_at="not-a-timestamp"),
    )

    assert result.status == ApplyStatus.committed
    committed = result.memory_items[0]
    # The malformed value was dropped; the item kept its materialized captured_at (a real datetime).
    assert isinstance(committed.captured_at, datetime)
    assert committed.captured_at != "not-a-timestamp"


def test_valid_timestamp_overrides_are_applied():
    result = apply_long_term_patch_transaction(
        control_state=_control(),
        operation=_operation(),
        patch_payload=_patch(captured_at="2026-07-14T00:00:00Z", updated_at="2026-07-14T01:00:00Z"),
    )

    assert result.status == ApplyStatus.committed
    committed = result.memory_items[0]
    assert committed.captured_at == datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc)
    assert committed.updated_at == datetime(2026, 7, 14, 1, 0, tzinfo=timezone.utc)

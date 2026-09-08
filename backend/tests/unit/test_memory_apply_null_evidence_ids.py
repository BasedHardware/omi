"""Regression test: a present-but-null evidence_ids must not 500 the durable-patch replay.

models.memory_apply.apply_long_term_patch_transaction synthesizes MemoryEvidence entries with
`for evidence_id in raw.get("evidence_ids", [])`. get's default only applies to an ABSENT key,
so a patch payload with evidence_ids=None makes `for x in None` raise TypeError at that
comprehension - before the DurableMemoryPatch(**raw) try/except - so the replay 500s instead of
returning invalid_patch. The iteration now coerces null to [], and the malformed payload is
rejected gracefully by patch validation.
"""

from datetime import datetime, timezone

from models.memory_apply import (
    ApplyStatus,
    MemoryControlState,
    apply_long_term_patch_transaction,
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


def test_null_evidence_ids_returns_invalid_patch_not_500():
    result = apply_long_term_patch_transaction(
        control_state=_control(),
        operation=_operation(),
        patch_payload=_patch(evidence_ids=None),
    )

    assert result.status == ApplyStatus.invalid_patch


def test_valid_evidence_ids_commit():
    result = apply_long_term_patch_transaction(
        control_state=_control(),
        operation=_operation(),
        patch_payload=_patch(evidence_ids=["ev1"]),
    )

    assert result.status == ApplyStatus.committed

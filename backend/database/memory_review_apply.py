"""Canonical commit bridge for fenced reversible Review memory lifecycle edits.

Review owns the raw snapshot comparisons and journal in the same transaction;
this module reuses canonical commit, source/account gates and projection intents.
"""

from database import memory_apply_store as canonical
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.legal_holds import assert_no_destructive_operation_transaction
from database.memory_collections import MemoryCollections
from database.memory_apply_store import MemoryFirestoreApplyError
from models.memory_apply import (
    ApplyResult,
    ApplyStatus,
    MemoryControlState,
    MemoryWriterClass,
    require_writer_admitted,
    memory_item_outbox_events,
)
from models.memory_operations import MemoryOperation, MemoryOperationType


def commit_review_memory_items(
    transaction, db_client, uid, operation_id, items, *, source_generation, stamp=False, new_evidence=None
):
    """Canonical commit/outboxes for a fenced reversible Review lifecycle edit.

    All item/source comparisons and the encrypted Review journal are owned by
    the caller in this same transaction. Never rewrites legacy projections.
    """
    canonical.require_canonical_intake_enabled()
    assert_no_destructive_operation_transaction(transaction, db_client, uid=uid)
    deletion = db_client.document(f'account_deletions/{uid}').get(transaction=transaction)
    deletion_payload = deletion.to_dict() or {}
    if account_deletion_blocks_access(
        normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=deletion_payload.get('wipe_status'))
    ):
        raise MemoryFirestoreApplyError('Review memory change blocked by account deletion')
    collections = MemoryCollections(uid=uid)
    control = canonical.read_model(
        ref=db_client.document(collections.memory_apply_control_state),
        transaction=transaction,
        model=MemoryControlState,
        label='memory control',
    )
    require_writer_admitted(control, MemoryWriterClass.ledger)
    if source_generation is not None and source_generation != control.source_generation:
        raise MemoryFirestoreApplyError('Review memory source generation changed')
    if any(item.uid != uid or item.account_generation != control.account_generation for item in items):
        raise MemoryFirestoreApplyError('Review memory account generation changed')
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.ledger_mutation,
        source_packet_id=operation_id,
        target_memory_id=items[0].memory_id,
        evidence_ids=sorted({ev.evidence_id for item in items for ev in item.evidence}),
        logical_payload={
            'decision': 'update',
            'target_memory_id': items[0].memory_id,
            'mutation_metadata': {'review_operation': operation_id},
        },
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    commit_id = control.next_commit_id(operation.operation_id)
    next_control = control.advance_head(commit_id)
    if stamp:
        items = [
            item.model_copy(update={'ledger_commit_id': commit_id, 'ledger_sequence': next_control.commit_sequence})
            for item in items
        ]
    events = memory_item_outbox_events(items, operation, control, next_control, commit_id)
    committed = operation.mark_committed(
        commit_id,
        committed_sequence=next_control.commit_sequence,
        committed_memory_item_ids=[item.memory_id for item in items],
        committed_outbox_event_ids=[event.event_id for event in events],
    )
    result = ApplyResult(
        status=ApplyStatus.committed,
        control_state=next_control,
        operation=committed,
        memory_items=items,
        outbox_events=events,
    )
    canonical.write_apply_result(
        transaction=transaction,
        db_client=db_client,
        collections=collections,
        operation_ref=db_client.document(f'{collections.memory_operations}/{operation.operation_id}'),
        result=result,
    )
    evidence_items = (
        []
        if new_evidence is None
        else (list(new_evidence) if isinstance(new_evidence, (list, tuple)) else [new_evidence])
    )
    for evidence in evidence_items:
        transaction.set(
            db_client.document(f'{collections.memory_evidence}/{evidence.evidence_id}'),
            canonical.firestore_data(evidence),
        )
    return control.source_generation, [canonical.firestore_data(item) for item in items]

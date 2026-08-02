"""Durable workflow-owned handoff for canonical recurrence signals."""

import hashlib
from datetime import datetime, timezone
from typing import Any

from config.canonical_memory_cohort import is_canonical_memory_user
from database.read_boundary import MalformedDocError, parse_snapshot_strict, parse_snapshots
from database.store import get_document_store
from database.store.sentinels import Increment
from models.memory_recurrence import CanonicalRecurrenceSignal
from models.workstream_association import (
    RecurrenceInboxReceipt,
    RecurrenceInboxStatus,
    RecurrenceOutcomeKind,
)
from models.task_intelligence import TaskWorkflowControl

RECURRENCE_INBOX_COLLECTION = 'task_recurrence_inbox'
TASK_INTELLIGENCE_CONTROL_COLLECTION = 'task_intelligence_control'
TASK_INTELLIGENCE_CONTROL_DOCUMENT = 'state'


class RecurrenceGenerationMismatchError(RuntimeError):
    pass


def _store():
    """The configured document store (``STORAGE_BACKEND`` seam, ADR-0002/0004). Tests patch this."""
    return get_document_store()


def _receipt_id(uid: str, loop_key: str, account_generation: int) -> str:
    digest = hashlib.sha256(f'{uid}:{account_generation}:{loop_key}'.encode('utf-8')).hexdigest()[:40]
    return f'recurrence_inbox_{digest}'


def _inbox_path(uid: str) -> str:
    return f'users/{uid}/{RECURRENCE_INBOX_COLLECTION}'


def _receipt_path(uid: str, receipt_id: str) -> str:
    return f'{_inbox_path(uid)}/{receipt_id}'


def _control_path(uid: str) -> str:
    return f'users/{uid}/{TASK_INTELLIGENCE_CONTROL_COLLECTION}/{TASK_INTELLIGENCE_CONTROL_DOCUMENT}'


def _validate_generation(snapshot: Any, *, uid: str, account_generation: int) -> None:
    if not is_canonical_memory_user(uid):
        raise RecurrenceGenerationMismatchError('canonical task intelligence is not enabled')
    if not snapshot.exists:
        control = TaskWorkflowControl()
    else:
        try:
            control = parse_snapshot_strict(TaskWorkflowControl, snapshot)
        except MalformedDocError as error:
            raise RecurrenceGenerationMismatchError('task workflow control is malformed') from error
    if control.account_generation != account_generation:
        raise RecurrenceGenerationMismatchError('account generation mismatch')


def _from_snapshot(snapshot: Any) -> RecurrenceInboxReceipt:
    return parse_snapshot_strict(RecurrenceInboxReceipt, snapshot)


def _storage(receipt: RecurrenceInboxReceipt) -> dict[str, Any]:
    payload = receipt.model_dump(mode='json')
    payload['created_at'] = receipt.created_at
    payload['updated_at'] = receipt.updated_at
    return payload


def enqueue_recurrence_signal(
    uid: str,
    signal: CanonicalRecurrenceSignal,
    *,
    account_generation: int,
) -> RecurrenceInboxReceipt:
    """Persist before mutation; completed receipts never reopen within a generation."""
    receipt_id = _receipt_id(uid, signal.stable_loop_key, account_generation)
    receipt_path = _receipt_path(uid, receipt_id)
    control_path = _control_path(uid)
    now = datetime.now(timezone.utc)

    def apply(tx):
        _validate_generation(tx.get(control_path), uid=uid, account_generation=account_generation)
        snapshot = tx.get(receipt_path)
        if snapshot.exists:
            stored = _from_snapshot(snapshot)
            # Freeze the first proposal until completion. If Candidate creation
            # committed but this receipt ack failed, mutating the proposal would
            # reuse its idempotency key with different content forever.
            return stored
        receipt = RecurrenceInboxReceipt(
            receipt_id=receipt_id,
            loop_key=signal.stable_loop_key,
            account_generation=account_generation,
            status=RecurrenceInboxStatus.pending,
            signal=signal,
            created_at=now,
            updated_at=now,
        )
        tx.set(receipt_path, _storage(receipt))
        return receipt

    return _store().run_transaction(apply)


def list_pending_recurrence_receipts(
    uid: str,
    *,
    account_generation: int,
    limit: int = 100,
) -> list[RecurrenceInboxReceipt]:
    docs = _store().query(
        _inbox_path(uid),
        filters=[
            ('status', '==', RecurrenceInboxStatus.pending.value),
            ('account_generation', '==', account_generation),
        ],
        limit=limit,
    )
    return parse_snapshots(RecurrenceInboxReceipt, docs)


def complete_recurrence_receipt(
    uid: str,
    receipt_id: str,
    *,
    outcome: RecurrenceOutcomeKind,
    account_generation: int,
) -> None:
    receipt_path = _receipt_path(uid, receipt_id)
    control_path = _control_path(uid)

    def apply(tx):
        _validate_generation(tx.get(control_path), uid=uid, account_generation=account_generation)
        snapshot = tx.get(receipt_path)
        if not snapshot.exists or _from_snapshot(snapshot).account_generation != account_generation:
            raise RecurrenceGenerationMismatchError('recurrence receipt generation mismatch')
        tx.update(
            receipt_path,
            {
                'status': RecurrenceInboxStatus.completed.value,
                'last_outcome': outcome.value,
                'last_error_code': None,
                'attempts': Increment(1),
                'updated_at': datetime.now(timezone.utc),
            },
        )

    _store().run_transaction(apply)


def retry_recurrence_receipt(
    uid: str,
    receipt_id: str,
    *,
    error_code: str,
    account_generation: int,
) -> None:
    receipt_path = _receipt_path(uid, receipt_id)
    control_path = _control_path(uid)

    def apply(tx):
        _validate_generation(tx.get(control_path), uid=uid, account_generation=account_generation)
        snapshot = tx.get(receipt_path)
        if not snapshot.exists or _from_snapshot(snapshot).account_generation != account_generation:
            raise RecurrenceGenerationMismatchError('recurrence receipt generation mismatch')
        tx.update(
            receipt_path,
            {
                'last_error_code': error_code[:128],
                'attempts': Increment(1),
                'updated_at': datetime.now(timezone.utc),
            },
        )

    _store().run_transaction(apply)


__all__ = [
    'complete_recurrence_receipt',
    'enqueue_recurrence_signal',
    'list_pending_recurrence_receipts',
    'retry_recurrence_receipt',
    'RecurrenceGenerationMismatchError',
]

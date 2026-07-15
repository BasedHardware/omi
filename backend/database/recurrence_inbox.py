"""Durable workflow-owned handoff for canonical recurrence signals."""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import ValidationError

from database._client import db as default_db
from models.memory_recurrence import CanonicalRecurrenceSignal
from models.workstream_association import (
    RecurrenceInboxReceipt,
    RecurrenceInboxStatus,
    RecurrenceOutcomeKind,
)
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode

logger = logging.getLogger(__name__)

RECURRENCE_INBOX_COLLECTION = 'task_recurrence_inbox'
TASK_INTELLIGENCE_CONTROL_COLLECTION = 'task_intelligence_control'
TASK_INTELLIGENCE_CONTROL_DOCUMENT = 'state'


class RecurrenceGenerationMismatchError(RuntimeError):
    pass


def _get_db(firestore_client: Any = None):
    return firestore_client if firestore_client is not None else default_db


def _receipt_id(uid: str, loop_key: str, account_generation: int) -> str:
    digest = hashlib.sha256(f'{uid}:{account_generation}:{loop_key}'.encode('utf-8')).hexdigest()[:40]
    return f'recurrence_inbox_{digest}'


def _receipt_ref(uid: str, receipt_id: str, *, firestore_client: Any = None):
    return (
        _get_db(firestore_client)
        .collection('users')
        .document(uid)
        .collection(RECURRENCE_INBOX_COLLECTION)
        .document(receipt_id)
    )


def _control_ref(uid: str, *, firestore_client: Any = None):
    return (
        _get_db(firestore_client)
        .collection('users')
        .document(uid)
        .collection(TASK_INTELLIGENCE_CONTROL_COLLECTION)
        .document(TASK_INTELLIGENCE_CONTROL_DOCUMENT)
    )


def _validate_generation(snapshot: Any, account_generation: int) -> None:
    try:
        control = (
            TaskWorkflowControl.model_validate(snapshot.to_dict() or {}) if snapshot.exists else TaskWorkflowControl()
        )
    except ValidationError as e:
        # A drifted control doc (extra='forbid' plus a renamed/removed field, a bad enum) must not crash the
        # recurrence handoff. Fall back to the legacy-safe default (workflow_mode=off, account_generation=0),
        # which fails the checks below, so a malformed control is treated as a generation mismatch (fail-closed)
        # rather than raising ValidationError. Log bounded error types only, never input_value (task text).
        logger.warning(
            'Ignoring malformed task workflow control in recurrence inbox: %s',
            [str(err.get('type', 'unknown')) for err in e.errors(include_input=False, include_url=False)[:5]],
        )
        control = TaskWorkflowControl()
    if control.account_generation != account_generation:
        raise RecurrenceGenerationMismatchError('account generation mismatch')
    if control.workflow_mode not in {TaskWorkflowMode.write, TaskWorkflowMode.read}:
        raise RecurrenceGenerationMismatchError('task workflow mode changed')


def _from_snapshot(snapshot: Any) -> RecurrenceInboxReceipt:
    return RecurrenceInboxReceipt.model_validate(snapshot.to_dict() or {})


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
    firestore_client: Any = None,
) -> RecurrenceInboxReceipt:
    """Persist before mutation; completed receipts never reopen within a generation."""
    client = _get_db(firestore_client)
    receipt_id = _receipt_id(uid, signal.stable_loop_key, account_generation)
    ref = _receipt_ref(uid, receipt_id, firestore_client=client)
    transaction = client.transaction()
    now = datetime.now(timezone.utc)

    @firestore.transactional
    def apply(write_transaction):
        _validate_generation(
            _control_ref(uid, firestore_client=client).get(transaction=write_transaction), account_generation
        )
        snapshot = ref.get(transaction=write_transaction)
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
        write_transaction.create(ref, _storage(receipt))
        return receipt

    return apply(transaction)


def list_pending_recurrence_receipts(
    uid: str,
    *,
    account_generation: int,
    limit: int = 100,
    firestore_client: Any = None,
) -> list[RecurrenceInboxReceipt]:
    query = (
        _get_db(firestore_client)
        .collection('users')
        .document(uid)
        .collection(RECURRENCE_INBOX_COLLECTION)
        .where(filter=FieldFilter('status', '==', RecurrenceInboxStatus.pending.value))
        .where(filter=FieldFilter('account_generation', '==', account_generation))
        .limit(limit)
    )
    return [_from_snapshot(snapshot) for snapshot in query.stream()]


def complete_recurrence_receipt(
    uid: str,
    receipt_id: str,
    *,
    outcome: RecurrenceOutcomeKind,
    account_generation: int,
    firestore_client: Any = None,
) -> None:
    client = _get_db(firestore_client)
    ref = _receipt_ref(uid, receipt_id, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction):
        _validate_generation(
            _control_ref(uid, firestore_client=client).get(transaction=write_transaction), account_generation
        )
        snapshot = ref.get(transaction=write_transaction)
        if not snapshot.exists or _from_snapshot(snapshot).account_generation != account_generation:
            raise RecurrenceGenerationMismatchError('recurrence receipt generation mismatch')
        write_transaction.update(
            ref,
            {
                'status': RecurrenceInboxStatus.completed.value,
                'last_outcome': outcome.value,
                'last_error_code': None,
                'attempts': firestore.Increment(1),
                'updated_at': datetime.now(timezone.utc),
            },
        )

    apply(transaction)


def retry_recurrence_receipt(
    uid: str,
    receipt_id: str,
    *,
    error_code: str,
    account_generation: int,
    firestore_client: Any = None,
) -> None:
    client = _get_db(firestore_client)
    ref = _receipt_ref(uid, receipt_id, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction):
        _validate_generation(
            _control_ref(uid, firestore_client=client).get(transaction=write_transaction), account_generation
        )
        snapshot = ref.get(transaction=write_transaction)
        if not snapshot.exists or _from_snapshot(snapshot).account_generation != account_generation:
            raise RecurrenceGenerationMismatchError('recurrence receipt generation mismatch')
        write_transaction.update(
            ref,
            {
                'last_error_code': error_code[:128],
                'attempts': firestore.Increment(1),
                'updated_at': datetime.now(timezone.utc),
            },
        )

    apply(transaction)


__all__ = [
    'complete_recurrence_receipt',
    'enqueue_recurrence_signal',
    'list_pending_recurrence_receipts',
    'retry_recurrence_receipt',
    'RecurrenceGenerationMismatchError',
]

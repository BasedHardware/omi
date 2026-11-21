"""Durable, generation-bound receipts for the account wipe's Go queue barrier."""

import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Literal

from google.cloud import firestore
from google.cloud.firestore_v1 import transactional

from database.account_deletion_marker import (
    account_deletion_document,
    account_deletion_firestore_client,
)

from database.batch_account_authority import write_account_authority
from database.legal_holds import assert_destructive_operation_transaction

ERASE_DEADLINE = timedelta(minutes=15)
ARMED_AT = 'go_queue_erase_armed_at'
RECEIPT_AT = 'go_queue_erase_receipt_at'
WIPE_AT = 'go_queue_erase_wipe_started_at'
CLAIM = 'go_queue_erase_claim'
CLAIM_EXPIRES_AT = 'go_queue_erase_claim_expires_at'
ERASE_LEASE_SECONDS = 180
ERASE_GRANT_DURATION = timedelta(seconds=25)
PROTECTED_ATTEMPT = 'go_queue_erase_protected_attempt'
PATH = 'go_queue_erase_path'
RECOVERY_QUEUE_ID = 'go_queue_erase_recovery_queue_id'
ORDER_UNKNOWN = 'go_queue_erase_prior_wipe_unknown'
Step = Literal['arm', 'verify', 'receipt', 'wipe']


def running_stale_window(marker: dict, default: timedelta) -> timedelta:
    if marker.get(ARMED_AT) is not None and marker.get(RECEIPT_AT) is None:
        return min(default, timedelta(minutes=4))
    return default


def claim_fingerprint(token: str) -> str:
    return sha256(token.encode()).hexdigest()


@transactional
def mark_wipe_running(transaction, ref, job_id: str, claim: str, operation_id: str) -> bool:
    snapshot = ref.get(transaction=transaction)
    marker = (snapshot.to_dict() or {}) if snapshot.exists else {}
    armed = marker.get(ARMED_AT) is not None
    if marker.get('wipe_job_id') != job_id or marker.get('wipe_status') != 'retrying':
        raise RuntimeError('account deletion wipe claim generation changed')
    now = datetime.now(timezone.utc)
    fields: dict[str, Any] = {
        'wipe_status': 'running',
        'wipe_running_at': now,
        PROTECTED_ATTEMPT: now,
        CLAIM: claim,
        CLAIM_EXPIRES_AT: None,
    }
    previous = marker.get('wipe_running_at')
    if previous and not armed and marker.get(PROTECTED_ATTEMPT) != previous:
        fields[ORDER_UNKNOWN] = True
    write_account_authority(transaction, ref, fields, merge=True, preimage=snapshot, operation_id=operation_id)
    return armed


def _generation_due(marker: dict[str, Any]) -> object:
    due = marker.get('wipe_due_at')
    restored = marker.get('wipe_restored_at')
    intent = marker.get('wipe_intent_at')
    grace_completed = marker.get('grace_actions_completed_at')
    if (
        isinstance(restored, datetime)
        and isinstance(intent, datetime)
        and restored < intent
        and (grace_completed is None or (isinstance(grace_completed, datetime) and grace_completed <= restored))
    ):
        # An immediate request after restore inherits the cancelled grace fields.
        armed = marker.get(ARMED_AT)
        if armed is None:
            return None
    return due


def valid_recovery_queue_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value) is not None


@transactional
def _record(
    transaction,
    client,
    ref,
    uid: str,
    job_id: str,
    claim: str,
    step: Step,
    path: str | None,
    expires: datetime | None,
    queue_id: str | None,
):
    assert_destructive_operation_transaction(
        transaction, client, uid=uid, kind='account_deletion', token=f'account-deletion:{uid}'
    )
    snapshot = ref.get(transaction=transaction)
    marker = snapshot.to_dict() or {}
    due = _generation_due(marker)
    if (
        marker.get('wipe_job_id') != job_id
        or marker.get('wipe_status') != 'running'
        or (
            due is not None
            and (not isinstance(due, datetime) or due.tzinfo is None or due > datetime.now(timezone.utc))
        )
    ):
        raise RuntimeError('Go queue erase requires the active due wipe generation')
    if marker.get(CLAIM) != claim:
        raise RuntimeError('Go queue erase claim changed')
    has_receipt = marker.get(RECEIPT_AT) is not None
    if has_receipt and marker.get(PATH) == 'postgres' and not valid_recovery_queue_id(marker.get(RECOVERY_QUEUE_ID)):
        raise RuntimeError('Go queue recovery receipt is missing verified queue identity')
    if step == 'arm':
        if has_receipt:
            return marker
        now = datetime.now(timezone.utc)
        if expires is None or not now < expires <= now + ERASE_GRANT_DURATION:
            raise RuntimeError('Go queue erase claim expired before arming')
        fields: dict[str, Any] = {CLAIM_EXPIRES_AT: expires}
        if marker.get(ARMED_AT) is None:
            fields.update({ARMED_AT: firestore.SERVER_TIMESTAMP, RECEIPT_AT: None})
            if due is None:
                fields['wipe_due_at'] = firestore.SERVER_TIMESTAMP
            if isinstance(marker.get('wipe_auth_deleted_at'), datetime):
                fields[WIPE_AT] = marker['wipe_auth_deleted_at']
        transaction.update(ref, fields)
    elif not isinstance(marker.get(ARMED_AT), datetime):
        raise RuntimeError('Go queue erase claim changed')
    elif step == 'verify' and (
        not isinstance(marker.get(CLAIM_EXPIRES_AT), datetime) or marker[CLAIM_EXPIRES_AT] <= datetime.now(timezone.utc)
    ):
        raise RuntimeError('Go queue erase claim expired')
    elif step == 'receipt' and marker.get(RECEIPT_AT) is None:
        fields: dict[str, Any] = {RECEIPT_AT: firestore.SERVER_TIMESTAMP, PATH: path, CLAIM_EXPIRES_AT: None}
        if path == 'postgres':
            if not valid_recovery_queue_id(queue_id):
                raise RuntimeError('Go queue recovery receipt is missing verified queue identity')
            fields[RECOVERY_QUEUE_ID] = queue_id
        transaction.update(ref, fields)
    elif step == 'wipe':
        if not isinstance(marker.get(RECEIPT_AT), datetime):
            raise RuntimeError('Go queue erase receipt missing')
        if marker.get(WIPE_AT) is None:
            transaction.update(ref, {WIPE_AT: firestore.SERVER_TIMESTAMP})
    return marker


def record(
    uid: str,
    job_id: str,
    claim: str,
    step: Step,
    path: str | None = None,
    *,
    expires: datetime | None = None,
    queue_id: str | None = None,
):
    client = account_deletion_firestore_client()
    ref = account_deletion_document(uid, firestore_client=client)
    return _record(client.transaction(), client, ref, uid, job_id, claim, step, path, expires, queue_id)


def summarize(now: datetime, markers) -> dict[str, int]:
    """Count matured cohorts by arming time, including those with no receipt."""
    cutoff = now - ERASE_DEADLINE
    start = now - timedelta(days=7)
    good = total = overdue = 0
    for marker in markers:
        armed = marker.get(ARMED_AT)
        if not isinstance(armed, datetime) or armed > cutoff:
            continue
        ack = marker.get(RECEIPT_AT)
        wipe = marker.get(WIPE_AT)
        if ack is None:
            overdue += 1
        if armed < start:
            continue
        total += 1
        if (
            marker.get(ORDER_UNKNOWN) is not True
            and isinstance(ack, datetime)
            and armed <= ack <= armed + ERASE_DEADLINE
            and (wipe is None or ack <= wipe)
        ):
            good += 1
    return {'met': good, 'eligible': total, 'overdue_pending': overdue}


def readback(now: datetime, collection) -> dict[str, int]:
    """Read aggregate evidence from the authoritative marker collection."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    cutoff = now - ERASE_DEADLINE
    recent = (
        collection.where(filter=FieldFilter(ARMED_AT, '>=', now - timedelta(days=7)))
        .where(filter=FieldFilter(ARMED_AT, '<=', cutoff))
        .select([ARMED_AT, RECEIPT_AT, WIPE_AT, ORDER_UNKNOWN])
    )
    result = summarize(now, (snapshot.to_dict() or {} for snapshot in recent.stream()))
    # Only armed, unresolved markers explicitly store a null receipt. Filter
    # the old ones in memory to avoid a cross-field composite index.
    pending = collection.where(filter=FieldFilter(RECEIPT_AT, '==', None)).select([ARMED_AT])
    for snapshot in pending.stream():
        armed = (snapshot.to_dict() or {}).get(ARMED_AT)
        if isinstance(armed, datetime) and armed < now - timedelta(days=7):
            result['overdue_pending'] += 1
    return result

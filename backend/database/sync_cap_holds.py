"""Transfer fenced sync-ledger ownership to durable, recoverable audio holds.

A held upload is acknowledged, but is not proof of completed transcription.
Only settlement of every referenced hold can publish that proof.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client
from database.sync_ledger import (
    sync_content_reference,
    sync_content_owner_matches,
    is_valid_completed_sync_content_result,
    is_valid_held_sync_content_result,
    LEDGER_RETENTION_DAYS,
)

PROTOCOL = 'stt_cap_hold_v1'


def mark_content_held(
    uid: str,
    content_id: str,
    job_id: str,
    result: dict,
    hold_ids: list[str],
    *,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    if not hold_ids or not is_valid_held_sync_content_result(result):
        raise ValueError('durable held audio receipts required')
    client = get_firestore_client()
    ref = sync_content_reference(client, uid, content_id)

    @firestore.transactional
    def commit(tx: Any) -> bool:
        row = ref.get(transaction=tx).to_dict() or {}
        if not sync_content_owner_matches(row, job_id, run_token, run_epoch):
            return False
        tx.update(
            ref,
            {
                'status': 'held',
                'dispatch_protocol': PROTOCOL,
                'result': result,
                'cap_hold_ids': sorted(set(hold_ids)),
                'pending_cap_hold_ids': sorted(set(hold_ids)),
                'updated_at': datetime.now(timezone.utc),
                # An unprocessed capture must survive inactive accounts.
                'expires_at': firestore.DELETE_FIELD,
            },
        )
        return True

    return commit(client.transaction())


def recovery_status(uid: str, content_id: str, hold_id: str) -> str:
    row = sync_content_reference(get_firestore_client(), uid, content_id).get().to_dict() or {}
    if row.get('status') == 'completed' and is_valid_completed_sync_content_result(row.get('result')):
        return 'completed'
    if row.get('dispatch_protocol') == PROTOCOL and row.get('status') == 'held':
        if hold_id not in row.get('cap_hold_ids', []):
            return 'waiting'
        return 'ready' if hold_id in row.get('pending_cap_hold_ids', []) else 'settled'
    return 'waiting'  # The original worker still owns preparation/retry.


def settle_hold(uid: str, content_id: str, hold_id: str, response: dict, pieces: int) -> bool:
    """Idempotently join one recovered hold; never overwrite another owner."""
    client = get_firestore_client()
    ref = sync_content_reference(client, uid, content_id)

    @firestore.transactional
    def commit(tx: Any) -> bool:
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('status') == 'completed':
            return is_valid_completed_sync_content_result(row.get('result'))
        if row.get('dispatch_protocol') != PROTOCOL or row.get('status') != 'held':
            return False
        if hold_id not in row.get('cap_hold_ids', []):
            return False
        pending = set(row.get('pending_cap_hold_ids') or [])
        if hold_id not in pending:
            return True
        pending.remove(hold_id)
        result = dict(row['result'])
        for key in ('new_memories', 'updated_memories'):
            result[key] = sorted(set(result.get(key) or []) | set(response.get(key) or []))
        result['recovered_segments'] = int(result.get('recovered_segments', 0)) + pieces
        result['held_audio'] = bool(pending)
        now = datetime.now(timezone.utc)
        updates: dict[str, Any] = {'result': result, 'pending_cap_hold_ids': sorted(pending), 'updated_at': now}
        if not pending:
            # All source audio has reached content/usage settlement; only now
            # can ordinary duplicate admission converge a completed result.
            result.update(failed_segments=0, errors=[], outcome='success')
            updates.update(status='completed', expires_at=now + timedelta(days=LEDGER_RETENTION_DAYS))
        tx.update(ref, updates)
        return True

    return commit(client.transaction())

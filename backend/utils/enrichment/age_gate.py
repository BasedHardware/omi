"""Reversible durable parking of historical enrichment, without deleting debt."""

from datetime import datetime, timezone
import logging
import math
import time
import uuid

from config import enrichment as enrichment_config

logger = logging.getLogger(__name__)
REASON = 'age_gate_72h'


def max_age_seconds() -> float:
    try:
        hours = float(enrichment_config.max_age_hours())
        seconds = hours * 3600
        if hours < 0 or not math.isfinite(seconds):
            return 72 * 3600
        return seconds
    except ValueError:
        return 72 * 3600


def timestamp(value) -> float | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.timestamp()
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            value = parsed.replace(tzinfo=timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp()
        except ValueError:
            return None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
        return float(value)
    return None


def expired(row, created_at=None, *, now: float) -> bool:
    seconds = max_age_seconds()
    if seconds == 0:
        return False
    cutoff = now - seconds
    return any(
        value is not None and value < cutoff
        for value in (timestamp(row.get('first_pending_at')), timestamp(created_at))
    )


def parked(row) -> bool:
    return bool(row.get('age_gate_parked') or row.get('deferred_reason') == REASON)


def park_row(row, *, now: float):
    # Keep identity, version, policy, first acceptance and every custody field.
    # A new token fences all old wakes; never steal an active lease.
    result = dict(row)
    result.update(
        age_gate_parked=True,
        dormant=True,
        deferred_reason=REASON,
        deferred_since=now,
        due_at=None,
        task_due_at=None,
        task_token=uuid.uuid4().hex,
        owner=None,
        lease_until=0,
    )
    return result


def conversation_created_at(row, client):
    if client is None or not row.get('uid') or not row.get('conversation_id'):
        return None
    snapshot = (
        client.collection('users')
        .document(row['uid'])
        .collection('conversations')
        .document(row['conversation_id'])
        .get(field_paths=['created_at'])
    )
    return (snapshot.to_dict() or {}).get('created_at') if snapshot.exists else None


def park_if_expired(row_id: str, token: str | None, *, now: float | None = None, client=None) -> bool:
    """CAS park only this unleased wake. True means it is durably parked.

    Created time is immutable scheduling metadata. No transcript or account
    profile is read. A missing timestamp cannot prove that work is historical.
    """
    seconds = max_age_seconds()
    current = time.time() if now is None else now
    if seconds == 0 or current <= seconds:
        return False
    from utils.enrichment import outbox

    resolved = client if client is not None else outbox.get_firestore_client()

    def update(old):
        if old is None:
            return old, False
        if parked(old):
            return old, True
        if old.get('dormant') or (token is not None and old.get('task_token') != token):
            return old, False
        if old.get('lease_until', 0) > current:
            return old, False
        created = None if expired(old, now=current) else conversation_created_at(old, resolved)
        if not expired(old, created, now=current):
            return old, False
        return park_row(old, now=current), True

    result = outbox.mutate_row(row_id, update, client=client)
    if result:
        logger.info('event=enrichment_age_gate outcome=parked reason=%s', REASON)
    return result

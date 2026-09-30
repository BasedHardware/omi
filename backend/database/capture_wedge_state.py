"""Atomic operational state for the capture-wedge self-heal detector.

One document per uid in ``capture_wedge_state`` carrying only operational
fields: ``first_seen_day`` (the UTC day the uid was first counted in the
wedge cohort) and ``last_nudge_at`` (the nudge cooldown stamp). Both claims
are transaction-owned so overlapping job ticks cannot double-count the daily
cohort or double-send a push. No tokens, transcripts, or device data live here.

A crash after a successful nudge claim may drop the nudge entirely — the
deliberate at-most-once tradeoff, preferred over double-sending to a user's
lock screen.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client

CAPTURE_WEDGE_STATE_COLLECTION = 'capture_wedge_state'
WEDGE_NUDGE_COOLDOWN = timedelta(hours=24)


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def claim_wedge_first_seen(
    uid: str,
    day: str,
    *,
    now: datetime | None = None,
    firestore_client: Any = None,
) -> bool:
    """Claim this uid's first-seen slot for ``day``; ``True`` only for the winner."""
    if not isinstance(uid, str) or not uid.strip():
        return False
    if not isinstance(day, str) or not day.strip():
        return False
    client = _client(firestore_client)
    clean_uid = uid.strip()
    clean_day = day.strip()
    doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(clean_uid)
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)

    def _txn(transaction: Any) -> bool:
        snapshot = doc_ref.get(transaction=transaction)
        data = snapshot.to_dict() or {} if getattr(snapshot, 'exists', False) else {}
        if data.get('first_seen_day') == clean_day:
            return False
        transaction.set(doc_ref, {'uid': clean_uid, 'first_seen_day': clean_day, 'updated_at': stamp}, merge=True)
        return True

    return firestore.transactional(_txn)(client.transaction())


def claim_wedge_nudge_cooldown(
    uid: str,
    *,
    cooldown: timedelta = WEDGE_NUDGE_COOLDOWN,
    now: datetime | None = None,
    firestore_client: Any = None,
) -> bool:
    """Claim the 24h nudge cooldown; ``True`` means the caller may send now.

    Claimed before the send so two racing ticks cannot both pass the check. If
    the process dies between claim and send the nudge is simply missed — the
    at-most-once tradeoff documented in the module docstring.
    """
    if not isinstance(uid, str) or not uid.strip():
        return False
    if not isinstance(cooldown, timedelta) or cooldown < timedelta(0):
        cooldown = WEDGE_NUDGE_COOLDOWN
    client = _client(firestore_client)
    clean_uid = uid.strip()
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(clean_uid)

    def _txn(transaction: Any) -> bool:
        snapshot = doc_ref.get(transaction=transaction)
        data = snapshot.to_dict() or {} if getattr(snapshot, 'exists', False) else {}
        last_nudge_at = data.get('last_nudge_at')
        if isinstance(last_nudge_at, datetime):
            if last_nudge_at.tzinfo is None:
                last_nudge_at = last_nudge_at.replace(tzinfo=timezone.utc)
            if now_dt - last_nudge_at < cooldown:
                return False
        transaction.set(doc_ref, {'uid': clean_uid, 'last_nudge_at': now_dt, 'updated_at': now_dt}, merge=True)
        return True

    return firestore.transactional(_txn)(client.transaction())


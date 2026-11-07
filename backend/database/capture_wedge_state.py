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


def _normalize_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def _normalize_utc(value: datetime | None) -> datetime:
    if not isinstance(value, datetime):
        return datetime.now(timezone.utc)
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_cooldown(cooldown: Any) -> timedelta:
    if not isinstance(cooldown, timedelta) or cooldown < timedelta(0):
        return WEDGE_NUDGE_COOLDOWN
    return cooldown


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    if not getattr(snapshot, 'exists', False):
        return {}
    return snapshot.to_dict() or {}


def claim_wedge_first_seen(
    uid: str,
    day: str,
    *,
    now: datetime | None = None,
    firestore_client: Any = None,
) -> bool:
    """Claim this uid's first-seen slot for ``day``; ``True`` only for the winner."""
    clean_uid = _normalize_non_empty_str(uid)
    clean_day = _normalize_non_empty_str(day)
    if not clean_uid or not clean_day:
        return False

    client = _client(firestore_client)
    collection = client.collection(CAPTURE_WEDGE_STATE_COLLECTION)
    doc_ref = collection.document(clean_uid)
    legacy_ref = collection.document(uid) if uid != clean_uid else None
    stamp = _normalize_utc(now)

    def _txn(transaction: Any) -> bool:
        snapshot = doc_ref.get(transaction=transaction)
        data = _snapshot_dict(snapshot)
        legacy_data = _snapshot_dict(legacy_ref.get(transaction=transaction)) if legacy_ref is not None else {}

        first_seen_day = data.get('first_seen_day')
        legacy_first_seen = legacy_data.get('first_seen_day')
        if (isinstance(first_seen_day, str) and first_seen_day.strip() == clean_day) or (
            isinstance(legacy_first_seen, str) and legacy_first_seen.strip() == clean_day
        ):
            return False

        payload: dict[str, Any] = {'uid': clean_uid, 'first_seen_day': clean_day, 'updated_at': stamp}
        if data.get('last_nudge_at') is None and isinstance(legacy_data.get('last_nudge_at'), datetime):
            payload['last_nudge_at'] = _normalize_utc(legacy_data['last_nudge_at'])
        transaction.set(doc_ref, payload, merge=True)
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
    clean_uid = _normalize_non_empty_str(uid)
    if not clean_uid:
        return False

    effective_cooldown = _normalize_cooldown(cooldown)
    now_utc = _normalize_utc(now)
    client = _client(firestore_client)
    collection = client.collection(CAPTURE_WEDGE_STATE_COLLECTION)
    doc_ref = collection.document(clean_uid)
    legacy_ref = collection.document(uid) if uid != clean_uid else None

    def _txn(transaction: Any) -> bool:
        snapshot = doc_ref.get(transaction=transaction)
        data = _snapshot_dict(snapshot)
        legacy_data = _snapshot_dict(legacy_ref.get(transaction=transaction)) if legacy_ref is not None else {}

        candidate_stamps = [
            _normalize_utc(stamp)
            for stamp in (data.get('last_nudge_at'), legacy_data.get('last_nudge_at'))
            if isinstance(stamp, datetime)
        ]
        if candidate_stamps and now_utc - max(candidate_stamps) < effective_cooldown:
            return False

        payload: dict[str, Any] = {'uid': clean_uid, 'last_nudge_at': now_utc, 'updated_at': now_utc}
        legacy_first_seen = legacy_data.get('first_seen_day')
        if data.get('first_seen_day') is None and isinstance(legacy_first_seen, str) and legacy_first_seen.strip():
            payload['first_seen_day'] = legacy_first_seen.strip()
        transaction.set(doc_ref, payload, merge=True)
        return True

    return firestore.transactional(_txn)(client.transaction())

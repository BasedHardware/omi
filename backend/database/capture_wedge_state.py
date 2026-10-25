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

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client

logger = logging.getLogger('capture_wedge_state')

CAPTURE_WEDGE_STATE_COLLECTION = 'capture_wedge_state'
WEDGE_NUDGE_COOLDOWN = timedelta(hours=24)
MAX_ID_LENGTH = 128
MAX_DAY_LENGTH = 32


def _clean_id(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    val = raw.strip()
    if not val or len(val) > MAX_ID_LENGTH:
        return None
    if '\x00' in val or '/' in val or '\\' in val or '..' in val:
        return None
    return val


def _clean_day(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    val = raw.strip()
    if not val or len(val) > MAX_DAY_LENGTH:
        return None
    if '\x00' in val or '/' in val or '\\' in val or '..' in val:
        return None
    return val


def _ensure_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _client(firestore_client: Any = None) -> Any:
    if firestore_client is not None:
        return firestore_client
    try:
        return get_firestore_client()
    except Exception:
        try:
            from database import _client as db_client
            if hasattr(db_client, 'db') and db_client.db is not None:
                return db_client.db
        except Exception:
            pass
        raise


def claim_wedge_first_seen(
    uid: str,
    day: str,
    *,
    now: datetime | None = None,
    firestore_client: Any = None,
) -> bool:
    """Claim this uid's first-seen slot for ``day``; ``True`` only for the winner."""
    clean_uid = _clean_id(uid)
    clean_day = _clean_day(day)
    if not clean_uid or not clean_day:
        return False

    try:
        client = _client(firestore_client)
        doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(clean_uid)
        stamp = _ensure_utc(now)

        def _txn(transaction: Any) -> bool:
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {} if getattr(snapshot, 'exists', False) else {}
            if data.get('first_seen_day') == clean_day:
                return False
            transaction.set(doc_ref, {'uid': clean_uid, 'first_seen_day': clean_day, 'updated_at': stamp}, merge=True)
            return True

        return bool(firestore.transactional(_txn)(client.transaction()))
    except Exception as exc:
        logger.warning('claim_wedge_first_seen failed for uid=%s day=%s: %s', clean_uid, clean_day, exc)
        return False


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
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return False

    try:
        client = _client(firestore_client)
        now_utc = _ensure_utc(now)
        doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(clean_uid)

        def _txn(transaction: Any) -> bool:
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {} if getattr(snapshot, 'exists', False) else {}
            last_nudge_at = data.get('last_nudge_at')
            if isinstance(last_nudge_at, datetime):
                last_nudge_utc = _ensure_utc(last_nudge_at)
                if now_utc - last_nudge_utc < cooldown:
                    return False
            transaction.set(doc_ref, {'uid': clean_uid, 'last_nudge_at': now_utc, 'updated_at': now_utc}, merge=True)
            return True

        return bool(firestore.transactional(_txn)(client.transaction()))
    except Exception as exc:
        logger.warning('claim_wedge_nudge_cooldown failed for uid=%s: %s', clean_uid, exc)
        return False


def get_wedge_state(
    uid: str,
    *,
    firestore_client: Any = None,
) -> dict[str, Any] | None:
    """Read the operational wedge state for inspection or recovery."""
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return None

    try:
        client = _client(firestore_client)
        doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(clean_uid)
        snapshot = doc_ref.get()
        if getattr(snapshot, 'exists', False):
            return snapshot.to_dict() or None
        return None
    except Exception as exc:
        logger.warning('get_wedge_state failed for uid=%s: %s', clean_uid, exc)
        return None


def reset_wedge_state(
    uid: str,
    *,
    firestore_client: Any = None,
) -> bool:
    """Reset operational wedge state for manual recovery or testing."""
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return False

    try:
        client = _client(firestore_client)
        doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(clean_uid)
        doc_ref.delete()
        return True
    except Exception as exc:
        logger.warning('reset_wedge_state failed for uid=%s: %s', clean_uid, exc)
        return False

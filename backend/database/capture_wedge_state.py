"""Atomic operational state for the capture-wedge self-heal detector.

One document per uid in ``capture_wedge_state`` carrying only operational
fields: ``first_seen_day`` (the UTC day the uid was first counted in the
wedge cohort) and ``last_nudge_at`` (the nudge cooldown stamp). Both claims
are transaction-owned so overlapping job ticks cannot double-count the daily
cohort or double-send a push. No tokens, transcripts, or device data live here.

A crash after a successful nudge claim may drop the nudge entirely – the
deliberate at-most-once tradeoff, preferred over double-sending to a user's
lock screen.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Optional

from google.cloud import firestore

from database._client import get_firestore_client, db

logger = logging.getLogger(__name__)

CAPTURE_WEDGE_STATE_COLLECTION = 'capture_wedge_state'
WEDGE_NUDGE_COOLDOWN = timedelta(hours=24)
MAX_ID_LENGTH = 128
MAX_DAY_LENGTH = 32


def _clean_id(id_val: Optional[str]) -> str:
    """Validate and sanitize user ID or identifier."""
    if not isinstance(id_val, str):
        return ""
    cleaned = id_val.strip()
    if (
        not cleaned
        or len(cleaned) > MAX_ID_LENGTH
        or "/" in cleaned
        or "\\" in cleaned
        or ".." in cleaned
        or "\x00" in cleaned
    ):
        return ""
    return cleaned


def _clean_day(day_val: Optional[str]) -> str:
    """Validate and sanitize day identifier (e.g. YYYY-MM-DD)."""
    if not isinstance(day_val, str):
        return ""
    cleaned = day_val.strip()
    if (
        not cleaned
        or len(cleaned) > MAX_DAY_LENGTH
        or "/" in cleaned
        or "\\" in cleaned
        or ".." in cleaned
        or "\x00" in cleaned
    ):
        return ""
    return cleaned


def _client(firestore_client: Any = None) -> Any:
    if firestore_client is not None:
        return firestore_client
    try:
        c = get_firestore_client()
        if c is not None:
            return c
    except Exception:
        pass
    return db


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
        logger.warning("Invalid uid %r or day %r in claim_wedge_first_seen", uid, day)
        return False

    client = _client(firestore_client)
    if client is None:
        logger.error("No firestore client available in claim_wedge_first_seen")
        return False

    doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(clean_uid)
    stamp = now or datetime.now(timezone.utc)

    def _txn(transaction: Any) -> bool:
        snapshot = doc_ref.get(transaction=transaction)
        data = snapshot.to_dict() or {} if getattr(snapshot, 'exists', False) else {}
        if data.get('first_seen_day') == clean_day:
            return False
        transaction.set(doc_ref, {'uid': clean_uid, 'first_seen_day': clean_day, 'updated_at': stamp}, merge=True)
        return True

    try:
        return bool(firestore.transactional(_txn)(client.transaction()))
    except Exception as e:
        logger.warning("Transaction error in claim_wedge_first_seen for uid %s: %s", clean_uid, e)
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
    the process dies between claim and send the nudge is simply missed – the
    at-most-once tradeoff documented in the module docstring.
    """
    clean_uid = _clean_id(uid)
    if not clean_uid:
        logger.warning("Invalid uid %r in claim_wedge_nudge_cooldown", uid)
        return False

    client = _client(firestore_client)
    if client is None:
        logger.error("No firestore client available in claim_wedge_nudge_cooldown")
        return False

    now = now or datetime.now(timezone.utc)
    doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(clean_uid)

    def _txn(transaction: Any) -> bool:
        snapshot = doc_ref.get(transaction=transaction)
        data = snapshot.to_dict() or {} if getattr(snapshot, 'exists', False) else {}
        last_nudge_at = data.get('last_nudge_at')
        if isinstance(last_nudge_at, datetime):
            if last_nudge_at.tzinfo is None:
                last_nudge_at = last_nudge_at.replace(tzinfo=timezone.utc)
            if now - last_nudge_at < cooldown:
                return False
        transaction.set(doc_ref, {'uid': clean_uid, 'last_nudge_at': now, 'updated_at': now}, merge=True)
        return True

    try:
        return bool(firestore.transactional(_txn)(client.transaction()))
    except Exception as e:
        logger.warning("Transaction error in claim_wedge_nudge_cooldown for uid %s: %s", clean_uid, e)
        return False


def get_wedge_state(
    uid: str,
    *,
    firestore_client: Any = None,
) -> Optional[dict[str, Any]]:
    """Retrieve operational state for a uid; returns None if not found or on error."""
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return None

    client = _client(firestore_client)
    if client is None:
        return None

    try:
        doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(clean_uid)
        snapshot = doc_ref.get()
        if getattr(snapshot, 'exists', False):
            return snapshot.to_dict() or {}
        return None
    except Exception as e:
        logger.warning("Failed to get wedge state for uid %s: %s", clean_uid, e)
        return None


def reset_wedge_state(
    uid: str,
    *,
    firestore_client: Any = None,
) -> bool:
    """Reset or delete the wedge state document for a uid (e.g. after repair or test teardown)."""
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return False

    client = _client(firestore_client)
    if client is None:
        return False

    try:
        doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(clean_uid)
        doc_ref.delete()
        return True
    except Exception as e:
        logger.warning("Failed to reset wedge state for uid %s: %s", clean_uid, e)
        return False


__all__ = [
    'CAPTURE_WEDGE_STATE_COLLECTION',
    'WEDGE_NUDGE_COOLDOWN',
    'claim_wedge_first_seen',
    'claim_wedge_nudge_cooldown',
    'get_wedge_state',
    'reset_wedge_state',
]

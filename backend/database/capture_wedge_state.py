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
import logging
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client

logger = logging.getLogger(__name__)

CAPTURE_WEDGE_STATE_COLLECTION = 'capture_wedge_state'
WEDGE_NUDGE_COOLDOWN = timedelta(hours=24)


def _clean_id(val: Any, field_name: str = "Identifier") -> str:
    """Sanitize identifier against path traversal, control chars, and length overruns."""
    if not isinstance(val, str):
        raise ValueError(f"{field_name} must be a string")
    cleaned = val.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    if len(cleaned) > 256:
        raise ValueError(f"{field_name} exceeds maximum allowable length of 256 characters")
    if '/' in cleaned or '\\' in cleaned or '..' in cleaned or '\x00' in cleaned:
        raise ValueError(f"{field_name} contains prohibited path-traversal or control characters")
    return cleaned


def _clean_day(day: Any) -> str:
    """Validate calendar date string strictly in YYYY-MM-DD format using datetime parsing."""
    if not isinstance(day, str):
        raise ValueError("day must be a string")
    cleaned = day.strip()
    try:
        datetime.strptime(cleaned, "%Y-%m-%d")
    except ValueError:
        raise ValueError("day must be a valid calendar date in YYYY-MM-DD format")
    return cleaned


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
    safe_uid = _clean_id(uid, "uid")
    safe_day = _clean_day(day)
    client = _client(firestore_client)
    doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(safe_uid)
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)

    def _txn(transaction: Any) -> bool:
        snapshot = doc_ref.get(transaction=transaction)
        data = snapshot.to_dict() or {} if getattr(snapshot, 'exists', False) else {}
        if data.get('first_seen_day') == safe_day:
            return False
        transaction.set(doc_ref, {'uid': safe_uid, 'first_seen_day': safe_day, 'updated_at': stamp}, merge=True)
        return True

    try:
        return bool(firestore.transactional(_txn)(client.transaction()))
    except Exception as exc:
        logger.error(f"Failed to claim capture wedge first seen for user {safe_uid}: {exc}", exc_info=True)
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
    safe_uid = _clean_id(uid, "uid")
    client = _client(firestore_client)
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(safe_uid)

    def _txn(transaction: Any) -> bool:
        snapshot = doc_ref.get(transaction=transaction)
        data = snapshot.to_dict() or {} if getattr(snapshot, 'exists', False) else {}
        last_nudge_at = data.get('last_nudge_at')
        if isinstance(last_nudge_at, datetime):
            if last_nudge_at.tzinfo is None:
                last_nudge_at = last_nudge_at.replace(tzinfo=timezone.utc)
            if now_dt - last_nudge_at < cooldown:
                return False
        transaction.set(doc_ref, {'uid': safe_uid, 'last_nudge_at': now_dt, 'updated_at': now_dt}, merge=True)
        return True

    try:
        return bool(firestore.transactional(_txn)(client.transaction()))
    except Exception as exc:
        logger.error(f"Failed to claim capture wedge nudge cooldown for user {safe_uid}: {exc}", exc_info=True)
        return False

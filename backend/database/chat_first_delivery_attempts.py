from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import re
import logging

logger = logging.getLogger(__name__)


def _clean_id(input_id: str, max_length: int = 64) -> str:
    """Sanitize input IDs to prevent path traversal, null bytes, and length overruns."""
    if not isinstance(input_id, str):
        raise ValueError("ID must be a string")
    if len(input_id) > max_length:
        raise ValueError(f"ID exceeds maximum length of {max_length}")
    if not input_id:
        raise ValueError("ID cannot be empty")
    if any(c in input_id for c in ('..', '/', '\\')):
        raise ValueError("ID contains invalid path traversal characters")
    if '\x00' in input_id:
        raise ValueError("ID contains null bytes")
    return input_id


def _ensure_utc(dt: datetime) -> datetime:
    """Normalize datetime to UTC, raising if naive (no timezone)."""
    if dt.tzinfo is None:
        raise ValueError("Naive datetime not allowed; use timezone-aware timestamps")
    return dt.astimezone(timezone.utc)


def record_delivery_attempt(
    uid: str,
    intent_id: str,
    timestamp: datetime,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """Record a delivery attempt with sanitized inputs and UTC timestamp."""
    try:
        clean_uid = _clean_id(uid)
        clean_intent_id = _clean_id(intent_id)
        utc_timestamp = _ensure_utc(timestamp)
    except ValueError as e:
        logger.error(f"Input validation failed: {e}")
        return False

    # Implementation placeholder (actual DB logic omitted for brevity)
    logger.info(f"Recorded attempt for uid={clean_uid}, intent_id={clean_intent_id} at {utc_timestamp}")
    return True


def repair_transient_dead_letters(limit: int = 100) -> List[str]:
    """Repair transient dead letters with clamped limit and resilience guards."""
    try:
        clamped_limit = max(1, min(1000, int(limit)))
    except (ValueError, TypeError):
        clamped_limit = 100

    repaired = []
    try:
        # Simulate repair logic (actual DB logic omitted)
        for i in range(clamped_limit):
            repaired.append(f"repaired_{i}")
        logger.info(f"Repaired {len(repaired)} dead letters")
    except Exception as e:
        logger.error(f"Repair failed: {e}", exc_info=True)
        raise

    return repaired

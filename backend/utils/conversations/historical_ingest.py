"""Historical-tier (T1+) ingest: stamp old backfill at create and settle it without enrichment.

Both producers (sync intake and the batch projection) create the row with a
final deterministic title and ``processing_tier='historical'`` when its trusted
capture start is past the tier age (``config/historical_tier.py``). Such a row
never enters the enrichment outbox: :func:`settle` finishes its sync hold with
the current content snapshot, so an identical later append is ``unchanged``
and only new speech reopens the hold. The summary waits for the owner's open.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from prometheus_client import Counter

from config import historical_tier
from database import conversations as conversations_db
from config.historical_tier import BLOCKED_REASON, TERMINAL_NO_DERIVED_EFFECTS_FIELD
from utils.conversations.summary_delivery import present
from utils.sync import processing_hold

logger = logging.getLogger(__name__)

ROWS = Counter(
    'omi_historical_tier_rows_total',
    'Historical-tier rows stamped at create and settled without enrichment',
    ['producer', 'outcome'],
)


def applies_at_create(capture_start: Any, *, trusted: bool, now: Any) -> bool:
    """Whether a new row from this capture is historical; the kill switch keeps new rows full."""
    if not historical_tier.tier_enabled():
        return False
    return historical_tier.applies(capture_start, None if trusted else historical_tier.UNTRUSTED, now)


def stamp(incoming: dict[str, Any], *, producer: str) -> None:
    """Mark a new row historical. Its structured must be the provenance-free minimum."""
    incoming['processing_tier'] = historical_tier.TIER
    incoming[TERMINAL_NO_DERIVED_EFFECTS_FIELD] = True
    incoming['summary_blocked_reason'] = BLOCKED_REASON
    ROWS.labels(producer=producer, outcome='stamped').inc()


def settled(conversation: Any) -> bool:
    """A historical row stored with its minimum: complete, nothing owed until the owner opens it."""
    if isinstance(conversation, Mapping):
        return historical_tier.is_historical(dict(conversation)) and not present(conversation.get('structured'))
    return historical_tier.is_historical(conversation) and not present(getattr(conversation, 'structured', None))


def settle(uid: str, conversation_id: str, *, producer: str) -> bool:
    """Finish the row's sync hold in place of an enrichment mark; False when it is not historical."""
    row = conversations_db.get_conversation(uid, conversation_id)
    if not row or not historical_tier.is_historical(row):
        ROWS.labels(producer=producer, outcome='not_historical').inc()
        return False
    completed = conversations_db.complete_sync_processing_hold(
        uid,
        conversation_id,
        row.get('sync_content_revision'),
        processing_hold.content_snapshot(row),
        automatic=False,
    )
    ROWS.labels(producer=producer, outcome='settled' if completed else 'fenced').inc()
    if not completed:
        logger.info('event=historical_tier_settle outcome=fenced producer=%s', producer)
    return True

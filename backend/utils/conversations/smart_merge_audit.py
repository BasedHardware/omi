"""Bounded false-merge signals around smart merge; never changes a merge or deletion outcome.

``record_survivor_deleted`` runs after a survivor's purge
(``merge_conversations.delete_conversation_with_sync_sources``) on the row that
function already read: no extra Firestore read. Age is measured from the
survivor's ``smart_merge.last_merged_at``; survivors merged before that stamp
existed fall back to the end of their newest ledger fragment, which is when
that donor finished (its absorb follows within the finalization job).

Deliberately left out: an unmerge counter (no unmerge tool ships here).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from utils.metrics import record_conversation_smart_merge_survivor_deleted

logger = logging.getLogger(__name__)

_AGE_BUCKETS = ((3600, 'lt_1h'), (86400, 'lt_24h'), (7 * 86400, 'lt_7d'))


def _merged_at(state: Mapping[str, Any]) -> Optional[datetime]:
    stamped = state.get('last_merged_at')
    if isinstance(stamped, datetime):
        return stamped
    fragments = state.get('fragments')
    if isinstance(fragments, list) and len(fragments) > 1 and isinstance(fragments[-1], Mapping):
        finished = fragments[-1].get('finished_at')
        if isinstance(finished, datetime):
            return finished
    return None


def survivor_age_bucket(row: Mapping[str, Any], *, now: Optional[datetime] = None) -> Optional[str]:
    """The bounded age bucket of a live survivor row, or ``None`` for any other row."""
    state = row.get('smart_merge')
    if not isinstance(state, Mapping) or state.get('role') != 'survivor' or row.get('deleted'):
        return None
    merged_at = _merged_at(state)
    if merged_at is None or merged_at.tzinfo is None:
        return 'unknown'
    age = ((now or datetime.now(timezone.utc)) - merged_at).total_seconds()
    return next((label for limit, label in _AGE_BUCKETS if age < limit), 'gte_7d')


def record_survivor_deleted(uid: str, conversation_id: str, row: Mapping[str, Any]) -> None:
    """Never raises."""
    try:
        bucket = survivor_age_bucket(row)
        if bucket is None:
            return
        record_conversation_smart_merge_survivor_deleted(bucket)
        logger.info(
            'event=smart_merge outcome=survivor_deleted age_bucket=%s uid=%s survivor=%s',
            bucket,
            uid,
            conversation_id,
        )
    except Exception:
        pass

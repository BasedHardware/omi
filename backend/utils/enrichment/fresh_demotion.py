"""Keep the reserved ``enrichment-fresh`` lane for fresh first summaries.

A row is bound to the fresh queue once, while its conversation is recent, and nothing used to
move it back. Under a backlog the 30-slot fresh queue then filled with hours-old work and new
recordings waited FIFO behind it while the 300-slot primary queue sat idle (prod 2026-11-16:
6,800 fresh tasks, oldest 2 h, primary 286 tasks / 19 in flight).

When the fresh queue delivers a first summary whose obligation is older than the demotion age,
the route re-binds it to the primary queue under a new token (the same fenced CAS shape the
sweep uses to promote, reversed) and answers 200 without spending a fresh slot on it.

Lifecycle: kill switch ``ENRICHMENT_FRESH_DEMOTE_AFTER_MIN=0`` (default: the promotion window,
``ENRICHMENT_FRESH_PROMOTE_MAX_AGE_MIN``, 30 min). Owner: enrichment lane.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from typing import Any

from prometheus_client import REGISTRY, Counter

from config import enrichment as enrichment_config
from config.summary_guarantee import first_week_open
from utils.enrichment import outbox
from utils.enrichment.age_gate import timestamp
from utils.enrichment.outbox import first_summary_pending, valid_dispatch_binding

logger = logging.getLogger(__name__)

ENV = enrichment_config.FRESH_DEMOTE_ENV
_IDENTITY_FIELDS = ('handler', 'audience', 'invoker_sa')


def _counter() -> Counter:
    name = 'omi_enrichment_fresh_demoted_total'
    try:
        return Counter(name, 'Aged first summaries moved from the fresh enrichment queue to the primary queue')
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[attr-defined]


DEMOTED = _counter()


def _now() -> float:
    return time.time()


def demote_after_seconds() -> float:
    """Obligation age after which a fresh-queue delivery is demoted; 0 disables demotion."""
    return enrichment_config.fresh_demote_after_seconds()


def stale_fresh(row: dict[str, Any] | None, *, now: float) -> bool:
    """True for a fresh-bound first-summary obligation older than the demotion age."""
    after = demote_after_seconds()
    fresh = enrichment_config.fresh_queue()
    if not row or after <= 0 or not fresh:
        return False
    # An open first-week obligation keeps its reserved lane for the whole stored
    # window, so the 30-minute demotion cannot strand it for the remaining days
    # even when no dedicated first-week queue is configured (SCA-4790).
    if first_week_open(row, now=now):
        return False
    dispatch = row.get('dispatch')
    if not valid_dispatch_binding(dispatch) or dispatch['queue'] != fresh:
        return False
    first = row.get('first_pending_at')
    if isinstance(first, bool) or not isinstance(first, (int, float)) or not math.isfinite(first):
        return False  # Unknown age cannot prove the work is old; leave it where it is.
    return first_summary_pending(row) and now - first > after


def _finished_long_ago(row: dict[str, Any], *, now: float, after: float) -> bool:
    """The conversation's own finish time (the clock promotion uses) is older than ``after``.

    A sync upload can open its obligation long before the recording ends, so ``first_pending_at``
    alone would demote a recording that just finished. Unknown or unreadable metadata keeps the
    row where it is.
    """
    try:
        finished = timestamp(outbox.conversation_finished_at(row['uid'], row['conversation_id']))
    except Exception:
        return False
    return finished is not None and now - finished > after


def demote_if_stale(row_id: str, token: str, *, now: float | None = None, client: Any = None) -> bool:
    """Re-bind this exact unleased fresh delivery to the primary queue. True means it was demoted.

    Only the delivery holding the current token can demote; an active lease, a dormant row or a
    changed binding leaves the row untouched. The new token makes this delivery stale, and the
    re-enqueued task keeps the row's own ``due_at`` (a held row stays held). The row is marked
    ``fresh_demoted`` so the sweep never promotes it back.
    """
    current = _now() if now is None else now
    after = demote_after_seconds()
    if after <= 0 or not enrichment_config.fresh_queue():
        return False
    # A no-op CAS is a plain read (no write when the row is unchanged).
    candidate = outbox.mutate_row(row_id, lambda old: (old, dict(old) if old else None), client=client)
    if not candidate or candidate.get('task_token') != token or not stale_fresh(candidate, now=current):
        return False
    if not _finished_long_ago(candidate, now=current, after=after):
        return False
    primary = enrichment_config.dispatch_binding(recent=False)
    if not valid_dispatch_binding(primary):
        return False  # Incomplete primary config: never write an unbound row.

    def update(old):
        if old is None or old.get('dormant') or old.get('task_token') != token:
            return old, None
        if old.get('lease_until', 0) > current or not stale_fresh(old, now=current):
            return old, None
        previous = old['dispatch']
        if primary['queue'] == previous['queue']:
            return old, None
        if any(primary[field] != previous[field] for field in _IDENTITY_FIELDS):
            return old, None  # Never move a row onto a different worker or identity.
        row = dict(old)
        row.update(
            dispatch=dict(primary),
            task_token=uuid.uuid4().hex,
            task_due_at=current,
            wake_check_after=0,
            fresh_demoted=True,
        )
        return row, row

    row = outbox.mutate_row(row_id, update, client=client)
    if row is None:
        return False
    DEMOTED.inc()
    logger.info('event=enrichment_fresh_demoted age_s=%.0f', current - float(row['first_pending_at']))
    # A lost enqueue after this CAS is repaired by the sweep, exactly as for promotion.
    outbox.wake_row(row)
    return True

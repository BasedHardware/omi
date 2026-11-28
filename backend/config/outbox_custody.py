"""Reason-bound custody deferral episodes shared by every enrichment outbox backend (PL-342).

Pure policy: ``utils.enrichment.outbox`` (Firestore), ``database.jobstore.outbox_pg`` (Postgres) and
``testing.outbox_sim`` all import it at module scope, so one rule and one set of constants govern them.
"""

from __future__ import annotations

from typing import Any, Mapping

LIVE_DEFER_SECONDS = 120
# Custody deferrals whose cause can outlive the obligation: a merge redirect that
# never resolves, a missing row, or a live target/bridge that never settles. On
# 2026-11-01 about 1.7k such rows, most of them days old, were re-polled every
# 30-120s: ~80% of backend-sync's /v2/sync-jobs/run deliveries. Once one reason
# has deferred a row past the grace (``deferred_since``), it polls hourly;
# custody, sweep repair and the eventual resume are unchanged.
STUCK_DEFER_REASONS = frozenset(
    {'redirect_unresolved', 'conversation_missing', 'open_live_target', 'pending_live_bridge'}
)
STUCK_DEFER_GRACE_SECONDS = 6 * 3600
STUCK_DEFER_POLL_SECONDS = 3600


def custody_deferred_since(row: Mapping[str, Any], reason: str, now: float) -> float:
    """Start of the row's current, uninterrupted deferral for ``reason``.

    A different reason, or a completed callback, starts a new episode. It can
    never predate the obligation's own acceptance, so a reopened dormant row
    does not inherit an old episode.
    """
    since = row.get('deferred_since') if row.get('deferred_reason') == reason else None
    if not isinstance(since, (int, float)):
        return now
    first = row.get('first_pending_at')
    return max(since, first) if isinstance(first, (int, float)) else since


def custody_defer_until(context: Mapping[str, Any], deferred_since: float, now: float) -> float:
    """Next wake for a callback custody deferral; long-stuck causes poll hourly."""
    due = context.get('defer_until', now + LIVE_DEFER_SECONDS)
    if context.get('defer_reason') in STUCK_DEFER_REASONS and now - deferred_since >= STUCK_DEFER_GRACE_SECONDS:
        return max(due, now + STUCK_DEFER_POLL_SECONDS)
    return due

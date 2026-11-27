"""The manual Finish timeline: where the time between Finish and the summary on Home goes.

Each stage observes the row its caller already holds, after that caller's own commit. It adds no Firestore
read or write. A sample has two possible anchors, and each goes to its own histogram:

* ``FINISH_STAGE{stage, path}`` measures from the Finish request. The anchor is the stamp a live-window Finish
  stores (``FINISH_STAMP_FIELD``) and the planner carries to the card. Only stamped Finishes are measured.
* ``MANUAL_END_STAGE{stage}`` measures from the manually ended row's ``finished_at``. That is the recording's end
  at admission and at the fast transcript, and the card's last speech from the builder on. Every manual-end card
  is measured, stamped or not. It is the anchor the Firestore cut-to-summary samples use.

Stages, in pipeline order (``metrics.FINISH_TIMELINE_STAGES``):

``admitted``
    Record admission took the manually finished recording's audio (backend-integration).
``transcript_fast``
    The fast first transcript was written (backend-integration). Batch-only Finishes skip this stage, so
    ``builder_started`` is their first stage after ``admitted``.
``builder_started``
    The builder pass that first committed the card as manually ended began (backend-sync).
``card_finished``
    That pass committed: Home now shows the ended card, writing its summary.
``notes_started``
    The card's first notes attempt began.
``summary_visible``
    The card's first manual-end settlement as a visible Home card, with its summary. This equals
    ``omi_conversations_v3_finish_to_visible_seconds`` for stamped Finishes.

Dependency-free beyond the meters, because batch admission imports it.
"""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Optional

from utils.conversations.v3 import metrics
from utils.conversations.v3.finish_stamp import FINISH_STAMP_FIELD, FINISH_STAMP_MAX_AGE, FINISH_STAMP_PATHS

STAGES = metrics.FINISH_TIMELINE_STAGES


def _seconds_since(at: Any, now: datetime) -> Optional[float]:
    """Seconds from ``at`` to ``now``, or None if ``at`` is not a time or is older than the stamp limit."""
    if not isinstance(at, datetime):
        return None
    at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    if now - at > FINISH_STAMP_MAX_AGE:
        return None
    return max(0.0, (now - at).total_seconds())


def samples(row: Mapping[str, Any], now: datetime) -> tuple[Optional[tuple[str, float]], Optional[float]]:
    """``((path, seconds) from the Finish stamp or None, seconds from finished_at or None)``."""
    stamp = row.get(FINISH_STAMP_FIELD)
    finish = None
    if isinstance(stamp, Mapping) and stamp.get('path') in FINISH_STAMP_PATHS:
        seconds = _seconds_since(stamp.get('at'), now)
        if seconds is not None:
            finish = (stamp['path'], seconds)
    return finish, _seconds_since(row.get('finished_at'), now)


def observe(stage: str, row: Mapping[str, Any], now: Optional[datetime] = None) -> None:
    """Record ``stage`` for ``row`` on both anchors that the row carries. Never raises."""

    def run():
        if stage not in STAGES or not isinstance(row, Mapping):
            return
        finish, ended = samples(row, now or datetime.now(timezone.utc))
        if finish is not None:
            metrics.FINISH_STAGE.labels(stage, finish[0]).observe(finish[1])
        if ended is not None:
            metrics.MANUAL_END_STAGE.labels(stage).observe(ended)

    metrics.safe_metric(run)


def first_manual_end_commit(row: Mapping[str, Any], prior: Optional[Mapping[str, Any]]) -> bool:
    """A builder commit that first shows ``row`` as a manually ended card (not backfill, not discarded)."""
    return bool(
        row.get('v3_derived')
        and row.get('manual_end')
        and not (prior or {}).get('manual_end')
        and not row.get('backfilled')
        and not row.get('discarded')
        and not row.get('home_hidden')
    )


def observe_card_finished(
    row: Mapping[str, Any],
    prior: Optional[Mapping[str, Any]],
    *,
    pass_started: datetime,
    visible: Callable[[Mapping[str, Any]], bool],
    now: Optional[datetime] = None,
) -> None:
    """After a builder commit: ``builder_started`` and ``card_finished`` for a newly ended, Home-visible card."""

    def run():
        if not first_manual_end_commit(row, prior) or not visible(row):
            return
        observe('builder_started', row, pass_started)
        observe('card_finished', row, now or datetime.now(timezone.utc))

    metrics.safe_metric(run)


def first_notes_attempt(row: Mapping[str, Any]) -> bool:
    """``row`` (as read before ``begin_processing``) is a shown manual-end card whose notes never started."""
    return bool(
        row.get('v3_derived')
        and row.get('manual_end')
        and not row.get('v3_notes_written')
        and not row.get('v3_process_attempts')
        and not row.get('backfilled')
        and not row.get('home_hidden')
    )

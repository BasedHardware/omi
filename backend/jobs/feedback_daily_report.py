"""Build the daily thumbs-down report.

Runs once a day over the previous UTC day: read every negative event from the
feedback ledger, resolve each one's conversation window to *pointers*, and
write one `feedback_reports/{YYYY-MM-DD}` document.

The job reads message metadata but never message text, so the report it writes
contains no plaintext conversation. Reviewers get the text from the admin
context endpoint, which decrypts one event at a time.
"""

import logging
from datetime import date as date_cls, datetime, time, timedelta, timezone
from typing import Optional

import database.feedback as feedback_db
from models.feedback import (
    FeedbackContextPointer,
    FeedbackEvent,
    FeedbackReport,
    FeedbackReportEntry,
)
from utils.feedback_context import resolve_context

logger = logging.getLogger(__name__)


def _day_bounds(day: date_cls) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def previous_utc_day(now: Optional[datetime] = None) -> date_cls:
    reference = now or datetime.now(timezone.utc)
    return (reference.astimezone(timezone.utc) - timedelta(days=1)).date()


def _collapse_per_target(events: list[FeedbackEvent]) -> list[FeedbackEvent]:
    """One entry per rated artifact, keeping the last event for it that day.

    The ledger is append-only, so a single thumbs-down can produce more than
    one row: the macOS client sends the rating the instant the user taps, then
    sends it again carrying the reason once they pick one. Toggling a rating
    off and on again does the same. A report that showed each row would
    double-count exactly the feedback that has the most information attached.

    Last-wins is what makes this correct rather than merely tidy: events arrive
    oldest-first, and the later row is the one carrying the reason.
    """
    latest: dict[tuple[str, str, str], FeedbackEvent] = {}
    for event in events:
        latest[(event.uid, event.target_kind.value, event.target_id)] = event
    return sorted(latest.values(), key=lambda e: e.created_at)


def generate_report(day: date_cls) -> FeedbackReport:
    """Build (and return) the report for one UTC day. Does not persist."""
    start_at, end_at = _day_bounds(day)
    cap = feedback_db.MAX_REPORT_ENTRIES
    events = feedback_db.list_negative_events(start_at, end_at, limit=cap + 1)

    events = _collapse_per_target(events)

    truncated = len(events) > cap
    if truncated:
        logger.warning(f'Feedback report {day.isoformat()}: more than {cap} thumbs-down; report is capped.')
        events = events[:cap]

    entries: list[FeedbackReportEntry] = []
    counts_by_surface: dict[str, int] = {}
    counts_by_reason: dict[str, int] = {}
    counts_by_platform: dict[str, int] = {}

    for event in events:
        surface = event.surface.value
        counts_by_surface[surface] = counts_by_surface.get(surface, 0) + 1

        # "not_captured" is a real, load-bearing bucket: the desktop client
        # shipped thumbs-down long before it shipped a reason picker, so a
        # blank here means "we never asked", not "the user declined to say".
        reason = event.reason.value if event.reason else 'not_captured'
        counts_by_reason[reason] = counts_by_reason.get(reason, 0) + 1

        platform = event.platform or 'unknown'
        counts_by_platform[platform] = counts_by_platform.get(platform, 0) + 1

        try:
            context = resolve_context(
                event.uid,
                event.target_kind,
                event.target_id,
                chat_session_id=event.chat_session_id,
            )
        except Exception as e:
            # One unresolvable window must not cost the rest of the report.
            logger.error(f'Context resolution failed for event {event.id}: {e}')
            context = FeedbackContextPointer(
                event_id=event.id,
                uid=event.uid,
                target_kind=event.target_kind,
                target_id=event.target_id,
                resolution_error='resolution_failed',
            )
        context.event_id = event.id
        entries.append(FeedbackReportEntry(event=event, context=context))

    return FeedbackReport(
        date=day.isoformat(),
        generated_at=datetime.now(timezone.utc),
        total_negative=len(entries),
        counts_by_surface=counts_by_surface,
        counts_by_reason=counts_by_reason,
        counts_by_platform=counts_by_platform,
        entries=entries,
        truncated=truncated,
    )


def run(day: Optional[date_cls] = None) -> FeedbackReport:
    """Generate and persist the report for `day` (default: previous UTC day)."""
    target = day or previous_utc_day()
    report = generate_report(target)
    feedback_db.save_report(report)
    logger.info(
        f'Feedback report {report.date}: {report.total_negative} thumbs-down '
        f'across {len(report.counts_by_surface)} surface(s).'
    )
    return report

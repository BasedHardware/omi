"""Build the daily thumbs-down report.

Runs once a day over the previous UTC day: read every negative event from the
feedback ledger, resolve each one's conversation window to *pointers*, and
write one `feedback_reports/{YYYY-MM-DD}` document.

The job reads message metadata but never message text, so the report it writes
contains no plaintext conversation. Reviewers get the text from the admin
context endpoint, which decrypts one event at a time.
"""

import json
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


def _is_more_informative(candidate: FeedbackEvent, incumbent: FeedbackEvent) -> bool:
    """Should `candidate` replace `incumbent` as the entry for one artifact?

    Every event here is a thumbs-down on the same target, so the question is
    only which row carries the most information. A row with a reason always
    wins over one without.

    Plain last-wins is not safe: the client sends the bare rating on tap and the
    reasoned rating when the user picks a chip, as two independent requests that
    can be written out of order. Ordering by arrival would then let the bare row
    land last and silently discard the reason the user actually gave — the whole
    point of asking. Ranking by information content is order-independent, so the
    reason survives however the two requests race.
    """
    candidate_rank = (candidate.reason is not None, bool(candidate.comment))
    incumbent_rank = (incumbent.reason is not None, bool(incumbent.comment))
    if candidate_rank != incumbent_rank:
        return candidate_rank > incumbent_rank
    return candidate.created_at >= incumbent.created_at


def _collapse_per_target(events: list[FeedbackEvent]) -> list[FeedbackEvent]:
    """One entry per rated artifact, keeping its most informative event.

    The ledger is append-only, so a single thumbs-down can produce more than
    one row: the macOS client sends the rating the instant the user taps, then
    sends it again carrying the reason once they pick one. Toggling a rating
    off and on again does the same. A report that showed each row would
    double-count exactly the feedback that has the most information attached.
    """
    best: dict[tuple[str, str, str], FeedbackEvent] = {}
    for event in events:
        key = (event.uid, event.target_kind.value, event.target_id)
        incumbent = best.get(key)
        if incumbent is None or _is_more_informative(event, incumbent):
            best[key] = event
    return sorted(best.values(), key=lambda e: e.created_at)


def _entry_bytes(entry: FeedbackReportEntry) -> int:
    """Serialized size of one entry, as the stored JSON measures it."""
    return len(json.dumps(entry.model_dump(mode='json'), default=str).encode('utf-8'))


def generate_report(day: date_cls) -> FeedbackReport:
    """Build (and return) the report for one UTC day. Does not persist."""
    start_at, end_at = _day_bounds(day)
    cap = feedback_db.MAX_REPORT_ENTRIES

    # Fetch with headroom, and judge truncation on the *raw* rows rather than
    # the collapsed ones. A reasoned thumbs-down writes two ledger rows (the
    # tap, then the reason), so a fetch capped at `cap + 1` could collapse to
    # half that many entries and still look complete — a silently partial
    # report, which is the one thing `truncated` exists to rule out.
    raw_limit = feedback_db.RAW_FETCH_LIMIT
    raw_events = feedback_db.list_negative_events(start_at, end_at, limit=raw_limit + 1)
    hit_raw_limit = len(raw_events) > raw_limit

    events = _collapse_per_target(raw_events[:raw_limit])

    truncated = hit_raw_limit or len(events) > cap
    if truncated:
        logger.warning(
            f'Feedback report {day.isoformat()}: capped — '
            f'{len(raw_events)} raw row(s) fetched (limit {raw_limit}), '
            f'{len(events)} entries after collapse (cap {cap}).'
        )

    entries: list[FeedbackReportEntry] = []
    counts_by_surface: dict[str, int] = {}
    counts_by_reason: dict[str, int] = {}
    counts_by_platform: dict[str, int] = {}

    # Counts cover every collapsed event the day produced; `entries` carry only
    # as many context windows as fit the document. Splitting them this way means
    # a heavy day still reports its true reason and surface distribution — the
    # part you act on — and loses only the per-event transcripts beyond the cap.
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

    budget = feedback_db.MAX_REPORT_DOCUMENT_BYTES
    used = 0

    for event in events[:cap]:
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
        entry = FeedbackReportEntry(event=event, context=context)

        # Firestore rejects the whole document over 1 MiB, so measure as we go
        # rather than discovering it at `save_report` and losing the entire day.
        used += _entry_bytes(entry)
        # `entries` guards the first one: a single window wider than the whole
        # budget would otherwise write an empty report, which tells a reviewer
        # nothing and looks identical to a quiet day.
        if used > budget and entries:
            truncated = True
            logger.warning(
                f'Feedback report {day.isoformat()}: stopped at {len(entries)} of '
                f'{len(events)} entries — document budget {budget} bytes reached.'
            )
            break
        entries.append(entry)

    if len(events) > cap:
        truncated = True

    return FeedbackReport(
        date=day.isoformat(),
        generated_at=datetime.now(timezone.utc),
        total_negative=len(events),
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
        f'across {len(report.counts_by_surface)} surface(s); '
        f'{len(report.entries)} with context'
        f'{" (truncated)" if report.truncated else ""}.'
    )
    return report

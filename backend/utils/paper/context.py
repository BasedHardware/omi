"""Everything the reader actually did on a given day, gathered from live sources.

This is the layer the whole edition rests on. It reads what Omi already
captured — conversations, screen activity, the stored daily summary, open
action items — and returns it as one structure. Nothing here calls a model and
nothing here invents: a source that fails is recorded as failed and returns
empty, because a section that silently disappears is indistinguishable from a
quiet day.
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import database.action_items as action_items_db
import database.conversations as conversations_db
import database.daily_summaries as daily_summaries_db
import database.screen_activity as screen_activity_db
from models.paper import FocusBlock, SourceHealth, TimelineEntry
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

# Screen samples this far apart belong to different sittings. The capture
# interval is a client setting we do not control, so focus time is measured
# from real gaps between samples rather than assumed to be a fixed cadence.
MAX_SAMPLE_GAP_MINUTES = 5

# A stretch shorter than this is noise — an app that flashed past, not focus.
MIN_BLOCK_MINUTES = 5

# Below this the capture covered so little of the day that printing it as
# "where the time went" misleads. A six-minute browser block beside a day
# holding hours of recorded conversation reads as the day's focus, and is not.
MIN_TRACKED_MINUTES = 30

# How many apps reach the page. Beyond this it stops being a summary.
MAX_FOCUS_BLOCKS = 6

# A recorded conversation longer than this is a session that was left open,
# not a conversation. One real day had a single 12h56m 'conversation' running
# 05:38 to 18:35 — 67% of the day's total — which made the headline figure
# wrong and buried every genuine session under it on the timeline.
MAX_PLAUSIBLE_SESSION_MINUTES = 240

CONVERSATION_LIMIT = 60
ACTION_ITEM_LIMIT = 50


class DayContext:
    """One day of the reader's own record, plus the health of each read.

    Attributes are plain containers so callers can be written against real
    shapes. ``health`` accumulates one entry per source touched.
    """

    def __init__(self, day: date) -> None:
        self.day = day
        self.summary: dict[str, Any] | None = None
        self.conversations: list[dict[str, Any]] = []
        self.timeline: list[TimelineEntry] = []
        self.focus: list[FocusBlock] = []
        self.screen_titles: list[str] = []
        self.commitments: list[dict[str, Any]] = []
        self.health: list[SourceHealth] = []

    @property
    def is_empty(self) -> bool:
        return not any([self.summary, self.conversations, self.focus, self.commitments])


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """UTC start and end of ``day``.

    Stored timestamps are UTC, so the window is built in UTC. Per-user timezone
    shifting belongs at the display layer, not here.
    """
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1) - timedelta(microseconds=1)


def _parse_screen_ts(raw: object) -> datetime | None:
    """Screen timestamps are stored as 'YYYY-MM-DD HH:MM:SS.mmm' strings."""
    text = str(raw or '').strip()
    if not text:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return None


def focus_blocks(rows: list[dict[str, Any]]) -> list[FocusBlock]:
    """Collapse screen samples into per-app focus time.

    Time is accumulated from the real gap between consecutive samples, capped at
    ``MAX_SAMPLE_GAP_MINUTES`` so an overnight gap does not read as ten hours in
    one app. This is why the number can be trusted: it is measured, not a
    sample count multiplied by an assumed interval.
    """
    stamped: list[tuple[datetime, str, str]] = []
    for row in rows:
        when = _parse_screen_ts(row.get('timestamp'))
        if when is None:
            continue
        stamped.append((when, str(row.get('appName') or 'Unknown'), str(row.get('windowTitle') or '')))
    if not stamped:
        return []

    stamped.sort(key=lambda entry: entry[0])

    minutes: dict[str, float] = {}
    titles: dict[str, list[str]] = {}
    for index, (when, app, title) in enumerate(stamped):
        if title:
            seen = titles.setdefault(app, [])
            if title not in seen and len(seen) < 4:
                seen.append(title)
        if index + 1 >= len(stamped):
            continue
        gap = (stamped[index + 1][0] - when).total_seconds() / 60.0
        minutes[app] = minutes.get(app, 0.0) + min(max(gap, 0.0), MAX_SAMPLE_GAP_MINUTES)

    blocks = [
        FocusBlock(label=app, minutes=int(round(total)), detail=', '.join(titles.get(app, [])[:3]))
        for app, total in minutes.items()
        if round(total) >= MIN_BLOCK_MINUTES
    ]
    blocks.sort(key=lambda block: -block.minutes)
    return blocks[:MAX_FOCUS_BLOCKS]


def _stamp_minutes(start: str, end: str) -> int:
    """Recorded length of a stretch, from its own stamps."""
    try:
        opened = datetime.fromisoformat(str(start).replace('Z', '+00:00'))
        closed = datetime.fromisoformat(str(end).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return 0
    return max(0, int((closed - opened).total_seconds() // 60))


def build_timeline(conversations: list[dict[str, Any]]) -> list[TimelineEntry]:
    """The day in order, from recorded conversation stamps.

    Nothing here is inferred. A conversation with no usable start stamp is left
    off rather than placed somewhere plausible, because the whole point of a
    timeline is that the position on it is a claim about when.
    """
    entries: list[TimelineEntry] = []
    for conversation in conversations:
        start = str(conversation.get('started_at') or conversation.get('created_at') or '')
        if len(start) < 16:
            continue
        end = str(conversation.get('finished_at') or '')
        structured = conversation.get('structured') or {}
        label = str(structured.get('title') or '').strip()
        if not label:
            continue
        minutes = _stamp_minutes(start, end) if end else 0
        unbounded = minutes > MAX_PLAUSIBLE_SESSION_MINUTES
        entries.append(
            TimelineEntry(
                label=label,
                start=start,
                end=end,
                kind='conversation',
                # Kept on the day at its real start, but not counted as a length.
                minutes=0 if unbounded else minutes,
                unbounded=unbounded,
            )
        )
    entries.sort(key=lambda entry: entry.start)
    return entries


def _read_summary(uid: str, day: date, context: DayContext) -> None:
    try:
        context.summary = daily_summaries_db.get_daily_summary_by_date(uid, day.isoformat())
        context.health.append(
            SourceHealth(
                source='daily summary',
                ok=True,
                fetched=1 if context.summary else 0,
                kept=1 if context.summary else 0,
                note='' if context.summary else 'no summary stored for this day',
            )
        )
    except Exception as e:  # noqa: BLE001 — one failed source must not lose the edition.
        logger.warning('paper: daily summary read failed: %s', sanitize(str(e)))
        context.health.append(SourceHealth(source='daily summary', ok=False, note=sanitize(str(e))[:200]))


def _read_conversations(uid: str, day: date, context: DayContext) -> None:
    start, end = day_bounds(day)
    try:
        rows = conversations_db.get_conversations(
            uid,
            limit=CONVERSATION_LIMIT,
            start_date=start,
            end_date=end,
        )
        context.conversations = rows or []
        context.timeline = build_timeline(context.conversations)
        context.health.append(
            SourceHealth(
                source='conversations',
                ok=True,
                fetched=len(context.conversations),
                kept=len(context.conversations),
            )
        )
    except Exception as e:  # noqa: BLE001
        logger.warning('paper: conversation read failed: %s', sanitize(str(e)))
        context.health.append(SourceHealth(source='conversations', ok=False, note=sanitize(str(e))[:200]))


def screen_day_window(day: date) -> tuple[str, str]:
    """Date-prefix bounds for one day of screen activity.

    Screen rows are queried by **string** comparison on a stored timestamp, and
    the stored format is ISO-8601 (``2026-08-02T02:32:46Z``). Passing datetimes
    makes the caller format bounds as ``2026-08-02 23:59:59.999``; because
    ``'T' > ' '``, every row on the requested day sorts above that end bound and
    a single-day query returns nothing at all.

    Date prefixes avoid the separator entirely: every same-day timestamp starts
    with the day, and the exclusive next-day bound is above all of them in
    either format. This is why the focus section has data instead of silently
    reporting a day with no capture.
    """
    return day.isoformat(), (day + timedelta(days=1)).isoformat()


def _read_screen(uid: str, day: date, context: DayContext) -> None:
    start, end = screen_day_window(day)
    try:
        rows = screen_activity_db.get_screen_activity(uid, start_date=start, end_date=end, limit=5000)
        measured = focus_blocks(rows or [])
        # Thin capture is reported as thin rather than printed as the day's
        # focus. Six minutes of browser next to hours of recorded conversation
        # is not where the time went, and saying so would mislead.
        tracked = sum(block.minutes for block in measured)
        context.focus = measured if tracked >= MIN_TRACKED_MINUTES else []
        context.screen_titles = [
            str(row.get('windowTitle') or '') for row in (rows or []) if str(row.get('windowTitle') or '').strip()
        ][:200]
        context.health.append(
            SourceHealth(
                source='screen',
                ok=True,
                fetched=len(rows or []),
                kept=len(context.focus),
                note=(
                    'no screen activity captured for this day'
                    if not rows
                    else ('' if context.focus else f'only {tracked} min captured, too thin to report focus')
                ),
            )
        )
    except Exception as e:  # noqa: BLE001
        logger.warning('paper: screen activity read failed: %s', sanitize(str(e)))
        context.health.append(SourceHealth(source='screen', ok=False, note=sanitize(str(e))[:200]))


def _read_commitments(uid: str, context: DayContext) -> None:
    """Open action items — what the reader said they would do and has not closed."""
    try:
        rows = action_items_db.get_action_items(uid, limit=ACTION_ITEM_LIMIT, completed=False)
        context.commitments = list(rows or [])
        context.health.append(
            SourceHealth(
                source='action items',
                ok=True,
                fetched=len(context.commitments),
                kept=len(context.commitments),
            )
        )
    except Exception as e:  # noqa: BLE001
        logger.warning('paper: action item read failed: %s', sanitize(str(e)))
        context.health.append(SourceHealth(source='action items', ok=False, note=sanitize(str(e))[:200]))


def gather(uid: str, day: date) -> DayContext:
    """Read one day of the reader's own record.

    Every source is attempted independently. A failure is recorded in
    ``health`` and leaves its field empty rather than raising, so one dead
    integration costs one section instead of the paper.
    """
    context = DayContext(day)
    _read_summary(uid, day, context)
    _read_conversations(uid, day, context)
    _read_screen(uid, day, context)
    _read_commitments(uid, context)
    return context


def record_lines(context: DayContext, limit: int = 40) -> list[str]:
    """Flatten the day into grounding lines a prompt may draw on.

    This is the only text the editorial prompts are allowed to use. Keeping the
    flattening here means there is one definition of what the model can see.

    Each source gets a reserved slice rather than the list being truncated at
    the tail. Appending summary, then conversations, then focus and cutting at
    ``limit`` meant that on the busiest days — the ones with the most signal —
    the focus lines were always the ones dropped, so the prompt was told nothing
    about where the time actually went.
    """
    summary_lines: list[str] = []
    conversation_lines: list[str] = []
    focus_lines: list[str] = []
    lines = summary_lines
    summary = context.summary or {}

    if summary.get('headline'):
        lines.append(f"Day headline: {summary['headline']}")
    if summary.get('overview'):
        lines.append(f"Overview: {summary['overview']}")

    for highlight in (summary.get('highlights') or [])[:8]:
        topic = (highlight or {}).get('topic') or ''
        detail = (highlight or {}).get('summary') or ''
        if topic or detail:
            lines.append(f"- {topic}: {detail}".strip(' -:'))

    for decision in (summary.get('decisions_made') or [])[:6]:
        text = (decision or {}).get('decision')
        if text:
            lines.append(f"- Decided: {text}")

    for question in (summary.get('unresolved_questions') or [])[:6]:
        text = (question or {}).get('question')
        if text:
            lines.append(f"- Open question: {text}")

    for nugget in (summary.get('knowledge_nuggets') or [])[:6]:
        text = (nugget or {}).get('insight')
        if text:
            lines.append(f"- Learned: {text}")

    for conversation in context.conversations[:12]:
        structured = conversation.get('structured') or {}
        title = structured.get('title') or ''
        overview = structured.get('overview') or ''
        if title or overview:
            conversation_lines.append(f"- Talked about {title}: {overview}".strip())

    for block in context.focus:
        detail = f" ({block.detail})" if block.detail else ''
        focus_lines.append(f"- Screen: {block.label} for {block.minutes} min{detail}")

    focus_budget = min(len(focus_lines), MAX_FOCUS_BLOCKS)
    conversation_budget = min(len(conversation_lines), 12)
    summary_budget = max(limit - focus_budget - conversation_budget, 0)
    return summary_lines[:summary_budget] + conversation_lines[:conversation_budget] + focus_lines[:focus_budget]

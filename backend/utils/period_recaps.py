"""Weekly and monthly recaps rolled up from the stored daily recaps (#4468).

A period recap is deterministic: it totals each day's stats, keeps the days'
highlights, decisions and open questions (spread across the period, busiest days
first), lists the live open tasks created in it, compares with the same stretch
of the previous period, and ranks the people the user talked to most (#3808).
No LLM call is made, so opening a recap costs a few reads and never spends chat
quota.
"""

from __future__ import annotations

import calendar
import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

RecapPeriod = Literal['week', 'month']
RECAP_PERIODS: Tuple[str, ...] = ('week', 'month')
MAX_RECAP_ITEMS = 10
MAX_HIGHLIGHTS_PER_DAY = 2
MAX_TOP_PEOPLE = 5
# The earliest anchor a recap accepts; older dates are never real data and the
# period arithmetic underflows near date.min.
MIN_RECAP_DATE = date(2000, 1, 1)
STAT_FIELDS = ('total_conversations', 'total_duration_minutes', 'action_items_created', 'memories_created')


def period_bounds(period: str, anchor: date) -> Tuple[date, date]:
    """The local calendar dates a period covers: Monday-Sunday, or the whole month."""
    if period == 'week':
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == 'month':
        last_day = calendar.monthrange(anchor.year, anchor.month)[1]
        return anchor.replace(day=1), anchor.replace(day=last_day)
    raise ValueError(f'unknown recap period: {period!r}')


def previous_period_bounds(period: str, start: date) -> Tuple[date, date]:
    """The period immediately before the one starting at ``start``."""
    return period_bounds(period, start - timedelta(days=1))


def comparable_previous_bounds(period: str, start: date, end: date, through: date) -> Tuple[date, date]:
    """The stretch of the previous period to compare with: like for like.

    ``through`` is the last day of the current period being compared. On or past
    the period's last day that is the whole previous period (so February 28
    compares with all of January, as it will tomorrow); otherwise the same
    number of days from the previous period's start, so four days into a month
    are not measured against a full month.
    """
    previous_start, previous_end = previous_period_bounds(period, start)
    if through >= end:
        return previous_start, previous_end
    elapsed = max((through - start).days, 0)
    return previous_start, min(previous_start + timedelta(days=elapsed), previous_end)


def _comparison_bounds(
    period: str, start: date, end: date, days: Sequence[Mapping[str, Any]], today: Optional[date]
) -> Optional[Tuple[date, date]]:
    """The previous-period dates to compare with, or None when nothing is comparable yet.

    A period that has ended compares with the whole previous one. While it is in
    progress, today counts only once its daily recap exists (it is written at the
    user's delivery hour, 22:00 by default); before that the comparison runs
    through yesterday, so the previous period never gets a day the current one is
    still missing. A user whose delivery hour is in the morning gets yesterday's
    recap only then (before noon the cron summarizes the day before), so early in
    the day "through yesterday" can still favour the previous period. That is
    unavoidable: a day with nothing recorded has no recap either, so a missing
    recap cannot tell "not written yet" from "empty day".
    """
    if today is None or today > end:
        return previous_period_bounds(period, start)
    has_today = any(_parse_day(day.get('date')) == today for day in days)
    through = today if has_today else today - timedelta(days=1)
    if through < start:
        return None
    return comparable_previous_bounds(period, start, end, through)


def _zone(time_zone: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(time_zone) if time_zone else ZoneInfo('UTC')
    except Exception:
        return ZoneInfo('UTC')


def local_today(time_zone: Optional[str]) -> date:
    """Today's date where the user is."""
    return datetime.now(_zone(time_zone)).date()


def period_utc_bounds(start: date, end: date, time_zone: Optional[str]) -> Tuple[datetime, datetime]:
    """UTC instants for the first and last moment of a local date range."""
    zone = _zone(time_zone)
    first = datetime.combine(start, time.min, tzinfo=zone).astimezone(timezone.utc)
    last = datetime.combine(end, time.max, tzinfo=zone).astimezone(timezone.utc)
    return first, last


def _parse_day(value: Any) -> Optional[date]:
    """A stored ``YYYY-MM-DD`` date, or None when it is not exactly one."""
    if not isinstance(value, str):
        return None
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return None
    return day if day.isoformat() == value else None


def _created_key(summary: Mapping[str, Any]) -> float:
    """When a daily recap was generated; a missing or unreadable stamp sorts oldest."""
    value = summary.get('created_at')
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return -math.inf
    if not isinstance(value, datetime):
        return -math.inf
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()


def _in_period(summaries: Iterable[Any], start: date, end: date) -> List[Dict[str, Any]]:
    """The period's daily recaps in date order, one per date (the newest regeneration)."""
    by_date: Dict[date, Dict[str, Any]] = {}
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        day = _parse_day(summary.get('date'))
        if day is None or not start <= day <= end:
            continue
        kept = by_date.get(day)
        if kept is None or _created_key(summary) > _created_key(kept):
            by_date[day] = summary
    return [by_date[day] for day in sorted(by_date)]


def _stat(summary: Mapping[str, Any], field: str) -> int:
    stats = summary.get('stats')
    value = stats.get(field) if isinstance(stats, dict) else None
    return value if isinstance(value, int) and value > 0 else 0


def _totals(summaries: Sequence[Mapping[str, Any]], fields: Sequence[str] = STAT_FIELDS) -> Dict[str, int]:
    return {field: sum(_stat(summary, field) for summary in summaries) for field in fields}


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _entries(summary: Mapping[str, Any], key: str) -> List[Dict[str, Any]]:
    value = summary.get(key)
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def _busiest_day(summaries: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    candidates = [s for s in summaries if _stat(s, 'total_conversations') or _stat(s, 'total_duration_minutes')]
    if not candidates:
        return None
    busiest = max(
        candidates,
        key=lambda s: (
            _stat(s, 'total_duration_minutes'),
            _stat(s, 'total_conversations'),
            -date.fromisoformat(s['date']).toordinal(),
        ),
    )
    return {
        'date': busiest['date'],
        'summary_id': _id(busiest.get('id')),
        'total_conversations': _stat(busiest, 'total_conversations'),
        'total_duration_minutes': _stat(busiest, 'total_duration_minutes'),
    }


def _spread(
    summaries: Sequence[Mapping[str, Any]],
    entries: Callable[[Mapping[str, Any]], List[Dict[str, Any]]],
    per_day: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Up to MAX_RECAP_ITEMS entries spread across the period, in date order.

    Days take turns, busiest first: every day gives its first entry before any
    day gives a second, so a month is not just its first few days. ``per_day``
    caps how many one day may give. Each day keeps its own entry order.
    """
    per_summary = [entries(summary)[:per_day] for summary in summaries]
    turns = sorted(
        range(len(summaries)),
        key=lambda i: (
            -_stat(summaries[i], 'total_duration_minutes'),
            -_stat(summaries[i], 'total_conversations'),
            summaries[i]['date'],
        ),
    )
    picked: List[Tuple[int, int]] = []
    depth = 0
    deepest = max((len(items) for items in per_summary), default=0)
    while depth < deepest and len(picked) < MAX_RECAP_ITEMS:
        for i in turns:
            if depth < len(per_summary[i]):
                picked.append((i, depth))
                if len(picked) == MAX_RECAP_ITEMS:
                    break
        depth += 1
    return [per_summary[i][level] for i, level in sorted(picked)]


def _day_highlights(summary: Mapping[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for entry in _entries(summary, 'highlights'):
        topic, text = _text(entry.get('topic')), _text(entry.get('summary'))
        if not (topic or text):
            continue
        ids = entry.get('conversation_ids')
        items.append(
            {
                'date': summary['date'],
                'topic': topic,
                'emoji': _text(entry.get('emoji')),
                'summary': text,
                'conversation_ids': [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else [],
            }
        )
    return items


def _highlights(summaries: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return _spread(summaries, _day_highlights, per_day=MAX_HIGHLIGHTS_PER_DAY)


def _collect(
    summaries: Sequence[Mapping[str, Any]], key: str, text_field: str, extra: Sequence[str]
) -> List[Dict[str, Any]]:
    def day_entries(summary: Mapping[str, Any]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for entry in _entries(summary, key):
            text = _text(entry.get(text_field))
            if text:
                items.append(
                    {'date': summary['date'], text_field: text, **{field: _id(entry.get(field)) for field in extra}}
                )
        return items

    return _spread(summaries, day_entries)


def _id(value: Any) -> Optional[str]:
    """A stored reference id, or None when it is not a non-empty string."""
    return value if isinstance(value, str) and value else None


def _iso_instant(value: Any) -> Optional[str]:
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def _open_action_items(action_items: Iterable[Any], zone: ZoneInfo) -> List[Dict[str, Any]]:
    """The live open tasks, in the order the task list gives them, dated where the user is.

    Locked (paywalled) tasks are left out, as the chat tools do: the recap has no
    locked state to show, so it must not carry their descriptions.
    """
    items: List[Dict[str, Any]] = []
    for item in action_items:
        if not isinstance(item, dict) or item.get('is_locked'):
            continue
        task_id, description, created_at = item.get('id'), _text(item.get('description')), item.get('created_at')
        if not isinstance(task_id, str) or not description or not isinstance(created_at, datetime):
            continue
        created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        items.append(
            {
                'id': task_id,
                'description': description,
                'date': created.astimezone(zone).date().isoformat(),
                'source_conversation_id': _id(item.get('conversation_id')),
                'due_at': _iso_instant(item.get('due_at')),
            }
        )
    return items[:MAX_RECAP_ITEMS]


def rank_people(people_stats: Mapping[str, Mapping[str, Any]]) -> List[str]:
    """Person ids, most talked to first: talk time, then conversations, then id."""
    return [
        person_id
        for person_id, _ in sorted(
            people_stats.items(),
            key=lambda item: (
                -(item[1].get('talk_seconds') or 0.0),
                -(item[1].get('conversation_count') or 0),
                item[0],
            ),
        )
    ]


def _top_people(
    people_stats: Optional[Mapping[str, Mapping[str, Any]]], people_names: Optional[Mapping[str, str]]
) -> List[Dict[str, Any]]:
    if not people_stats:
        return []
    names = people_names or {}
    ranked = [person_id for person_id in rank_people(people_stats) if _text(names.get(person_id))]
    return [
        {
            'person_id': person_id,
            'name': _text(names.get(person_id)),
            'conversations': int(people_stats[person_id].get('conversation_count') or 0),
            'talk_minutes': math.ceil((people_stats[person_id].get('talk_seconds') or 0.0) / 60),
        }
        for person_id in ranked[:MAX_TOP_PEOPLE]
    ]


def build_period_recap(
    period: str,
    start: date,
    end: date,
    summaries: Iterable[Any],
    *,
    previous_summaries: Optional[Iterable[Any]] = None,
    today: Optional[date] = None,
    action_items: Optional[Iterable[Any]] = None,
    time_zone: Optional[str] = None,
    people_stats: Optional[Mapping[str, Mapping[str, Any]]] = None,
    people_names: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Roll the daily recaps between ``start`` and ``end`` (local dates) into one recap.

    ``previous_summaries`` gives the trend, compared like for like as of
    ``today`` (the whole previous period when ``today`` is not given); it is
    None until the current period has a comparable day. ``action_items`` are
    the live open tasks created in the period; the task snapshots stored on the
    daily recaps are never used, as they go stale.
    """
    if period not in RECAP_PERIODS:
        raise ValueError(f'unknown recap period: {period!r}')
    days = _in_period(summaries, start, end)
    previous = None
    bounds = _comparison_bounds(period, start, end, days, today) if previous_summaries is not None else None
    if previous_summaries is not None and bounds is not None:
        previous_start, previous_end = bounds
        previous = {
            'start_date': previous_start.isoformat(),
            'end_date': previous_end.isoformat(),
            **_totals(
                _in_period(previous_summaries, previous_start, previous_end),
                ('total_conversations', 'total_duration_minutes'),
            ),
        }
    return {
        'period': period,
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'days_recorded': len(days),
        'stats': _totals(days),
        'busiest_day': _busiest_day(days),
        'highlights': _highlights(days),
        'decisions': _collect(days, 'decisions_made', 'decision', ('conversation_id',)),
        'open_questions': _collect(days, 'unresolved_questions', 'question', ('conversation_id',)),
        'open_action_items': _open_action_items(action_items or (), _zone(time_zone)),
        'top_people': _top_people(people_stats, people_names),
        'previous': previous,
    }

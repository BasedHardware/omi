"""Weekly and monthly recaps rolled up from the stored daily recaps (#4468).

A period recap is deterministic: it totals each day's stats, keeps the days'
highlights, decisions, open questions and open action items, compares with the
previous period, and ranks the people the user talked to most (#3808). No LLM
call is made, so opening a recap costs a few reads and never spends chat quota.
"""

from __future__ import annotations

import calendar
import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

RecapPeriod = Literal['week', 'month']
RECAP_PERIODS: Tuple[str, ...] = ('week', 'month')
MAX_RECAP_ITEMS = 10
MAX_HIGHLIGHTS_PER_DAY = 2
MAX_TOP_PEOPLE = 5
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


def _in_period(summaries: Iterable[Any], start: date, end: date) -> List[Dict[str, Any]]:
    first, last = start.isoformat(), end.isoformat()
    by_date: Dict[str, Dict[str, Any]] = {}
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        day = summary.get('date')
        if isinstance(day, str) and first <= day <= last:
            by_date.setdefault(day, summary)
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
        'summary_id': busiest.get('id'),
        'total_conversations': _stat(busiest, 'total_conversations'),
        'total_duration_minutes': _stat(busiest, 'total_duration_minutes'),
    }


def _highlights(summaries: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for summary in summaries:
        kept = 0
        for entry in _entries(summary, 'highlights'):
            topic, text = _text(entry.get('topic')), _text(entry.get('summary'))
            if not (topic or text) or kept == MAX_HIGHLIGHTS_PER_DAY:
                continue
            kept += 1
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
    return items[:MAX_RECAP_ITEMS]


def _collect(
    summaries: Sequence[Mapping[str, Any]], key: str, text_field: str, extra: Sequence[str]
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for summary in summaries:
        for entry in _entries(summary, key):
            text = _text(entry.get(text_field))
            if not text:
                continue
            items.append({'date': summary['date'], text_field: text, **{field: entry.get(field) for field in extra}})
            if len(items) == MAX_RECAP_ITEMS:
                return items
    return items


def _open_action_items(summaries: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    open_items = [
        {**summary, 'action_items': [e for e in _entries(summary, 'action_items') if e.get('completed') is not True]}
        for summary in summaries
    ]
    return _collect(open_items, 'action_items', 'description', ('priority', 'source_conversation_id'))


def _top_people(
    people_stats: Optional[Mapping[str, Mapping[str, Any]]], people_names: Optional[Mapping[str, str]]
) -> List[Dict[str, Any]]:
    if not people_stats:
        return []
    names = people_names or {}
    ranked = sorted(
        ((person_id, stats) for person_id, stats in people_stats.items() if _text(names.get(person_id))),
        key=lambda item: (-(item[1].get('talk_seconds') or 0.0), -(item[1].get('conversation_count') or 0), item[0]),
    )
    return [
        {
            'person_id': person_id,
            'name': _text(names.get(person_id)),
            'conversations': int(stats.get('conversation_count') or 0),
            'talk_minutes': math.ceil((stats.get('talk_seconds') or 0.0) / 60),
        }
        for person_id, stats in ranked[:MAX_TOP_PEOPLE]
    ]


def build_period_recap(
    period: str,
    start: date,
    end: date,
    summaries: Iterable[Any],
    *,
    previous_summaries: Optional[Iterable[Any]] = None,
    people_stats: Optional[Mapping[str, Mapping[str, Any]]] = None,
    people_names: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Roll the daily recaps between ``start`` and ``end`` (local dates) into one recap."""
    if period not in RECAP_PERIODS:
        raise ValueError(f'unknown recap period: {period!r}')
    days = _in_period(summaries, start, end)
    previous = None
    if previous_summaries is not None:
        previous_start, previous_end = previous_period_bounds(period, start)
        previous = _totals(
            _in_period(previous_summaries, previous_start, previous_end),
            ('total_conversations', 'total_duration_minutes'),
        )
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
        'open_action_items': _open_action_items(days),
        'top_people': _top_people(people_stats, people_names),
        'previous': previous,
    }

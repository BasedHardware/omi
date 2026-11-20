"""Pure day-level computations (no product imports): normalization, memory delta, readiness.

``runs/<run_id>/day.json`` = ``{daily_summary, goals:[...], memory_delta:{added, updated,
removed}, notifications:[...]}`` plus ``chat_index`` (an addition the handoff asks for).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from testing.pipeline_lab.chain.export import memory as normalize_memory
from testing.pipeline_lab.chain.export import notification as normalize_notification
from testing.pipeline_lab.stack.io import iso, parse_time, plain

DAILY_SUMMARY_FIELDS = ('headline', 'overview', 'highlights', 'memories_learned', 'stats', 'date')
GOAL_FIELDS = (
    'id',
    'title',
    'description',
    'current_value',
    'target_value',
    'unit',
    'is_active',
    'latest_progress_sequence',
)


def day_bounds(day: str, tz_name: str | None) -> tuple[datetime, datetime]:
    """UTC bounds of the local calendar day ``day`` (YYYY-MM-DD)."""
    tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    local = datetime.combine(date.fromisoformat(day), time(0, 0), tzinfo=tz)
    return local.astimezone(timezone.utc), (local + timedelta(days=1)).astimezone(timezone.utc)


def recap_instant(
    day: str, tz_name: str | None, *, local_hour: int = 22, production_at: Any = None
) -> tuple[datetime, str]:
    """When the recap runs: production's own instant when known, else ``local_hour`` local time."""
    parsed = parse_time(production_at)
    if parsed is not None:
        return parsed, 'production'
    tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    local = datetime.combine(date.fromisoformat(day), time(local_hour, 0), tzinfo=tz)
    return local.astimezone(timezone.utc), f'local_{local_hour:02d}h'


def normalize_daily_summary(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {name: plain(row.get(name)) for name in DAILY_SUMMARY_FIELDS if name in row}


def normalize_goal(row: Mapping[str, Any]) -> dict[str, Any]:
    return {name: plain(row.get(name)) for name in GOAL_FIELDS if name in row}


def contract_daily_summary(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """A product daily-summary row in the contract shape ``{title, overview, highlights}`` (RULINGS 5).

    The other product fields (``date``, ``stats``, ``memories_learned``) ride along as extras.
    """
    if not row:
        return None
    highlights = row.get('highlights') or []
    out = {
        'title': str(row.get('headline') or row.get('title') or ''),
        'overview': str(row.get('overview') or row.get('summary') or ''),
        'highlights': plain(list(highlights) if isinstance(highlights, list) else [highlights]),
    }
    out.update({name: plain(row.get(name)) for name in ('date', 'stats', 'memories_learned') if name in row})
    return out


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def contract_goals(before: Iterable[Mapping[str, Any]], after: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Goals as ``{title, progress_before, progress_after, target, note}`` (RULINGS 5), id and unit as extras."""
    start = {str(g.get('id')): g for g in before if g.get('id') is not None}
    out = []
    for goal in after:
        old = start.get(str(goal.get('id')), {})
        row = {
            'id': goal.get('id'),
            'title': str(goal.get('title') or ''),
            'progress_before': _number(old.get('current_value')),
            'progress_after': _number(goal.get('current_value')),
            'target': _number(goal.get('target_value')),
            'note': '' if old else 'new during the day',
        }
        if goal.get('unit'):
            row['unit'] = goal.get('unit')
        out.append(row)
    return sorted(out, key=lambda g: str(g.get('id')))


def _memory_key(row: Mapping[str, Any]) -> str:
    return str(row.get('id') or normalize_memory(row)['key'])


def _live(row: Mapping[str, Any]) -> bool:
    return not row.get('deleted') and not row.get('invalid_at') and not row.get('superseded_by')


def memory_delta(before: Iterable[Mapping[str, Any]], after: Iterable[Mapping[str, Any]]) -> dict[str, list[dict]]:
    """Added / updated / removed live memories between the start state and the end of the day.

    Identity is the memory id; a row that is live before and gone (or invalidated,
    superseded) after counts as removed. Updated = same id, different content or category.
    """
    start = {_memory_key(row): row for row in before if _live(row)}
    end = {_memory_key(row): row for row in after if _live(row)}

    def view(row: Mapping[str, Any]) -> dict[str, Any]:
        normalized = normalize_memory(row)
        return {'id': row.get('id'), **normalized, 'conversation_id': row.get('conversation_id')}

    added = [view(end[k]) for k in sorted(end.keys() - start.keys())]
    removed = [view(start[k]) for k in sorted(start.keys() - end.keys())]
    updated = []
    for key in sorted(start.keys() & end.keys()):
        old, new = normalize_memory(start[key]), normalize_memory(end[key])
        if (old['content'], old['category']) != (new['content'], new['category']):
            updated.append({**view(end[key]), 'before': {'content': old['content'], 'category': old['category']}})
    return {'added': added, 'updated': updated, 'removed': removed}


def chat_index_readiness(
    conversation_ids: Sequence[str],
    *,
    has_vector: Callable[[str], bool],
    has_search_doc: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Can chat over the replayed day find these conversations?

    ``has_vector`` checks the ns1 summary vector; ``has_search_doc`` checks the Typesense
    conversation document when a checker is supplied. Ready = every kept conversation
    is in each checked index.
    """
    missing_vectors = [cid for cid in conversation_ids if not has_vector(cid)]
    result: dict[str, Any] = {
        'conversations': len(conversation_ids),
        'vector_indexed': len(conversation_ids) - len(missing_vectors),
        'missing_vectors': missing_vectors,
        'search_checked': has_search_doc is not None,
    }
    ready = not missing_vectors
    if has_search_doc is not None:
        missing_docs = [cid for cid in conversation_ids if not has_search_doc(cid)]
        result['search_indexed'] = len(conversation_ids) - len(missing_docs)
        result['missing_search_docs'] = missing_docs
        ready = ready and not missing_docs
    result['ready'] = ready
    return result


def build_day_json(
    *,
    daily_summary: Mapping[str, Any] | None,
    goals: Iterable[Mapping[str, Any]],
    memories_before: Iterable[Mapping[str, Any]],
    memories_after: Iterable[Mapping[str, Any]],
    notifications: Iterable[Mapping[str, Any]],
    chat_index: Mapping[str, Any] | None = None,
    recap: Mapping[str, Any] | None = None,
    goals_before: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    pushes = sorted(
        ({**normalize_notification(row), 'conversation_id': row.get('conversation_id')} for row in notifications),
        key=lambda row: str(row.get('at') or ''),
    )
    return {
        'daily_summary': contract_daily_summary(normalize_daily_summary(daily_summary)),
        'goals': contract_goals(list(goals_before), [normalize_goal(goal) for goal in goals]),
        'memory_delta': memory_delta(memories_before, memories_after),
        'notifications': pushes,
        'chat_index': dict(chat_index) if chat_index is not None else {'checked': False},
        'recap': dict(recap or {}),
    }


def vector_id_checker(index: Any, uid: str, namespace_prefix: str = 'ns1') -> Callable[[str], bool]:
    """``has_vector`` over a :class:`NumericVectorIndex`, across the owner-routed copies of ns1."""

    def check(conversation_id: str) -> bool:
        vector_id = f'{uid}-{conversation_id}'
        for namespace in index.namespaces():
            if (
                namespace == namespace_prefix
                or namespace.startswith(namespace_prefix + '-')
                or namespace.startswith(namespace_prefix + '_')
            ):
                if vector_id in index.fetch(ids=[vector_id], namespace=namespace)['vectors']:
                    return True
        return False

    return check


__all__ = [
    'build_day_json',
    'chat_index_readiness',
    'day_bounds',
    'memory_delta',
    'normalize_daily_summary',
    'normalize_goal',
    'recap_instant',
    'vector_id_checker',
    'iso',
]

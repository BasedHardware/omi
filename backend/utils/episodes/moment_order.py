"""An episode's moments read by time, whichever form their clocks are stored in."""

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from config.episodes import COMPOSER_MIN_SECTION_SECONDS, MAX_MOMENTS


def _moment_time(value: Any) -> Optional[datetime]:
    """A moment's clock as a datetime: fresh writes hold one, a document unsealed from storage holds ISO text."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _moment_order(moment: Mapping[str, Any]) -> datetime:
    return _moment_time(moment.get('started_at')) or datetime.min.replace(tzinfo=timezone.utc)


def newest_moments(moments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The cap drops the earliest moments by time; a late recording's moment arrives last and may be old."""
    newest = sorted(moments, key=_moment_order)[-MAX_MOMENTS:]
    keep = {id(moment) for moment in newest}
    return [moment for moment in moments if id(moment) in keep]


def timeline_moments(moments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Moments in time order, not arrival order. A stored section seconds long runs to the next on its recording."""
    ordered = sorted(moments, key=_moment_order)
    read = []
    for index, moment in enumerate(ordered):
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        start, end = _moment_time(moment.get('started_at')), _moment_time(moment.get('ended_at'))
        if (
            moment.get('points')
            and following
            and following.get('conversation_id') == moment.get('conversation_id')
            and start
            and end
            and (end - start).total_seconds() < COMPOSER_MIN_SECTION_SECONDS
        ):
            moment = {**moment, 'ended_at': following.get('started_at'), 'end_offset': following.get('start_offset')}
        read.append(moment)
    return read

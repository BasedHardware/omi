"""Deterministic evidence filter; no identities or events are invented."""

import re
from datetime import datetime, timezone
from typing import Any, Sequence

from utils.conversations.episode_compaction import episode_words

_CALL = re.compile(
    r'\b(google meet|zoom meeting|teams meeting|call ended|left the call|waiting for|microphone|muted)\b', re.I
)
_GENERIC = {
    'meeting',
    'project',
    'people',
    'screen',
    'working',
    'work',
    'update',
    'notes',
    'conversation',
    'discuss',
    'today',
    'tomorrow',
    'message',
}


def _datetime(value: str | None) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value or '')
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def after_capture(item: Any, finished_at: str | None) -> bool:
    if item.source_kind in {'calendar', 'open_task'}:
        return False  # Scheduled/due times are expectations, not observation clocks.
    observed, finish = _datetime(item.time), _datetime(finished_at)
    return bool(observed and finish and observed > finish)


def deterministic_episode_selection(items: Sequence[Any], *, finished_at: str | None = None) -> list[Any]:
    """Conservative independent links, not names/co-occurrence alone. Speech is intact."""
    speech = [item for item in items if item.source_kind == 'speech']
    words = episode_words(' '.join(item.content for item in speech)) - _GENERIC
    actors = {item.actor.casefold() for item in speech if item.actor and item.actor != 'account owner'}
    chosen = []
    for item in items:
        if item.source_kind == 'speech':
            chosen.append(item)
            continue
        if after_capture(item, finished_at):
            continue
        overlap = (episode_words(item.content) - _GENERIC) & words
        named = any(re.search(r'(?<!\w)' + re.escape(actor) + r'(?!\w)', item.content.casefold()) for actor in actors)
        if item.source_kind in {'calendar', 'roster', 'device_state'}:
            chosen.append(item)
        elif (
            len(overlap) >= 3
            or (named and len(overlap) >= 2)
            or (item.source_kind in {'screen_frame', 'screen_ocr'} and _CALL.search(item.content))
        ):
            chosen.append(item)
    return chosen

"""Bounding primitives for the daily-summary notifications job (#12530).

The daily-summary cron is a Cloud Run Job with a hard 600s task timeout. Two
unbounded quantities used to make it unsurvivable:

1. **Per-user input.** ``generate_comprehensive_daily_summary`` renders *every*
   conversation of the user's day into one prompt. A heavy day overflowed the
   model context window (observed ~290k tokens against a 272k limit), which
   raised a provider 400 every single day for the same account.
2. **Job scope.** Every execution restarted the hour groups from the beginning,
   so whoever sat past the 600s mark was never reached — a silent, permanent
   tail loss rather than a visible failure.

This module holds the two bounds, kept out of ``utils/other/notifications.py``
so they are unit-testable without importing the job's dependency graph:

* ``select_conversations_within_budget`` — most-recent-first selection under a
  rendered-character budget.
* ``read_job_cursor`` / ``write_job_cursor`` / ``clear_job_cursor`` — a
  fail-soft Redis checkpoint so the next execution resumes at the unfinished
  tail instead of re-walking the head.

Every Redis helper here is *synchronous* and must be called through
``run_blocking(db_executor, ...)`` from async code.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, TypeVar, cast

logger = logging.getLogger(__name__)

# Cursor keys are scoped to the UTC hour the job is serving: the hour groups are
# recomputed from wall-clock every execution, so a cursor from a previous hour
# points into a different user population. 2h TTL covers the every-minute
# scheduler plus clock skew without leaving stale keys around.
JOB_CURSOR_TTL_SECONDS = 60 * 60 * 2

_CURSOR_HOUR = 'hour'
_CURSOR_UID = 'uid'

T = TypeVar('T')


class BoundedConversations(NamedTuple):
    """Result of applying the per-user input bound."""

    conversations: List[Any]
    dropped: int
    rendered_chars: int

    @property
    def truncated(self) -> bool:
        return self.dropped > 0


def _sort_key(conversation: Any) -> datetime:
    """Recency key that tolerates naive datetimes and missing fields."""
    value = getattr(conversation, 'started_at', None) or getattr(conversation, 'created_at', None)
    if not isinstance(value, datetime):
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _default_render(conversation: Any) -> str:
    # Imported lazily: this module is loaded by unit tests that do not want the
    # conversation model graph, and the renderer is only needed for measurement.
    from utils.conversations.render import conversations_to_string

    return conversations_to_string([conversation])


def select_conversations_within_budget(
    conversations: Sequence[Any],
    max_chars: int,
    render: Optional[Callable[[Any], str]] = None,
) -> BoundedConversations:
    """Keep the most recent conversations that fit inside ``max_chars``.

    The summary prompt is built from the *whole* day, so a user with an
    exceptional day could exceed the model's context window and get a provider
    400 forever. Selection is most-recent-first (the part of the day a recap is
    actually about), and the kept conversations are returned in their original
    chronological order so the prompt's ``Conversation #N`` numbering and the
    generator's id map stay consistent.

    The first conversation is always kept: a single oversized conversation must
    still produce a summary attempt rather than an empty prompt.
    """
    if max_chars <= 0 or not conversations:
        return BoundedConversations(list(conversations), 0, 0)

    render_one = render or _default_render
    original_order = {id(c): i for i, c in enumerate(conversations)}
    by_recency = sorted(conversations, key=_sort_key, reverse=True)

    kept: List[Any] = []
    used = 0
    dropped = 0
    for conversation in by_recency:
        try:
            size = len(render_one(conversation))
        except Exception as e:  # a single unrenderable conversation must not sink the recap
            logger.warning('daily_summary_budget_render_failed error=%s', e)
            size = 0
        if kept and used + size > max_chars:
            dropped += 1
            continue
        kept.append(conversation)
        used += size

    kept.sort(key=lambda c: original_order[id(c)])
    return BoundedConversations(kept, dropped, used)


def job_cursor_key(now_utc: datetime) -> str:
    """Cursor key for the UTC hour currently being served."""
    return f'daily_summary_job_cursor:{now_utc.strftime("%Y-%m-%dT%H")}'


def make_cursor(target_hour: Optional[int], uid: Optional[str]) -> Dict[str, Any]:
    return {_CURSOR_HOUR: target_hour, _CURSOR_UID: uid}


def cursor_hour(cursor: Optional[Dict[str, Any]]) -> Optional[int]:
    if not cursor:
        return None
    value = cursor.get(_CURSOR_HOUR)
    return value if isinstance(value, int) else None


def cursor_uid(cursor: Optional[Dict[str, Any]]) -> Optional[str]:
    if not cursor:
        return None
    value = cursor.get(_CURSOR_UID)
    return value if isinstance(value, str) and value else None


def rotate_to(items: Sequence[T], start: Optional[T]) -> List[T]:
    """Rotate ``items`` so it begins at ``start`` (identity by equality).

    Rotation rather than slicing: the unfinished tail is served first, but the
    head is still covered in the same pass, so no user is systematically
    starved and a stale cursor cannot strand anyone.
    """
    ordered = list(items)
    if start is None:
        return ordered
    try:
        index = ordered.index(start)
    except ValueError:
        return ordered
    return ordered[index:] + ordered[:index]


def _redis_client() -> Any:
    from database.redis_db import r

    return r


def read_job_cursor(key: str) -> Optional[Dict[str, Any]]:
    """Read the checkpoint. Never raises — a Redis outage just means no resume."""
    try:
        raw = _redis_client().get(key)
    except Exception as e:
        logger.warning('daily_summary_cursor_read_failed key=%s error=%s', key, e)
        return None
    if not raw:
        return None
    try:
        loaded: object = json.loads(raw)
    except Exception:
        return None
    return cast(Dict[str, Any], loaded) if isinstance(loaded, dict) else None


def write_job_cursor(key: str, cursor: Dict[str, Any], ttl: int = JOB_CURSOR_TTL_SECONDS) -> None:
    """Persist the checkpoint. Never raises — losing it only costs a re-walk."""
    try:
        _redis_client().set(key, json.dumps(cursor), ex=ttl)
    except Exception as e:
        logger.warning('daily_summary_cursor_write_failed key=%s error=%s', key, e)


def clear_job_cursor(key: str) -> None:
    """Drop the checkpoint after a full pass. Never raises."""
    try:
        _redis_client().delete(key)
    except Exception as e:
        logger.warning('daily_summary_cursor_clear_failed key=%s error=%s', key, e)

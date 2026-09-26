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

# The checkpoint is a single stable key, bounded only by its TTL. It used to be
# scoped to the UTC hour being served, which made it unreadable by design: the
# execution that exhausted its budget wrote `...:2026-09-02T18` and the next
# execution read `...:2026-09-02T19`, so the unfinished tail was never resumed
# and the whole point of the checkpoint was lost. The serving cohort that a
# checkpoint describes has to outlive the hour bucket, so the key must too.
#
# Starvation is prevented by `rotate_to`, not by the key: a run rotates the hour
# groups to start at the checkpoint and then walks the *whole* rotated list, so
# a carried-over cursor reorders a pass and never removes an hour from it. The
# TTL is the staleness bound — a cursor no execution reached within two hours
# describes a population that no longer exists, and expiring it costs a
# re-walk from the head, never a lost summary.
JOB_CURSOR_TTL_SECONDS = 60 * 60 * 2
JOB_CURSOR_KEY = 'daily_summary_job_cursor'

# Fallback bound when the deployed budget is missing or nonpositive. ~360k chars
# is roughly 90k tokens, comfortably inside the 272k-token model limit.
DEFAULT_MAX_HISTORY_CHARS = 360_000

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
    if not conversations:
        return BoundedConversations([], 0, 0)
    if max_chars <= 0:
        # A nonpositive budget used to return the whole day, i.e. it removed the
        # only bound protecting the prompt from the context overflow this module
        # exists for. Misconfiguration falls back to the bound, never past it.
        logger.warning('daily_summary_budget_invalid_max_chars value=%s', max_chars)
        max_chars = DEFAULT_MAX_HISTORY_CHARS

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
            # Counting it as zero and keeping it only moved the failure into the
            # summary render, where it costs the whole recap instead of one
            # conversation. Drop it and report it as dropped.
            logger.warning('daily_summary_budget_render_failed error=%s', e)
            dropped += 1
            continue
        if kept and used + size > max_chars:
            dropped += 1
            continue
        kept.append(conversation)
        used += size

    if not kept:
        # Every render failed, so the fault is in the renderer, not in any one
        # conversation. Dropping the whole day would turn that into a silently
        # missing recap; hand the material over and let the generator fail
        # loudly on its own instead.
        logger.warning('daily_summary_budget_all_renders_failed count=%d', len(conversations))
        return BoundedConversations(list(conversations), 0, 0)
    kept.sort(key=lambda c: original_order[id(c)])
    return BoundedConversations(kept, dropped, used)


def job_cursor_key() -> str:
    """Checkpoint key for the daily-summary job. Stable across hour rollovers."""
    return JOB_CURSOR_KEY


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

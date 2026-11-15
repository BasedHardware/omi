"""Backend-owned AI user profile: source selection, cadence and the canonical write.

``users/{uid}.ai_user_profile`` is the one profile every surface reads (desktop chat and
assistants, the notes agent, MCP, owner-name fallback). The backend selects the sources
itself, runs ``utils.llm.ai_user_profile`` and writes the field; clients only read it,
edit it (``source=user_edit``) or seed it (``source=exploration``). There is no history:
the stored text, including a user's edit, is the past profile the next synthesis
consolidates, so knowledge accumulates and corrections carry forward.

Cadence: ``refresh_if_stale`` runs after a processed conversation and when a client reads
the profile. It is a no-op unless the last backend refresh is older than
``REFRESH_AFTER``, the owner may spend generated compute, and the per-owner Redis lock
(held for an hour, so a failure is not retried in a loop) is free.
``AI_PROFILE_BACKEND_REFRESH_ENABLED=false`` stops automatic refreshes; the explicit
``POST /v1/users/ai-profile/refresh`` keeps working under its own rate limit.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import database.action_items as action_items_db
import database.chat as chat_db
import database.conversations as conversations_db
import database.goals as goals_db
import database.redis_db as redis_db
import database.users as users_db
from utils.generated_compute import generated_compute_allowed
from utils.llm import ai_user_profile as profile_llm
from utils.llms.memory import get_prompt_memories

logger = logging.getLogger(__name__)

KILL_SWITCH_ENV = 'AI_PROFILE_BACKEND_REFRESH_ENABLED'
REFRESH_AFTER = timedelta(hours=20)
CONVERSATION_DAYS = 7
MEMORY_LINES = 100
TASK_LIMIT = 50
CONVERSATION_LIMIT = 20
MESSAGE_LIMIT = 30
SOURCE_BACKEND = 'backend'
SOURCE_USER_EDIT = 'user_edit'


class RefreshError(Exception):
    """Typed outcome of an explicit refresh; ``code`` is the HTTP detail string."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def automatic_refresh_enabled() -> bool:
    return os.getenv(KILL_SWITCH_ENV, 'true').strip().lower() not in {'false', '0', 'off', 'no'}


def _parse_time(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def is_stale(profile: Optional[dict], now: Optional[datetime] = None) -> bool:
    refreshed_at = _parse_time((profile or {}).get('refreshed_at'))
    return refreshed_at is None or (now or datetime.now(timezone.utc)) - refreshed_at >= REFRESH_AFTER


def _safe(name: str, uid: str, read) -> list[str]:
    # One unreadable source degrades the profile; it must not abort the refresh.
    try:
        return [line for line in read() if line and line.strip()]
    except Exception as error:
        logger.warning('event=ai_profile_source_failed source=%s uid=%s exc=%s', name, uid, type(error).__name__)
        return []


def _memories(uid: str) -> list[str]:
    _, rendered = get_prompt_memories(uid)
    return [line.strip() for line in str(rendered or '').splitlines() if line.strip()][:MEMORY_LINES]


def _tasks(uid: str) -> list[str]:
    items = action_items_db.get_action_items(uid, limit=TASK_LIMIT) or []
    return [
        f"[{'done' if item.get('completed') else 'todo'}/{item.get('priority') or 'medium'}] {item.get('description')}"
        for item in items
        if item.get('description')
    ]


def _goals(uid: str) -> list[str]:
    lines = []
    for goal in goals_db.get_all_goals(uid) or []:
        title = goal.get('title')
        if not title:
            continue
        target = float(goal.get('target_value') or 0)
        current = float(goal.get('current_value') or 0)
        progress = int(current / target * 100) if target > 0 else 0
        lines.append(f'{title} ({progress}% complete)')
    return lines


def _conversations(uid: str, now: datetime) -> list[str]:
    rows = (
        conversations_db.get_conversations_without_photos(
            uid,
            limit=CONVERSATION_LIMIT,
            start_date=now - timedelta(days=CONVERSATION_DAYS),
            end_date=now,
        )
        or []
    )
    lines = []
    for row in rows:
        structured = (row or {}).get('structured') or {}
        title = structured.get('title')
        if title:
            lines.append(f"{title}: {structured.get('overview') or ''}".strip())
    return lines


def _messages(uid: str) -> list[str]:
    rows = chat_db.get_messages(uid, limit=MESSAGE_LIMIT) or []
    return [f"[{row.get('sender')}] {row.get('text')}" for row in rows if row.get('text')]


def collect_sources(uid: str, now: Optional[datetime] = None) -> profile_llm.ProfileSources:
    now = now or datetime.now(timezone.utc)
    return profile_llm.ProfileSources(
        memories=_safe('memories', uid, lambda: _memories(uid)),
        tasks=_safe('tasks', uid, lambda: _tasks(uid)),
        goals=_safe('goals', uid, lambda: _goals(uid)),
        conversations=_safe('conversations', uid, lambda: _conversations(uid, now)),
        messages=_safe('messages', uid, lambda: _messages(uid)),
    )


def _generate(uid: str) -> tuple[dict, bool]:
    """Synthesize and write; returns (stored profile, written). Raises ``RefreshError`` without writing."""
    now = datetime.now(timezone.utc)
    previous = users_db.get_ai_user_profile_fresh(uid) or {}
    previous_text = str(previous.get('profile_text') or '').strip()
    sources = collect_sources(uid, now)
    if sources.total_items() == 0:
        raise RefreshError('ai_profile_insufficient_data')
    synthesis = profile_llm.synthesize_ai_user_profile(
        uid,
        sources,
        past_profiles=[previous_text] if previous_text else [],
        latest_past_user_edited=previous.get('source') == SOURCE_USER_EDIT,
    )
    if synthesis is None:
        raise RefreshError('ai_profile_synthesis_failed')
    stamp = now.isoformat()
    profile = {
        'profile_text': synthesis.profile_text,
        'generated_at': stamp,
        'refreshed_at': stamp,
        'data_sources_used': synthesis.item_count,
        'source': SOURCE_BACKEND,
    }
    # The user may have edited or deleted the profile while the model ran; their
    # change wins (atomically) and is folded in by the next refresh.
    if not users_db.write_ai_user_profile_if_unchanged(uid, previous_text, profile):
        logger.info('event=ai_profile_refresh outcome=superseded uid=%s', uid)
        return users_db.get_ai_user_profile_fresh(uid) or {}, False
    logger.info(
        'event=ai_profile_refresh outcome=written uid=%s items=%d chars=%d sources=%s',
        uid,
        synthesis.item_count,
        len(synthesis.profile_text),
        ','.join(synthesis.data_sources_used),
    )
    return profile, True


def refresh_now(uid: str) -> dict:
    """Explicit refresh for the owner. Caller has already passed compute admission."""
    try:
        acquired = redis_db.try_acquire_ai_profile_refresh_lock(uid, ttl=10 * 60)
    except Exception:
        acquired = True  # An explicit, rate-limited request may proceed without Redis.
    if not acquired:
        raise RefreshError('ai_profile_refresh_in_progress')
    try:
        return _generate(uid)[0]
    finally:
        try:
            # Release so a later manual retry is not blocked; the stamp gates the daily cadence.
            redis_db.release_ai_profile_refresh_lock(uid)
        except Exception:
            pass


def refresh_if_stale(uid: str) -> str:
    """Automatic refresh; returns an outcome label and never raises."""
    try:
        if not uid or not automatic_refresh_enabled():
            return 'disabled'
        if not is_stale(users_db.get_ai_user_profile(uid)):
            return 'fresh'
        try:
            if not redis_db.try_acquire_ai_profile_refresh_lock(uid):
                return 'locked'
        except Exception:
            return 'lock_unavailable'  # Fail closed: no lock, no spend.
        if not is_stale(users_db.get_ai_user_profile_fresh(uid)):
            return 'fresh'
        if not generated_compute_allowed(uid, 'memories'):
            return 'compute_denied'
        return 'written' if _generate(uid)[1] else 'superseded'
    except RefreshError as error:
        logger.info('event=ai_profile_refresh outcome=%s uid=%s', error.code, uid)
        return error.code
    except Exception as error:
        logger.warning('event=ai_profile_refresh outcome=error uid=%s exc=%s', uid, type(error).__name__)
        return 'error'

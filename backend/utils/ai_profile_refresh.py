"""Backend-owned AI user profile: source selection, cadence and the canonical write.

``users/{uid}.ai_user_profile`` is the one profile every surface reads (desktop chat and
assistants, the notes agent, MCP, owner-name fallback). The backend selects the sources
itself, runs ``utils.llm.ai_user_profile`` and writes the field; clients only read it,
edit it (``source=user_edit``) or seed it (``source=exploration``). There is no history:
the stored text, including a user's edit, is the past profile the next synthesis
consolidates, so knowledge accumulates and corrections carry forward.

Cadence: ``schedule_refresh`` runs after a processed conversation and when a client reads
the profile. It is a no-op unless the last backend refresh is older than
``REFRESH_AFTER``; at most ``MAX_CONCURRENT_AUTOMATIC`` automatic refreshes run per process,
so they never occupy more than that many postprocessing workers, and a skipped one is
retried by the next trigger. A refresh then needs the owner's hourly automatic cooldown
key (so a failure is not retried in a loop), the short in-progress lock that it shares
with the explicit route, and generated-compute admission. Redis errors fail closed.
``AI_PROFILE_BACKEND_REFRESH_ENABLED=false`` stops automatic refreshes; the explicit
``POST /v1/users/ai-profile/refresh`` keeps working under its own fail-closed rate limit.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

import database.action_items as action_items_db
import database.chat as chat_db
import database.conversation_tombstones as conversation_tombstones_db
import database.conversations as conversations_db
import database.goals as goals_db
import database.redis_db as redis_db
import database.users as users_db
from database._client import get_firestore_client
from database.conversation_effect_fence import (
    ConversationEffectFenced,
    ConversationEffectSource,
    ConversationEffectSourceChanged,
    ProfileConversationInput,
)
from models.knowledge_ledger_policy import is_prompt_memory_visible
from utils.executors import postprocess_executor, submit_with_context
from utils.generated_compute import generated_compute_allowed
from utils.llm import ai_user_profile as profile_llm
from utils.memory.memory_service import MemoryService

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
IN_PROGRESS_TTL_SECONDS = 10 * 60
AUTOMATIC_COOLDOWN_SECONDS = 60 * 60
MAX_CONCURRENT_AUTOMATIC = 2

_automatic_slots = threading.BoundedSemaphore(MAX_CONCURRENT_AUTOMATIC)
_scheduled_lock = threading.Lock()
# Only conversation-owned jobs can need a separately requested account refresh.
_conversation_jobs: dict[str, threading.Event] = {}


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
    # The canonical default-visible read the memories list and prompt context use.
    rows = MemoryService(db_client=get_firestore_client()).read(uid, limit=MEMORY_LINES)
    lines = []
    for memory in rows or []:
        if not is_prompt_memory_visible(memory) or not memory.content:
            continue
        category = getattr(memory.category, 'value', memory.category)
        lines.append(f'[{category}] {memory.content}')
    return lines


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


def _conversations(uid: str, now: datetime) -> tuple[list[str], tuple[ProfileConversationInput, ...]]:
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
    inputs = []
    for row in rows:
        structured = (row or {}).get('structured') or {}
        title = structured.get('title')
        conversation_id, updated_at = row.get('id'), row.get('updated_at')
        if not title or not conversation_id or not isinstance(updated_at, datetime):
            continue
        # Legacy deletion paths can leave a visible row behind the durable intent.
        if conversation_tombstones_db.is_deleted(uid, conversation_id):
            continue
        lines.append(f"{title}: {structured.get('overview') or ''}".strip())
        inputs.append(ProfileConversationInput(conversation_id, row.get('sync_content_revision'), updated_at))
    return lines, tuple(inputs)


def _messages(uid: str) -> list[str]:
    rows = chat_db.get_messages(uid, limit=MESSAGE_LIMIT) or []
    return [f"[{row.get('sender')}] {row.get('text')}" for row in rows if row.get('text')]


def collect_sources(
    uid: str, now: Optional[datetime] = None
) -> tuple[profile_llm.ProfileSources, tuple[ProfileConversationInput, ...]]:
    now = now or datetime.now(timezone.utc)
    try:
        conversations, inputs = _conversations(uid, now)
    except Exception as error:
        logger.warning('event=ai_profile_source_failed source=conversations uid=%s exc=%s', uid, type(error).__name__)
        conversations, inputs = [], ()
    sources = profile_llm.ProfileSources(
        memories=_safe('memories', uid, lambda: _memories(uid)),
        tasks=_safe('tasks', uid, lambda: _tasks(uid)),
        goals=_safe('goals', uid, lambda: _goals(uid)),
        conversations=conversations,
        messages=_safe('messages', uid, lambda: _messages(uid)),
    )
    return sources, inputs[: profile_llm.MAX_LINES_PER_SOURCE]


def _generate(uid: str, *, effect_source: ConversationEffectSource | None = None) -> tuple[dict, bool]:
    """Synthesize and write; returns (stored profile, written). Raises ``RefreshError`` without writing."""
    now = datetime.now(timezone.utc)
    previous = users_db.get_ai_user_profile_fresh(uid) or {}
    previous_text = str(previous.get('profile_text') or '').strip()
    sources, conversation_inputs = collect_sources(uid, now)
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
    if not users_db.write_ai_user_profile_if_unchanged(
        uid, previous_text, profile, effect_source=effect_source, conversation_inputs=conversation_inputs
    ):
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


def _release_in_progress(uid: str) -> None:
    try:
        redis_db.release_ai_profile_refresh_lock(uid)
    except Exception:
        pass  # The lock expires on its own after IN_PROGRESS_TTL_SECONDS.


def refresh_now(uid: str) -> dict:
    """Explicit refresh for the owner. Caller has already passed compute admission."""
    try:
        acquired = redis_db.try_acquire_ai_profile_refresh_lock(uid, ttl=IN_PROGRESS_TTL_SECONDS)
    except Exception:
        raise RefreshError('ai_profile_refresh_unavailable')  # No lock, no spend.
    if not acquired:
        raise RefreshError('ai_profile_refresh_in_progress')
    try:
        return _generate(uid)[0]
    except ConversationEffectFenced as error:
        raise RefreshError('ai_profile_refresh_superseded') from error
    finally:
        _release_in_progress(uid)


def refresh_if_stale(uid: str, *, effect_source: ConversationEffectSource | None = None) -> str:
    """Automatic refresh; returns an outcome label and never raises."""
    cooldown_token = None
    try:
        if not uid or not automatic_refresh_enabled():
            return 'disabled'
        if not is_stale(users_db.get_ai_user_profile(uid)):
            return 'fresh'
        cooldown_token = uuid4().hex if effect_source is not None else None
        try:
            if not redis_db.try_acquire_ai_profile_auto_cooldown(
                uid, ttl=AUTOMATIC_COOLDOWN_SECONDS, **({'token': cooldown_token} if cooldown_token is not None else {})
            ):
                return 'cooldown'
            if not redis_db.try_acquire_ai_profile_refresh_lock(uid, ttl=IN_PROGRESS_TTL_SECONDS):
                return 'locked'
        except Exception:
            return 'lock_unavailable'  # Fail closed: no lock, no spend.
        try:
            if not is_stale(users_db.get_ai_user_profile_fresh(uid)):
                return 'fresh'
            if not generated_compute_allowed(uid, 'memories'):
                return 'compute_denied'
            return 'written' if _generate(uid, effect_source=effect_source)[1] else 'superseded'
        finally:
            _release_in_progress(uid)
    except ConversationEffectSourceChanged:
        if cooldown_token is not None:
            try:
                redis_db.release_ai_profile_auto_cooldown(uid, cooldown_token)
            except Exception as error:
                logger.warning('event=ai_profile_refresh outcome=cooldown_release_error exc=%s', type(error).__name__)
        return 'source_fenced'
    except ConversationEffectFenced:
        return 'account_fenced'
    except RefreshError as error:
        logger.info('event=ai_profile_refresh outcome=%s uid=%s', error.code, uid)
        return error.code
    except Exception as error:
        logger.warning('event=ai_profile_refresh outcome=error uid=%s exc=%s', uid, type(error).__name__)
        return 'error'


def _run_scheduled(uid: str, effect_source: ConversationEffectSource | None = None) -> None:
    try:
        if effect_source is None:
            refresh_if_stale(uid)
            return
        try:
            outcome = refresh_if_stale(uid, effect_source=effect_source)
        finally:
            with _scheduled_lock:
                independent = _conversation_jobs.pop(uid).is_set()
        if outcome == 'source_fenced' and independent:
            # A read requested its own refresh. Collect fresh inputs after the
            # rejected synthesis releases the shared Redis lock and cooldown.
            refresh_if_stale(uid)
    finally:
        _automatic_slots.release()


def schedule_refresh(
    uid: str,
    profile: Optional[dict] = None,
    *,
    known: bool = False,
    effect_source: ConversationEffectSource | None = None,
) -> bool:
    """Queue an automatic refresh if the profile looks stale and a process slot is free.

    ``known`` means ``profile`` is the caller's current read (``None`` = no profile), which
    saves a cache read. Never blocks and never raises. Returns whether work was
    queued or an independent request joined a queued conversation job.
    """
    try:
        if not uid or not automatic_refresh_enabled():
            return False
        if not is_stale(profile if known else users_db.get_ai_user_profile(uid)):
            return False
        with _scheduled_lock:
            pending = _conversation_jobs.get(uid)
            if pending is not None:
                if effect_source is None:
                    pending.set()
                    return True
                return False
            if not _automatic_slots.acquire(blocking=False):
                return False  # Busy: the next trigger retries.
            if effect_source is not None:
                _conversation_jobs[uid] = threading.Event()
        try:
            if effect_source is None:
                submit_with_context(postprocess_executor, _run_scheduled, uid)
            else:
                submit_with_context(postprocess_executor, _run_scheduled, uid, effect_source)
        except Exception:
            with _scheduled_lock:
                if effect_source is not None:
                    _conversation_jobs.pop(uid)
            _automatic_slots.release()
            raise
        return True
    except Exception as error:
        logger.warning('event=ai_profile_refresh outcome=schedule_error uid=%s exc=%s', uid, type(error).__name__)
        return False

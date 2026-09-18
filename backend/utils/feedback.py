"""Shared write path into the feedback ledger.

Three separate endpoints rate a chat message (mobile legacy, mobile v2,
desktop) and each already had its own persistence. Rather than teach each one
how to build a ledger row, they all call ``record_chat_message_feedback``,
which looks the message up once and captures the coordinates the daily report
needs: which session the turn belonged to, when it happened, and which prompt
revision produced it.

Capturing coordinates at write time is the point. Without them the report job
would have to scan a user's whole message history to locate a rated turn, which
is both slow and — on a collection this size — expensive enough to matter.
"""

import logging
from typing import Optional

import database.chat as chat_db
import database.feedback as feedback_db
from models.feedback import FeedbackSurface, FeedbackTargetKind

logger = logging.getLogger(__name__)


def _attr(message, key: str):
    """Read a field off a Message model or the raw dict, whichever we got."""
    value = getattr(message, key, None)
    if value is None and isinstance(message, dict):
        value = message.get(key)
    return value


def record_chat_message_feedback(
    uid: str,
    message_id: str,
    value: int,
    *,
    surface: FeedbackSurface = FeedbackSurface.chat_text,
    reason: Optional[str] = None,
    comment: Optional[str] = None,
    platform: Optional[str] = None,
    app_version: Optional[str] = None,
) -> Optional[str]:
    """Append a chat-message rating to the ledger. Returns the event id or None.

    Best-effort by design: the caller has already persisted the rating itself,
    so this never raises and never fails the user's request.
    """
    chat_session_id = None
    target_created_at = None
    app_id = None
    langsmith_run_id = None
    prompt_name = None
    prompt_commit = None

    try:
        found = chat_db.get_message(uid, message_id)
        if found:
            message, _ = found
            chat_session_id = _attr(message, 'chat_session_id')
            target_created_at = _attr(message, 'created_at')
            app_id = _attr(message, 'app_id')
            langsmith_run_id = _attr(message, 'langsmith_run_id')
            prompt_name = _attr(message, 'prompt_name')
            prompt_commit = _attr(message, 'prompt_commit')
    except Exception as e:
        # Coordinates are an optimization; a rating with none is still worth
        # recording, and the report resolves the window from the id alone.
        logger.error(f'Could not read coordinates for rated message {message_id}: {e}')

    return feedback_db.record_feedback_event(
        uid,
        surface,
        FeedbackTargetKind.chat_message,
        message_id,
        value,
        reason=reason,
        comment=comment,
        platform=platform,
        app_version=app_version,
        app_id=app_id,
        chat_session_id=chat_session_id,
        target_created_at=target_created_at,
        langsmith_run_id=langsmith_run_id,
        prompt_name=prompt_name,
        prompt_commit=prompt_commit,
    )


def record_conversation_summary_feedback(
    uid: str,
    conversation_id: str,
    value: int,
    *,
    reason: Optional[str] = None,
    comment: Optional[str] = None,
) -> Optional[str]:
    return feedback_db.record_feedback_event(
        uid,
        FeedbackSurface.conversation_summary,
        FeedbackTargetKind.conversation,
        conversation_id,
        value,
        reason=reason,
        comment=comment,
    )


def record_memory_feedback(uid: str, memory_id: str, keep: bool) -> Optional[str]:
    """Record a memory keep/discard verdict.

    Discarding a memory is the memories list's thumbs-down. Until now it only
    set ``user_review: False`` on the memory document — a mutable flag with no
    timestamp, so "which memories were rejected yesterday" had no answer. The
    ledger row gives that verdict a time and puts it in the same report as
    every other negative signal.
    """
    return feedback_db.record_feedback_event(
        uid,
        FeedbackSurface.memory,
        FeedbackTargetKind.memory,
        memory_id,
        1 if keep else -1,
    )

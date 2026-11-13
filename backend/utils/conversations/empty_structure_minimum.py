"""Recovery with no enriched structure completes a kept, plain conversation on the deterministic minimum.

Narrower than the typed refusal it replaces: only a kept, decoded, non-empty plain
conversation whose stored structure is replaceable. Every other case keeps the
refusal, so rich or titled stored content is never overwritten.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Optional

import database.notifications as notification_db
from models.conversation import Conversation
from models.structured import Structured
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured
from utils.conversations.processing_trigger import ProcessingTrigger, is_recovery_trigger
from utils.conversations.recovery import (
    recovery_empty_structure_minimum_enabled,
    recovery_transcript_word_count,
    structured_is_rich,
)
from utils.conversations.relevance import content_free_rule, final_relevance
from utils.conversations.wake_word import find_wake_word_matches
from utils.llm.notes_short_clip import has_explicit_reminder
from utils.release_probe import is_release_probe_uid

logger = logging.getLogger(__name__)


def _eligible(
    *,
    uid: str,
    trigger: ProcessingTrigger,
    conversation: Any,
    structured: Structured,
    discarded: bool,
    decisions: list[Any],
    app_id: Optional[str],
    recovery_transcript_decoded: bool,
    recovery_minimum_fallback: bool,
    final_attempt: bool,
) -> bool:
    if not final_attempt:
        # Earlier attempts keep the typed refusal, so a transient empty answer is retried.
        return False
    if not is_recovery_trigger(trigger) or not recovery_empty_structure_minimum_enabled():
        return False
    if recovery_minimum_fallback or discarded or structured_is_rich(structured):
        return False
    if not recovery_transcript_decoded or not isinstance(conversation, Conversation):
        return False
    if recovery_transcript_word_count(conversation) <= 0:
        return False
    relevance = final_relevance(decisions[0] if decisions else None, discarded=discarded)
    if relevance is None or relevance.verdict != 'keep':
        return False
    if app_id or is_release_probe_uid(uid):
        return False
    segments = conversation.transcript_segments or []
    texts = [segment.text for segment in segments]
    if content_free_rule(texts, has_photos=False, trusted_wake_word=bool(find_wake_word_matches(segments))):
        # Mic checks and filler stay on the discard path, as in the ordinary rule.
        return False
    if conversation.photos or has_explicit_reminder(conversation.transcript_segments):
        return False
    stored = conversation.structured
    stored_title = (getattr(stored, 'title', '') or '').strip()
    return not structured_is_rich(stored) and (
        not stored_title or getattr(stored, 'title_provenance', None) == 'server_minimum'
    )


def apply_empty_structure_minimum(
    uid: str,
    trigger: ProcessingTrigger,
    conversation: Any,
    structured: Structured,
    discarded: bool,
    decisions: list[Any],
    app_id: Optional[str],
    recovery_transcript_decoded: bool,
    recovery_minimum_fallback: bool,
    final_attempt: bool = True,
) -> tuple[Structured, bool]:
    """Return ``(structured, applied)``; ``applied`` means the minimum replaced the empty structure."""
    if not _eligible(
        uid=uid,
        trigger=trigger,
        conversation=conversation,
        structured=structured,
        discarded=discarded,
        decisions=decisions,
        app_id=app_id,
        recovery_transcript_decoded=recovery_transcript_decoded,
        recovery_minimum_fallback=recovery_minimum_fallback,
        final_attempt=final_attempt,
    ):
        return structured, False
    minimum = build_deterministic_minimum_structured(
        conversation,
        uid=uid,
        tz_name_provider=lambda: notification_db.get_user_time_zone(uid),
    )
    logger.warning('selfheal empty structure minimum applied relevance_verdict=keep')
    sys.stdout.write(
        json.dumps(
            {
                'event': 'selfheal_guard',
                'outcome': 'minimum_fallback',
                'reason': 'empty_structured',
                'structure_reason': 'no_enriched_structure',
                'relevance_verdict': 'keep',
                'uid': uid,
                'conversation_id': conversation.id,
            },
            default=str,
        )
        + '\n'
    )
    sys.stdout.flush()
    return minimum, True

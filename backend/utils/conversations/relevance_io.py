"""The I/O side of the relevance step: lookups, the model-withheld path, and recording.

``relevance.py`` stays pure (policy and tiers); this module holds what touches
Firestore or metrics, so ``process_conversation`` only wires them together.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable, Optional

from database import conversations as conversations_db
from utils.conversation_continuity import DEFAULT_GAP_SECONDS
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance import (
    RELEVANCE_DECISION_FIELD,
    Neighbor,
    RelevanceDecision,
    decide_relevance,
    find_neighbor,
)
from utils.conversations.wake_word import find_wake_word_matches
from utils.metrics import record_conversation_relevance
from utils.release_probe import is_release_probe_uid

logger = logging.getLogger(__name__)

NEIGHBOR_CANDIDATE_LIMIT = 10


def adjacent_conversation(uid: str, conversation: Any, conversation_id: Optional[str]) -> Optional[Neighbor]:
    """A kept conversation this one would have joined had capture not split it (fail-open)."""
    started_at, finished_at = conversation.started_at, conversation.finished_at
    if started_at is None or finished_at is None:
        return None
    try:
        rows = conversations_db.get_conversations_finished_after(
            uid,
            status='completed',
            finished_after=started_at - timedelta(seconds=DEFAULT_GAP_SECONDS),
            limit=NEIGHBOR_CANDIDATE_LIMIT,
        )
    except Exception as error:
        logger.warning('relevance neighbor lookup failed uid=%s: %s', uid, error)
        return None
    return find_neighbor(
        rows,
        conversation_id=conversation_id or getattr(conversation, 'id', None),
        started_at=started_at,
        finished_at=finished_at,
        gap_seconds=DEFAULT_GAP_SECONDS,
    )


def rules_only_relevance(
    uid: str,
    conversation: Any,
    trigger: ProcessingTrigger,
    user_kept: bool,
    calendar_retains: Callable[[], bool],
) -> RelevanceDecision:
    """The relevance step where the plan withholds the model (free-tier desktop).

    The rules cost nothing, so capture that stores without enrichment is still
    assessed; anything they cannot settle is kept. Any wake-word match skips the
    rules entirely, the conservative reading of the model path's trusted marker.
    """
    segments = list(getattr(conversation, 'transcript_segments', None) or [])
    return decide_relevance(
        trigger=trigger,
        texts=[segment.text for segment in segments],
        speech_seconds=None,
        has_photos=any((photo.description or '').strip() for photo in getattr(conversation, 'photos', None) or []),
        user_kept=user_kept,
        exempt=is_release_probe_uid(uid),
        trusted_wake_word=bool(find_wake_word_matches(segments)),
        model_discards=None,
        calendar_retains=calendar_retains,
    )


def record_decision(decision: RelevanceDecision) -> None:
    record_conversation_relevance(
        trigger=decision.trigger.value,
        verdict=decision.verdict,
        decided_by=decision.decided_by,
        reason=decision.reason,
    )


def apply_relevance(conversation: Any, payload: dict[str, Any], decision: RelevanceDecision) -> None:
    """Stamp a decision onto an in-memory conversation and its persist payload."""
    conversation.discarded = decision.discard
    payload['discarded'] = decision.discard
    payload[RELEVANCE_DECISION_FIELD] = decision.as_record()
    record_decision(decision)

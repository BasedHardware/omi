"""Replay-safe required effects for durable conversation finalization.

The durable ledger stores only these stable effect names. Conversation content
stays on the conversation row and is supplied to each effect at execution time.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, cast

import database.vector_db as vector_db
from models.conversation import Conversation
from utils.conversations.process_conversation import (
    TRANSCRIPT_CHUNK_INDEXING_ENABLED,
    save_structured_vector,
    save_transcript_chunk_vectors,
)
from utils.conversations.transcript_chunks import build_transcript_chunks

PLAN_VERSION = 2
REQUIRED_EFFECT_KEYS = ('structured_vector', 'transcript_vectors')
REQUIRED_ENRICHMENT_UNAVAILABLE_CODE = 'required_enrichment_vector_store_unavailable'


class RequiredEnrichmentUnavailable(RuntimeError):
    """A required finalization dependency is not available."""

    def __init__(self) -> None:
        super().__init__(REQUIRED_ENRICHMENT_UNAVAILABLE_CODE)


@dataclass(frozen=True)
class RequiredEnrichmentEffect:
    """One independently checkpointed finalization effect."""

    key: str
    execute: Callable[[], None]
    resource_count: int = 0


def _disabled_transcript_index() -> None:
    """Represent a disabled optional index as a completed no-op stage."""


def _require_vector_store() -> None:
    if vector_db.index is None:
        raise RequiredEnrichmentUnavailable()


def _save_structured_vector(
    uid: str,
    conversation: Conversation,
    require_vector_store: bool,
    finalization_vector_generation_id: str | None,
) -> None:
    if require_vector_store:
        _require_vector_store()
    save_structured_vector(uid, conversation, False, finalization_vector_generation_id)


def _save_transcript_vectors(
    uid: str,
    conversation: Conversation,
    require_vector_store: bool,
    finalization_vector_generation_id: str | None,
    expected_vector_count: int,
) -> None:
    if require_vector_store:
        _require_vector_store()
    if _transcript_vector_count(conversation) != expected_vector_count:
        raise RuntimeError('transcript_vector_plan_changed')
    save_transcript_chunk_vectors(uid, conversation, finalization_vector_generation_id)


def _transcript_vector_count(conversation: Conversation) -> int:
    segments = [segment.dict() if hasattr(segment, 'dict') else segment for segment in conversation.transcript_segments]
    chunks = build_transcript_chunks(
        cast(list[dict[str, Any]], segments),
        conversation.started_at or conversation.created_at,
    )
    return len(chunks)


def cleanup_required_enrichment(
    uid: str,
    conversation_id: str,
    *,
    finalization_vector_generation_id: str,
    transcript_vector_count: int,
    require_vector_store: bool,
) -> None:
    """Remove one exact vector generation after its source stops owning the job."""
    if vector_db.index is None:
        if require_vector_store:
            raise RequiredEnrichmentUnavailable()
        return
    vector_db.delete_finalization_enrichment_vectors(
        uid,
        conversation_id,
        finalization_vector_generation_id,
        transcript_vector_count,
    )


def required_enrichment_effects(
    uid: str,
    conversation: Conversation,
    *,
    finalization_vector_generation_id: str | None = None,
    require_vector_store: bool = True,
    transcript_vector_count: int | None = None,
) -> tuple[RequiredEnrichmentEffect, ...]:
    """Build the fixed v2 effect plan from already-persisted conversation data."""
    if transcript_vector_count is None:
        transcript_vector_count = _transcript_vector_count(conversation) if TRANSCRIPT_CHUNK_INDEXING_ENABLED else 0
    transcript_effect = (
        partial(
            _save_transcript_vectors,
            uid,
            conversation,
            require_vector_store,
            finalization_vector_generation_id,
            transcript_vector_count,
        )
        if transcript_vector_count
        else _disabled_transcript_index
    )
    return (
        RequiredEnrichmentEffect(
            'structured_vector',
            partial(
                _save_structured_vector,
                uid,
                conversation,
                require_vector_store,
                finalization_vector_generation_id,
            ),
            resource_count=1,
        ),
        RequiredEnrichmentEffect('transcript_vectors', transcript_effect, resource_count=transcript_vector_count),
    )

"""Product-analytics telemetry for transcript-conversation memory extraction.

Attempts the ``Conversation Memories Extracted`` PostHog event at most once after
a durable successful persistence result on the server-side transcript-memory path
(the path that previously wrote memories to the database but fired no analytics
event). Bounded dimensions only: a closed memory-count bucket and closed
``source``/``path`` enums. It never carries the conversation id, memory text,
transcript content, prompts, provider payloads, exception strings, or user
identifiers in the event properties — the analytics identity is the ``uid``,
passed as the PostHog ``distinct_id`` (mirrors ``utils/integration_telemetry``).

Emission contract (see ``process_conversation.extract_memories``):

* **Zero extraction** — the extraction paths return ``count == 0`` and no event
  is emitted (no false success).
* **Persistence failure** — emission runs only after the durable write returned
  successfully; a raised exception propagates and the event is skipped.
* **Retry / idempotency** — at most one analytics delivery attempt per
  ``(uid, conversation_id)`` across retries/re-finalization. The emit atomically
  creates a permanent Firestore marker under the authoritative conversation
  document; there is no cache TTL or eviction window. If that durable claim
  cannot be consulted, telemetry is skipped (fail closed) while extraction keeps
  running. ``conversation_id`` is used only for the internal marker path — it
  never appears in PostHog properties.

The event is intentionally distinct from the desktop ``Memory Extracted``
(proactive screen-context assistant) and from ``Memory Created`` (which is a
recording/conversation-session reconciliation proxy, not extracted memory).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict

from database.conversations import try_claim_conversation_memory_analytics
from models.conversation import ConversationSource
from utils.observability.fallback import record_fallback
from utils.product_telemetry import emit_product_event

logger = logging.getLogger(__name__)

CONVERSATION_MEMORIES_EXTRACTED = "Conversation Memories Extracted"

# Closed enums — source-faithful to the extraction paths in process_conversation.
SOURCE_TRANSCRIPTION = "transcription"
SOURCE_EXTERNAL_INTEGRATION = "external_integration"
_VALID_SOURCES = frozenset({SOURCE_TRANSCRIPTION, SOURCE_EXTERNAL_INTEGRATION})

PATH_CANONICAL = "canonical"
PATH_LEGACY = "legacy"
_VALID_PATHS = frozenset({PATH_CANONICAL, PATH_LEGACY})


@dataclass(frozen=True)
class ConversationMemoryExtractionResult:
    """Result of one transcript-conversation memory extraction pass.

    Returned by the extraction paths and emitted once at the public
    ``extract_memories`` boundary. ``count == 0`` means nothing was persisted
    (the path returned before any durable write) and no event is emitted;
    ``count > 0`` means persistence succeeded.
    """

    count: int
    source: str
    path: str


def source_for_conversation(conversation: Any) -> str:
    """Closed ``source`` dimension for an extraction, derived from the
    conversation's source. External-integration text extraction is a distinct
    input from transcript-segment extraction."""
    if getattr(conversation, "source", None) == ConversationSource.external_integration:
        return SOURCE_EXTERNAL_INTEGRATION
    return SOURCE_TRANSCRIPTION


def emit_conversation_memories_extracted(
    uid: str, conversation_id: str, result: ConversationMemoryExtractionResult, *, source_platform: str = 'unknown'
) -> None:
    """Attempt the event for one successful extraction, at most once per
    ``(uid, conversation_id)``. No-op when identity is empty, nothing was
    persisted, or a prior pass already claimed the delivery attempt."""
    if not uid or not conversation_id or result.count <= 0:
        return
    # Durable idempotency: atomically claim a permanent Firestore marker under
    # the conversation before capture. A retry/re-finalization finds that marker
    # and emits nothing, so it cannot inflate the metric. If the authoritative
    # store is unavailable, fail closed for this optional event: never capture a
    # success whose duplicate-safety cannot be verified. conversation_id remains
    # an internal marker path component and never reaches PostHog properties.
    try:
        acquired = try_claim_conversation_memory_analytics(uid, conversation_id)
    except Exception:  # noqa: BLE001 - telemetry must never break extraction
        record_fallback(
            component='memory_analytics',
            from_mode='durable_claim',
            to_mode='telemetry_skipped',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return
    if not acquired:
        return
    source = result.source if result.source in _VALID_SOURCES else SOURCE_TRANSCRIPTION
    path = result.path if result.path in _VALID_PATHS else PATH_LEGACY
    properties: Dict[str, Any] = {
        "memory_count_bucket": _bucket_memory_count(result.count),
        "source": source,
        "path": path,
        "source_platform": source_platform,
    }
    emit_product_event(uid=uid, event=CONVERSATION_MEMORIES_EXTRACTED, properties=properties)


def _bucket_memory_count(count: int) -> str:
    """Closed memory-count bucket so the raw count never reaches PostHog."""
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count == 2:
        return "2"
    if count == 3:
        return "3"
    if count <= 9:
        return "4_9"
    return "10_plus"

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

import importlib
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from database.conversations import try_claim_conversation_memory_analytics
from models.conversation import ConversationSource
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

CONVERSATION_MEMORIES_EXTRACTED = "Conversation Memories Extracted"

# Closed enums — source-faithful to the extraction paths in process_conversation.
SOURCE_TRANSCRIPTION = "transcription"
SOURCE_EXTERNAL_INTEGRATION = "external_integration"
_VALID_SOURCES = frozenset({SOURCE_TRANSCRIPTION, SOURCE_EXTERNAL_INTEGRATION})

PATH_CANONICAL = "canonical"
PATH_LEGACY = "legacy"
_VALID_PATHS = frozenset({PATH_CANONICAL, PATH_LEGACY})

_posthog_client: Optional[Any] = None
_posthog_disabled = False


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
    uid: str, conversation_id: str, result: ConversationMemoryExtractionResult
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
    }
    try:
        # Client construction belongs inside the fail-open boundary too: a
        # configured-but-broken SDK must never turn durable memory extraction
        # into a finalization failure.
        client = _get_posthog_client()
        if client is None:
            return
        client.capture(
            distinct_id=uid,
            event=CONVERSATION_MEMORIES_EXTRACTED,
            properties=properties,
        )
    except Exception:  # noqa: BLE001 - telemetry must never break extraction
        record_fallback(
            component='memory_analytics',
            from_mode='posthog_capture',
            to_mode='telemetry_skipped',
            reason='other',
            outcome='degraded',
            log=logger,
        )


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


def _get_posthog_client() -> Optional[Any]:
    """Lazy PostHog client. Disabled (and remembered) when no API key is set so
    the extraction hot path skips cheaply. Mirrors integration_telemetry."""
    global _posthog_client, _posthog_disabled
    if _posthog_disabled:
        return None
    if _posthog_client is not None:
        return _posthog_client

    api_key = os.getenv("POSTHOG_PROJECT_API_KEY") or os.getenv("POSTHOG_API_KEY")
    if not api_key:
        _posthog_disabled = True
        return None

    host = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
    try:
        posthog_module = importlib.import_module("posthog")
        posthog_client_cls = getattr(posthog_module, "Posthog")
        _posthog_client = posthog_client_cls(project_api_key=api_key, host=host)
    except Exception:  # noqa: BLE001 - fail open, never break extraction
        record_fallback(
            component='memory_analytics',
            from_mode='posthog_client',
            to_mode='telemetry_skipped',
            reason='config_incomplete',
            outcome='degraded',
            log=logger,
        )
        _posthog_disabled = True
        return None
    return _posthog_client


def set_posthog_client_for_tests(client: Optional[Any]) -> None:
    """Inject a fake PostHog client (or reset to prod behaviour) for unit tests."""
    global _posthog_client, _posthog_disabled
    _posthog_client = client
    _posthog_disabled = client is None

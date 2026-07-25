"""Product-analytics telemetry for transcript-conversation memory extraction.

Emits the ``Conversation Memories Extracted`` PostHog event exactly once after a
durable successful persistence result on the server-side transcript-memory path
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
* **Retry / idempotency** — exactly one event per successful
  ``extract_memories`` invocation. The canonical and legacy paths are both
  retraction-based (retract/delete then write deterministic memory ids), so a
  re-finalization re-processes the conversation and re-emits; the count always
  reflects the memories persisted in *this* pass, never a cached/stale value.

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

from models.conversation import ConversationSource

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


def emit_conversation_memories_extracted(uid: str, result: ConversationMemoryExtractionResult) -> None:
    """Emit the ``Conversation Memories Extracted`` event for one successful
    extraction pass. No-op when ``uid`` is empty or nothing was persisted."""
    if not uid or result.count <= 0:
        return
    source = result.source if result.source in _VALID_SOURCES else SOURCE_TRANSCRIPTION
    path = result.path if result.path in _VALID_PATHS else PATH_LEGACY
    properties: Dict[str, Any] = {
        "memory_count_bucket": _bucket_memory_count(result.count),
        "source": source,
        "path": path,
    }
    client = _get_posthog_client()
    if client is None:
        return
    try:
        client.capture(
            distinct_id=uid,
            event=CONVERSATION_MEMORIES_EXTRACTED,
            properties=properties,
        )
    except Exception as exc:  # noqa: BLE001 - telemetry must never break extraction
        logger.warning("conversation memory telemetry posthog_emit_failed error=%s", type(exc).__name__)


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
    except Exception as exc:  # noqa: BLE001 - fail open, never break extraction
        logger.warning("conversation memory telemetry posthog_import_failed error=%s", type(exc).__name__)
        _posthog_disabled = True
        return None

    _posthog_client = posthog_client_cls(project_api_key=api_key, host=host)
    return _posthog_client


def set_posthog_client_for_tests(client: Optional[Any]) -> None:
    """Inject a fake PostHog client (or reset to prod behaviour) for unit tests."""
    global _posthog_client, _posthog_disabled
    _posthog_client = client
    _posthog_disabled = client is None

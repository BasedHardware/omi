"""Shared custody admission and deferred delivery seams for enrichment workers."""

import asyncio
from typing import cast

from prometheus_client import REGISTRY, Counter

from models.conversation import Conversation

# Sync tests re-import admission while retaining the process-wide metrics registry.
TRANSCRIPT_DECODE_FAILURES = cast(
    Counter,
    getattr(REGISTRY, '_names_to_collectors', {}).get('omi_sync_finalization_transcript_decode_failure_total')
    or Counter(
        'omi_sync_finalization_transcript_decode_failure_total',
        'Sync finalization attempts stopped because the stored transcript could not be decoded',
    ),
)


def require_transcript_decoded(row: dict) -> None:
    if row.get('_recovery_transcript_decoded') is False:
        from utils.enrichment.outbox import TranscriptUnreadable

        TRANSCRIPT_DECODE_FAILURES.inc()
        raise TranscriptUnreadable('transcript_decode_failed')


class SyncConversationPersistenceFenced(RuntimeError):
    """Conversation lifecycle rejected this worker's stale processing result."""


def require_current_persistence(persisted: bool) -> None:
    """Turn a lifecycle fence into the worker's terminal supersession signal."""
    if not persisted:
        raise SyncConversationPersistenceFenced('sync conversation persistence fenced')


def run_created_webhook(uid: str, conversation: Conversation) -> None:
    """Load the webhook surface only in the post-processing worker that uses it."""
    from utils.webhooks import conversation_created_webhook

    asyncio.run(conversation_created_webhook(uid, conversation))


class ConversationAbsorbed(RuntimeError):
    """The durable redirect owns this content; no donor processing may continue."""

    def __init__(self, canonical_id: str):
        super().__init__('conversation_absorbed')
        self.canonical_id = canonical_id

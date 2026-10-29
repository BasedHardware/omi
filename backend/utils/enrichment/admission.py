"""Shared custody admission and deferred delivery seams for enrichment workers."""

import asyncio

from models.conversation import Conversation


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

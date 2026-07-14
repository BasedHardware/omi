"""Shared persisted-conversation finalizer for pusher and Cloud Tasks workers.

This is intentionally not callable from the listen WebSocket as a local
fallback.  Callers must first own a durable finalization job lease.
"""

from __future__ import annotations

import logging

from database import conversations as conversations_db
from database.redis_db import get_cached_user_geolocation
from models.conversation_enums import ConversationStatus
from models.geolocation import Geolocation
from utils.app_integrations import trigger_external_integrations
from utils.conversations.factory import deserialize_conversation
from utils.conversations.location import async_get_google_maps_location
from utils.conversations.process_conversation import process_conversation
from utils.conversations import lifecycle as lifecycle_service
from utils.executors import db_executor, postprocess_executor, run_blocking

logger = logging.getLogger(__name__)


class ConversationFinalizationError(RuntimeError):
    """A retryable persisted-conversation finalization failure."""


async def finalize_persisted_conversation(uid: str, conversation_id: str, language: str | None = None) -> None:
    """Finalize persisted data once the caller has acquired the job lease.

    The pusher WebSocket request already installs request-scoped BYOK context
    before calling this helper.  Cloud Tasks never does, so it cannot silently
    substitute platform credentials for a BYOK job.
    """
    conversation_data = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
    if not conversation_data:
        raise ConversationFinalizationError('conversation_not_found')

    conversation = deserialize_conversation(conversation_data)
    if conversation.status == ConversationStatus.completed:
        return
    if conversation.status != ConversationStatus.processing:
        admitted = await run_blocking(db_executor, lifecycle_service.ensure_processing, uid, conversation.id)
        if not admitted:
            return
        conversation.status = ConversationStatus.processing

    try:
        geolocation = await run_blocking(db_executor, get_cached_user_geolocation, uid)
        if geolocation:
            geolocation = Geolocation(**geolocation)
            conversation.geolocation = await async_get_google_maps_location(geolocation.latitude, geolocation.longitude)

        # The post-processing bulkhead preserves request context (including
        # validated live BYOK keys) while isolating this expensive sync path
        # from WebSocket and Cloud Tasks event loops.
        resolved_language = language or getattr(conversation, 'language', None) or 'en'
        conversation = await run_blocking(
            postprocess_executor, process_conversation, uid, resolved_language, conversation
        )
        await trigger_external_integrations(uid, conversation)
    except Exception as error:
        # Provider and validation exceptions can contain transcript excerpts.
        # The job stores and logs only a bounded failure code.
        logger.error(
            'persisted conversation finalization failed uid=%s conversation=%s failure=processing_failed',
            uid,
            conversation_id,
        )
        raise ConversationFinalizationError('processing_failed') from error

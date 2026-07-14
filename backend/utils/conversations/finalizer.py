"""Shared persisted-conversation finalizer for pusher and Cloud Tasks workers.

This is intentionally not callable from the listen WebSocket as a local
fallback.  Callers must first own a durable finalization job lease.
"""

from __future__ import annotations

import logging
from enum import Enum

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


class ConversationFinalizationDisposition(str, Enum):
    completed = 'completed'
    fenced = 'fenced'


async def finalize_persisted_conversation(
    uid: str,
    conversation_id: str,
    language: str | None = None,
    *,
    finalization_job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
) -> ConversationFinalizationDisposition:
    """Finalize persisted data once the caller has acquired the job lease.

    The pusher WebSocket request already installs request-scoped BYOK context
    before calling this helper.  Cloud Tasks never does, so it cannot silently
    substitute platform credentials for a BYOK job.
    """
    conversation_data = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
    if not conversation_data:
        # A deleted conversation is a successful no-fanout outcome. Retrying
        # its lease would only risk resurrecting a stale processor result.
        logger.info(
            'persisted conversation finalization fenced because row is missing uid=%s conversation=%s',
            uid,
            conversation_id,
        )
        return ConversationFinalizationDisposition.fenced

    conversation = deserialize_conversation(conversation_data)
    if conversation.status != ConversationStatus.completed and conversation.status != ConversationStatus.processing:
        admitted = await run_blocking(db_executor, lifecycle_service.ensure_processing, uid, conversation.id)
        if not admitted:
            return ConversationFinalizationDisposition.fenced
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
        if conversation.status != ConversationStatus.completed:
            conversation = await run_blocking(
                postprocess_executor, process_conversation, uid, resolved_language, conversation
            )
        # This is deliberately the only fanout admission read. The lifecycle
        # transaction re-reads the durable conversation together with the job
        # lease, so a discard or superseding generation cannot slip between a
        # stale pre-read and the integration side effect.
        fanout = await run_blocking(
            db_executor,
            lifecycle_service.claim_finalization_fanout,
            finalization_job_id,
            dispatch_generation,
            lease_epoch,
        )
        if fanout['status'] == 'claimed':
            await trigger_external_integrations(
                uid,
                conversation,
                idempotency_key=fanout['fanout_key'],
                require_delivery=True,
            )
            fanout_completed = await run_blocking(
                db_executor,
                lifecycle_service.complete_finalization_fanout,
                finalization_job_id,
                dispatch_generation,
                lease_epoch,
            )
            if not fanout_completed:
                raise ConversationFinalizationError('fanout_completion_conflict')
        elif fanout['status'] == 'fenced':
            logger.info(
                'persisted conversation finalization fenced before fanout uid=%s conversation=%s',
                uid,
                conversation_id,
            )
            return ConversationFinalizationDisposition.fenced
        elif fanout['status'] != 'completed':
            raise ConversationFinalizationError('fanout_lease_conflict')
        return ConversationFinalizationDisposition.completed
    except Exception as error:
        # Provider and validation exceptions can contain transcript excerpts.
        # The job stores and logs only a bounded failure code.
        logger.error(
            'persisted conversation finalization failed uid=%s conversation=%s failure=processing_failed',
            uid,
            conversation_id,
        )
        raise ConversationFinalizationError('processing_failed') from error

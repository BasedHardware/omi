"""Occasion attachment keeps source/device/meeting boundaries together."""

from typing import Optional

from models.conversation_enums import ConversationStatus
from models.conversation_continuity import resumable_continuation
from utils.conversations.process_conversation import retrieve_in_progress_conversation
from utils.transcribe_decisions import normalize_listen_source, should_attach_to_existing_in_progress
from routers.listen.boundary_poll import merge_permitted
import logging

logger = logging.getLogger(__name__)


async def occasion_attach_target(controller) -> Optional[str]:
    if not getattr(controller.host, 'occasion_mode', False) or controller.host.is_multi_channel:
        return None
    if controller.host.request.onboarding_mode and controller.host.onboarding_admitted:
        return None
    existing = await controller.host.persistence.call(retrieve_in_progress_conversation, controller.host.request.uid)
    if not existing or existing.get('status') not in (ConversationStatus.in_progress, 'in_progress'):
        return None
    source = getattr(existing.get('source'), 'value', existing.get('source'))
    if (
        any(existing.get(key) for key in ('deleted', 'discarded', 'is_locked'))
        or existing.get('client_device_id') != controller.host.client_device_context.client_device_id
        or not should_attach_to_existing_in_progress(
            existing_source=source if isinstance(source, str) else None, request_source=controller.host.request.source
        )
        or controller._occasion_span_exceeded(existing)
    ):
        return None
    if not await merge_permitted(controller, existing):
        return None
    existing = await controller._continuity_row(existing)
    if not resumable_continuation(
        existing,
        source=normalize_listen_source(controller.host.request.source),
        device_id=controller.host.client_device_context.client_device_id,
        now=controller.clock(),
        timeout=controller.host.conversation_creation_timeout,
    ):
        return None
    logger.info('event=occasion_attach conversation=%s', existing['id'])
    return str(existing['id'])

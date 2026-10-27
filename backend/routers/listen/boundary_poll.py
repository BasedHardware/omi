"""Bounded calendar discovery for meetings that start inside a long occasion."""

from config.occasion_conversations import EPISODE_BOUNDARIES_MODE_ENV
from config.refactor_modes import shadow_or_serve
from utils.episodes.boundaries import ingest_context, conversation_decision, merge_allowed

POLL_SECONDS = 60


async def poll_calendar(controller) -> None:
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return
    now = controller.clock()
    previous = getattr(controller, '_boundary_calendar_polled_at', None)
    if previous is not None and (now - previous).total_seconds() < POLL_SECONDS:
        return
    controller._boundary_calendar_polled_at = now
    # The existing two-minute lookup also records imminent events, so the
    # ordinary lifecycle tick observes their exact start/end without more reads.
    await controller._active_calendar_meeting()


async def ingest_calendar(controller, meeting):
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return
    await controller.host.persistence.call(ingest_context, controller.host.request.uid, meeting, allow_reschedule=True)


async def conversation_action(controller, row):
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return 'legacy'
    return await controller.host.persistence.call(
        conversation_decision, controller.host.request.uid, row, controller.clock()
    )


async def merge_permitted(controller, row):
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return True
    return await controller.host.persistence.call(
        merge_allowed, controller.host.request.uid, row, {'started_at': controller.clock()}
    )

"""Bounded calendar discovery for shared meeting evidence."""

from utils.episodes.boundaries import ingest_context

POLL_SECONDS = 60


async def poll_calendar(controller) -> None:
    now = controller.clock()
    previous = getattr(controller, '_boundary_calendar_polled_at', None)
    if previous is not None and (now - previous).total_seconds() < POLL_SECONDS:
        return
    controller._boundary_calendar_polled_at = now
    # The existing two-minute lookup also records imminent events for evidence consumers.
    await controller._active_calendar_meeting()


async def ingest_calendar(controller, meeting):
    await controller.host.persistence.call(ingest_context, controller.host.request.uid, meeting, allow_reschedule=True)

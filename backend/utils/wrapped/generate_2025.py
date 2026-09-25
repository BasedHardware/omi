import asyncio
import logging
from typing import Any

from .error_sanitizer import sanitize_error
from ..models import WrappedStatus  # hypothetical ORM model
from ..db import get_db_session  # DB session provider

logger = logging.getLogger(__name__)


async def _run_wrapped_generation(year: int, payload: dict[str, Any]) -> None:
    """
    Core background task that performs the Wrapped‑2025 generation.

    Any exception raised here is caught, sanitised and persisted to the
    `WrappedStatus` table so that the status endpoint can surface a safe
    error message.
    """
    try:
        # Placeholder for the real generation logic.
        # In production this would involve heavy I/O, external API calls, etc.
        await asyncio.sleep(0)  # simulate async work
        # ... actual generation code ...

        # Mark success in DB
        async with get_db_session() as session:
            await session.execute(
                WrappedStatus.update()
                .where(WrappedStatus.year == year)
                .values(status="completed", error=None)
            )
            await session.commit()
    except Exception as exc:  # pragma: no cover – exercised via tests
        safe_msg = sanitize_error(exc)
        logger.error("Wrapped generation failed for year %s: %s", year, safe_msg)

        # Persist the sanitized error message
        async with get_db_session() as session:
            await session.execute(
                WrappedStatus.update()
                .where(WrappedStatus.year == year)
                .values(status="failed", error=safe_msg)
            )
            await session.commit()


def generate_wrapped_2025(year: int, payload: dict[str, Any]) -> None:
    """
    Public entry‑point used by the API layer to kick‑off background generation.

    This function schedules `_run_wrapped_generation` on the event loop
    without awaiting it, so the request can return immediately.
    """
    loop = asyncio.get_event_loop()
    # Schedule the coroutine; any exception will be handled inside the task.
    loop.create_task(_run_wrapped_generation(year, payload))

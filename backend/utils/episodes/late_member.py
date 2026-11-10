"""Re-arm a composed closed episode when a member joins it late.

The settle job's own trigger is the member's finalize. A sync intake attach can
land after that finalize and be suppressed by the attach memo, so the closed
episode would keep notes that never saw this member. This reuses the composer's
evidence compare: it stamps ``compose_pending_since`` only when the member
actually changed the evidence, and the paid-once lease still dedupes.
"""

import logging
from typing import Any, Mapping, Optional

from config.episodes import episode_compose_late_attach_enabled

logger = logging.getLogger(__name__)


def schedule(
    uid: str,
    conversation_id: str,
    episode: Optional[Mapping[str, Any]],
    row: Mapping[str, Any],
    c: Any,
) -> None:
    """Fail-open; a live or uncomposed episode is left to its own close-time compose."""
    if not episode_compose_late_attach_enabled():
        return
    if not episode or episode.get('status') == 'live' or not episode.get('composed_at'):
        return
    from utils.episodes import composer

    try:
        composer.schedule_for_conversation(uid, conversation_id, collaborators=c, row=row)
    except Exception as error:
        logger.warning('event=episode_late_member_compose outcome=error exception_type=%s', type(error).__name__)

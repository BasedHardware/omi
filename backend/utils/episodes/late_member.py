"""Re-arm closed notes at attach, including when finalization is memoized.

Membership remains owned by the timeline transaction. This post-attach signal
only uses the existing composer; late episodes defer to open/grace recovery.
"""

import logging
from typing import Any, Mapping

from config.episodes import episode_compose_late_attach_enabled
from utils.episodes import composer, policy

logger = logging.getLogger(__name__)


def joined(uid: str, conversation_id: str, row: Mapping[str, Any], episode: Mapping[str, Any] | None, c: Any) -> None:
    """Fail-open: a live or uncomposed episode is left to its own close-time compose."""
    if not episode_compose_late_attach_enabled():
        return
    if not episode or policy.is_live(episode) or not episode.get('composed_at'):
        return
    try:
        composer.schedule_for_conversation(uid, conversation_id, collaborators=c, row=row)
    except Exception as error:
        logger.warning('event=episode_late_member_compose outcome=error exception_type=%s', type(error).__name__)

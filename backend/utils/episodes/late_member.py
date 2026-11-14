"""Re-arm closed notes at attach, including when finalization is memoized.

Membership remains owned by the timeline transaction. This post-attach signal
only uses the existing composer; late episodes defer to open/grace recovery.
"""

from typing import Any, Mapping

from config.episodes import episode_late_compose_enabled
from utils.episodes import composer, policy


def joined(uid: str, conversation_id: str, row: Mapping[str, Any], episode: Mapping[str, Any] | None, c: Any) -> None:
    if episode_late_compose_enabled() and episode and not policy.is_live(episode) and episode.get('composed_at'):
        composer.schedule_for_conversation(uid, conversation_id, collaborators=c, row=row)

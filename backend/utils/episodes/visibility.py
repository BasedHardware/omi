"""Read projection: hidden conversations cannot leave an empty episode row."""

from typing import Any, Optional

from database import conversations


def visible_episode(
    uid: str, episode: Optional[dict[str, Any]], *, firestore_client: Any = None
) -> Optional[dict[str, Any]]:
    if not episode or 'conversation_ids' not in episode:
        return episode
    for cid in episode.get('conversation_ids') or []:
        row = conversations.get_conversation_raw_snapshot(
            uid, cid, field_paths=['discarded', 'deleted', 'sync_merged_into'], firestore_client=firestore_client
        )
        # Missing metadata is not evidence of a discard.
        if row is None or not any(row.get(key) for key in ('discarded', 'deleted', 'sync_merged_into')):
            return episode
    return None

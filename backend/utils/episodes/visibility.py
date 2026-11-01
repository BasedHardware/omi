"""Read projection: hidden conversations cannot leave an empty episode row."""

from typing import Any, Optional

from database import conversations
from utils.conversations.fragment_visibility import is_relevance_discarded

VISIBILITY_FIELDS = [
    'discarded',
    'deleted',
    'sync_merged_into',
    'relevance_decision',
    'sync_relevance_user_kept',
    'has_photos',
    'photos',
    'user_title',
    'starred',
    'folder_user_set',
]


def hidden_member(row: dict[str, Any]) -> bool:
    return bool(row.get('deleted') or row.get('sync_merged_into') or is_relevance_discarded(row))


def hidden_conversation(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    row = conversations.get_conversation_raw_snapshot(
        uid,
        conversation_id,
        field_paths=VISIBILITY_FIELDS,
        firestore_client=firestore_client,
    )
    return bool(row and hidden_member(row))


def visible_episode(
    uid: str, episode: Optional[dict[str, Any]], *, firestore_client: Any = None
) -> Optional[dict[str, Any]]:
    if not episode or 'conversation_ids' not in episode:
        return episode
    for cid in episode.get('conversation_ids') or []:
        row = conversations.get_conversation_raw_snapshot(
            uid, cid, field_paths=VISIBILITY_FIELDS, firestore_client=firestore_client
        )
        # Missing metadata is not evidence of a discard.
        if row is None or not hidden_member(row):
            return episode
    return None

"""Account-data erasure across top-level batch stores and recursive user data."""

from collections.abc import Callable
import logging
from typing import Any

logger = logging.getLogger(__name__)


def purge_user_subtree(uid: str, client: Any, delete_collection: Callable) -> dict:
    # Top-level batch stores are outside users/{uid}; fence and purge them
    # before deleting the last references needed for retryable object erasure.
    from database.batch_pipeline_purge import purge_batch_owner

    purge_batch_owner(uid)
    user_ref = client.collection('users').document(uid)
    root_exists = user_ref.get().exists

    # Enumerate subcollections live even when the root document is missing.
    # Firestore permits immediate children to survive a parent deletion; an
    # early "User not found" return would falsely mark the deletion complete.
    # This picks up
    # everything the user has written (conversations, deleted_conversations, memories, action_items,
    # folders, goals, integrations, task_integrations, fcm_tokens, fair_use_*,
    # hourly_usage, meetings, screen_activity, files, people, chat_sessions,
    # messages, and any future additions).
    for sub in user_ref.collections():
        logger.info(f"Deleting subcollection {sub.id} for user {uid}")
        delete_collection(sub, client=client)

    if root_exists:
        logger.info(f"Deleting user document: {uid}")
        user_ref.delete()
    return {'status': 'ok', 'message': 'Account deleted successfully'}

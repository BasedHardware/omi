"""Account-data erasure across top-level batch stores and recursive user data."""

from collections.abc import Callable
import logging
from typing import Any

from database.quiet_check_retirement import stop_quiet_checks_for_account
from database._client import get_data_plane_firestore_client
from database.memory_collections import RELEASED_MEMORY_CHANGE_HEAD
from database.staged_promote_cache import invalidate_around_write
from config.list_projection import STATE_COLLECTION, ROW_COLLECTIONS

logger = logging.getLogger(__name__)


@invalidate_around_write
def purge_user_subtree(uid: str, client: Any, delete_collection: Callable) -> dict:
    # Top-level batch stores are outside users/{uid}; fence and purge them
    # before deleting the last references needed for retryable object erasure.
    from database.batch_pipeline_purge import purge_batch_owner

    purge_batch_owner(uid)
    # Membership is user data outside the recursive users/{uid} subtree, and it
    # lives in the customer data plane (which can differ from this compute
    # client's project). A failed delete must propagate so the account wipe
    # retries it.
    get_data_plane_firestore_client().collection('rollout_cohorts').document(uid).delete()
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
    # A historical-source-index bump or build (database/memories.py) can land
    # after memory_state was walked; the doc holds only hashes, but drop it too.
    user_ref.collection('memory_state').document('historical_source_index').delete()
    # Atomic source deletes also maintain this derived head. Erase it after
    # every source collection, including when memory_state was visited first.
    user_ref.collection('memory_state').document(RELEASED_MEMORY_CHANGE_HEAD).delete()
    # Source deletes can rotate these content-free heads after their collection
    # was walked, including a retry whose root user document is already absent.
    for family in ROW_COLLECTIONS:
        user_ref.collection(STATE_COLLECTION).document(family).delete()

    if root_exists:
        logger.info(f"Deleting user document: {uid}")
        user_ref.delete()
    stop_quiet_checks_for_account(uid, firestore_client=client)
    return {'status': 'ok', 'message': 'Account deleted successfully'}

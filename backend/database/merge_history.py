"""
Firestore database operations for conversation merge history.

Handles storage and retrieval of merge operations for rollback capability.
Collection path: users/{uid}/merge_history/{merge_id}

TTL: 24 hours from merge_time (configurable)
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from google.cloud import firestore
from ._client import db


def create_merge_history(uid: str, merge_history: Dict[str, Any]) -> None:
    """
    Store merge history snapshot in Firestore.

    Args:
        uid: User ID
        merge_history: MergeHistory dict (from MergeHistory.model_dump())

    Collection path:
        users/{uid}/merge_history/{merge_id}

    Example:
        merge_history = {
            'merge_id': 'abc-123',
            'uid': 'user-456',
            'merged_conversation_id': 'conv-789',
            'source_conversations': [...],  # Full snapshots
            'merge_time': datetime,
            'rollback_expiration': datetime,
            'rolled_back': False,
            ...
        }
    """
    merge_id = merge_history['merge_id']

    db.collection('users').document(uid) \
      .collection('merge_history').document(merge_id) \
      .set(merge_history)


def get_merge_history(uid: str, merge_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch merge history by ID.

    Args:
        uid: User ID
        merge_id: Merge operation ID

    Returns:
        MergeHistory dict if exists, None otherwise
    """
    doc = db.collection('users').document(uid) \
            .collection('merge_history').document(merge_id).get()

    return doc.to_dict() if doc.exists else None


def update_merge_history(uid: str, merge_id: str, updates: Dict[str, Any]) -> None:
    """
    Update merge history fields (typically for rollback tracking).

    Args:
        uid: User ID
        merge_id: Merge operation ID
        updates: Dict of fields to update

    Example:
        update_merge_history(uid, merge_id, {
            'rolled_back': True,
            'rollback_time': datetime.now(timezone.utc),
            'rollback_reason': 'User requested'
        })
    """
    db.collection('users').document(uid) \
      .collection('merge_history').document(merge_id) \
      .update(updates)


def get_merge_history_for_conversation(uid: str, conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Find merge history for a given merged conversation.

    Args:
        uid: User ID
        conversation_id: Merged conversation ID

    Returns:
        MergeHistory dict if found, None otherwise
    """
    docs = db.collection('users').document(uid) \
             .collection('merge_history') \
             .where('merged_conversation_id', '==', conversation_id) \
             .where('rolled_back', '==', False) \
             .limit(1).stream()

    for doc in docs:
        return doc.to_dict()

    return None


def get_recent_merge_history(
    uid: str,
    limit: int = 10,
    include_rolled_back: bool = False
) -> List[Dict[str, Any]]:
    """
    Get recent merge history entries for a user.

    Args:
        uid: User ID
        limit: Maximum number of results (default 10)
        include_rolled_back: Include rolled back merges (default False)

    Returns:
        List of MergeHistory dicts, sorted by merge_time desc
    """
    query = db.collection('users').document(uid) \
              .collection('merge_history') \
              .order_by('merge_time', direction=firestore.Query.DESCENDING) \
              .limit(limit)

    if not include_rolled_back:
        query = query.where('rolled_back', '==', False)

    docs = query.stream()
    return [doc.to_dict() for doc in docs]


def delete_expired_merge_history(uid: str, current_time: Optional[datetime] = None) -> int:
    """
    Delete expired merge history entries (past rollback_expiration).

    This can be run periodically as a cleanup task.

    Args:
        uid: User ID
        current_time: Current time (default: now UTC)

    Returns:
        Number of deleted entries
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    # Query expired entries
    expired_docs = db.collection('users').document(uid) \
                     .collection('merge_history') \
                     .where('rollback_expiration', '<', current_time) \
                     .stream()

    deleted_count = 0
    for doc in expired_docs:
        doc.reference.delete()
        deleted_count += 1

    return deleted_count


def check_rollback_available(uid: str, merge_id: str) -> tuple[bool, Optional[str]]:
    """
    Check if a merge can still be rolled back.

    Args:
        uid: User ID
        merge_id: Merge operation ID

    Returns:
        Tuple of (is_available, reason)
        - (True, None) if rollback available
        - (False, reason_string) if not available
    """
    merge_history = get_merge_history(uid, merge_id)

    if not merge_history:
        return (False, "Merge history not found")

    if merge_history.get('rolled_back', False):
        return (False, "Merge already rolled back")

    current_time = datetime.now(timezone.utc)
    expiration = merge_history.get('rollback_expiration')

    if expiration and current_time > expiration:
        return (False, f"Rollback window expired at {expiration}")

    return (True, None)

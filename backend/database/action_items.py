from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db


# Collection name
action_items_collection = 'action_items'


def _prepare_action_item_for_write(action_item_data: dict) -> dict:
    """Prepare action item data for writing to database"""
    # Ensure timestamps are properly formatted
    if 'created_at' in action_item_data and action_item_data['created_at']:
        if isinstance(action_item_data['created_at'], str):
            action_item_data['created_at'] = datetime.fromisoformat(
                action_item_data['created_at'].replace('Z', '+00:00')
            )

    if 'updated_at' in action_item_data and action_item_data['updated_at']:
        if isinstance(action_item_data['updated_at'], str):
            action_item_data['updated_at'] = datetime.fromisoformat(
                action_item_data['updated_at'].replace('Z', '+00:00')
            )

    if 'due_at' in action_item_data and action_item_data['due_at']:
        if isinstance(action_item_data['due_at'], str):
            action_item_data['due_at'] = datetime.fromisoformat(action_item_data['due_at'].replace('Z', '+00:00'))

    if 'completed_at' in action_item_data and action_item_data['completed_at']:
        if isinstance(action_item_data['completed_at'], str):
            action_item_data['completed_at'] = datetime.fromisoformat(
                action_item_data['completed_at'].replace('Z', '+00:00')
            )

    return action_item_data


def _prepare_action_item_for_read(action_item_data: dict) -> dict:
    """Prepare action item data for reading from database"""
    for field in ['created_at', 'updated_at', 'due_at', 'completed_at']:
        if field in action_item_data and action_item_data[field]:
            if hasattr(action_item_data[field], 'timestamp'):
                action_item_data[field] = datetime.fromtimestamp(action_item_data[field].timestamp(), tz=timezone.utc)
    return action_item_data


# *****************************
# ********** CREATE ***********
# *****************************


def create_action_item(uid: str, action_item_data: dict) -> str:
    """
    Create a new action item for a user.

    Args:
        uid: User ID
        action_item_data: Action item data including description, dates, etc.

    Returns:
        The ID of the created action item
    """
    action_item_data = _prepare_action_item_for_write(action_item_data)

    user_ref = db.collection('users').document(uid)
    action_items_ref = user_ref.collection(action_items_collection)

    if 'created_at' not in action_item_data:
        action_item_data['created_at'] = datetime.now(timezone.utc)
    if 'updated_at' not in action_item_data:
        action_item_data['updated_at'] = datetime.now(timezone.utc)

    # Set completed_at if the item is being created as completed
    if action_item_data.get('completed', False) and 'completed_at' not in action_item_data:
        action_item_data['completed_at'] = datetime.now(timezone.utc)

    doc_ref = action_items_ref.add(action_item_data)[1]

    return doc_ref.id


def create_action_items_batch(uid: str, action_items_data: List[dict]) -> List[str]:
    """
    Create multiple action items in a batch operation.

    Args:
        uid: User ID
        action_items_data: List of action item data dictionaries

    Returns:
        List of created action item IDs
    """
    if not action_items_data:
        return []

    user_ref = db.collection('users').document(uid)
    action_items_ref = user_ref.collection(action_items_collection)

    batch = db.batch()
    doc_refs = []

    for action_item_data in action_items_data:
        action_item_data = _prepare_action_item_for_write(action_item_data)

        if 'created_at' not in action_item_data:
            action_item_data['created_at'] = datetime.now(timezone.utc)
        if 'updated_at' not in action_item_data:
            action_item_data['updated_at'] = datetime.now(timezone.utc)

        # Set completed_at if the item is being created as completed
        if action_item_data.get('completed', False) and 'completed_at' not in action_item_data:
            action_item_data['completed_at'] = datetime.now(timezone.utc)

        doc_ref = action_items_ref.document()
        batch.set(doc_ref, action_item_data)
        doc_refs.append(doc_ref.id)

    # Commit batch
    batch.commit()

    return doc_refs


# *****************************
# ********** READ *************
# *****************************


def get_action_item(uid: str, action_item_id: str) -> Optional[dict]:
    """
    Get a single action item by ID.

    Args:
        uid: User ID
        action_item_id: Action item ID

    Returns:
        Action item data or None if not found
    """
    user_ref = db.collection('users').document(uid)
    action_item_ref = user_ref.collection(action_items_collection).document(action_item_id)
    doc = action_item_ref.get()

    if not doc.exists:
        return None

    data = doc.to_dict()
    data['id'] = doc.id
    return _prepare_action_item_for_read(data)


def get_action_items(
    uid: str,
    conversation_id: Optional[str] = None,
    completed: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[dict]:
    """
    Get action items for a user with optional filters.

    Args:
        uid: User ID
        conversation_id: Filter by conversation ID (None for standalone items)
        completed: Filter by completion status
        start_date: Filter by start date (inclusive)
        end_date: Filter by end date (inclusive)
        limit: Maximum number of items to return
        offset: Number of items to skip

    Returns:
        List of action items
    """
    user_ref = db.collection('users').document(uid)
    query = user_ref.collection(action_items_collection)

    # Apply filters
    if conversation_id is not None:
        query = query.where(filter=FieldFilter('conversation_id', '==', conversation_id))
    elif conversation_id is None and completed is None:
        pass

    if completed is not None:
        query = query.where(filter=FieldFilter('completed', '==', completed))

    # Order by created date
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING)

    # Apply pagination
    if offset > 0:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)

    # Execute query
    docs = query.stream()

    action_items = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        action_item = _prepare_action_item_for_read(data)

        # Apply date range filter in memory if needed
        if start_date is not None or end_date is not None:
            created_at = action_item.get('created_at')
            due_at = action_item.get('due_at')

            # Check if either created_at or due_at falls within the date range
            date_in_range = False

            if created_at is not None:
                if start_date is not None and created_at < start_date:
                    pass  # created_at is before start_date
                elif end_date is not None and created_at > end_date:
                    pass  # created_at is after end_date
                else:
                    date_in_range = True

            if not date_in_range and due_at is not None:
                if start_date is not None and due_at < start_date:
                    pass  # due_at is before start_date
                elif end_date is not None and due_at > end_date:
                    pass  # due_at is after end_date
                else:
                    date_in_range = True

            # If we have date filters but no dates fall in range, skip this item
            if not date_in_range:
                continue

        action_items.append(action_item)

    action_items.sort(
        key=lambda x: (
            x.get('due_at') is None,
            x.get('due_at') or datetime.max.replace(tzinfo=timezone.utc),
            -(x.get('created_at', datetime.min.replace(tzinfo=timezone.utc)).timestamp()),
        )
    )

    return action_items


def get_action_items_by_conversation(uid: str, conversation_id: str) -> List[dict]:
    """
    Get all action items for a specific conversation.

    Args:
        uid: User ID
        conversation_id: Conversation ID

    Returns:
        List of action items for the conversation
    """
    return get_action_items(uid, conversation_id=conversation_id)


# *****************************
# ********** UPDATE ***********
# *****************************


def update_action_item(uid: str, action_item_id: str, update_data: dict) -> bool:
    """
    Update an action item.

    Args:
        uid: User ID
        action_item_id: Action item ID
        update_data: Fields to update

    Returns:
        True if updated successfully, False otherwise
    """
    # Prepare data
    update_data = _prepare_action_item_for_write(update_data)

    user_ref = db.collection('users').document(uid)
    action_item_ref = user_ref.collection(action_items_collection).document(action_item_id)

    # Check if exists
    if not action_item_ref.get().exists:
        return False

    # Add updated timestamp
    update_data['updated_at'] = datetime.now(timezone.utc)

    # Update the document
    action_item_ref.update(update_data)

    return True


def mark_action_item_completed(uid: str, action_item_id: str, completed: bool = True) -> bool:
    """
    Mark an action item as completed or uncompleted.

    Args:
        uid: User ID
        action_item_id: Action item ID
        completed: Completion status

    Returns:
        True if updated successfully, False otherwise
    """
    update_data = {'completed': completed, 'completed_at': datetime.now(timezone.utc) if completed else None}
    return update_action_item(uid, action_item_id, update_data)


# *****************************
# ********** DELETE ***********
# *****************************


def delete_action_item(uid: str, action_item_id: str) -> bool:
    """
    Delete an action item.

    Args:
        uid: User ID
        action_item_id: Action item ID

    Returns:
        True if deleted successfully, False otherwise
    """
    user_ref = db.collection('users').document(uid)
    action_item_ref = user_ref.collection(action_items_collection).document(action_item_id)

    # Check if exists
    if not action_item_ref.get().exists:
        return False

    # Delete the document
    action_item_ref.delete()

    return True


def delete_action_items_for_conversation(uid: str, conversation_id: str) -> int:
    """
    Delete all action items for a specific conversation.

    Args:
        uid: User ID
        conversation_id: Conversation ID

    Returns:
        Number of deleted items
    """
    user_ref = db.collection('users').document(uid)
    query = user_ref.collection(action_items_collection).where(
        filter=FieldFilter('conversation_id', '==', conversation_id)
    )

    docs = query.stream()
    batch = db.batch()
    count = 0

    for doc in docs:
        batch.delete(doc.reference)
        count += 1

    if count > 0:
        batch.commit()

    return count


def unlock_all_action_items(uid: str):
    """
    Finds all action items for a user with is_locked: True and updates them to is_locked = False.
    """
    action_items_ref = db.collection('users').document(uid).collection(action_items_collection)
    locked_items_query = action_items_ref.where(filter=FieldFilter('is_locked', '==', True))

    batch = db.batch()
    docs = locked_items_query.stream()
    count = 0
    for doc in docs:
        batch.update(doc.reference, {'is_locked': False})
        count += 1
        if count >= 499:  # Firestore batch limit is 500
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()
    print(f"Unlocked all action items for user {uid}")

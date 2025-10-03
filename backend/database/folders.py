from datetime import datetime, timezone
from typing import List, Optional
import uuid
from google.cloud.firestore_v1 import FieldFilter
from ._client import db

folders_collection = 'folders'
conversations_collection = 'conversations'


def get_or_create_default_folder(uid: str) -> dict:
    """Get or create default folder for user"""
    user_ref = db.collection('users').document(uid)
    folders_ref = user_ref.collection(folders_collection)

    # Check for existing default folder
    default_folders = folders_ref.where(filter=FieldFilter('is_default', '==', True)).limit(1).stream()
    default_folder_docs = list(default_folders)

    if default_folder_docs:
        return default_folder_docs[0].to_dict()

    # Create default folder
    folder_id = str(uuid.uuid4())
    folder_data = {
        'id': folder_id,
        'name': 'General',
        'color': '#6B7280',
        'icon': 'folder',
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
        'order': 0,
        'is_default': True,
        'conversation_count': 0,
    }

    folders_ref.document(folder_id).set(folder_data)

    # Count conversations without folder_id (they belong to default) using aggregation
    conversations_ref = user_ref.collection(conversations_collection)

    # Total non-discarded conversations
    total_query = conversations_ref.where(filter=FieldFilter('discarded', '==', False))
    total_count = total_query.count().get()[0][0].value

    # Conversations assigned to folders (where folder_id field exists and has a value)
    assigned_query = conversations_ref.where(filter=FieldFilter('discarded', '==', False)).where(
        filter=FieldFilter('folder_id', '>', '')
    )
    assigned_count = assigned_query.count().get()[0][0].value

    # Default folder count = total - assigned
    unassigned_count = total_count - assigned_count

    folders_ref.document(folder_id).update({'conversation_count': unassigned_count})
    folder_data['conversation_count'] = unassigned_count

    return folder_data


def create_folder(uid: str, name: str, color: Optional[str] = None, icon: Optional[str] = None) -> dict:
    """Create a new folder"""
    user_ref = db.collection('users').document(uid)
    folders_ref = user_ref.collection(folders_collection)

    # Get max order
    existing_folders = folders_ref.order_by('order', direction='DESCENDING').limit(1).stream()
    max_order = 0
    for folder in existing_folders:
        max_order = folder.to_dict().get('order', 0)

    folder_id = str(uuid.uuid4())
    folder_data = {
        'id': folder_id,
        'name': name,
        'color': color or '#6B7280',  # allow users to pick color from frontend/UI
        'icon': icon or 'folder',  # allow users to pick icon from frontend/UI
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
        'order': max_order + 1,
        'is_default': False,
        'conversation_count': 0,
    }

    folders_ref.document(folder_id).set(folder_data)
    return folder_data


def get_folders(uid: str) -> List[dict]:
    """Get all folders for a user"""
    # Ensure default folder exists
    get_or_create_default_folder(uid)

    user_ref = db.collection('users').document(uid)
    folders_ref = user_ref.collection(folders_collection)

    folders = []
    for doc in folders_ref.order_by('order').stream():
        folder_data = doc.to_dict()
        folders.append(folder_data)

    return folders


def get_folder(uid: str, folder_id: str) -> Optional[dict]:
    """Get a specific folder"""
    user_ref = db.collection('users').document(uid)
    folder_ref = user_ref.collection(folders_collection).document(folder_id)
    folder_doc = folder_ref.get()

    if not folder_doc.exists:
        return None

    return folder_doc.to_dict()


def update_folder(uid: str, folder_id: str, update_data: dict) -> bool:
    """Update folder metadata"""
    user_ref = db.collection('users').document(uid)
    folder_ref = user_ref.collection(folders_collection).document(folder_id)

    # Prevent changing is_default flag
    if 'is_default' in update_data:
        del update_data['is_default']

    update_data['updated_at'] = datetime.now(timezone.utc)
    folder_ref.update(update_data)
    return True


def delete_folder(uid: str, folder_id: str, move_conversations_to_folder_id: Optional[str] = None) -> bool:
    """Delete a folder and move conversations to another folder"""
    user_ref = db.collection('users').document(uid)
    folder_ref = user_ref.collection(folders_collection).document(folder_id)

    # Check if it's default folder
    folder_data = folder_ref.get().to_dict()
    if folder_data and folder_data.get('is_default'):
        raise ValueError("Cannot delete default folder")

    # Get target folder (default if not specified)
    if move_conversations_to_folder_id is None:
        target_folder = get_or_create_default_folder(uid)
        move_conversations_to_folder_id = target_folder['id']

    # Move all conversations to target folder
    conversations_ref = user_ref.collection(conversations_collection)
    conversations_to_move = conversations_ref.where(filter=FieldFilter('folder_id', '==', folder_id)).stream()

    batch = db.batch()
    count = 0

    for conv_doc in conversations_to_move:
        batch.update(conv_doc.reference, {'folder_id': move_conversations_to_folder_id})
        count += 1

        if count >= 450:
            batch.commit()
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()

    # Update conversation counts
    update_folder_conversation_count(uid, move_conversations_to_folder_id)

    # Delete folder
    folder_ref.delete()

    return True


def move_conversation_to_folder(uid: str, conversation_id: str, folder_id: Optional[str]) -> bool:
    """Move a conversation to a folder"""
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)

    # Get current folder_id
    conv_data = conversation_ref.get().to_dict()
    if not conv_data:
        return False

    old_folder_id = conv_data.get('folder_id')

    # If folder_id is None, get default folder
    if folder_id is None:
        default_folder = get_or_create_default_folder(uid)
        folder_id = default_folder['id']

    # Update conversation
    conversation_ref.update({'folder_id': folder_id})

    # Update conversation counts
    if old_folder_id:
        update_folder_conversation_count(uid, old_folder_id)
    else:
        # It was in default folder
        default_folder = get_or_create_default_folder(uid)
        update_folder_conversation_count(uid, default_folder['id'])

    update_folder_conversation_count(uid, folder_id)

    return True


def update_folder_conversation_count(uid: str, folder_id: str):
    """Update the conversation count for a folder using Firestore aggregation"""
    user_ref = db.collection('users').document(uid)
    folder_ref = user_ref.collection(folders_collection).document(folder_id)

    folder_data = folder_ref.get().to_dict()
    if not folder_data:
        return

    conversations_ref = user_ref.collection(conversations_collection)

    # Count conversations in this folder using Firestore aggregation queries
    if folder_data.get('is_default'):
        # For default folder: total non-discarded - conversations in other folders
        total_query = conversations_ref.where(filter=FieldFilter('discarded', '==', False))
        total_count = total_query.count().get()[0][0].value

        # Conversations assigned to other folders (where folder_id field exists)
        assigned_query = conversations_ref.where(filter=FieldFilter('discarded', '==', False)).where(
            filter=FieldFilter('folder_id', '>', '')
        )
        assigned_count = assigned_query.count().get()[0][0].value

        count = total_count - assigned_count
    else:
        # For regular folders, count conversations with this folder_id
        query = conversations_ref.where(filter=FieldFilter('folder_id', '==', folder_id)).where(
            filter=FieldFilter('discarded', '==', False)
        )
        count = query.count().get()[0][0].value

    folder_ref.update({'conversation_count': count})


def get_conversations_in_folder(
    uid: str, folder_id: Optional[str], limit: int = 100, offset: int = 0, include_discarded: bool = False
) -> List[str]:
    """
    Get all conversation IDs in a folder.
    Returns list of conversation IDs to be fetched using conversations_db.get_conversations
    """
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection(conversations_collection)

    # Filter by folder
    if folder_id is None:
        # Get default folder
        default_folder = get_or_create_default_folder(uid)
        folder_id = default_folder['id']

    folder_data = get_folder(uid, folder_id)

    if folder_data and folder_data.get('is_default'):
        # For default folder, get conversations without folder_id or with default folder_id
        query = conversations_ref
        if not include_discarded:
            query = query.where(filter=FieldFilter('discarded', '==', False))

        query = query.order_by('created_at', direction='DESCENDING')

        all_conversations = list(query.stream())
        filtered_ids = []
        for doc in all_conversations:
            doc_data = doc.to_dict()
            if doc_data.get('folder_id') == folder_id or doc_data.get('folder_id') is None:
                filtered_ids.append(str(doc.id))

        return filtered_ids[offset : offset + limit]
    else:
        # Regular folder
        query = conversations_ref.where(filter=FieldFilter('folder_id', '==', folder_id))

        if not include_discarded:
            query = query.where(filter=FieldFilter('discarded', '==', False))

        query = query.order_by('created_at', direction='DESCENDING')
        query = query.limit(limit).offset(offset)

        return [str(doc.id) for doc in query.stream()]


def bulk_move_conversations_to_folder(uid: str, conversation_ids: List[str], folder_id: str) -> bool:
    """Move multiple conversations to a folder at once"""
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection(conversations_collection)

    # Ensure folder exists
    folder_data = get_folder(uid, folder_id)
    if not folder_data:
        return False

    # Track affected folders for count updates
    affected_folders = set()

    batch = db.batch()
    count = 0

    # Get all conversations to be moved
    for conversation_id in conversation_ids:
        conv_ref = conversations_ref.document(conversation_id)
        conv_data = conv_ref.get().to_dict()

        if conv_data:
            old_folder_id = conv_data.get('folder_id')
            if old_folder_id:
                affected_folders.add(old_folder_id)
            else:
                # Was in default folder
                default_folder = get_or_create_default_folder(uid)
                affected_folders.add(default_folder['id'])

            batch.update(conv_ref, {'folder_id': folder_id})
            count += 1

            if count >= 450:
                batch.commit()
                batch = db.batch()
                count = 0

    if count > 0:
        batch.commit()

    # Update all affected folder counts
    affected_folders.add(folder_id)
    for affected_folder_id in affected_folders:
        update_folder_conversation_count(uid, affected_folder_id)

    return True

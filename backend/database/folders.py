import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db
from models.folder import Folder


# System folders that are created for new users
SYSTEM_FOLDERS = [
    {
        'name': 'Work',
        'category_mapping': 'work',
        'icon': '💼',
        'color': '#3B82F6',
        'description': 'Work, business, professional, and career-related conversations',
    },
    {
        'name': 'Personal',
        'category_mapping': 'personal',
        'icon': '👤',
        'color': '#10B981',
        'description': 'Personal life, family, health, hobbies, and self-improvement',
    },
    {
        'name': 'Social',
        'category_mapping': 'social',
        'icon': '👥',
        'color': '#8B5CF6',
        'description': 'Friends, social gatherings, entertainment, and casual conversations',
    },
]

# Map all categories to one of the 3 system folders
CATEGORY_TO_FOLDER_MAPPING = {
    # Work folder - professional/business/career related
    'work': 'work',
    'business': 'work',
    'entrepreneurship': 'work',
    'technology': 'work',
    'finance': 'work',
    'economics': 'work',
    'legal': 'work',
    'education': 'work',  # Often career/learning related
    'science': 'work',
    'architecture': 'work',
    'design': 'work',
    # Personal folder - individual/self/family related
    'personal': 'personal',
    'health': 'personal',
    'family': 'personal',
    'parenting': 'personal',
    'romance': 'personal',
    'romantic': 'personal',
    'spiritual': 'personal',
    'inspiration': 'personal',
    'travel': 'personal',
    'sports': 'personal',
    'philosophy': 'personal',
    'psychology': 'personal',
    'literature': 'personal',
    'history': 'personal',
    # Social folder - friends/entertainment/casual related
    'social': 'social',
    'entertainment': 'social',
    'music': 'social',
    'politics': 'social',
    'news': 'social',
    'weather': 'social',
    'environment': 'social',
    'real': 'social',
    'other': 'personal',
}


def get_folders(uid: str) -> List[dict]:
    """Get all folders for a user, sorted by order."""
    user_ref = db.collection('users').document(uid)
    folders_ref = user_ref.collection('folders')

    folders = []
    for doc in folders_ref.order_by('order').stream():
        folder_data = doc.to_dict()
        folder_data['id'] = doc.id
        folders.append(folder_data)

    return folders


def get_folder(uid: str, folder_id: str) -> Optional[dict]:
    """Get a specific folder by ID."""
    user_ref = db.collection('users').document(uid)
    folder_doc = user_ref.collection('folders').document(folder_id).get()

    if folder_doc.exists:
        folder_data = folder_doc.to_dict()
        folder_data['id'] = folder_doc.id
        return folder_data

    return None


def create_folder(
    uid: str,
    name: str,
    description: Optional[str] = None,
    color: Optional[str] = None,
    icon: Optional[str] = None,
) -> dict:
    """Create a new custom folder for a user."""
    user_ref = db.collection('users').document(uid)
    folders_ref = user_ref.collection('folders')

    # Get the highest order number
    existing_folders = list(folders_ref.order_by('order', direction=firestore.Query.DESCENDING).limit(1).stream())
    max_order = existing_folders[0].to_dict().get('order', 0) if existing_folders else 0

    folder_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    folder_data = {
        'id': folder_id,
        'name': name,
        'description': description,
        'color': color or '#6B7280',
        'icon': icon or '📁',
        'created_at': now,
        'updated_at': now,
        'order': max_order + 1,
        'is_default': False,
        'is_system': False,
        'category_mapping': None,
        'conversation_count': 0,
    }

    folders_ref.document(folder_id).set(folder_data)
    return folder_data


def update_folder(uid: str, folder_id: str, update_data: dict) -> bool:
    """Update a folder's metadata."""
    user_ref = db.collection('users').document(uid)
    folder_ref = user_ref.collection('folders').document(folder_id)

    # Add updated_at timestamp
    update_data['updated_at'] = datetime.now(timezone.utc)

    folder_ref.update(update_data)
    return True


def delete_folder(uid: str, folder_id: str, move_to_folder_id: Optional[str] = None) -> bool:
    """
    Delete a folder and move its conversations to another folder.
    If move_to_folder_id is not provided, moves to the default 'Other' folder.
    """
    user_ref = db.collection('users').document(uid)
    folder_ref = user_ref.collection('folders').document(folder_id)

    # Find target folder
    target_folder_id = move_to_folder_id
    if not target_folder_id:
        # Find the default folder (usually 'Other')
        folders = get_folders(uid)
        default_folder = next((f for f in folders if f.get('is_default')), None)
        if default_folder:
            target_folder_id = default_folder['id']

    # Move all conversations from this folder to the target folder
    if target_folder_id:
        conversations_ref = user_ref.collection('conversations')
        conversations = conversations_ref.where(filter=FieldFilter('folder_id', '==', folder_id)).stream()

        batch = db.batch()
        count = 0
        for conv_doc in conversations:
            batch.update(conv_doc.reference, {'folder_id': target_folder_id})
            count += 1
            if count >= 450:
                batch.commit()
                batch = db.batch()
                count = 0

        if count > 0:
            batch.commit()

        # Update target folder count
        update_folder_conversation_count(uid, target_folder_id)

    # Delete the folder
    folder_ref.delete()
    return True


def reorder_folders(uid: str, folder_ids: List[str]) -> bool:
    """Reorder folders by providing an ordered list of folder IDs."""
    user_ref = db.collection('users').document(uid)
    folders_ref = user_ref.collection('folders')

    batch = db.batch()
    for i, folder_id in enumerate(folder_ids):
        folder_ref = folders_ref.document(folder_id)
        batch.update(folder_ref, {'order': i, 'updated_at': datetime.now(timezone.utc)})

    batch.commit()
    return True


def initialize_system_folders(uid: str) -> List[dict]:
    """
    Create system folders for a new user or user without folders.
    Returns the list of created folders.
    """
    user_ref = db.collection('users').document(uid)
    folders_ref = user_ref.collection('folders')

    # Check if already initialized
    existing = list(folders_ref.limit(1).stream())
    if existing:
        return get_folders(uid)

    created_folders = []
    now = datetime.now(timezone.utc)

    for i, folder_config in enumerate(SYSTEM_FOLDERS):
        folder_id = str(uuid.uuid4())
        folder_data = {
            'id': folder_id,
            'name': folder_config['name'],
            'description': folder_config['description'],
            'color': folder_config['color'],
            'icon': folder_config['icon'],
            'created_at': now,
            'updated_at': now,
            'order': i,
            'is_default': folder_config['category_mapping'] == 'other',
            'is_system': True,
            'category_mapping': folder_config['category_mapping'],
            'conversation_count': 0,
        }
        folders_ref.document(folder_id).set(folder_data)
        created_folders.append(folder_data)

    return created_folders


def get_conversations_in_folder(
    uid: str,
    folder_id: str,
    limit: int = 100,
    offset: int = 0,
    include_discarded: bool = False,
) -> List[dict]:
    """Get all conversations in a specific folder."""
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection('conversations')

    query = conversations_ref.where(filter=FieldFilter('folder_id', '==', folder_id))

    if not include_discarded:
        query = query.where(filter=FieldFilter('discarded', '==', False))

    query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
    query = query.offset(offset).limit(limit)

    conversations = []
    for doc in query.stream():
        conv_data = doc.to_dict()
        conv_data['id'] = doc.id
        conversations.append(conv_data)

    return conversations


def move_conversation_to_folder(
    uid: str,
    conversation_id: str,
    folder_id: Optional[str],
) -> bool:
    """Move a conversation to a different folder."""
    user_ref = db.collection('users').document(uid)
    conv_ref = user_ref.collection('conversations').document(conversation_id)

    # Get the old folder_id to update counts
    conv_doc = conv_ref.get()
    if not conv_doc.exists:
        return False

    old_folder_id = conv_doc.to_dict().get('folder_id')

    # Update the conversation's folder_id
    conv_ref.update({'folder_id': folder_id})

    # Update folder counts
    if old_folder_id:
        update_folder_conversation_count(uid, old_folder_id)
    if folder_id:
        update_folder_conversation_count(uid, folder_id)

    return True


def bulk_move_conversations_to_folder(
    uid: str,
    conversation_ids: List[str],
    folder_id: str,
) -> int:
    """Move multiple conversations to a folder. Returns count of moved conversations."""
    if not conversation_ids:
        return 0

    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection('conversations')

    conv_refs = [conversations_ref.document(conv_id) for conv_id in conversation_ids]
    conv_docs = db.get_all(conv_refs)

    affected_folders = set()
    batch = db.batch()
    count = 0
    moved = 0

    for conv_doc in conv_docs:
        if conv_doc is None or not conv_doc.exists:
            continue

        old_folder_id = conv_doc.to_dict().get('folder_id')
        if old_folder_id:
            affected_folders.add(old_folder_id)

        batch.update(conv_doc.reference, {'folder_id': folder_id})
        moved += 1
        count += 1

        if count >= 450:
            batch.commit()
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()

    affected_folders.add(folder_id)
    for fid in affected_folders:
        update_folder_conversation_count(uid, fid)

    return moved


def update_folder_conversation_count(uid: str, folder_id: str) -> int:
    """Update the conversation count for a folder."""
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection('conversations')

    query = conversations_ref.where(filter=FieldFilter('folder_id', '==', folder_id)).where(
        filter=FieldFilter('discarded', '==', False)
    )

    count_query = query.count()
    result = count_query.get()
    count = result[0][0].value

    folder_ref = user_ref.collection('folders').document(folder_id)
    folder_ref.update({'conversation_count': count})

    return count


def get_folder_by_category_mapping(uid: str, category_mapping: str) -> Optional[dict]:
    """Get a folder by its category_mapping value."""
    folders = get_folders(uid)
    return next((f for f in folders if f.get('category_mapping') == category_mapping), None)

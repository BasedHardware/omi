import copy
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from models.chat_convo import ConversationChatMessage
from utils import encryption
from ._client import db
from .helpers import set_data_protection_level, prepare_for_write, prepare_for_read


# *********************************
# ******* ENCRYPTION HELPERS ******
# *********************************


def _encrypt_conversation_chat_data(chat_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    """Encrypt conversation chat data for storage"""
    data = copy.deepcopy(chat_data)

    if 'text' in data and isinstance(data['text'], str):
        data['text'] = encryption.encrypt(data['text'], uid)
    return data


def _decrypt_conversation_chat_data(chat_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    """Decrypt conversation chat data for reading"""
    data = copy.deepcopy(chat_data)

    if 'text' in data and isinstance(data['text'], str):
        try:
            data['text'] = encryption.decrypt(data['text'], uid)
        except Exception:
            pass

    return data


def _prepare_data_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    """Prepare conversation chat data for writing with encryption if needed"""
    if level == 'enhanced':
        return _encrypt_conversation_chat_data(data, uid)
    return data


def _prepare_message_for_read(message_data: Optional[Dict[str, Any]], uid: str) -> Optional[Dict[str, Any]]:
    """Prepare conversation chat message for reading with decryption if needed"""
    if not message_data:
        return None

    level = message_data.get('data_protection_level')
    if level == 'enhanced':
        return _decrypt_conversation_chat_data(message_data, uid)

    return message_data


# *****************************
# ********** CRUD *************
# *****************************


@set_data_protection_level(data_arg_name='message_data')
@prepare_for_write(data_arg_name='message_data', prepare_func=_prepare_data_for_write)
def add_conversation_message(uid: str, message_data: dict):
    """Add a message to a conversation chat"""
    # Remove any computed fields that shouldn't be stored
    if 'conversation' in message_data:
        del message_data['conversation']

    user_ref = db.collection('users').document(uid)
    user_ref.collection('conversation_chats').add(message_data)
    return message_data


@prepare_for_read(decrypt_func=_prepare_message_for_read)
def get_conversation_messages(
    uid: str,
    conversation_id: str,
    limit: int = 100,
    offset: int = 0,
    include_references: bool = False,
) -> List[dict]:
    """Get all messages for a specific conversation chat"""
    print('get_conversation_messages', uid, conversation_id, limit, offset, include_references)

    user_ref = db.collection('users').document(uid)
    messages_ref = (
        user_ref.collection('conversation_chats')
        .where(filter=FieldFilter('conversation_id', '==', conversation_id))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(limit)
        .offset(offset)
    )

    messages = []
    memories_id = set()
    action_items_id = set()

    # Fetch messages and collect reference IDs
    for doc in messages_ref.stream():
        message = doc.to_dict()
        if message.get('reported') is True:
            continue
        messages.append(message)
        memories_id.update(message.get('memories_id', []))
        action_items_id.update(message.get('action_items_id', []))

    if not include_references:
        return messages

    # Fetch referenced memories and action items
    if memories_id:
        memories = get_conversation_memories(uid, conversation_id, list(memories_id))
        memories_dict = {memory['id']: memory for memory in memories}

        for message in messages:
            message['memories'] = [
                memories_dict[memory_id] for memory_id in message.get('memories_id', []) if memory_id in memories_dict
            ]

    if action_items_id:
        action_items = get_conversation_action_items(uid, conversation_id, list(action_items_id))
        action_items_dict = {item['id']: item for item in action_items}

        for message in messages:
            message['action_items'] = [
                action_items_dict[item_id]
                for item_id in message.get('action_items_id', [])
                if item_id in action_items_dict
            ]

    return messages


def get_conversation_message(uid: str, message_id: str) -> tuple[ConversationChatMessage, str] | None:
    """Get a specific conversation chat message by ID"""
    user_ref = db.collection('users').document(uid)
    message_ref = user_ref.collection('conversation_chats').where('id', '==', message_id).limit(1).stream()
    message_doc = next(message_ref, None)
    if not message_doc:
        return None

    message_data = message_doc.to_dict()
    if not message_data:
        return None

    decrypted_data = _prepare_message_for_read(message_data, uid)
    message = ConversationChatMessage(**decrypted_data)

    return message, message_doc.id


def report_conversation_message(uid: str, msg_doc_id: str):
    """Report a conversation chat message"""
    user_ref = db.collection('users').document(uid)
    message_ref = user_ref.collection('conversation_chats').document(msg_doc_id)
    try:
        message_ref.update({'reported': True})
        return {"message": "Message reported"}
    except Exception as e:
        print("Update failed:", e)
        return {"message": f"Update failed: {e}"}


def clear_conversation_chat(uid: str, conversation_id: str):
    """Clear all messages in a conversation chat"""
    try:
        user_ref = db.collection('users').document(uid)
        print(f"Deleting conversation chat messages for user: {uid}, conversation: {conversation_id}")
        if not user_ref.get().exists:
            return {"message": "User not found"}
        batch_delete_conversation_messages(user_ref, conversation_id)
        return None
    except Exception as e:
        return {"message": str(e)}


def batch_delete_conversation_messages(parent_doc_ref, conversation_id: str, batch_size=450):
    """Batch delete conversation chat messages"""
    messages_ref = parent_doc_ref.collection('conversation_chats').where(
        filter=FieldFilter('conversation_id', '==', conversation_id)
    )
    print('batch_delete_conversation_messages', conversation_id)

    while True:
        docs_stream = messages_ref.limit(batch_size).stream()
        docs_list = list(docs_stream)

        if not docs_list:
            print("No more conversation chat messages to delete")
            break

        batch = db.batch()
        for doc in docs_list:
            batch.delete(doc.reference)
        batch.commit()

        print(f'Deleted {len(docs_list)} conversation chat messages')

        if len(docs_list) < batch_size:
            print("Processed all conversation chat messages")
            break


def get_conversation_memories(uid: str, conversation_id: str, memory_ids: Optional[List[str]] = None) -> List[dict]:
    """Get memories associated with a conversation"""
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('memories')

    # Filter by conversation_id
    memories_ref = memories_ref.where(filter=FieldFilter('conversation_id', '==', conversation_id))

    # If specific memory IDs are requested, filter by those too
    if memory_ids:
        memories_ref = memories_ref.where(filter=FieldFilter('id', 'in', memory_ids))

    return [doc.to_dict() for doc in memories_ref.stream()]


def get_conversation_action_items(
    uid: str, conversation_id: str, action_item_ids: Optional[List[str]] = None
) -> List[dict]:
    """Get action items associated with a conversation"""
    user_ref = db.collection('users').document(uid)
    action_items_ref = user_ref.collection('action_items')

    # Filter by conversation_id
    action_items_ref = action_items_ref.where(filter=FieldFilter('conversation_id', '==', conversation_id))

    # If specific action item IDs are requested, filter by those too
    if action_item_ids:
        action_items_ref = action_items_ref.where(filter=FieldFilter('id', 'in', action_item_ids))

    return [doc.to_dict() for doc in action_items_ref.stream()]


def get_conversation_data(uid: str, conversation_id: str) -> dict:
    """Get the base conversation data"""
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection('conversations').document(conversation_id)
    conversation_doc = conversation_ref.get()

    if not conversation_doc.exists:
        return None

    return conversation_doc.to_dict()


# **************************************
# ********* MIGRATION HELPERS **********
# **************************************


def get_conversation_chats_to_migrate(uid: str, target_level: str) -> List[dict]:
    """Find all conversation chat messages that need protection level migration"""
    messages_ref = db.collection('users').document(uid).collection('conversation_chats')
    all_messages = messages_ref.select(['data_protection_level']).stream()

    to_migrate = []
    for doc in all_messages:
        doc_data = doc.to_dict()
        current_level = doc_data.get('data_protection_level', 'standard')
        if target_level != current_level:
            to_migrate.append({'id': doc.id, 'type': 'conversation_chat'})

    return to_migrate


def migrate_conversation_chats_level_batch(uid: str, message_doc_ids: List[str], target_level: str):
    """Migrate a batch of conversation chat messages to the target protection level"""
    batch = db.batch()
    messages_ref = db.collection('users').document(uid).collection('conversation_chats')
    doc_refs = [messages_ref.document(msg_id) for msg_id in message_doc_ids]
    doc_snapshots = db.get_all(doc_refs)

    for doc_snapshot in doc_snapshots:
        if not doc_snapshot.exists:
            print(f"Conversation chat message {doc_snapshot.id} not found, skipping.")
            continue

        message_data = doc_snapshot.to_dict()
        current_level = message_data.get('data_protection_level', 'standard')

        if current_level == target_level:
            continue

        plain_data = _prepare_message_for_read(message_data, uid)
        plain_text = plain_data.get('text')
        migrated_text = plain_text
        if target_level == 'enhanced':
            if isinstance(plain_text, str):
                migrated_text = encryption.encrypt(plain_text, uid)

        update_data = {'data_protection_level': target_level, 'text': migrated_text}
        batch.update(doc_snapshot.reference, update_data)

    batch.commit()

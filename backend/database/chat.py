import uuid
from datetime import datetime, timezone
from typing import Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from models.chat import Message
from utils.other.endpoints import timeit
from ._client import db


@timeit
def add_message(uid: str, message_data: dict):
    del message_data['memories']
    message_data['deleted'] = False
    user_ref = db.collection('users').document(uid)
    user_ref.collection('messages').add(message_data)
    return message_data


def add_plugin_message(text: str, plugin_id: str, uid: str, memory_id: Optional[str] = None) -> Message:
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        plugin_id=plugin_id,
        from_external_integration=False,
        type='text',
        memories_id=[memory_id] if memory_id else [],
    )
    add_message(uid, ai_message.dict())
    return ai_message


def add_summary_message(text: str, uid: str) -> Message:
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        plugin_id=None,
        from_external_integration=False,
        type='day_summary',
        memories_id=[],
    )
    add_message(uid, ai_message.dict())
    return ai_message


def get_plugin_messages(uid: str, plugin_id: str, limit: int = 20, offset: int = 0, include_memories: bool = False):
    user_ref = db.collection('users').document(uid)
    messages_ref = (
        user_ref.collection('messages')
        .where(filter=FieldFilter('plugin_id', '==', plugin_id))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(limit)
        .offset(offset)
    )
    messages = []
    memories_id = set()

    # Fetch messages and collect memory IDs
    for doc in messages_ref.stream():
        message = doc.to_dict()

        if message.get('deleted') is True:
            continue

        messages.append(message)
        memories_id.update(message.get('memories_id', []))

    if not include_memories:
        return messages

    # Fetch all memories at once
    memories = {}
    memories_ref = user_ref.collection('memories')
    doc_refs = [memories_ref.document(str(memory_id)) for memory_id in memories_id]
    docs = db.get_all(doc_refs)
    for doc in docs:
        if doc.exists:
            memory = doc.to_dict()
            memories[memory['id']] = memory

    # Attach memories to messages
    for message in messages:
        message['memories'] = [
            memories[memory_id] for memory_id in message.get('memories_id', []) if memory_id in memories
        ]

    return messages


@timeit
def get_messages(
        uid: str, limit: int = 20, offset: int = 0, include_memories: bool = False, plugin_id: Optional[str] = None,
        # include_plugin_id_filter: bool = True,
):
    print('get_messages', uid, limit, offset, plugin_id, include_memories)
    user_ref = db.collection('users').document(uid)
    messages_ref = (
        user_ref.collection('messages')
        .where(filter=FieldFilter('deleted', '==', False))
    )
    # if include_plugin_id_filter:
    messages_ref = messages_ref.where(filter=FieldFilter('plugin_id', '==', plugin_id))

    messages_ref = messages_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit).offset(offset)

    messages = []
    memories_id = set()

    # Fetch messages and collect memory IDs
    for doc in messages_ref.stream():
        message = doc.to_dict()
        # if message.get('deleted') is True:
        #     continue
        messages.append(message)
        memories_id.update(message.get('memories_id', []))

    if not include_memories:
        return messages

    # Fetch all memories at once
    memories = {}
    memories_ref = user_ref.collection('memories')
    doc_refs = [memories_ref.document(str(memory_id)) for memory_id in memories_id]
    docs = db.get_all(doc_refs)
    for doc in docs:
        if doc.exists:
            memory = doc.to_dict()
            memories[memory['id']] = memory

    # Attach memories to messages
    for message in messages:
        message['memories'] = [
            memories[memory_id] for memory_id in message.get('memories_id', []) if memory_id in memories
        ]

    return messages


def get_message(uid: str, message_id: str) -> tuple[Message, str] | None:
    user_ref = db.collection('users').document(uid)
    message_ref = user_ref.collection('messages').where('id', '==', message_id).limit(1).stream()
    message_doc = next(message_ref, None)
    message = Message(**message_doc.to_dict()) if message_doc else None

    if not message:
        return None

    if message.deleted is True:
        return None

    return message, message_doc.id


def report_message(uid: str, msg_doc_id: str):
    user_ref = db.collection('users').document(uid)
    message_ref = user_ref.collection('messages').document(msg_doc_id)
    try:
        message_ref.update({'deleted': True, 'reported': True})
        return {"message": "Message reported"}
    except Exception as e:
        print("Update failed:", e)
        return {"message": f"Update failed: {e}"}


def batch_delete_messages(parent_doc_ref, batch_size=450, plugin_id: Optional[str] = None):
    messages_ref = (
        parent_doc_ref.collection('messages')
        .where(filter=FieldFilter('deleted', '==', False))
    )
    messages_ref = messages_ref.where(filter=FieldFilter('plugin_id', '==', plugin_id))
    print('batch_delete_messages', plugin_id)
    last_doc = None  # For pagination

    while True:
        if last_doc:
            docs = messages_ref.limit(batch_size).start_after(last_doc).stream()
        else:
            docs = messages_ref.limit(batch_size).stream()

        docs_list = list(docs)

        if not docs_list:
            print("No more messages to delete")
            break

        batch = db.batch()

        for doc in docs_list:
            print('Deleting message:', doc.id)
            batch.update(doc.reference, {'deleted': True})

        batch.commit()

        if len(docs_list) < batch_size:
            print("Processed all messages")
            break

        last_doc = docs_list[-1]


def clear_chat(uid: str, plugin_id: Optional[str] = None):
    try:
        user_ref = db.collection('users').document(uid)
        print(f"Deleting messages for user: {uid}")
        if not user_ref.get().exists:
            return {"message": "User not found"}
        batch_delete_messages(user_ref, plugin_id=plugin_id)
        return None
    except Exception as e:
        return {"message": str(e)}

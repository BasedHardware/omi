import uuid
from datetime import datetime, timezone
from typing import Optional

from google.cloud import firestore

from models.chat import Message
from ._client import db


def add_message(uid: str, message_data: dict):
    del message_data['memories']
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


def get_messages(uid: str, limit: int = 20, offset: int = 0, include_memories: bool = False):
    user_ref = db.collection('users').document(uid)
    messages_ref = (
        user_ref.collection('messages')
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


def batch_delete_messages(parent_doc_ref, batch_size=450):
    messages_ref = parent_doc_ref.collection('messages')
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
            batch.update(doc.reference, {'deleted': True})

        batch.commit()

        if len(docs_list) < batch_size:
            print("Processed all messages")
            break

        last_doc = docs_list[-1]


def clear_chat(uid: str):
    try:
        user_ref = db.collection('users').document(uid)
        print(f"Deleting messages for user: {uid}")
        if not user_ref.get().exists:
            return {"message": "User not found"}
        batch_delete_messages(user_ref)
        return None
    except Exception as e:
        return {"message": str(e)}

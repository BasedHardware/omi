from google.cloud import firestore

from ._client import db


def add_message(uid: str, message_data: dict):
    user_ref = db.collection('users').document(uid)
    user_ref.collection('messages').add(message_data)
    return message_data


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

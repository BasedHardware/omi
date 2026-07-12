import copy
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, cast

from google.api_core.exceptions import AlreadyExists, Conflict, FailedPrecondition
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from models.chat import Message
from utils import encryption
from ._client import db
from .helpers import prepare_for_read, prepare_for_write, set_data_protection_level

logger = logging.getLogger(__name__)

BATCH_LIMIT = 500  # Firestore hard limit
DELETE_MESSAGES_BATCH_LIMIT = 200  # Leaves room for one session-counter write per deleted message.
DELETE_MESSAGES_CONFLICT_RETRIES = 3


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Typed adapter for a Firestore DocumentSnapshot.to_dict() result.

    Returns an empty dict when the document has no fields (None payload),
    so callers can safely mutate and read keys without Optional checks.
    """
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


# *********************************
# ******* ENCRYPTION HELPERS ******
# *********************************


def _encrypt_chat_data(chat_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    data = copy.deepcopy(chat_data)

    if 'text' in data and isinstance(data['text'], str):
        data['text'] = encryption.encrypt(data['text'], uid)
    return data


def _decrypt_chat_data(chat_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    data = copy.deepcopy(chat_data)

    if 'text' in data and isinstance(data['text'], str):
        try:
            data['text'] = encryption.decrypt(data['text'], uid)
        except Exception:
            pass

    return data


def _prepare_data_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    if level == 'enhanced':
        return _encrypt_chat_data(data, uid)
    return data


def _prepare_message_for_read(message_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    level = message_data.get('data_protection_level')
    if level == 'enhanced':
        return _decrypt_chat_data(message_data, uid)

    return message_data


# *****************************
# ********** CRUD *************
# *****************************


@set_data_protection_level(data_arg_name='message_data')
@prepare_for_write(data_arg_name='message_data', prepare_func=_prepare_data_for_write)
def add_message(uid: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
    del message_data['memories']
    user_ref = db.collection('users').document(uid)
    user_ref.collection('messages').add(message_data)
    return message_data


def add_app_message(text: str, app_id: str, uid: str, conversation_id: Optional[str] = None) -> Message:
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',  # type: ignore[reportArgumentType]  # pydantic accepts str for MessageSender enum
        app_id=app_id,
        from_external_integration=False,
        type='text',  # type: ignore[reportArgumentType]  # pydantic accepts str for MessageType enum
        memories_id=[conversation_id] if conversation_id else [],
    )
    add_message(uid, ai_message.model_dump())
    return ai_message


def add_integration_chat_message(text: str, app_id: Optional[str], uid: str) -> Message:
    """Add a chat message from an external integration (e.g. notification API),
    linking it to the user's existing chat session so it appears in the chat feed."""
    chat_session = get_chat_session(uid, app_id=app_id)
    chat_session_id = chat_session['id'] if chat_session else None

    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',  # type: ignore[reportArgumentType]  # pydantic accepts str for MessageSender enum
        app_id=app_id,
        from_external_integration=True,
        type='text',  # type: ignore[reportArgumentType]  # pydantic accepts str for MessageType enum
        chat_session_id=chat_session_id,
    )
    add_message(uid, ai_message.model_dump())
    if chat_session_id:
        add_message_to_chat_session(uid, chat_session_id, ai_message.id)
    return ai_message


def add_summary_message(text: str, uid: str) -> Message:
    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',  # type: ignore[reportArgumentType]  # pydantic accepts str for MessageSender enum
        app_id=None,
        from_external_integration=False,
        type='day_summary',  # type: ignore[reportArgumentType]  # pydantic accepts str for MessageType enum
        memories_id=[],
    )
    add_message(uid, ai_message.model_dump())
    return ai_message


@prepare_for_read(decrypt_func=_prepare_message_for_read)
def get_app_messages(
    uid: str, app_id: str, limit: int = 20, offset: int = 0, include_conversations: bool = False
) -> List[Dict[str, Any]]:
    user_ref = db.collection('users').document(uid)
    messages_ref = (
        user_ref.collection('messages')
        .where(filter=FieldFilter('plugin_id', '==', app_id))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(limit)
        .offset(offset)
    )
    messages: List[Dict[str, Any]] = []
    conversations_id: set[str] = set()

    # Fetch messages and collect conversation IDs
    for doc in messages_ref.stream():
        message: Dict[str, Any] = _typed_doc(doc)
        if message.get('reported') is True:
            continue
        messages.append(message)
        conversations_id.update(message.get('memories_id', []))

    if not include_conversations:
        return messages

    # Fetch all conversations at once
    conversations: Dict[str, Any] = {}
    conversations_ref = user_ref.collection('conversations')
    doc_refs = [conversations_ref.document(str(conversation_id)) for conversation_id in conversations_id]
    docs = db.get_all(doc_refs)
    for doc in docs:
        if doc.exists:
            conversation: Dict[str, Any] = _typed_doc(doc)
            conversations[conversation['id']] = conversation

    # Attach conversations to messages
    for message in messages:
        message['memories'] = [
            conversations[conversation_id]
            for conversation_id in message.get('memories_id', [])
            if conversation_id in conversations
        ]

    return messages


@prepare_for_read(decrypt_func=_prepare_message_for_read)
def get_messages(
    uid: str,
    limit: int = 20,
    offset: int = 0,
    include_conversations: bool = False,
    app_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    logger.info(f'get_messages {uid} {limit} {offset} {app_id} {include_conversations}')
    user_ref = db.collection('users').document(uid)
    messages_ref = user_ref.collection('messages')
    if chat_session_id:
        # Session-scoped query: filter by session only, skip plugin_id filter
        # because the session already determines which app the messages belong to.
        messages_ref = messages_ref.where(filter=FieldFilter('chat_session_id', '==', chat_session_id))
    else:
        # App-scoped query: filter by plugin_id (None = main chat)
        messages_ref = messages_ref.where(filter=FieldFilter('plugin_id', '==', app_id))

    messages_ref = messages_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit).offset(offset)

    messages: List[Dict[str, Any]] = []
    conversations_id: set[str] = set()
    files_id: set[str] = set()

    # Fetch messages and collect conversation IDs
    for doc in messages_ref.stream():
        message: Dict[str, Any] = _typed_doc(doc)
        if message.get('reported') is True:
            continue
        messages.append(message)
        conversations_id.update(message.get('memories_id', []))
        files_id.update(message.get('files_id', []))

    if not include_conversations:
        return messages

    # Fetch all conversations at once
    conversations: Dict[str, Any] = {}
    conversations_ref = user_ref.collection('conversations')
    doc_refs = [conversations_ref.document(str(conversation_id)) for conversation_id in conversations_id]
    docs = db.get_all(doc_refs)
    for doc in docs:
        if doc.exists:
            conversation: Dict[str, Any] = _typed_doc(doc)
            conversations[conversation['id']] = conversation

    # Attach conversations to messages
    for message in messages:
        message['memories'] = [
            conversations[conversation_id]
            for conversation_id in message.get('memories_id', [])
            if conversation_id in conversations
        ]

    # Fetch file chat
    files: Dict[str, Any] = {}
    files_ref = user_ref.collection('files')
    files_ref = [files_ref.document(str(file_id)) for file_id in files_id]
    doc_files = db.get_all(files_ref)
    for doc in doc_files:
        if doc.exists:
            file: Dict[str, Any] = _typed_doc(doc)
            files[file['id']] = file

    # Attach files to messages
    for message in messages:
        message['files'] = [files[file_id] for file_id in message.get('files_id', []) if file_id in files]

    return messages


def get_message_count(uid: str) -> int:
    """Return the number of chat messages visible to the user.

    Reported messages are hidden from every chat view (``get_messages`` and ``get_app_messages``
    skip ``reported == True``), so this stat excludes them too; otherwise it would exceed the number
    of messages the user can actually see anywhere. Uses count() aggregation (total minus the
    reported subset) rather than streaming every message. A ``reported == False`` count would be
    wrong because legacy messages may omit the field.
    """
    messages_ref = db.collection('users').document(uid).collection('messages')
    total_res = messages_ref.count().get()
    total = int(total_res[0][0].value) if total_res and total_res[0] else 0
    reported_res = messages_ref.where(filter=FieldFilter('reported', '==', True)).count().get()
    reported = int(reported_res[0][0].value) if reported_res and reported_res[0] else 0
    return max(0, total - reported)


def iter_all_messages(uid: str, batch_size: int = 1000) -> Iterator[Dict[str, Any]]:
    """Yield all chat messages for a user, decrypted, in batches. Used for streaming data export."""
    user_ref = db.collection('users').document(uid)
    msgs_ref = user_ref.collection('messages').order_by('created_at', direction=firestore.Query.DESCENDING)
    offset = 0
    while True:
        batch_ref = msgs_ref.limit(batch_size).offset(offset)
        batch: List[Dict[str, Any]] = []
        for doc in batch_ref.stream():
            msg: Dict[str, Any] = _typed_doc(doc)
            msg['id'] = doc.id
            msg = _prepare_message_for_read(msg, uid) or msg
            batch.append(msg)
        yield from batch
        if len(batch) < batch_size:
            break
        offset += batch_size


def get_message(uid: str, message_id: str) -> tuple[Message, str] | None:
    user_ref = db.collection('users').document(uid)
    message_ref = user_ref.collection('messages').where('id', '==', message_id).limit(1).stream()
    message_doc = next(message_ref, None)
    if not message_doc:
        return None

    message_data: Dict[str, Any] = _typed_doc(message_doc)
    if not message_data:
        return None

    decrypted_data: Dict[str, Any] = _prepare_message_for_read(message_data, uid)
    message = Message(**decrypted_data)

    return message, message_doc.id


def report_message(uid: str, msg_doc_id: str) -> Dict[str, str]:
    user_ref = db.collection('users').document(uid)
    message_ref = user_ref.collection('messages').document(msg_doc_id)
    try:
        message_ref.update({'reported': True})
        return {"message": "Message reported"}
    except Exception as e:
        logger.error(f"Update failed: {e}")
        return {"message": f"Update failed: {e}"}


def update_message_rating(uid: str, message_id: str, rating: Optional[int]) -> bool:
    """
    Update the rating on a message document.

    Args:
        uid: User ID
        message_id: Message ID (not doc ID)
        rating: Rating value (1 = thumbs up, -1 = thumbs down, None = no rating)
    """
    user_ref = db.collection('users').document(uid)
    message_ref = user_ref.collection('messages').where('id', '==', message_id).limit(1).stream()
    message_doc = next(message_ref, None)
    if not message_doc:
        logger.warning(f"⚠️ Message {message_id} not found for user {uid}")
        return False

    try:
        user_ref.collection('messages').document(message_doc.id).update({'rating': rating})
        logger.info(f"✅ Updated message {message_id} rating to {rating}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to update message rating: {e}")
        return False


def batch_delete_messages(
    parent_doc_ref: Any, batch_size: int = 450, app_id: Optional[str] = None, chat_session_id: Optional[str] = None
) -> None:
    messages_ref = parent_doc_ref.collection('messages')
    messages_ref = messages_ref.where(filter=FieldFilter('plugin_id', '==', app_id))
    if chat_session_id:
        messages_ref = messages_ref.where(filter=FieldFilter('chat_session_id', '==', chat_session_id))
    logger.info(f'batch_delete_messages {app_id}')

    while True:
        docs_stream = messages_ref.limit(batch_size).stream()
        docs_list: List[Any] = list(docs_stream)

        if not docs_list:
            logger.info("No more messages to delete")
            break

        batch = db.batch()
        for doc in docs_list:
            batch.delete(doc.reference)
        batch.commit()

        logger.info(f'Deleted {len(docs_list)} messages')

        if len(docs_list) < batch_size:
            logger.info("Processed all messages")
            break


def clear_chat(
    uid: str, app_id: Optional[str] = None, chat_session_id: Optional[str] = None
) -> Optional[Dict[str, str]]:
    try:
        user_ref = db.collection('users').document(uid)
        logger.info(f"Deleting messages for user: {uid}")
        if not user_ref.get().exists:
            return {"message": "User not found"}
        batch_delete_messages(user_ref, app_id=app_id, chat_session_id=chat_session_id)
        return None
    except Exception as e:
        return {"message": str(e)}


def add_multi_files(uid: str, files_data: List[Dict[str, Any]]) -> None:
    batch = db.batch()
    user_ref = db.collection('users').document(uid)

    for file_data in files_data:
        file_ref = user_ref.collection('files').document(file_data['id'])
        batch.set(file_ref, file_data)

    batch.commit()


def get_chat_files(uid: str, files_id: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    files_ref = db.collection('users').document(uid).collection('files')

    if files_id is None:
        files_id = []

    # If no specific files requested, return all
    if len(files_id) == 0:
        return [_typed_doc(doc) for doc in files_ref.stream()]

    # Firestore IN operator supports max 30 values, so chunk the queries
    if len(files_id) <= 30:
        files_ref = files_ref.where(filter=FieldFilter('id', 'in', files_id))
        return [_typed_doc(doc) for doc in files_ref.stream()]

    # Chunk into batches of 30
    results: List[Dict[str, Any]] = []
    for i in range(0, len(files_id), 30):
        chunk = files_id[i : i + 30]
        chunk_ref = db.collection('users').document(uid).collection('files')
        chunk_ref = chunk_ref.where(filter=FieldFilter('id', 'in', chunk))
        results.extend([_typed_doc(doc) for doc in chunk_ref.stream()])

    return results


def get_chat_files_desc(uid: str, files_id: Optional[List[str]] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Get the most recent chat files ordered by created_at descending, optionally filtered by file IDs"""
    files_ref = db.collection('users').document(uid).collection('files')

    if files_id is None:
        files_id = []

    # If no specific files requested, return most recent files
    if len(files_id) == 0:
        files_ref = files_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
        return [_typed_doc(doc) for doc in files_ref.stream()]

    # If specific files requested, filter by them first
    # Firestore IN operator supports max 30 values
    if len(files_id) <= 30:
        files_ref = files_ref.where(filter=FieldFilter('id', 'in', files_id))
        files_ref = files_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
        return [_typed_doc(doc) for doc in files_ref.stream()]

    # Chunk into batches of 30 if more than 30 files
    results: List[Dict[str, Any]] = []
    for i in range(0, len(files_id), 30):
        chunk = files_id[i : i + 30]
        chunk_ref = db.collection('users').document(uid).collection('files')
        chunk_ref = chunk_ref.where(filter=FieldFilter('id', 'in', chunk))
        chunk_ref = chunk_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
        results.extend([_typed_doc(doc) for doc in chunk_ref.stream()])

    # Sort all results by created_at and limit
    results.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
    return results[:limit]


def delete_multi_files(uid: str, files_data: List[Dict[str, Any]]) -> None:
    batch = db.batch()
    user_ref = db.collection('users').document(uid)

    for file_data in files_data:
        file_ref = user_ref.collection('files').document(file_data["id"])
        batch.delete(file_ref)

    batch.commit()


def add_chat_session(uid: str, chat_session_data: Dict[str, Any]) -> Dict[str, Any]:
    user_ref = db.collection('users').document(uid)
    user_ref.collection('chat_sessions').document(chat_session_data['id']).set(chat_session_data)
    return chat_session_data


def get_chat_session(uid: str, app_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    session_ref = (
        db.collection('users')
        .document(uid)
        .collection('chat_sessions')
        .where(filter=FieldFilter('plugin_id', '==', app_id))
        .limit(1)
    )

    sessions = session_ref.stream()
    for session in sessions:
        return _typed_doc(session)

    return None


def get_chat_session_by_id(uid: str, chat_session_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific chat session by its ID"""
    user_ref = db.collection('users').document(uid)
    session_ref = user_ref.collection('chat_sessions').document(chat_session_id)
    session_doc = session_ref.get()

    if session_doc.exists:
        data = session_doc.to_dict()
        data['id'] = chat_session_id
        return _normalize_chat_session(data)

    return None


def delete_chat_session(uid: str, chat_session_id: str, cascade_messages: bool = False) -> Optional[bool]:
    user_ref = db.collection('users').document(uid)
    session_ref = user_ref.collection('chat_sessions').document(chat_session_id)

    if cascade_messages:
        if not session_ref.get().exists:
            return False
        msg_col = user_ref.collection('messages')
        query = msg_col.where(filter=FieldFilter('chat_session_id', '==', chat_session_id))
        while True:
            docs: List[Any] = list(query.limit(BATCH_LIMIT).stream())
            if not docs:
                break
            batch = db.batch()
            for doc in docs:
                batch.delete(msg_col.document(doc.id))
            batch.commit()

    session_ref.delete()
    return None


def add_message_to_chat_session(uid: str, chat_session_id: str, message_id: str) -> None:
    user_ref = db.collection('users').document(uid)
    session_ref = user_ref.collection('chat_sessions').document(chat_session_id)
    session_ref.update({"message_ids": firestore.ArrayUnion([message_id])})


def add_files_to_chat_session(uid: str, chat_session_id: str, file_ids: List[str]) -> None:
    if not file_ids:
        return

    user_ref = db.collection('users').document(uid)
    session_ref = user_ref.collection('chat_sessions').document(chat_session_id)
    session_ref.update({"file_ids": firestore.ArrayUnion(file_ids)})


def update_chat_session_openai_ids(uid: str, chat_session_id: str, thread_id: str, assistant_id: str) -> None:
    """Update OpenAI thread and assistant IDs for a chat session"""
    user_ref = db.collection('users').document(uid)
    session_ref = user_ref.collection('chat_sessions').document(chat_session_id)

    update_data: Dict[str, str] = {}
    if thread_id:
        update_data['openai_thread_id'] = thread_id
    if assistant_id:
        update_data['openai_assistant_id'] = assistant_id

    if update_data:
        session_ref.update(update_data)
        logger.info(f"Updated session {chat_session_id} with thread {thread_id} and assistant {assistant_id}")


# **************************************
# ********* MIGRATION HELPERS **********
# **************************************


def get_chats_to_migrate(uid: str, target_level: str) -> List[Dict[str, Any]]:
    """
    Finds all chat messages that are not at the target protection level by fetching all documents
    and filtering them in memory. This simplifies the code but may be less performant for
    users with a very large number of documents.
    """
    messages_ref = db.collection('users').document(uid).collection('messages')
    all_messages = messages_ref.select(['data_protection_level']).stream()

    to_migrate: List[Dict[str, Any]] = []
    for doc in all_messages:
        doc_data: Dict[str, Any] = _typed_doc(doc)
        current_level = doc_data.get('data_protection_level', 'standard')
        if target_level != current_level:
            to_migrate.append({'id': doc.id, 'type': 'chat'})

    return to_migrate


def migrate_chats_level_batch(uid: str, message_doc_ids: List[str], target_level: str) -> None:
    """
    Migrates a batch of chat messages to the target protection level.
    """
    batch = db.batch()
    messages_ref = db.collection('users').document(uid).collection('messages')
    doc_refs = [messages_ref.document(msg_id) for msg_id in message_doc_ids]
    doc_snapshots = db.get_all(doc_refs)

    for doc_snapshot in doc_snapshots:
        if not doc_snapshot.exists:
            logger.warning(f"Message {doc_snapshot.id} not found, skipping.")
            continue

        message_data: Dict[str, Any] = _typed_doc(doc_snapshot)
        current_level = message_data.get('data_protection_level', 'standard')

        if current_level == target_level:
            continue

        plain_data: Dict[str, Any] = _prepare_message_for_read(message_data, uid)
        plain_text = plain_data.get('text')
        migrated_text = plain_text
        if target_level == 'enhanced':
            if isinstance(plain_text, str):
                migrated_text = encryption.encrypt(plain_text, uid)

        update_data: Dict[str, Any] = {'data_protection_level': target_level, 'text': migrated_text}
        batch.update(doc_snapshot.reference, update_data)

    batch.commit()


# ============================================================================
# CHAT SESSIONS (v2)
#
# v2 sessions support: title, preview, message_count, starred, updated_at.
# v1 sessions store: message_ids, file_ids, openai_thread_id.
# Both schemas coexist in the same Firestore collection.
# Both MUST write plugin_id alongside app_id for cross-platform query compat.
# ============================================================================


def _normalize_chat_session(data: Optional[dict]) -> Optional[dict]:
    """Guarantee a v2 chat-session dict satisfies ``ChatSessionResponse``.

    Firestore holds sessions written by several code paths (Python v2, the Rust
    desktop backend, legacy docs). Some rows are missing fields the response
    model requires (``title``, ``created_at``, ``message_count``, ``starred``),
    which makes FastAPI raise ``ResponseValidationError`` (HTTP 500). Fill safe
    defaults so listing/reading sessions never 500 on an incomplete doc.
    """
    if data is None:
        return None
    data.setdefault('title', 'New Chat')
    data.setdefault('preview', None)
    data.setdefault('message_count', 0)
    data.setdefault('starred', False)
    # created_at/updated_at are required datetimes; fall back to each other when
    # one is missing (the list query orders by updated_at, so it is present there).
    if data.get('created_at') is None:
        data['created_at'] = data.get('updated_at') or datetime.now(timezone.utc)
    if data.get('updated_at') is None:
        data['updated_at'] = data.get('created_at') or datetime.now(timezone.utc)
    return data


def create_chat_session(uid: str, title: Optional[str] = None, app_id: Optional[str] = None) -> Dict[str, Any]:
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
        'id': session_id,
        'title': title or 'New Chat',
        'preview': None,
        'created_at': now,
        'updated_at': now,
        'app_id': app_id,
        'plugin_id': app_id,  # Python chat.py queries chat_sessions by plugin_id
        'message_count': 0,
        'starred': False,
    }
    db.collection('users').document(uid).collection('chat_sessions').document(session_id).set(doc)
    return doc


def acquire_chat_session(uid: str, app_id: Optional[str] = None) -> str:
    """Get or create a chat session for the given app_id (None = main chat).

    Queries by plugin_id to match both Python chat.py and Rust backend behavior.
    For main chat (app_id=None), matches sessions where plugin_id is None.
    """
    col = db.collection('users').document(uid).collection('chat_sessions')
    query = col.where(filter=FieldFilter('plugin_id', '==', app_id)).limit(1)
    docs = list(query.stream())
    if docs:
        return docs[0].id
    session = create_chat_session(uid, app_id=app_id)
    return session['id']


def get_chat_sessions(
    uid: str,
    app_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    starred: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    col = db.collection('users').document(uid).collection('chat_sessions')
    # Order by updated_at — v2 sessions always have this field.
    # Legacy v1 sessions (missing updated_at) are excluded by Firestore,
    # which is correct since this endpoint serves v2 clients only.
    query = col.order_by('updated_at', direction=firestore.Query.DESCENDING)

    # Always filter — when app_id is None this returns only default-chat sessions
    query = query.where(filter=FieldFilter('plugin_id', '==', app_id))
    if starred is not None:
        query = query.where(filter=FieldFilter('starred', '==', starred))

    query = query.offset(offset).limit(limit)
    items: List[Dict[str, Any]] = []
    for doc in query.stream():
        data: Dict[str, Any] = _typed_doc(doc)
        data['id'] = doc.id
        normalized = _normalize_chat_session(data)
        if normalized is not None:
            items.append(normalized)
    return items


def update_chat_session(
    uid: str,
    session_id: str,
    title: Optional[str] = None,
    starred: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    ref = db.collection('users').document(uid).collection('chat_sessions').document(session_id)
    if not ref.get().exists:
        return None
    updates: Dict[str, Any] = {'updated_at': datetime.now(timezone.utc)}
    if title is not None:
        updates['title'] = title
    if starred is not None:
        updates['starred'] = starred
    ref.update(updates)
    result: Dict[str, Any] = _typed_doc(ref.get())
    result['id'] = session_id
    return _normalize_chat_session(result)


# ============================================================================
# MESSAGES (v2)
#
# Persistence-only message writes (no LLM streaming).  They write the same
# field set as the Message model for cross-platform compatibility:
#   plugin_id, app_id, type='text', chat_session_id, from_external_integration
#
# When session_id is not provided, acquire_chat_session() auto-creates one.
# ============================================================================


def save_message(
    uid: str,
    text: str,
    sender: str,
    app_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[str] = None,
    client_message_id: Optional[str] = None,
    message_source: str = 'desktop_chat',
) -> Dict[str, Any]:
    """Save a chat message for the desktop app.

    Writes all fields expected by chat.py's Message model so messages are
    visible across platforms.  Auto-acquires a session if none provided.
    """
    msg_id = client_message_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    message_ref = db.collection('users').document(uid).collection('messages').document(msg_id)
    if client_message_id:
        existing_message = message_ref.get()
        if existing_message.exists:
            existing: Dict[str, Any] = _typed_doc(existing_message)
            existing_created_at = existing.get('created_at')
            if existing_created_at is not None and hasattr(existing_created_at, 'isoformat'):
                existing_created_at = existing_created_at.isoformat()
            return {
                'id': msg_id,
                'created_at': existing_created_at or now.isoformat(),
                'session_id': existing.get('chat_session_id') or existing.get('session_id'),
                'created': False,
            }

    # Auto-acquire session (matches Rust backend behavior)
    if not session_id:
        session_id = acquire_chat_session(uid, app_id=app_id)

    doc: Dict[str, Any] = {
        'id': msg_id,
        'text': text,
        'created_at': now,
        'sender': sender,
        'type': 'text',  # Desktop messages are always type 'text'
        'app_id': app_id,
        'plugin_id': app_id,  # chat.py queries messages by plugin_id
        'session_id': session_id,
        'chat_session_id': session_id,  # chat.py uses this field name
        'from_external_integration': False,
        'rating': None,
        'reported': False,
        'memories_id': [],
        'metadata': metadata,
        'message_source': message_source,
    }
    created = True
    if client_message_id:
        try:
            message_ref.create(doc)
        except (AlreadyExists, Conflict):
            existing = _typed_doc(message_ref.get())
            existing_created_at = existing.get('created_at')
            if existing_created_at is not None and hasattr(existing_created_at, 'isoformat'):
                existing_created_at = existing_created_at.isoformat()
            return {
                'id': msg_id,
                'created_at': existing_created_at or now.isoformat(),
                'session_id': existing.get('chat_session_id') or existing.get('session_id'),
                'created': False,
            }
    else:
        message_ref.set(doc)

    # Update session message_count and preview (skip if session was deleted).
    # Retried client_message_id saves are idempotent and must not bump counters.
    if session_id and created:
        session_ref = db.collection('users').document(uid).collection('chat_sessions').document(session_id)
        if session_ref.get().exists:
            session_ref.update(
                {
                    'updated_at': now,
                    'message_count': firestore.Increment(1),
                    'preview': text[:100] if text else None,
                }
            )

    return {'id': msg_id, 'created_at': now.isoformat(), 'session_id': session_id, 'created': created}


def delete_messages(uid: str, app_id: Optional[str] = None, session_id: Optional[str] = None) -> int:
    """Delete messages and apply inverse session metadata updates atomically."""
    user_ref = db.collection('users').document(uid)
    col = user_ref.collection('messages')
    if session_id:
        # Session-scoped delete: filter by session only (same logic as get_messages)
        query = col.where(filter=FieldFilter('chat_session_id', '==', session_id))
    else:
        # App-scoped delete: filter by plugin_id (None = main chat)
        query = col.where(filter=FieldFilter('plugin_id', '==', app_id))

    deleted = 0
    consecutive_conflicts = 0
    while True:
        docs: List[Any] = list(query.limit(DELETE_MESSAGES_BATCH_LIMIT).stream())
        if not docs:
            break

        deleted_by_session: Dict[str, int] = {}
        deleted_message_ids_by_session: Dict[str, List[str]] = {}
        deleted_previews_by_session: Dict[str, set[str]] = {}
        for doc in docs:
            data = _typed_doc(doc)
            message_session_id = data.get('chat_session_id') or data.get('session_id')
            if isinstance(message_session_id, str) and message_session_id:
                deleted_by_session[message_session_id] = deleted_by_session.get(message_session_id, 0) + 1
                stored_message_id = data.get('id')
                deleted_message_ids_by_session.setdefault(message_session_id, []).append(
                    stored_message_id if isinstance(stored_message_id, str) and stored_message_id else doc.id
                )
                text = data.get('text')
                if isinstance(text, str) and text:
                    deleted_previews_by_session.setdefault(message_session_id, set()).add(text[:100])

        session_snapshots: Dict[str, Any] = {}
        for message_session_id in deleted_by_session:
            session_snapshots[message_session_id] = (
                user_ref.collection('chat_sessions').document(message_session_id).get()
            )

        batch = db.batch()
        for doc in docs:
            delete_option = db.write_option(last_update_time=doc.update_time)
            batch.delete(col.document(doc.id), option=delete_option)

        for message_session_id, deleted_from_session in deleted_by_session.items():
            session_snapshot = session_snapshots[message_session_id]
            if not session_snapshot.exists:
                continue
            session_data = _typed_doc(session_snapshot)
            stored_count = session_data.get('message_count')
            updates: Dict[str, Any] = {}
            if isinstance(session_data.get('message_ids'), list):
                updates['message_ids'] = firestore.ArrayRemove(deleted_message_ids_by_session[message_session_id])
            if isinstance(stored_count, int) and stored_count > 0:
                decrement = min(stored_count, deleted_from_session)
                updates['message_count'] = firestore.Increment(-decrement)
            current_preview = session_data.get('preview')
            if isinstance(current_preview, str) and current_preview in deleted_previews_by_session.get(
                message_session_id, set()
            ):
                updates['preview'] = None
            if not updates:
                continue
            session_ref = user_ref.collection('chat_sessions').document(message_session_id)
            option = db.write_option(last_update_time=session_snapshot.update_time)
            batch.update(session_ref, updates, option=option)

        try:
            batch.commit()
        except FailedPrecondition:
            # Another clear or a concurrent session mutation won the race.
            # The batch is atomic, so re-query before applying any decrement.
            consecutive_conflicts += 1
            if consecutive_conflicts >= DELETE_MESSAGES_CONFLICT_RETRIES:
                raise
            continue
        deleted += len(docs)
        consecutive_conflicts = 0

    return deleted

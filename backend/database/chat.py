import copy
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, cast

from models.chat import Message
from utils import encryption
from database.store import Filter, get_document_store
from database.store.errors import AlreadyExists
from database.store.sentinels import ArrayRemove, ArrayUnion, Increment
from .helpers import prepare_for_read, prepare_for_write, set_data_protection_level
from database.read_boundary import parse_snapshot_or_none


def _store():
    """The configured document store (``STORAGE_BACKEND`` seam, ADR-0002/0004). Tests patch this."""
    return get_document_store()


def _messages_path(uid: str) -> str:
    return f'users/{uid}/messages'


def _sessions_path(uid: str) -> str:
    return f'users/{uid}/chat_sessions'


def _files_path(uid: str) -> str:
    return f'users/{uid}/files'

logger = logging.getLogger(__name__)

BATCH_LIMIT = 500  # Firestore hard limit
DELETE_MESSAGES_BATCH_LIMIT = 200  # Leaves room for one session-counter write per deleted message.
CHAT_HISTORY_BASE_VISIBLE_MESSAGES = 10
CHAT_HISTORY_APPEND_EPOCH_MESSAGES = 8
# Maximum number of reported (hidden) rows to over-fetch per raw Firestore
# query when reading cache-aligned history. Keeps the raw read bounded even
# when a user has thousands of lifetime reported messages; the newest page
# rarely contains more reported rows than this cap.
CHAT_HISTORY_REPORTED_RAW_SCAN_CAP = 50


class ClientMessageIdPayloadConflict(ValueError):
    """The same client id was reused for a different immutable message."""


class MessageReconcileCursorError(ValueError):
    """A desktop journal cursor is absent or outside the authenticated scope."""


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
    # Firestore .add() stored messages under an auto-generated doc id (independent of the logical
    # message id); preserve that with a fresh doc id.
    _store().set(f'{_messages_path(uid)}/{str(uuid.uuid4())}', message_data)
    return message_data


def add_app_message(text: str, app_id: str, uid: str, conversation_id: Optional[str] = None) -> Message:
    """Add a chat message an app posted for the user, linking it to that app's chat session so it
    appears in the chat feed. get_messages filters by chat_session_id whenever a session exists, so
    a message stored without one is never returned on that path."""
    chat_session = get_chat_session(uid, app_id=app_id)
    chat_session_id = chat_session['id'] if chat_session else None

    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',  # type: ignore[reportArgumentType]  # pydantic accepts str for MessageSender enum
        app_id=app_id,
        from_external_integration=False,
        type='text',  # type: ignore[reportArgumentType]  # pydantic accepts str for MessageType enum
        memories_id=[conversation_id] if conversation_id else [],
        chat_session_id=chat_session_id,
    )
    add_message(uid, ai_message.model_dump())
    if chat_session_id:
        add_message_to_chat_session(uid, chat_session_id, ai_message.id)
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
    store = _store()
    messages: List[Dict[str, Any]] = []
    conversations_id: set[str] = set()

    # Fetch messages and collect conversation IDs
    for doc in store.query(
        _messages_path(uid), filters=[('plugin_id', '==', app_id)],
        order_by='created_at', direction='desc', limit=limit, offset=offset,
    ):
        message: Dict[str, Any] = _typed_doc(doc)
        if message.get('reported') is True:
            continue
        messages.append(message)
        conversations_id.update(message.get('memories_id', []))

    if not include_conversations:
        return messages

    # Fetch all conversations at once
    conversations: Dict[str, Any] = {}
    for doc in store.get_many(f'users/{uid}/conversations', [str(cid) for cid in conversations_id]):
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
    store = _store()
    if chat_session_id:
        # Session-scoped query: filter by session only, skip plugin_id filter
        # because the session already determines which app the messages belong to.
        message_filters: List[Filter] = [('chat_session_id', '==', chat_session_id)]
    else:
        # App-scoped query: filter by plugin_id (None = main chat)
        message_filters = [('plugin_id', '==', app_id)]

    messages: List[Dict[str, Any]] = []
    conversations_id: set[str] = set()
    files_id: set[str] = set()

    # Fetch messages and collect conversation IDs
    for doc in store.query(
        _messages_path(uid), filters=message_filters,
        order_by='created_at', direction='desc', limit=limit, offset=offset,
    ):
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
    for doc in store.get_many(f'users/{uid}/conversations', [str(cid) for cid in conversations_id]):
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
    for doc in store.get_many(_files_path(uid), [str(file_id) for file_id in files_id]):
        file: Dict[str, Any] = _typed_doc(doc)
        files[file['id']] = file

    # Attach files to messages
    for message in messages:
        message['files'] = [files[file_id] for file_id in message.get('files_id', []) if file_id in files]

    return messages


def cache_aligned_history_limit(total_visible_messages: int) -> int:
    """Return a bounded history size whose start moves only at epoch boundaries.

    A fixed newest-N window changes at the front on every chat turn, invalidating
    Anthropic's cumulative message-prefix cache. This policy keeps at least the
    existing ten-message continuity window and lets it grow append-only for eight
    messages before resetting to ten. The request therefore carries 10..17
    messages, never less history than before and never an unbounded transcript.
    """
    if total_visible_messages < 0:
        raise ValueError('total_visible_messages must be non-negative')
    if total_visible_messages <= CHAT_HISTORY_BASE_VISIBLE_MESSAGES:
        return total_visible_messages
    return CHAT_HISTORY_BASE_VISIBLE_MESSAGES + (
        (total_visible_messages - CHAT_HISTORY_BASE_VISIBLE_MESSAGES) % CHAT_HISTORY_APPEND_EPOCH_MESSAGES
    )


def get_cache_aligned_messages(
    uid: str,
    *,
    app_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read a cache-aligned, scope-safe chat history in newest-first order.

    Reported messages are excluded from the visible count and read. Over-fetching
    by the scoped reported count guarantees the target number of visible messages
    even when hidden records fall inside the selected raw Firestore page.
    """
    store = _store()
    scope_filters: List[Filter] = (
        [('chat_session_id', '==', chat_session_id)] if chat_session_id else [('plugin_id', '==', app_id)]
    )
    total = store.count(_messages_path(uid), filters=scope_filters)
    reported = store.count(_messages_path(uid), filters=scope_filters + [('reported', '==', True)])
    visible_total = max(0, total - reported)
    visible_limit = cache_aligned_history_limit(visible_total)
    if visible_limit == 0:
        return []

    # Cap the raw Firestore read so a large lifetime reported count cannot
    # cause unbounded document reads on every chat send. The over-fetch only
    # needs to cover reported rows that fall inside the newest raw page, not
    # the lifetime total.
    reported_overfetch = min(reported, CHAT_HISTORY_REPORTED_RAW_SCAN_CAP)
    raw_limit = min(total, visible_limit + reported_overfetch)
    return get_messages(
        uid,
        limit=raw_limit,
        app_id=app_id,
        chat_session_id=chat_session_id,
    )[:visible_limit]


@prepare_for_read(decrypt_func=_prepare_message_for_read)
def get_messages_reconcile_page(
    uid: str,
    *,
    limit: int,
    cursor_message_id: Optional[str] = None,
    app_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], Optional[str], bool]:
    """Return a stable, owner-scoped keyset page for the desktop journal.

    `get_messages` remains offset-compatible for existing clients. This path is
    deliberately separate: a Firestore document snapshot cursor cannot skip or
    duplicate rows when a newer message is inserted between page requests.
    Reported rows are scanned but not returned, with a bounded scan budget and a
    cursor over the last inspected document so filtering cannot stall progress.
    """
    if limit < 1 or limit > 100:
        raise ValueError('reconcile page limit must be between 1 and 100')

    store = _store()
    base_filters: List[Filter] = (
        [('chat_session_id', '==', chat_session_id)] if chat_session_id else [('plugin_id', '==', app_id)]
    )

    # Keyset cursor over (created_at, doc-id) via the port's tie-safe start_after (ADR-0018): a page
    # boundary never skips or duplicates rows that share a created_at.
    cursor: Optional[Dict[str, Any]] = None
    if cursor_message_id:
        cursor_doc = store.get(f'{_messages_path(uid)}/{cursor_message_id}')
        if not cursor_doc.exists:
            raise MessageReconcileCursorError('message cursor does not exist')
        cursor_payload = cursor_doc.to_dict() or {}
        cursor_in_scope = (
            cursor_payload.get('chat_session_id') == chat_session_id
            if chat_session_id
            else cursor_payload.get('plugin_id') == app_id
        )
        cursor_created_at = cursor_payload.get('created_at')
        if not cursor_in_scope or cursor_created_at is None:
            raise MessageReconcileCursorError('message cursor is outside the requested scope')
        cursor = {'value': cursor_created_at, 'id': cursor_message_id}

    # Four pages of reported rows may be traversed per request. The returned
    # cursor lets a caller resume if the bounded budget is exhausted.
    scan_budget = min(1000, max(100, limit * 4))
    scanned = 0
    messages: List[Dict[str, Any]] = []
    next_cursor = cursor_message_id
    has_more = False

    while scanned < scan_budget and len(messages) < limit:
        batch_limit = min(100, scan_budget - scanned)
        documents = store.query(
            _messages_path(uid), filters=base_filters, order_by='created_at', direction='desc',
            limit=batch_limit, start_after=cursor,
        )
        if not documents:
            has_more = False
            break

        reached_return_limit = False
        for document in documents:
            scanned += 1
            message = _typed_doc(document)
            cursor = {'value': message.get('created_at'), 'id': str(document.id)}
            next_cursor = str(document.id)
            if message.get('reported') is not True:
                messages.append(message)
                if len(messages) == limit:
                    reached_return_limit = True
                    break

        if reached_return_limit:
            # An extra empty page is harmless when the last returned row was the
            # collection tail; claiming continuation avoids a racey count query.
            has_more = True
            break
        if len(documents) < batch_limit:
            has_more = False
            break
        has_more = True

    if scanned >= scan_budget and len(messages) < limit:
        has_more = True
    if next_cursor == cursor_message_id and not messages:
        next_cursor = None
    return messages, next_cursor, has_more


def get_message_count(uid: str) -> int:
    """Return the number of chat messages visible to the user.

    Reported messages are hidden from every chat view (``get_messages`` and ``get_app_messages``
    skip ``reported == True``), so this stat excludes them too; otherwise it would exceed the number
    of messages the user can actually see anywhere. Uses count() aggregation (total minus the
    reported subset) rather than streaming every message. A ``reported == False`` count would be
    wrong because legacy messages may omit the field.
    """
    store = _store()
    total = store.count(_messages_path(uid))
    reported = store.count(_messages_path(uid), filters=[('reported', '==', True)])
    return max(0, total - reported)


def iter_all_messages(uid: str, batch_size: int = 1000) -> Iterator[Dict[str, Any]]:
    """Yield all chat messages for a user, decrypted, in batches. Used for streaming data export."""
    store = _store()
    offset = 0
    while True:
        docs = store.query(
            _messages_path(uid), order_by='created_at', direction='desc', limit=batch_size, offset=offset
        )
        batch: List[Dict[str, Any]] = []
        for doc in docs:
            msg: Dict[str, Any] = _typed_doc(doc)
            msg['id'] = doc.id
            msg = _prepare_message_for_read(msg, uid) or msg
            batch.append(msg)
        yield from batch
        if len(batch) < batch_size:
            break
        offset += batch_size


def get_message(uid: str, message_id: str) -> tuple[Message, str] | None:
    docs = _store().query(_messages_path(uid), filters=[('id', '==', message_id)], limit=1)
    if not docs:
        return None
    message_doc = docs[0]

    message = parse_snapshot_or_none(
        Message,
        message_doc,
        payload_from_snapshot=lambda snapshot: _prepare_message_for_read(_typed_doc(snapshot), uid),
    )
    if message is None:
        return None

    return message, message_doc.id


def report_message(uid: str, msg_doc_id: str) -> Dict[str, str]:
    try:
        _store().update(f'{_messages_path(uid)}/{msg_doc_id}', {'reported': True})
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
    store = _store()
    docs = store.query(_messages_path(uid), filters=[('id', '==', message_id)], limit=1)
    if not docs:
        logger.warning(f"⚠️ Message {message_id} not found for user {uid}")
        return False

    try:
        store.update(f'{_messages_path(uid)}/{docs[0].id}', {'rating': rating})
        logger.info(f"✅ Updated message {message_id} rating to {rating}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to update message rating: {e}")
        return False


def batch_delete_messages(
    uid: str, batch_size: int = 450, app_id: Optional[str] = None, chat_session_id: Optional[str] = None
) -> None:
    store = _store()
    filters: List[Filter] = [('plugin_id', '==', app_id)]
    if chat_session_id:
        filters.append(('chat_session_id', '==', chat_session_id))
    logger.info(f'batch_delete_messages {app_id}')

    while True:
        docs_list = store.query(_messages_path(uid), filters=filters, limit=batch_size)
        if not docs_list:
            logger.info("No more messages to delete")
            break

        batch = store.batch()
        for doc in docs_list:
            batch.delete(doc.path)
        batch.commit()

        logger.info(f'Deleted {len(docs_list)} messages')

        if len(docs_list) < batch_size:
            logger.info("Processed all messages")
            break


def clear_chat(
    uid: str, app_id: Optional[str] = None, chat_session_id: Optional[str] = None
) -> Optional[Dict[str, str]]:
    try:
        logger.info(f"Deleting messages for user: {uid}")
        if not _store().exists(f'users/{uid}'):
            return {"message": "User not found"}
        batch_delete_messages(uid, app_id=app_id, chat_session_id=chat_session_id)
        return None
    except Exception as e:
        return {"message": str(e)}


def add_multi_files(uid: str, files_data: List[Dict[str, Any]]) -> None:
    batch = _store().batch()
    for file_data in files_data:
        batch.set(f"{_files_path(uid)}/{file_data['id']}", file_data)
    batch.commit()


def get_chat_files(uid: str, files_id: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    store = _store()
    if files_id is None:
        files_id = []

    # If no specific files requested, return all
    if len(files_id) == 0:
        return [_typed_doc(doc) for doc in store.query(_files_path(uid))]

    # Firestore's IN operator caps at 30 values; chunk the queries (harmless on Mongo).
    results: List[Dict[str, Any]] = []
    for i in range(0, len(files_id), 30):
        chunk = files_id[i : i + 30]
        results.extend([_typed_doc(doc) for doc in store.query(_files_path(uid), filters=[('id', 'in', chunk)])])

    return results


def get_chat_files_desc(uid: str, files_id: Optional[List[str]] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Get the most recent chat files ordered by created_at descending, optionally filtered by file IDs"""
    store = _store()
    if files_id is None:
        files_id = []

    # If no specific files requested, return most recent files
    if len(files_id) == 0:
        return [
            _typed_doc(doc)
            for doc in store.query(_files_path(uid), order_by='created_at', direction='desc', limit=limit)
        ]

    # Firestore's IN operator caps at 30 values; chunk the queries (harmless on Mongo).
    results: List[Dict[str, Any]] = []
    for i in range(0, len(files_id), 30):
        chunk = files_id[i : i + 30]
        results.extend(
            _typed_doc(doc)
            for doc in store.query(
                _files_path(uid), filters=[('id', 'in', chunk)], order_by='created_at', direction='desc', limit=limit
            )
        )

    # Sort all results by created_at and limit. Use a tz-aware sentinel for a missing created_at so it
    # never TypeError-compares against the tz-aware Firestore datetimes and sinks to the bottom of the
    # descending sort (same class as the review-queue tz sentinel in #9571).
    results.sort(key=lambda x: x.get('created_at', datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return results[:limit]


def delete_multi_files(uid: str, files_data: List[Dict[str, Any]]) -> None:
    batch = _store().batch()
    for file_data in files_data:
        batch.delete(f"{_files_path(uid)}/{file_data['id']}")
    batch.commit()


def add_chat_session(uid: str, chat_session_data: Dict[str, Any]) -> Dict[str, Any]:
    _store().set(f"{_sessions_path(uid)}/{chat_session_data['id']}", chat_session_data)
    return chat_session_data


def get_chat_session(uid: str, app_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    docs = _store().query(_sessions_path(uid), filters=[('plugin_id', '==', app_id)], limit=1)
    return _typed_doc(docs[0]) if docs else None


def get_chat_session_by_id(uid: str, chat_session_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific chat session by its ID"""
    session_doc = _store().get(f'{_sessions_path(uid)}/{chat_session_id}')

    if session_doc.exists:
        data = session_doc.to_dict()
        data['id'] = chat_session_id
        return _normalize_chat_session(data)

    return None


def delete_chat_session(uid: str, chat_session_id: str, cascade_messages: bool = False) -> Optional[bool]:
    store = _store()
    session_path = f'{_sessions_path(uid)}/{chat_session_id}'

    if cascade_messages:
        if not store.exists(session_path):
            return False
        while True:
            docs = store.query(_messages_path(uid), filters=[('chat_session_id', '==', chat_session_id)], limit=BATCH_LIMIT)
            if not docs:
                break
            batch = store.batch()
            for doc in docs:
                batch.delete(doc.path)
            batch.commit()

    store.delete(session_path)
    return None


def add_message_to_chat_session(uid: str, chat_session_id: str, message_id: str) -> None:
    _store().update(f'{_sessions_path(uid)}/{chat_session_id}', {"message_ids": ArrayUnion([message_id])})


def add_files_to_chat_session(uid: str, chat_session_id: str, file_ids: List[str]) -> None:
    if not file_ids:
        return

    _store().update(f'{_sessions_path(uid)}/{chat_session_id}', {"file_ids": ArrayUnion(file_ids)})


def update_chat_session_openai_ids(uid: str, chat_session_id: str, thread_id: str, assistant_id: str) -> None:
    """Update OpenAI thread and assistant IDs for a chat session"""
    update_data: Dict[str, str] = {}
    if thread_id:
        update_data['openai_thread_id'] = thread_id
    if assistant_id:
        update_data['openai_assistant_id'] = assistant_id

    if update_data:
        _store().update(f'{_sessions_path(uid)}/{chat_session_id}', update_data)
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
    all_messages = _store().query(_messages_path(uid), fields=['data_protection_level'])

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
    store = _store()
    batch = store.batch()
    for doc_snapshot in store.get_many(_messages_path(uid), message_doc_ids):
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
        batch.update(doc_snapshot.path, update_data)

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
    _store().set(f'{_sessions_path(uid)}/{session_id}', doc)
    return doc


def acquire_chat_session(uid: str, app_id: Optional[str] = None) -> str:
    """Get or create a chat session for the given app_id (None = main chat).

    Queries by plugin_id to match both Python chat.py and Rust backend behavior.
    For main chat (app_id=None), matches sessions where plugin_id is None.
    """
    docs = _store().query(_sessions_path(uid), filters=[('plugin_id', '==', app_id)], limit=1)
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
    # Order by updated_at — v2 sessions always have this field. Legacy v1 sessions (missing
    # updated_at) are excluded, which is correct since this endpoint serves v2 clients only.
    # Always filter — when app_id is None this returns only default-chat sessions.
    filters: List[Filter] = [('plugin_id', '==', app_id)]
    if starred is not None:
        filters.append(('starred', '==', starred))

    items: List[Dict[str, Any]] = []
    for doc in _store().query(
        _sessions_path(uid), filters=filters, order_by='updated_at', direction='desc', offset=offset, limit=limit
    ):
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
    store = _store()
    path = f'{_sessions_path(uid)}/{session_id}'
    if not store.exists(path):
        return None
    updates: Dict[str, Any] = {'updated_at': datetime.now(timezone.utc)}
    if title is not None:
        updates['title'] = title
    if starred is not None:
        updates['starred'] = starred
    store.update(path, updates)
    result: Dict[str, Any] = _typed_doc(store.get(path))
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
    journal_revision: Optional[int] = None,
) -> Dict[str, Any]:
    """Save a chat message for the desktop app.

    Writes all fields expected by chat.py's Message model so messages are
    visible across platforms.  Auto-acquires a session if none provided.
    """
    msg_id = client_message_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    requested_session_id = session_id
    idempotency_payload_hash = _message_idempotency_payload_hash(
        text=text,
        sender=sender,
        app_id=app_id,
        session_id=requested_session_id,
        metadata=metadata,
        message_source=message_source,
    )

    store = _store()
    message_path = f'{_messages_path(uid)}/{msg_id}'
    if client_message_id:
        if store.exists(message_path):
            existing_result = _apply_existing_message_revision(
                message_path,
                text=text,
                sender=sender,
                app_id=app_id,
                session_id=requested_session_id,
                metadata=metadata,
                message_source=message_source,
                payload_hash=idempotency_payload_hash,
                journal_revision=journal_revision,
            )
            if existing_result is not None:
                return _message_revision_response(msg_id, existing_result, now)

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
    if client_message_id:
        doc['client_message_id'] = client_message_id
        doc['client_message_payload_hash'] = idempotency_payload_hash
        if journal_revision is not None:
            doc['journal_revision'] = journal_revision
    created = True
    if client_message_id:
        try:
            store.create(message_path, doc)
        except AlreadyExists:
            existing_result = _apply_existing_message_revision(
                message_path,
                text=text,
                sender=sender,
                app_id=app_id,
                session_id=requested_session_id,
                metadata=metadata,
                message_source=message_source,
                payload_hash=idempotency_payload_hash,
                journal_revision=journal_revision,
            )
            if existing_result is None:
                raise ClientMessageIdPayloadConflict('client_message_id disappeared during revision arbitration')
            return _message_revision_response(msg_id, existing_result, now)
    else:
        store.set(message_path, doc)

    # Update session message_count and preview (skip if session was deleted).
    # Retried client_message_id saves are idempotent and must not bump counters.
    if session_id and created:
        session_path = f'{_sessions_path(uid)}/{session_id}'
        if store.exists(session_path):
            store.update(
                session_path,
                {
                    'updated_at': now,
                    'message_count': Increment(1),
                    'preview': text[:100] if text else None,
                },
            )

    return {
        'id': msg_id,
        'created_at': now.isoformat(),
        'session_id': session_id,
        'created': created,
        'updated': False,
        'journal_revision': journal_revision,
    }


def _apply_existing_message_revision(
    message_path: str,
    *,
    text: str,
    sender: str,
    app_id: Optional[str],
    session_id: Optional[str],
    metadata: Optional[str],
    message_source: str,
    payload_hash: str,
    journal_revision: Optional[int],
) -> Optional[Dict[str, Any]]:
    """Atomically arbitrate an idempotent retry or monotonic journal enrichment."""

    def apply(write_transaction: Any) -> Optional[Dict[str, Any]]:
        snapshot = write_transaction.get(message_path)
        if not snapshot.exists:
            return None
        existing = _typed_doc(snapshot)
        _assert_message_identity(
            existing,
            sender=sender,
            app_id=app_id,
            session_id=session_id,
            message_source=message_source,
        )
        stored_revision = int(existing.get('journal_revision') or 1)
        if journal_revision is None:
            _assert_idempotent_message_payload(
                existing,
                text=text,
                sender=sender,
                app_id=app_id,
                session_id=session_id,
                metadata=metadata,
                message_source=message_source,
                payload_hash=payload_hash,
            )
            existing['_revision_updated'] = False
            existing['journal_revision'] = existing.get('journal_revision')
            return existing
        if journal_revision < stored_revision:
            existing['_revision_updated'] = False
            return existing
        if journal_revision == stored_revision:
            _assert_idempotent_message_payload(
                existing,
                text=text,
                sender=sender,
                app_id=app_id,
                session_id=session_id,
                metadata=metadata,
                message_source=message_source,
                payload_hash=payload_hash,
            )
            existing['_revision_updated'] = False
            return existing
        patch = {
            'text': text,
            'metadata': metadata,
            'client_message_payload_hash': payload_hash,
            'journal_revision': journal_revision,
        }
        write_transaction.update(message_path, patch)
        existing.update(patch)
        existing['_revision_updated'] = True
        return existing

    return _store().run_transaction(apply)


def _assert_message_identity(
    existing: Dict[str, Any],
    *,
    sender: str,
    app_id: Optional[str],
    session_id: Optional[str],
    message_source: str,
) -> None:
    mismatched = existing.get('sender') != sender
    mismatched = mismatched or existing.get('message_source', 'desktop_chat') != message_source
    existing_app_ids = [existing[field] for field in ('app_id', 'plugin_id') if field in existing] or [None]
    mismatched = mismatched or any(existing_app_id != app_id for existing_app_id in existing_app_ids)
    if session_id is not None:
        existing_session_ids = [
            existing[field] for field in ('chat_session_id', 'session_id') if field in existing
        ] or [None]
        mismatched = mismatched or any(
            existing_session_id != session_id for existing_session_id in existing_session_ids
        )
    if mismatched:
        raise ClientMessageIdPayloadConflict('client_message_id already exists with a different canonical identity')


def _message_revision_response(msg_id: str, existing: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    existing_created_at = existing.get('created_at')
    if existing_created_at is not None and hasattr(existing_created_at, 'isoformat'):
        existing_created_at = existing_created_at.isoformat()
    return {
        'id': msg_id,
        'created_at': existing_created_at or now.isoformat(),
        'session_id': existing.get('chat_session_id') or existing.get('session_id'),
        'created': False,
        'updated': bool(existing.get('_revision_updated')),
        'journal_revision': existing.get('journal_revision'),
    }


def _assert_idempotent_message_payload(
    existing: Dict[str, Any],
    *,
    text: str,
    sender: str,
    app_id: Optional[str],
    session_id: Optional[str],
    metadata: Optional[str],
    message_source: str,
    payload_hash: str,
) -> None:
    """Reject an idempotency-key collision without exposing message content."""
    existing_payload_hash = existing.get('client_message_payload_hash')
    if existing_payload_hash is not None:
        if existing_payload_hash != payload_hash:
            raise ClientMessageIdPayloadConflict('client_message_id already exists with a different payload')
        return

    # Legacy messages predate the request-payload fingerprint. Preserve retries
    # for them while validating every field whose original request value can be
    # reconstructed from the stored row. New writes always use the exact hash.
    mismatched = existing.get('text') != text or existing.get('sender') != sender
    mismatched = mismatched or existing.get('metadata') != metadata
    mismatched = mismatched or existing.get('message_source', 'desktop_chat') != message_source
    existing_app_ids = [existing[field] for field in ('app_id', 'plugin_id') if field in existing] or [None]
    mismatched = mismatched or any(existing_app_id != app_id for existing_app_id in existing_app_ids)
    if session_id is not None:
        existing_session_ids = [
            existing[field] for field in ('chat_session_id', 'session_id') if field in existing
        ] or [None]
        mismatched = mismatched or any(
            existing_session_id != session_id for existing_session_id in existing_session_ids
        )
    if mismatched:
        raise ClientMessageIdPayloadConflict('client_message_id already exists with a different payload')


def _message_idempotency_payload_hash(
    *,
    text: str,
    sender: str,
    app_id: Optional[str],
    session_id: Optional[str],
    metadata: Optional[str],
    message_source: str,
) -> str:
    """Return a stable digest of the caller-controlled immutable payload."""
    payload = {
        'app_id': app_id,
        'message_source': message_source,
        'metadata': metadata,
        'sender': sender,
        'session_id': session_id,
        'text': text,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return f'sha256:{hashlib.sha256(canonical.encode("utf-8")).hexdigest()}'


def delete_messages(uid: str, app_id: Optional[str] = None, session_id: Optional[str] = None) -> int:
    """Delete messages and apply inverse session metadata updates atomically.

    Each batch runs in a storage-port transaction: the session docs are read and updated together
    with the message deletes, so the counters stay consistent, and the transaction's contention
    retry replaces the Firestore ``last_update_time`` preconditions the raw path used (WP2, ADR-0002).
    """
    store = _store()
    filters: List[Filter] = (
        [('chat_session_id', '==', session_id)] if session_id else [('plugin_id', '==', app_id)]
    )

    deleted = 0
    while True:
        docs = store.query(_messages_path(uid), filters=filters, limit=DELETE_MESSAGES_BATCH_LIMIT)
        if not docs:
            break

        deleted_by_session: Dict[str, int] = {}
        deleted_message_ids_by_session: Dict[str, List[str]] = {}
        deleted_previews_by_session: Dict[str, set[str]] = {}
        message_paths: List[str] = []
        for doc in docs:
            message_paths.append(doc.path)
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

        def _apply(tx) -> None:
            # Reads first (transactions require all reads before writes on Firestore).
            session_data_by_id: Dict[str, Dict[str, Any]] = {}
            for message_session_id in deleted_by_session:
                snapshot = tx.get(f'{_sessions_path(uid)}/{message_session_id}')
                if snapshot.exists:
                    session_data_by_id[message_session_id] = snapshot.to_dict() or {}
            # Writes: delete the messages, then apply the inverse session-metadata updates.
            for path in message_paths:
                tx.delete(path)
            for message_session_id, deleted_from_session in deleted_by_session.items():
                session_data = session_data_by_id.get(message_session_id)
                if session_data is None:
                    continue
                stored_count = session_data.get('message_count')
                updates: Dict[str, Any] = {}
                if isinstance(session_data.get('message_ids'), list):
                    updates['message_ids'] = ArrayRemove(deleted_message_ids_by_session[message_session_id])
                if isinstance(stored_count, int) and stored_count > 0:
                    decrement = min(stored_count, deleted_from_session)
                    updates['message_count'] = Increment(-decrement)
                current_preview = session_data.get('preview')
                if isinstance(current_preview, str) and current_preview in deleted_previews_by_session.get(
                    message_session_id, set()
                ):
                    updates['preview'] = None
                if updates:
                    tx.update(f'{_sessions_path(uid)}/{message_session_id}', updates)

        store.run_transaction(_apply)
        deleted += len(docs)

    return deleted

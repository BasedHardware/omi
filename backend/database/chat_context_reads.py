"""Cache-aligned visibility window reader, shared by app and channel chat."""

from typing import Optional, List, Dict, Any
from google.cloud.firestore_v1 import FieldFilter
from database.chat_history_window import cache_aligned_history_limit


def get_cache_aligned_messages(
    uid: str,
    *,
    app_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read a cache-aligned, scope-safe chat history in newest-first order.

    Count the same visibility predicate as the page reader, preserving the
    append epoch when historical automatic rows are present. Provenance can be
    serialized JSON, so aggregates cannot express this exclusion: project only
    visibility fields, without loading message text or attachments.
    """
    from database import chat as chat_db

    user_ref = chat_db.db.collection('users').document(uid)
    scoped_ref = user_ref.collection('messages')
    if chat_session_id:
        scoped_ref = scoped_ref.where(filter=FieldFilter('chat_session_id', '==', chat_session_id))
    else:
        scoped_ref = scoped_ref.where(filter=FieldFilter('plugin_id', '==', app_id))

    visibility_fields = ['reported', 'sender', 'metadata', 'message_source', 'type', 'content_blocks']
    visible_total = 0
    for document in scoped_ref.select(visibility_fields).stream():
        message = chat_db._typed_doc(document)
        if message.get('reported') is not True and not chat_db.is_automatic_chat_message(message):
            visible_total += 1
    visible_limit = cache_aligned_history_limit(visible_total)
    if visible_limit == 0:
        return []

    return chat_db.get_messages(
        uid,
        limit=visible_limit,
        app_id=app_id,
        chat_session_id=chat_session_id,
    )

"""Cache-aligned visibility window reader, shared by app and channel chat."""

from typing import Optional, List, Dict, Any
from google.cloud.firestore_v1 import FieldFilter
from database.chat_history_window import cache_aligned_history_limit
from database.chat_context_prefetch import no_retry

ACTIVITY_READ_SECONDS = 1.0


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
        message = chat_db.typed_message_document(document)
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


def get_recent_activity(uid, since="", exclude_session=None):
    from database import chat as chat_db

    # A recent sample, never a paginated scan. Single-session users read at most
    # twenty metadata candidates and decrypt zero active-session messages.
    query = (
        chat_db.db.collection('users')
        .document(uid)
        .collection('messages')
        .order_by('created_at', direction='DESCENDING')
        .limit(20)
    )
    rows = []
    # This read now overlaps turn setup. The former 75ms RPC deadline was below
    # observed Firestore latency, independently of the outer coroutine deadline.
    for document in query.stream(timeout=ACTIVITY_READ_SECONDS, retry=no_retry()):
        row = document.to_dict() or {}
        if exclude_session is not None and row.get('chat_session_id') == exclude_session:
            continue
        if row.get('reported') is True or chat_db.is_automatic_chat_message(row):
            continue
        if since and row['created_at'].isoformat() <= since:
            continue
        rows.append(chat_db.decrypt_message_payload(row, uid))
    return sorted(rows, key=lambda r: (r['created_at'], r['id']))

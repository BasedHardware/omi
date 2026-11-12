"""Task membership reads against canonical action_items, never summary suggestions.

No new projection, counter, migration or task writer. Completed/manual tasks
count; deleted tasks and rejected Candidates do not. Callers own presentation.
"""

from typing import Any, Dict, List, Optional

from google.cloud.firestore_v1 import FieldFilter
from google.cloud import firestore

from database._client import get_firestore_client
from database.action_items_cache import (
    get_action_items_list_version,
    list_cache_key,
    read_cached_list,
    write_cached_list,
)
from database.conversations import document_data_with_revision, is_visible_conversation, prepare_conversation_for_read
from models.conversation import Conversation
from models.conversation_tasks import TaskConversationPageRequest
from utils.conversation_page_cursor import BookmarkDict, decode_cursor, encode_cursor
from utils.conversations import transcribing_hold
from utils.conversations.fragment_visibility import SETTLING_FIELDS
from utils.other.list_budget import ListReadBudget, budgeted_stream_iter


def linked_task_presence(
    uid: str, ids: List[str], *, budget: ListReadBudget, firestore_client: Any = None
) -> Dict[str, bool]:
    """Read only membership/deletion metadata, within the caller's deadline."""
    if not ids:
        return {}
    ids = sorted(set(ids))
    if len(ids) > 100:
        raise ValueError('task presence batch exceeds 100 conversations')
    version = get_action_items_list_version(uid)
    key = None if version is None else list_cache_key(uid, version, {'conversation-task-presence-v1': ids})
    cached = read_cached_list(key) if key else None
    if cached and isinstance(cached.get('body'), dict):
        body = cached['body']
        if set(body) == set(ids) and all(type(value) is bool for value in body.values()):
            budget.check()
            return body
    client = firestore_client or get_firestore_client()
    result = dict.fromkeys(ids, False)
    for offset in range(0, len(ids), 30):
        batch = ids[offset : offset + 30]
        query = (
            client.collection('users')
            .document(uid)
            .collection('action_items')
            .where(filter=FieldFilter('conversation_id', 'in', batch))
            .select(['conversation_id', 'deleted'])
            .order_by('__name__')
        )
        cursor = None
        while not all(result[cid] for cid in batch):
            page_query = query.limit(100)
            if cursor is not None:
                page_query = page_query.start_after(cursor)
            page = list(budgeted_stream_iter(page_query, budget))
            for snapshot in page:
                data = snapshot.to_dict() or {}
                cid = data.get('conversation_id')
                if cid in result and not data.get('deleted'):
                    result[cid] = True
            if len(page) < 100:
                break
            cursor = page[-1]
    budget.check()
    if key and get_action_items_list_version(uid) == version:
        write_cached_list(key, body=result, etag='', ttl=15)
    return result


def visible_task_presence(
    uid: str, ids: List[str], *, budget: ListReadBudget, firestore_client: Any = None
) -> Dict[str, bool]:
    """Unknown, foreign, deleted and locked parents never disclose task presence."""
    client = firestore_client or get_firestore_client()
    collection = client.collection('users').document(uid).collection('conversations')
    result = dict.fromkeys(ids, False)
    refs = [collection.document(cid) for cid in ids]
    budget.check()
    eligible = []
    for snapshot in client.get_all(
        refs, field_paths=['is_locked', 'deleted'], timeout=budget.rpc_timeout(), retry=None
    ):
        budget.charge()
        data = snapshot.to_dict() or {}
        if snapshot.exists and not data.get('deleted') and not data.get('is_locked'):
            eligible.append(snapshot.id)
    result.update(linked_task_presence(uid, eligible, budget=budget, firestore_client=client))
    return result


def browse_candidate_page(
    uid: str,
    filters: TaskConversationPageRequest,
    *,
    after: Optional[str],
    scope: str,
    budget: ListReadBudget,
    firestore_client: Any = None,
) -> tuple[List[tuple[str, Optional[dict]]], bool]:
    """One bounded raw page. Every snapshot advances, including hidden rows."""
    client = firestore_client or get_firestore_client()
    query = client.collection('users').document(uid).collection('conversations')
    # Use the existing chronological index for candidate discovery. Membership,
    # visibility, folder and star are intersected before emission by the shared
    # filter owner. This also includes legacy rows without optional flags and
    # avoids making a mobile release depend on a new family of composites.
    if filters.start_date:
        query = query.where(filter=FieldFilter('created_at', '>=', filters.start_date))
    if filters.end_date:
        query = query.where(filter=FieldFilter('created_at', '<=', filters.end_date))
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING).order_by(
        '__name__', direction=firestore.Query.DESCENDING
    )
    if after:
        stamp, cid = decode_cursor(after, scope)
        query = query.start_after(BookmarkDict({'created_at': stamp, '__name__': cid}))
    # Reuse the existing conversation codec, without fetching transcript blobs.
    # All visibility receipts remain in the projection, including holds/redirects.
    fields = set(Conversation.model_fields) - {'transcript_segments', 'transcript_segments_compressed', 'photos'}
    fields.update(
        {
            'data_protection_level',
            'user_title',
            'user_corrections_compressed',
            'folder_user_set',
            *SETTLING_FIELDS,
            *transcribing_hold.READ_FIELDS,
            'deleted',
            'dream_duplicate_of',
            'sync_bridge_pending',
            'relevance_decision',
            'sync_relevance_user_kept',
            'finalization_status',
            'has_photos',
        }
    )
    snapshots = list(budgeted_stream_iter(query.select(sorted(fields)).limit(50), budget))
    rows = []
    for snapshot in snapshots:
        budget.check()
        raw = document_data_with_revision(snapshot)
        if raw is None:
            raise ValueError('conversation ordering metadata unavailable')
        raw['id'] = snapshot.id
        position = encode_cursor(raw['created_at'], snapshot.id, scope)
        row = None
        if is_visible_conversation(raw, include_discarded=filters.include_discarded, presentation=True):
            row = prepare_conversation_for_read(raw, uid, firestore_client=client, read_budget=budget)
        rows.append((position, row))
    return rows, len(snapshots) == 50

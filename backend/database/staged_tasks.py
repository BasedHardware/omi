"""Database operations for desktop staged tasks (users/{uid}/staged_tasks)."""

from datetime import datetime, timezone
from typing import Optional, List, Tuple

from google.cloud import firestore

from ._client import db
import logging

logger = logging.getLogger(__name__)

COLLECTION = 'staged_tasks'


def _prepare_for_read(data: dict) -> dict:
    """Convert Firestore timestamps to Python datetimes."""
    for field in ['created_at', 'updated_at', 'due_at', 'completed_at', 'deleted_at']:
        if field in data and data[field] and hasattr(data[field], 'timestamp'):
            data[field] = datetime.fromtimestamp(data[field].timestamp(), tz=timezone.utc)
    return data


# --- CREATE ---


def create_staged_task(uid: str, data: dict) -> dict:
    """Create a staged task. Returns the created document with id."""
    now = datetime.now(timezone.utc)
    data.setdefault('created_at', now)
    data.setdefault('updated_at', now)
    data.setdefault('completed', False)

    ref = db.collection('users').document(uid).collection(COLLECTION)
    _, doc_ref = ref.add(data)
    result = data.copy()
    result['id'] = doc_ref.id
    return result


# --- READ ---


def get_staged_tasks(uid: str, limit: int = 100, offset: int = 0) -> Tuple[List[dict], bool]:
    """List staged tasks ordered by relevance_score ASC. Returns (items, has_more)."""
    ref = db.collection('users').document(uid).collection(COLLECTION)
    query = ref.order_by('relevance_score', direction=firestore.Query.ASCENDING)

    # Fetch limit+1 to detect has_more
    fetch_limit = limit + 1
    if offset > 0:
        query = query.offset(offset)
    query = query.limit(fetch_limit)

    docs = list(query.stream())
    items = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        items.append(_prepare_for_read(data))

    has_more = len(items) > limit
    if has_more:
        items = items[:limit]
    return items, has_more


def get_staged_task(uid: str, task_id: str) -> Optional[dict]:
    """Get a single staged task by ID."""
    doc = db.collection('users').document(uid).collection(COLLECTION).document(task_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    data['id'] = doc.id
    return _prepare_for_read(data)


# --- UPDATE ---


def batch_update_scores(uid: str, scores: List[dict]) -> None:
    """Batch update relevance_score for multiple staged tasks.

    Args:
        scores: List of {"id": str, "relevance_score": int}
    """
    if not scores:
        return
    batch = db.batch()
    ref = db.collection('users').document(uid).collection(COLLECTION)
    now = datetime.now(timezone.utc)
    for item in scores:
        doc_ref = ref.document(item['id'])
        batch.update(doc_ref, {'relevance_score': item['relevance_score'], 'updated_at': now})
    batch.commit()


# --- DELETE ---


def delete_staged_task(uid: str, task_id: str) -> bool:
    """Hard-delete a staged task. Returns True if deleted."""
    doc_ref = db.collection('users').document(uid).collection(COLLECTION).document(task_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False
    doc_ref.delete()
    return True


def delete_staged_tasks_batch(uid: str, task_ids: List[str]) -> int:
    """Hard-delete multiple staged tasks. Returns count deleted."""
    if not task_ids:
        return 0
    batch = db.batch()
    ref = db.collection('users').document(uid).collection(COLLECTION)
    for task_id in task_ids:
        batch.delete(ref.document(task_id))
    batch.commit()
    return len(task_ids)


# --- PROMOTE ---


def get_active_ai_action_items(uid: str) -> List[dict]:
    """Get active action items that were promoted from staged (from_staged=true, not completed, not deleted)."""
    ref = db.collection('users').document(uid).collection('action_items')
    query = ref.where(filter=firestore.FieldFilter('from_staged', '==', True)).where(
        filter=firestore.FieldFilter('completed', '==', False)
    )
    items = []
    for doc in query.stream():
        data = doc.to_dict()
        # Skip soft-deleted
        if data.get('deleted'):
            continue
        data['id'] = doc.id
        items.append(_prepare_for_read(data))
    return items


def promote_staged_task(uid: str, staged_task: dict) -> dict:
    """Create an action item from a staged task (from_staged=true). Returns created action item."""
    now = datetime.now(timezone.utc)
    action_item_data = {
        'description': staged_task['description'],
        'completed': False,
        'created_at': now,
        'updated_at': now,
        'from_staged': True,
        'source': staged_task.get('source'),
        'priority': staged_task.get('priority'),
        'metadata': staged_task.get('metadata'),
        'category': staged_task.get('category'),
        'relevance_score': staged_task.get('relevance_score'),
    }
    if staged_task.get('due_at'):
        action_item_data['due_at'] = staged_task['due_at']

    ref = db.collection('users').document(uid).collection('action_items')
    _, doc_ref = ref.add(action_item_data)
    action_item_data['id'] = doc_ref.id
    return action_item_data


# --- SCORES (daily/weekly/overall) ---


def get_action_items_for_daily_score(uid: str, due_start: str, due_end: str) -> Tuple[int, int]:
    """Count completed vs total action items due on a specific day.

    Returns (completed_count, total_count).
    """
    ref = db.collection('users').document(uid).collection('action_items')
    start_dt = datetime.fromisoformat(due_start.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(due_end.replace('Z', '+00:00'))

    query = ref.where(filter=firestore.FieldFilter('due_at', '>=', start_dt)).where(
        filter=firestore.FieldFilter('due_at', '<=', end_dt)
    )

    completed = 0
    total = 0
    for doc in query.stream():
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        total += 1
        if data.get('completed'):
            completed += 1
    return completed, total


def get_action_items_for_weekly_score(uid: str, week_start: str, week_end: str) -> Tuple[int, int]:
    """Count completed vs total action items in a 7-day window.

    Returns (completed_count, total_count).
    """
    # Same logic as daily but wider date range
    return get_action_items_for_daily_score(uid, week_start, week_end)


def get_action_items_for_overall_score(uid: str) -> Tuple[int, int]:
    """Count completed vs total action items (all time, not deleted).

    Returns (completed_count, total_count).
    """
    ref = db.collection('users').document(uid).collection('action_items')

    completed = 0
    total = 0
    for doc in ref.stream():
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        total += 1
        if data.get('completed'):
            completed += 1
    return completed, total

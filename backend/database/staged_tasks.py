"""Staged tasks — AI-generated tasks awaiting user promotion to action items.

Collection: users/{uid}/staged_tasks
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from ._client import db
import database.action_items as action_items_db

logger = logging.getLogger(__name__)

BATCH_LIMIT = 500  # Firestore hard limit


def _user_col(uid: str, collection: str) -> Any:
    """Shorthand for users/{uid}/{collection}."""
    return db.collection('users').document(uid).collection(collection)


def _commit_batch(batch: Any, count: int) -> Tuple[Any, int]:
    """Commit batch if count reaches BATCH_LIMIT; return fresh batch and 0."""
    if count >= BATCH_LIMIT:
        batch.commit()
        return db.batch(), 0
    return batch, count


def create_staged_task(uid: str, description: str, **kwargs: Any) -> Dict[str, Any]:
    """Create a staged task.  Deduplicates by normalized description.

    Uses the same normalization (``_normalize_description``) as the
    promotion-time dedup in ``promote_staged_task`` → an "[screen] Email
    John" extraction collapses to an existing "Email John" staged task,
    so we don't end up with two staged candidates that resolve to the
    same action_item at promotion time.
    """
    col = _user_col(uid, 'staged_tasks')

    # Deduplicate
    desc_norm = _normalize_desc(description)
    for candidate in col.stream():
        data = cast(Dict[str, Any], candidate.to_dict())
        if _normalize_desc(data.get('description', '')) == desc_norm:
            data['id'] = candidate.id
            return data

    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
        'id': task_id,
        'description': description,
        'completed': False,
        'created_at': now,
        'updated_at': now,
    }
    for field in ('due_at', 'source', 'priority', 'metadata', 'category', 'relevance_score'):
        if field in kwargs and kwargs[field] is not None:
            doc[field] = kwargs[field]

    col.document(task_id).set(doc)
    return doc


def get_staged_tasks(uid: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Fetch uncompleted staged tasks ordered by relevance (ascending)."""
    col = _user_col(uid, 'staged_tasks')
    query = col.where(filter=FieldFilter('completed', '==', False))
    query = query.order_by('relevance_score', direction=firestore.Query.ASCENDING)
    if offset > 0:
        query = query.offset(offset)
    query = query.limit(limit)

    items: List[Dict[str, Any]] = []
    for doc in query.stream():
        data = cast(Dict[str, Any], doc.to_dict())
        data['id'] = doc.id
        items.append(data)
    return items


def delete_staged_task(uid: str, task_id: str) -> bool:
    ref = _user_col(uid, 'staged_tasks').document(task_id)
    if not ref.get().exists:
        return False
    ref.delete()
    return True


def batch_update_staged_scores(uid: str, scores: List[Dict[str, Any]]) -> None:
    """Update relevance_score for staged tasks in batches of 500.

    Pre-filters to active (uncompleted) document IDs so stale/deleted/promoted
    task references from the client don't cause NotFound errors on batch.update().
    """
    if not scores:
        return
    col = _user_col(uid, 'staged_tasks')
    active_query = col.where(filter=FieldFilter('completed', '==', False)).select([])
    existing_ids = {doc.id for doc in active_query.stream()}
    valid_scores = [s for s in scores if s['id'] in existing_ids]
    if not valid_scores:
        return
    now = datetime.now(timezone.utc)
    batch = db.batch()
    count = 0
    for item in valid_scores:
        ref = col.document(item['id'])
        batch.update(ref, {'relevance_score': item['relevance_score'], 'updated_at': now})
        count += 1
        batch, count = _commit_batch(batch, count)
    if count > 0:
        batch.commit()


def promote_staged_task(uid: str) -> Optional[Dict[str, Any]]:
    """Promote the top-scored staged task to an action_item.

    Returns the new (or pre-existing) action_item dict, or None if no staged
    tasks exist. Uses ``database.action_items.create_action_item()`` for
    consistent field handling.

    Deduplicates against the live ``action_items`` collection: if a user
    already has an active (uncompleted, undeleted) action_item with the same
    normalized description, the staged task is closed (``completed=True``,
    ``promotion_skipped='duplicate'``, ``promoted_to`` pointing at the existing
    item) and the existing item is returned instead of creating a fresh row.

    Without this guard, every conversation that re-mentions the same task is
    extracted into a new staged task and promoted into a fresh action_item
    document — Firestore allocates a new id on each ``add()``, so the user's
    list accumulates 5–6 duplicates per task description over the course of
    a few hours of activity.
    """
    col = _user_col(uid, 'staged_tasks')
    query = (
        col.where(filter=FieldFilter('completed', '==', False))
        .order_by('relevance_score', direction=firestore.Query.ASCENDING)
        .limit(1)
    )
    docs = list(query.stream())
    if not docs:
        return None

    staged = cast(Dict[str, Any], docs[0].to_dict())
    staged['id'] = docs[0].id

    # Dedup: skip promotion if an active action_item with the same description
    # already exists. Close the staged task pointing at the existing item.
    existing = _get_active_by_desc(uid, staged['description'])
    if existing is not None:
        # Merge enrichment fields the existing item is missing. The staged
        # task may carry richer context from a later conversation
        # (e.g. a due_at the user mentioned later) that the original
        # action_item lacks; without this merge that scheduling info is
        # silently dropped.
        merge_fields: Dict[str, Any] = {}
        for field in ('due_at', 'priority', 'category'):
            staged_value = staged.get(field)
            if staged_value is not None and not existing.get(field):
                merge_fields[field] = staged_value
        if merge_fields:
            try:
                _update_item(uid, existing['id'], merge_fields)
                existing.update(merge_fields)
            except Exception as e:
                # Merge is best-effort — the dedup itself is the primary
                # win, so don't fail the promotion path on a metadata write.
                logger.warning(
                    "Failed to merge staged metadata into action_item %s for user %s: %s",
                    existing['id'],
                    uid,
                    e,
                )

        col.document(staged['id']).update(
            {
                'completed': True,
                'promoted_at': datetime.now(timezone.utc),
                'promotion_skipped': 'duplicate',
                'promoted_to': existing['id'],
            }
        )
        logger.info(
            "Skipped promotion of staged task %s for user %s — duplicate of action_item %s (merged %d fields)",
            staged['id'],
            uid,
            existing['id'],
            len(merge_fields),
        )
        return existing

    # Build action_item data from staged task fields
    action_data: Dict[str, Any] = {
        'description': staged['description'],
        'completed': False,
        'from_staged': True,
    }
    for field in ('due_at', 'source', 'priority', 'metadata', 'category', 'relevance_score'):
        if staged.get(field) is not None:
            action_data[field] = staged[field]

    action_id = _create_item(uid, action_data)

    # Mark staged task as completed
    col.document(staged['id']).update({'completed': True, 'promoted_at': datetime.now(timezone.utc)})

    action_item = _get_item(uid, action_id)
    return action_item


def migrate_ai_tasks(uid: str) -> Dict[str, Any]:
    """One-time migration: move excess AI tasks from action_items to staged_tasks.

    Keeps top 3 AI tasks in action_items, moves the rest to staged_tasks.
    Uses a 'source' field marker to identify AI-created tasks.
    """
    col = _user_col(uid, 'action_items')
    query = col.where(filter=FieldFilter('completed', '==', False))

    all_items: List[Dict[str, Any]] = []
    for doc in query.stream():
        data = cast(Dict[str, Any], doc.to_dict())
        data['id'] = doc.id
        if data.get('deleted'):
            continue
        all_items.append(data)

    # Separate AI-generated tasks from manual ones
    ai_tasks = [item for item in all_items if 'screenshot' in (item.get('source') or '')]
    if len(ai_tasks) <= 3:
        return {'moved': 0, 'kept': len(ai_tasks)}

    # Sort by relevance_score ascending (best first)
    ai_tasks.sort(key=lambda x: x.get('relevance_score') or 999)
    keep = ai_tasks[:3]
    to_move = ai_tasks[3:]

    staged_col = _user_col(uid, 'staged_tasks')
    batch = db.batch()
    batch_count = 0
    for task in to_move:
        batch.set(staged_col.document(task['id']), task)
        batch.delete(col.document(task['id']))
        batch_count += 2  # set + delete = 2 operations
        batch, batch_count = _commit_batch(batch, batch_count)
    if batch_count > 0:
        batch.commit()

    return {'moved': len(to_move), 'kept': len(keep)}


def migrate_conversation_items_to_staged(uid: str) -> Dict[str, Any]:
    """Move conversation-sourced action items (without 'source') to staged_tasks."""
    col = _user_col(uid, 'action_items')
    staged_col = _user_col(uid, 'staged_tasks')

    batch = db.batch()
    moved = 0
    batch_count = 0
    for doc in col.stream():
        data = cast(Dict[str, Any], doc.to_dict())
        if data.get('deleted') or data.get('completed'):
            continue
        if data.get('conversation_id') and not data.get('source'):
            data['id'] = doc.id
            data['source'] = 'conversation_migration'
            batch.set(staged_col.document(doc.id), data)
            batch.delete(col.document(doc.id))
            moved += 1
            batch_count += 2  # set + delete = 2 operations
            batch, batch_count = _commit_batch(batch, batch_count)
    if batch_count > 0:
        batch.commit()

    return {'moved': moved}


# ---------------------------------------------------------------------------
# Typed adapters for ``database.action_items`` (not yet strict-enrolled).
#
# These thin wrappers pin fully-typed callable shapes at this module's boundary.
# Attribute access happens at CALL time (inside the wrapper bodies), matching
# the original inline calls — so tests that stub ``database.action_items`` as
# an empty module before importing this file keep working. Drop these once
# action_items.py is strict-enrolled.
# ---------------------------------------------------------------------------
def _normalize_desc(desc: Optional[str]) -> str:
    return cast(str, action_items_db._normalize_description(desc))  # type: ignore[reportPrivateUsage]  # cross-module dedup helper, intentionally shared


def _get_active_by_desc(uid: str, description: str) -> Optional[Dict[str, Any]]:
    return cast(
        Optional[Dict[str, Any]],
        action_items_db.get_active_action_item_by_description(uid, description),  # type: ignore[reportUnknownMemberType]  # action_items not yet strict-enrolled
    )


def _update_item(uid: str, action_item_id: str, update_data: Dict[str, Any]) -> bool:
    return cast(
        bool,
        action_items_db.update_action_item(uid, action_item_id, update_data),  # type: ignore[reportUnknownMemberType]  # action_items not yet strict-enrolled
    )


def _create_item(uid: str, action_item_data: Dict[str, Any]) -> str:
    return cast(
        str,
        action_items_db.create_action_item(uid, action_item_data),  # type: ignore[reportUnknownMemberType]  # action_items not yet strict-enrolled
    )


def _get_item(uid: str, action_item_id: str) -> Optional[Dict[str, Any]]:
    return cast(
        Optional[Dict[str, Any]],
        action_items_db.get_action_item(uid, action_item_id),  # type: ignore[reportUnknownMemberType]  # action_items not yet strict-enrolled
    )

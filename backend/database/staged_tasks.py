"""Staged tasks — AI-generated tasks awaiting user promotion to action items.

Collection: users/{uid}/staged_tasks
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from database.store import get_document_store
import database.action_items as action_items_db

logger = logging.getLogger(__name__)

BATCH_LIMIT = 500  # bulk-write chunk size (adapters honor their own batch limits)


def _store():
    return get_document_store()


def _col(uid: str, collection: str) -> str:
    """Logical path for users/{uid}/{collection}."""
    return f'users/{uid}/{collection}'


def _commit_batch(batch, count):
    """Commit batch if count reaches BATCH_LIMIT; return fresh batch and 0."""
    if count >= BATCH_LIMIT:
        batch.commit()
        return _store().batch(), 0
    return batch, count


def create_staged_task(uid: str, description: str, **kwargs) -> dict:
    """Create a staged task.  Deduplicates by normalized description.

    Uses the same normalization (``_normalize_description``) as the
    promotion-time dedup in ``promote_staged_task`` → an "[screen] Email
    John" extraction collapses to an existing "Email John" staged task,
    so we don't end up with two staged candidates that resolve to the
    same action_item at promotion time.
    """
    col = _col(uid, 'staged_tasks')

    # Deduplicate
    desc_norm = action_items_db._normalize_description(description)
    for doc in _store().query(col):
        if action_items_db._normalize_description(doc.to_dict().get('description', '')) == desc_norm:
            existing = doc.to_dict()
            existing['id'] = doc.id
            return existing

    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        'id': task_id,
        'description': description,
        'completed': False,
        'created_at': now,
        'updated_at': now,
    }
    for field in ('due_at', 'source', 'priority', 'metadata', 'category', 'relevance_score'):
        if field in kwargs and kwargs[field] is not None:
            doc[field] = kwargs[field]

    _store().set(f'{col}/{task_id}', doc)
    return doc


def get_staged_tasks(uid: str, limit: int = 100, offset: int = 0) -> List[dict]:
    """Fetch uncompleted staged tasks ordered by relevance (ascending)."""
    col = _col(uid, 'staged_tasks')
    docs = _store().query(
        col,
        filters=[('completed', '==', False)],
        order_by='relevance_score',
        direction='asc',
        limit=limit,
        offset=offset if offset > 0 else None,
    )

    items = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        items.append(data)
    return items


def get_all_staged_tasks_for_migration(uid: str) -> List[dict]:
    """Read active and terminal staged rows for idempotent Candidate reconciliation."""

    items: List[dict] = []
    for snapshot in _store().query(_col(uid, 'staged_tasks')):
        data = snapshot.to_dict() or {}
        data['id'] = snapshot.id
        items.append(data)
    return items


def get_top_staged_task_for_promotion(uid: str) -> Optional[dict]:
    """Select the exact active row that a fenced write-mode promotion will mutate."""

    docs = _store().query(
        _col(uid, 'staged_tasks'),
        filters=[('completed', '==', False)],
        order_by='relevance_score',
        direction='asc',
        limit=1,
    )
    if not docs:
        return None
    row = docs[0].to_dict() or {}
    row['id'] = docs[0].id
    return row


def delete_staged_task(uid: str, task_id: str) -> bool:
    path = f'{_col(uid, "staged_tasks")}/{task_id}'
    if not _store().exists(path):
        return False
    _store().delete(path)
    return True


def complete_staged_task_promotion(
    uid: str,
    staged_id: str,
    task_id: str,
    *,
    promotion_skipped: Optional[str] = None,
) -> None:
    patch = {
        'completed': True,
        'promoted_at': datetime.now(timezone.utc),
        'promoted_to': task_id,
    }
    if promotion_skipped is not None:
        patch['promotion_skipped'] = promotion_skipped
    _store().update(f'{_col(uid, "staged_tasks")}/{staged_id}', patch)


def suppress_staged_task_for_terminal_candidate(uid: str, staged_id: str, *, reason: str) -> None:
    """Close a legacy row whose canonical sidecar is already terminal without creating a task."""

    now = datetime.now(timezone.utc)
    _store().update(
        f'{_col(uid, "staged_tasks")}/{staged_id}',
        {
            'completed': True,
            'updated_at': now,
            'candidate_terminal_reason': reason,
            'promotion_skipped': 'candidate_terminal',
        },
    )


def batch_update_staged_scores(uid: str, scores: List[dict]) -> None:
    """Update relevance_score for staged tasks in batches of 500.

    Pre-filters to active (uncompleted) document IDs so stale/deleted/promoted
    task references from the client don't cause NotFound errors on batch.update().
    """
    if not scores:
        return
    col = _col(uid, 'staged_tasks')
    existing_ids = {doc.id for doc in _store().query(col, filters=[('completed', '==', False)], fields=[])}
    valid_scores = [s for s in scores if s['id'] in existing_ids]
    if not valid_scores:
        return
    now = datetime.now(timezone.utc)
    store = _store()
    batch = store.batch()
    count = 0
    for item in valid_scores:
        batch.update(f'{col}/{item["id"]}', {'relevance_score': item['relevance_score'], 'updated_at': now})
        count += 1
        batch, count = _commit_batch(batch, count)
    if count > 0:
        batch.commit()


def promote_staged_task(
    uid: str,
    task_id: Optional[str] = None,
    *,
    include_staged_id: bool = False,
    action_item_id: Optional[str] = None,
    reservation_kind: Optional[str] = None,
) -> Optional[dict]:
    """Promote a staged task to an action_item.

    When ``task_id`` is given, promote that specific candidate; otherwise promote the
    top-scored active staged task (the original behavior). Returns the new (or pre-existing)
    action_item dict, or None if there is nothing to promote — no staged tasks exist, or the
    given id does not exist or is already promoted/completed. Uses
    ``database.action_items.create_action_item()`` for consistent field handling.
    ``action_item_id`` reserves the exact document id for a crash-retried
    Candidate write; semantic dedup is honored when it resolves to that id.
    An ``existing`` reservation never creates that document if the user has
    completed or deleted it after reservation.

    Deduplicates against the live ``action_items`` collection: if a user
    already has an active (uncompleted, undeleted) action_item with the same
    normalized description, the staged task is closed (``completed=True``,
    ``promotion_skipped='duplicate'``, ``promoted_to`` pointing at the existing
    item) and the existing item is returned instead of creating a fresh row.

    Without this guard, every conversation that re-mentions the same task is
    extracted into a new staged task and promoted into a fresh action_item
    document — each ``create`` allocates a new id, so the user's
    list accumulates 5–6 duplicates per task description over the course of
    a few hours of activity.
    """
    col = _col(uid, 'staged_tasks')
    if reservation_kind not in {None, 'create', 'existing'}:
        raise ValueError('reservation_kind must be create or existing')
    if task_id is not None:
        snap = _store().get(f'{col}/{task_id}')
        if not snap.exists:
            return None
        staged = snap.to_dict() or {}
        if staged.get('completed'):
            # Already promoted/closed — nothing to do.
            return None
        staged['id'] = snap.id
    else:
        docs = _store().query(
            col,
            filters=[('completed', '==', False)],
            order_by='relevance_score',
            direction='asc',
            limit=1,
        )
        if not docs:
            return None
        staged = docs[0].to_dict()
        staged['id'] = docs[0].id

    # Dedup: skip promotion if an active action_item with the same description
    # already exists. Close the staged task pointing at the existing item.
    existing = action_items_db.get_active_action_item_by_description(uid, staged['description'])
    if existing is not None and (action_item_id is None or existing.get('id') == action_item_id):
        # Merge enrichment fields the existing item is missing. The staged
        # task may carry richer context from a later conversation
        # (e.g. a due_at the user mentioned later) that the original
        # action_item lacks; without this merge that scheduling info is
        # silently dropped.
        merge_fields = {}
        for field in ('due_at', 'priority', 'category'):
            staged_value = staged.get(field)
            if staged_value is not None and not existing.get(field):
                merge_fields[field] = staged_value
        if merge_fields:
            try:
                action_items_db.update_action_item(uid, existing['id'], merge_fields)
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

        _store().update(
            f'{col}/{staged["id"]}',
            {
                'completed': True,
                'promoted_at': datetime.now(timezone.utc),
                'promotion_skipped': 'duplicate',
                'promoted_to': existing['id'],
            },
        )
        logger.info(
            "Skipped promotion of staged task %s for user %s — duplicate of action_item %s (merged %d fields)",
            staged['id'],
            uid,
            existing['id'],
            len(merge_fields),
        )
        return {**existing, '_staged_task_id': staged['id']} if include_staged_id else existing

    if reservation_kind == 'existing':
        if action_item_id is None:
            raise ValueError('existing reservation requires action_item_id')
        _store().update(
            f'{col}/{staged["id"]}',
            {
                'completed': True,
                'promoted_at': datetime.now(timezone.utc),
                'promotion_skipped': 'duplicate_target_closed',
                'promoted_to': action_item_id,
            },
        )
        result = {'id': action_item_id}
        return {**result, '_staged_task_id': staged['id']} if include_staged_id else result

    # Build action_item data from staged task fields
    action_data = {
        'description': staged['description'],
        'completed': False,
        'from_staged': True,
    }
    for field in ('due_at', 'source', 'priority', 'metadata', 'category', 'relevance_score'):
        if staged.get(field) is not None:
            action_data[field] = staged[field]

    action_id = (
        action_items_db.create_action_item(uid, action_data, document_id=action_item_id)
        if action_item_id is not None
        else action_items_db.create_action_item(uid, action_data)
    )

    # Mark staged task as completed
    _store().update(
        f'{col}/{staged["id"]}',
        {
            'completed': True,
            'promoted_at': datetime.now(timezone.utc),
            'promoted_to': action_id,
        },
    )

    action_item = action_items_db.get_action_item(uid, action_id)
    if action_item is None:
        return None
    return {**action_item, '_staged_task_id': staged['id']} if include_staged_id else action_item


def clear_staged_tasks(uid: str) -> int:
    """Delete all active (uncompleted) staged tasks for a user in one call.

    Returns the number deleted. Scoped to completed==False so promotion history
    (completed/promoted staged tasks) is preserved.
    """
    col = _col(uid, 'staged_tasks')
    store = _store()
    batch = store.batch()
    count = 0
    total = 0
    for doc in store.query(col, filters=[('completed', '==', False)], fields=[]):
        batch.delete(doc.path)
        count += 1
        total += 1
        batch, count = _commit_batch(batch, count)
    if count > 0:
        batch.commit()
    return total


def migrate_ai_tasks(uid: str) -> dict:
    """One-time migration: move excess AI tasks from action_items to staged_tasks.

    Keeps top 3 AI tasks in action_items, moves the rest to staged_tasks.
    Uses a 'source' field marker to identify AI-created tasks.
    """
    col = _col(uid, 'action_items')

    all_items = []
    for doc in _store().query(col, filters=[('completed', '==', False)]):
        data = doc.to_dict()
        data['id'] = doc.id
        if data.get('deleted'):
            continue
        all_items.append(data)

    # Separate AI-generated tasks from manual ones
    ai_tasks = [item for item in all_items if 'screenshot' in (item.get('source') or '')]
    if len(ai_tasks) <= 3:
        return {'moved': 0, 'kept': len(ai_tasks)}

    # Sort by relevance_score ascending (best first). relevance_score is an int in
    # 0-1000 where 0 is the most relevant, so only a genuinely missing (None) score
    # should sort last: `or 999` would also demote a valid best score of 0.
    ai_tasks.sort(key=lambda x: 999 if x.get('relevance_score') is None else x.get('relevance_score'))
    keep = ai_tasks[:3]
    to_move = ai_tasks[3:]

    staged_col = _col(uid, 'staged_tasks')
    store = _store()
    batch = store.batch()
    batch_count = 0
    for task in to_move:
        batch.set(f'{staged_col}/{task["id"]}', task)
        batch.delete(f'{col}/{task["id"]}')
        batch_count += 2  # set + delete = 2 operations
        batch, batch_count = _commit_batch(batch, batch_count)
    if batch_count > 0:
        batch.commit()

    return {'moved': len(to_move), 'kept': len(keep)}


def migrate_conversation_items_to_staged(uid: str) -> dict:
    """Move conversation-sourced action items (without 'source') to staged_tasks."""
    col = _col(uid, 'action_items')
    staged_col = _col(uid, 'staged_tasks')

    store = _store()
    batch = store.batch()
    moved = 0
    batch_count = 0
    for doc in store.query(col):
        data = doc.to_dict()
        if data.get('deleted') or data.get('completed'):
            continue
        if data.get('conversation_id') and not data.get('source'):
            data['id'] = doc.id
            data['source'] = 'conversation_migration'
            batch.set(f'{staged_col}/{doc.id}', data)
            batch.delete(f'{col}/{doc.id}')
            moved += 1
            batch_count += 2  # set + delete = 2 operations
            batch, batch_count = _commit_batch(batch, batch_count)
    if batch_count > 0:
        batch.commit()

    return {'moved': moved}

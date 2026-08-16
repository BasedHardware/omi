"""Staged tasks — AI-generated tasks awaiting user promotion to action items.

Collection: users/{uid}/staged_tasks
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from google.api_core.exceptions import AlreadyExists, Conflict, FailedPrecondition
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from ._client import db, get_firestore_client
from .firestore_index_registry import LEGACY_CONVERSATION_RECOVERY_QUERY
import database.action_items as action_items_db

logger = logging.getLogger(__name__)

BATCH_LIMIT = 500  # Firestore hard limit

# Recovery uses one atomic create-if-absent batch per row. Keep the page small
# enough that a user with a large historical migration never holds an HTTP
# request open for an unbounded number of Firestore commits.
LEGACY_CONVERSATION_RECOVERY_PAGE_SIZE = 50
LEGACY_CONVERSATION_RECOVERY_MAX_CONTENTION_RETRIES = 3


def _user_col(uid: str, collection: str):
    """Shorthand for users/{uid}/{collection}."""
    return db.collection('users').document(uid).collection(collection)


def _commit_batch(batch, count):
    """Commit batch if count reaches BATCH_LIMIT; return fresh batch and 0."""
    if count >= BATCH_LIMIT:
        batch.commit()
        return db.batch(), 0
    return batch, count


def create_staged_task(uid: str, description: str, **kwargs) -> dict:
    """Create a staged task.  Deduplicates by normalized description.

    Uses the same normalization (``_normalize_description``) as the
    promotion-time dedup in ``promote_staged_task`` → an "[screen] Email
    John" extraction collapses to an existing "Email John" staged task,
    so we don't end up with two staged candidates that resolve to the
    same action_item at promotion time.
    """
    col = _user_col(uid, 'staged_tasks')

    # Deduplicate
    desc_norm = action_items_db._normalize_description(description)
    for doc in col.stream():
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

    col.document(task_id).set(doc)
    return doc


def get_staged_tasks(uid: str, limit: int = 100, offset: int = 0) -> List[dict]:
    """Fetch uncompleted staged tasks ordered by relevance (ascending)."""
    col = _user_col(uid, 'staged_tasks')
    query = col.where(filter=FieldFilter('completed', '==', False))
    query = query.order_by('relevance_score', direction=firestore.Query.ASCENDING)
    if offset > 0:
        query = query.offset(offset)
    query = query.limit(limit)

    items = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        items.append(data)
    return items


def get_all_staged_tasks_for_migration(uid: str) -> List[dict]:
    """Read active and terminal staged rows for idempotent Candidate reconciliation."""

    items: List[dict] = []
    for snapshot in _user_col(uid, 'staged_tasks').stream():
        data = snapshot.to_dict() or {}
        data['id'] = snapshot.id
        items.append(data)
    return items


def get_active_staged_tasks_for_compatibility(uid: str) -> List[dict]:
    """Read every active historical row for complete released compatibility."""

    # Do not filter in Firestore: old rows may predate the ``completed`` field,
    # and a field predicate would silently hide exactly the data this adapter
    # exists to preserve.
    query = _user_col(uid, 'staged_tasks').order_by('__name__')
    items: List[dict] = []
    for snapshot in query.stream():
        data = snapshot.to_dict() or {}
        if data.get('completed'):
            continue
        data['id'] = snapshot.id
        items.append(data)
    return items


def get_staged_task_for_compatibility(uid: str, staged_id: str) -> Optional[dict]:
    """Point-read one active historical row without scanning the account."""

    snapshot = _user_col(uid, 'staged_tasks').document(staged_id).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    if data.get('completed'):
        return None
    data['id'] = snapshot.id
    return data


def get_top_staged_task_for_promotion(uid: str) -> Optional[dict]:
    """Select the exact active row that a fenced write-mode promotion will mutate."""

    query = (
        _user_col(uid, 'staged_tasks')
        .where(filter=FieldFilter('completed', '==', False))
        .order_by('relevance_score', direction=firestore.Query.ASCENDING)
        .limit(1)
    )
    docs = list(query.stream())
    if not docs:
        return None
    row = docs[0].to_dict() or {}
    row['id'] = docs[0].id
    return row


def delete_staged_task(uid: str, task_id: str) -> bool:
    ref = _user_col(uid, 'staged_tasks').document(task_id)
    if not ref.get().exists:
        return False
    ref.delete()
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
    _user_col(uid, 'staged_tasks').document(staged_id).update(patch)


def suppress_staged_task_for_terminal_candidate(uid: str, staged_id: str, *, reason: str) -> None:
    """Close a legacy row whose canonical sidecar is already terminal without creating a task."""

    now = datetime.now(timezone.utc)
    _user_col(uid, 'staged_tasks').document(staged_id).update(
        {
            'completed': True,
            'updated_at': now,
            'candidate_terminal_reason': reason,
            'promotion_skipped': 'candidate_terminal',
        }
    )


def batch_update_staged_scores(uid: str, scores: List[dict]) -> None:
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
    document — Firestore allocates a new id on each ``add()``, so the user's
    list accumulates 5–6 duplicates per task description over the course of
    a few hours of activity.
    """
    col = _user_col(uid, 'staged_tasks')
    if reservation_kind not in {None, 'create', 'existing'}:
        raise ValueError('reservation_kind must be create or existing')
    if task_id is not None:
        snap = col.document(task_id).get()
        if not snap.exists:
            return None
        staged = snap.to_dict() or {}
        if staged.get('completed'):
            # Already promoted/closed — nothing to do.
            return None
        staged['id'] = snap.id
    else:
        query = (
            col.where(filter=FieldFilter('completed', '==', False))
            .order_by('relevance_score', direction=firestore.Query.ASCENDING)
            .limit(1)
        )
        docs = list(query.stream())
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
        return {**existing, '_staged_task_id': staged['id']} if include_staged_id else existing

    if reservation_kind == 'existing':
        if action_item_id is None:
            raise ValueError('existing reservation requires action_item_id')
        col.document(staged['id']).update(
            {
                'completed': True,
                'promoted_at': datetime.now(timezone.utc),
                'promotion_skipped': 'duplicate_target_closed',
                'promoted_to': action_item_id,
            }
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
    col.document(staged['id']).update(
        {
            'completed': True,
            'promoted_at': datetime.now(timezone.utc),
            'promoted_to': action_id,
        }
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
    col = _user_col(uid, 'staged_tasks')
    active_query = col.where(filter=FieldFilter('completed', '==', False)).select([])
    batch = db.batch()
    count = 0
    total = 0
    for doc in active_query.stream():
        batch.delete(col.document(doc.id))
        count += 1
        total += 1
        batch, count = _commit_batch(batch, count)
    if count > 0:
        batch.commit()
    return total


def restore_legacy_conversation_items(
    uid: str,
    *,
    limit: int = LEGACY_CONVERSATION_RECOVERY_PAGE_SIZE,
    cursor: Optional[str] = None,
    firestore_client=None,
) -> dict:
    """Restore rows moved by the retired desktop conversation migration.

    Only active ``conversation_migration`` rows qualify. Each row is restored
    with an atomic create+delete batch, so an existing action item is never
    overwritten; an action item created or restored concurrently wins. Results
    are ordered by document ID and cursor-paginated so the client can finish a
    large recovery without one request exceeding its Firestore deadline.
    """

    if limit < 1:
        raise ValueError('limit must be positive')

    # Resolve the client at the call boundary. The legacy ``db`` proxy is safe
    # for older helpers in this module, but recovery must be independently
    # testable and must not capture a client during import.
    client = firestore_client or get_firestore_client()
    user_doc = client.collection('users').document(uid)
    action_items_col = user_doc.collection('action_items')
    staged_col = user_doc.collection('staged_tasks')
    migrated_query = LEGACY_CONVERSATION_RECOVERY_QUERY.build(
        staged_col,
        {'source': 'conversation_migration'},
        field_filter_factory=FieldFilter,
    ).order_by('__name__')
    if cursor:
        migrated_query = migrated_query.start_after({'__name__': staged_col.document(cursor)})
    # Read one look-ahead document so the caller can distinguish a complete
    # recovery from a page that must be continued with ``next_cursor``.
    migrated_rows = list(migrated_query.limit(limit + 1).stream())
    page = migrated_rows[:limit]
    has_more = len(migrated_rows) > limit
    next_cursor = page[-1].id if has_more and page else None
    restored = 0
    skipped_existing = 0

    for staged_snapshot in page:
        # Keep the marker check in addition to the indexed query so a permissive
        # fake or future query refactor can never restore an ordinary staged row.
        action_item_ref = action_items_col.document(staged_snapshot.id)
        staged_ref = staged_col.document(staged_snapshot.id)
        for attempt in range(LEGACY_CONVERSATION_RECOVERY_MAX_CONTENTION_RETRIES + 1):
            staged_row = staged_snapshot.to_dict() or {}
            if staged_row.get('source') != 'conversation_migration' or staged_row.get('completed'):
                break

            action_item = dict(staged_row)
            # `id` is document identity and `source` is the recovery marker, not
            # original action-item data. Recreating either would mutate the legacy
            # task's meaning rather than restoring it.
            action_item.pop('id', None)
            action_item.pop('source', None)

            batch = client.batch()
            batch.create(action_item_ref, action_item)
            # Keep the streamed staged row as the delete authority. If promotion
            # or another recovery attempt updates it after the query, Firestore
            # rejects the atomic batch instead of deleting the newer record.
            delete_option = client.write_option(last_update_time=staged_snapshot.update_time)
            batch.delete(staged_ref, option=delete_option)
            try:
                batch.commit()
            except (AlreadyExists, Conflict):
                # An action-item collision preserves both copies for the next
                # recovery pass or manual inspection.
                skipped_existing += 1
                break
            except FailedPrecondition:
                # A stale-row update is not an identity collision: it may be a
                # score or metadata write with no corresponding action item.
                # Refresh the row and retry so recovery never acknowledges an
                # arbitrary contention as complete. Exhaustion re-raises and
                # leaves the sweep unacknowledged for a later request.
                if attempt >= LEGACY_CONVERSATION_RECOVERY_MAX_CONTENTION_RETRIES:
                    raise
                refreshed_snapshot = staged_ref.get()
                if not refreshed_snapshot.exists:
                    break
                staged_snapshot = refreshed_snapshot
                continue
            else:
                restored += 1
                break

    return {
        'restored': restored,
        'skipped_existing': skipped_existing,
        'has_more': has_more,
        'next_cursor': next_cursor,
    }

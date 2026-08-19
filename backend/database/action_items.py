from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, Iterable, List, Optional, Protocol, cast

from google.api_core.exceptions import NotFound
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database.firestore_read_metrics import FirestoreReadFamily, FirestoreReadMode, record_firestore_read
from ._client import db, get_firestore_client

logger = logging.getLogger(__name__)


# Collection name
action_items_collection = 'action_items'
TASK_INTELLIGENCE_CONTROL_COLLECTION = 'task_intelligence_control'
TASK_INTELLIGENCE_CONTROL_DOCUMENT = 'state'


class TaskRelationshipConflictError(ValueError):
    pass


def validate_task_relationship_in_transaction(
    uid: str,
    *,
    goal_id: Optional[str],
    workstream_id: Optional[str],
    transaction: Any,
    firestore_client: Any = None,
    allow_ended_goal: bool = False,
    account_generation: Optional[int] = None,
) -> None:
    """Final relationship check that participates in the caller's task-write transaction."""

    client = firestore_client or db
    user_ref = client.collection('users').document(uid)
    if goal_id is not None:
        goal_snapshot = user_ref.collection('goals').document(goal_id).get(transaction=transaction)
        if not goal_snapshot.exists:
            raise TaskRelationshipConflictError('goal does not exist')
        goal = _typed_doc(goal_snapshot)
        if account_generation is not None and goal.get('account_generation', 0) != account_generation:
            raise TaskRelationshipConflictError('goal account generation mismatch')
        status = goal.get('status')
        if not allow_ended_goal and (
            status in {'achieved', 'abandoned'} or (status is None and goal.get('is_active') is False)
        ):
            raise TaskRelationshipConflictError('ended goal cannot receive new task links')
    if workstream_id is not None:
        workstream_snapshot = user_ref.collection('workstreams').document(workstream_id).get(transaction=transaction)
        if not workstream_snapshot.exists:
            raise TaskRelationshipConflictError('workstream does not exist')
        workstream = _typed_doc(workstream_snapshot)
        if account_generation is not None and workstream.get('account_generation', 0) != account_generation:
            raise TaskRelationshipConflictError('workstream account generation mismatch')
        if workstream.get('goal_id') != goal_id:
            raise TaskRelationshipConflictError('task goal_id must match workstream goal_id')


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Typed adapter for a Firestore DocumentSnapshot.to_dict() result.

    Returns an empty dict when the document has no fields (None payload),
    so callers can safely mutate the result without None checks.
    """
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


class _BatchUpdateEntry(Protocol):
    """Structural type for batch update entries (matches BatchUpdateActionItemEntry)."""

    id: str
    sort_order: Optional[int]
    indent_level: Optional[int]


@dataclass
class BatchMutationResult:
    """Outcome for partial batch mutations where missing ids must be explicit."""

    updated_ids: List[str] = field(default_factory=list[str])
    missing_ids: List[str] = field(default_factory=list[str])
    noop_ids: List[str] = field(default_factory=list[str])

    @property
    def updated_count(self) -> int:
        return len(self.updated_ids)

    def model(self) -> Dict[str, Any]:
        return {
            'updated_count': len(self.updated_ids),
            'updated_ids': self.updated_ids,
            'missing_ids': self.missing_ids,
            'noop_ids': self.noop_ids,
        }


def get_action_item_ids(uid: str) -> List[str]:
    """Return all action item document IDs for a user (IDs-only projection, no field reads).

    Used for bulk operations like account deletion (e.g. to purge derived Pinecone vectors)."""
    coll = db.collection('users').document(uid).collection(action_items_collection)
    return [doc.id for doc in coll.select([]).stream()]


def get_visible_action_item_ids(
    uid: str,
    *,
    completed: bool,
    firestore_client: Any = None,
) -> List[str]:
    """Return IDs in one visible Tasks status bucket.

    The account-wide ID census intentionally includes every document for reconciliation
    and account deletion. UI Select All needs a narrower contract: exclude soft-deleted
    rows and include only rows that the explicit ``completed`` list filter can render.

    The ``completed`` filter is pushed server-side via ``FieldFilter`` so Firestore only
    streams (and bills) documents in the requested bucket, instead of the whole collection.
    Firestore equality does not match documents where the field is absent and does not
    conflate 1/0 with booleans, so this is equivalent to the old Python identity check
    (``completed_value is completed``) for every doc the query now returns.

    ``deleted`` is deliberately NOT pushed into the query as
    ``.where('deleted', '==', False)``: Firestore equality filters never match documents
    where the field is absent, and most rows have no ``deleted`` field at all (it is only
    set on soft-deleted rows). A server-side filter on it would silently drop every
    undeleted row. Keep this check in Python instead.
    """
    client = firestore_client or get_firestore_client()
    coll = client.collection('users').document(uid).collection(action_items_collection)
    query = coll.select(['completed', 'deleted']).where(filter=FieldFilter('completed', '==', completed))
    visible_ids: List[str] = []
    doc_count = 0
    for doc in query.stream():
        doc_count += 1
        data = _typed_doc(doc)
        if data.get('deleted'):
            continue
        visible_ids.append(doc.id)
    record_firestore_read(
        FirestoreReadFamily.ACTION_ITEMS_VISIBLE_IDS,
        FirestoreReadMode.UNBOUNDED,
        doc_count,
    )
    return visible_ids


def _prepare_action_item_for_write(action_item_data: Dict[str, Any], *, partial: bool = False) -> Dict[str, Any]:
    """Prepare action item data for writing to database"""
    action_item_data = dict(action_item_data)
    if not partial or 'status' in action_item_data or 'completed' in action_item_data:
        status = action_item_data.get('status')
        completed = action_item_data.get('completed')
        if status is None:
            status = 'completed' if completed is True else 'active'
            action_item_data['status'] = status
        if completed is None:
            action_item_data['completed'] = status == 'completed'
        elif completed != (status == 'completed'):
            raise ValueError('completed must agree with canonical status')
    if not partial:
        action_item_data.setdefault('owner', 'unknown')
        action_item_data.setdefault('source', 'legacy')
        action_item_data.setdefault('provenance', [])
        action_item_data.setdefault('sort_order', 0)
        action_item_data.setdefault('indent_level', 0)
    # Normalize date fields to timezone-aware UTC datetimes. These can arrive as
    # ISO strings or datetime objects from tool-/LLM-created action items (extraction
    # models use plain ``datetime``, not ``AwareDatetime``). Firestore rejects
    # tz-naive datetimes, and a failed batch create on the fire-and-forget
    # postprocess path silently drops extracted tasks. Mirror
    # ``api_key_metadata._coerce_utc_datetime`` / ``mcp_action_items.parse_due_at``:
    # parse strings tolerantly, attach UTC to naive values, drop only malformed
    # / out-of-range values (ValueError or OverflowError from UTC normalization)
    # so a single bad field cannot 500 the whole create/update or batch.
    for date_field in ('created_at', 'updated_at', 'due_at', 'completed_at'):
        value = action_item_data.get(date_field)
        if value is None or value == '':
            if date_field in action_item_data and value == '':
                action_item_data.pop(date_field, None)
            continue
        try:
            if isinstance(value, datetime):
                parsed = value
            elif isinstance(value, str):
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            else:
                logger.warning(
                    "Dropping non-datetime %s type=%s on action item write",
                    date_field,
                    type(value).__name__,
                )
                action_item_data.pop(date_field, None)
                continue

            # OverflowError: boundary aware values whose offset conversion leaves
            # Python's datetime range (same tolerance as api_key_metadata).
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
        except (OverflowError, ValueError):
            logger.warning("Dropping malformed %s=%r on action item write", date_field, value)
            action_item_data.pop(date_field, None)
            continue
        action_item_data[date_field] = parsed

    return action_item_data


def _prepare_action_item_for_read(action_item_data: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare action item data for reading from database"""
    # `completed` may be missing OR explicitly null (legacy/partial writes). setdefault
    # won't overwrite an existing null, so drop it first and let status derive a concrete
    # bool — strict client parsers reject a null `completed` and drop the whole page.
    if action_item_data.get('completed') is None:
        action_item_data.pop('completed', None)
    action_item_data.setdefault('status', 'completed' if action_item_data.get('completed') else 'active')
    action_item_data.setdefault('completed', action_item_data['status'] == 'completed')
    action_item_data.setdefault('owner', 'unknown')
    action_item_data.setdefault('source', 'legacy')
    action_item_data.setdefault('provenance', [])
    action_item_data.setdefault('sort_order', 0)
    action_item_data.setdefault('indent_level', 0)
    for field in ['created_at', 'updated_at', 'due_at', 'completed_at']:
        if field in action_item_data and action_item_data[field]:
            if hasattr(action_item_data[field], 'timestamp'):
                action_item_data[field] = datetime.fromtimestamp(action_item_data[field].timestamp(), tz=timezone.utc)
    return action_item_data


# *****************************
# ********** CREATE ***********
# *****************************


def create_action_item(
    uid: str,
    action_item_data: Dict[str, Any],
    idempotency_key: Optional[str] = None,
    *,
    document_id: Optional[str] = None,
) -> str:
    """
    Create a new action item for a user.

    Args:
        uid: User ID
        action_item_data: Action item data including description, dates, etc.
        idempotency_key: Optional opaque key. When supplied, the function looks
            for an existing action_item with the same key (any state) and returns
            its id without creating a new document. This makes the call safe to
            retry on flaky networks or duplicate event delivery — the previous
            behaviour silently allocated a fresh Firestore id on every call,
            producing user-visible duplicates. The key is stored on the
            document so future calls can find it. Callers that want
            content-based idempotency typically pass
            ``hashlib.sha256(f"{uid}:{normalized_description}".encode()).hexdigest()``.
        document_id: Optional caller-reserved Firestore document id. Reusing
            the id returns the existing document without rewriting it, making
            a crash-retried create deterministic.

    Returns:
        The ID of the created (or pre-existing, when idempotency_key matches)
        action item.
    """
    action_item_data = _prepare_action_item_for_write(action_item_data)
    user_ref = db.collection('users').document(uid)
    action_items_ref = user_ref.collection(action_items_collection)

    if 'created_at' not in action_item_data:
        action_item_data['created_at'] = datetime.now(timezone.utc)
    if 'updated_at' not in action_item_data:
        action_item_data['updated_at'] = datetime.now(timezone.utc)

    # Set completed_at if the item is being created as completed
    if action_item_data.get('completed', False) and 'completed_at' not in action_item_data:
        action_item_data['completed_at'] = datetime.now(timezone.utc)

    if idempotency_key:
        action_item_data['idempotency_key'] = idempotency_key

    goal_id = action_item_data.get('goal_id')
    workstream_id = action_item_data.get('workstream_id')
    if document_id is not None and not document_id:
        raise ValueError('document_id must not be empty')
    doc_ref = action_items_ref.document(document_id) if document_id is not None else action_items_ref.document()

    @firestore.transactional
    def create_in_generation(write_transaction):
        control_snapshot = (
            user_ref.collection(TASK_INTELLIGENCE_CONTROL_COLLECTION)
            .document(TASK_INTELLIGENCE_CONTROL_DOCUMENT)
            .get(transaction=write_transaction)
        )
        control = _typed_doc(control_snapshot) if control_snapshot.exists else {}
        account_generation = int(control.get('account_generation', 0))
        if idempotency_key:
            existing_query = action_items_ref.where(filter=FieldFilter('idempotency_key', '==', idempotency_key)).where(
                filter=FieldFilter('completed', '==', False)
            )
            if account_generation > 0:
                existing_query = existing_query.where(
                    filter=FieldFilter('account_generation', '==', account_generation)
                )
            existing_query = existing_query.limit(5)
            for existing in existing_query.stream(transaction=write_transaction):
                data = _typed_doc(existing)
                if account_generation == 0 and int(data.get('account_generation', 0)) != 0:
                    continue
                if not data.get('deleted'):
                    return existing.id
        if document_id is not None:
            existing_document = doc_ref.get(transaction=write_transaction)
            if existing_document.exists:
                existing_generation = int(_typed_doc(existing_document).get('account_generation', 0))
                if existing_generation != account_generation:
                    raise TaskRelationshipConflictError('document id belongs to another account generation')
                return document_id
        if goal_id is not None or workstream_id is not None:
            validate_task_relationship_in_transaction(
                uid,
                goal_id=cast(Optional[str], goal_id),
                workstream_id=cast(Optional[str], workstream_id),
                transaction=write_transaction,
                firestore_client=db,
                account_generation=account_generation,
            )
        payload = dict(action_item_data)
        payload['account_generation'] = account_generation
        write_transaction.set(doc_ref, payload)
        return doc_ref.id

    return cast(
        str,
        run_with_transaction_contention_retry(
            db.transaction,
            create_in_generation,
            operation_name="action_item_create",
        ),
    )


def create_action_items_batch(
    uid: str,
    action_items_data: List[Dict[str, Any]],
    *,
    document_ids: Optional[List[str]] = None,
) -> List[str]:
    """
    Create multiple action items in a batch operation.

    Args:
        uid: User ID
        action_items_data: List of action item data dictionaries

    Returns:
        List of created action item IDs
    """
    if not action_items_data:
        return []
    if document_ids is not None and len(document_ids) != len(action_items_data):
        raise ValueError('document_ids must match action_items_data length')

    user_ref = db.collection('users').document(uid)
    action_items_ref = user_ref.collection(action_items_collection)

    doc_refs: List[str] = []
    prepared_items: List[Dict[str, Any]] = []
    document_refs: List[Any] = []

    for index, action_item_data in enumerate(action_items_data):
        action_item_data = _prepare_action_item_for_write(action_item_data)

        if 'created_at' not in action_item_data:
            action_item_data['created_at'] = datetime.now(timezone.utc)
        if 'updated_at' not in action_item_data:
            action_item_data['updated_at'] = datetime.now(timezone.utc)

        # Set completed_at if the item is being created as completed
        if action_item_data.get('completed', False) and 'completed_at' not in action_item_data:
            action_item_data['completed_at'] = datetime.now(timezone.utc)

        doc_ref = (
            action_items_ref.document(document_ids[index]) if document_ids is not None else action_items_ref.document()
        )
        prepared_items.append(action_item_data)
        document_refs.append(doc_ref)
        doc_refs.append(doc_ref.id)

    if len(prepared_items) > 400:
        raise ValueError('action-item batches are limited to 400 items')

    @firestore.transactional
    def create_batch_in_generation(write_transaction):
        control_snapshot = (
            user_ref.collection(TASK_INTELLIGENCE_CONTROL_COLLECTION)
            .document(TASK_INTELLIGENCE_CONTROL_DOCUMENT)
            .get(transaction=write_transaction)
        )
        control = _typed_doc(control_snapshot) if control_snapshot.exists else {}
        account_generation = int(control.get('account_generation', 0))
        if any(item.get('goal_id') is not None or item.get('workstream_id') is not None for item in prepared_items):
            for item in prepared_items:
                validate_task_relationship_in_transaction(
                    uid,
                    goal_id=cast(Optional[str], item.get('goal_id')),
                    workstream_id=cast(Optional[str], item.get('workstream_id')),
                    transaction=write_transaction,
                    firestore_client=db,
                    account_generation=account_generation,
                )
        for doc_ref, item in zip(document_refs, prepared_items):
            write_transaction.set(doc_ref, {**item, 'account_generation': account_generation})
        return doc_refs

    return cast(
        List[str],
        run_with_transaction_contention_retry(
            db.transaction,
            create_batch_in_generation,
            operation_name="action_item_batch_create",
        ),
    )


# *****************************
# ********** READ *************
# *****************************


def get_action_item(uid: str, action_item_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single action item by ID.

    Args:
        uid: User ID
        action_item_id: Action item ID

    Returns:
        Action item data or None if not found
    """
    user_ref = db.collection('users').document(uid)
    action_item_ref = user_ref.collection(action_items_collection).document(action_item_id)
    doc = action_item_ref.get()

    if not doc.exists:
        return None

    data: Dict[str, Any] = _typed_doc(doc)
    data['id'] = doc.id
    return _prepare_action_item_for_read(data)


# Hard safety caps for list reads. Unbounded streams + in-process sort caused prod GET
# /v1/action-items to hit HTTP_GET_TIMEOUT (30s) → 504 on large accounts.
_ACTION_ITEMS_LIST_HARD_MAX = 2000
# Slack so a handful of soft-deleted rows in a Firestore prefix still fill the page.
_ACTION_ITEMS_LIST_DELETED_SLACK = 32
# Lean projection for GET /v1/action-items. Omit `provenance` (evidence arrays dominate
# payload on large accounts; ActionItemResponse defaults it to []). Do not add
# `order_by due_at` here: missing `due_at` is excluded from that index and would
# drop undated tasks. Existing `action_items_completed_due` stays for due-range reads.
_ACTION_ITEMS_LIST_SELECT_FIELDS = (
    'description',
    'status',
    'completed',
    'deleted',
    'goal_id',
    'workstream_id',
    'owner',
    'due_at',
    'due_confidence',
    'source',
    'priority',
    'sort_order',
    'indent_level',
    'recurrence_rule',
    'recurrence_parent_id',
    'created_at',
    'updated_at',
    'completed_at',
    'superseded_by',
    'conversation_id',
    'is_locked',
    'exported',
    'export_date',
    'export_platform',
    'apple_reminder_id',
)


def _list_scan_budget(row_budget: int) -> int:
    """Docs to pull for one page: the page itself plus deleted slack, never 2× the page."""
    if row_budget <= 0:
        return 0
    return min(_ACTION_ITEMS_LIST_HARD_MAX, int(row_budget) + _ACTION_ITEMS_LIST_DELETED_SLACK)


def _action_item_list_sort_key(item: Dict[str, Any]) -> tuple:
    """Active-first product order (see get_action_items)."""
    return (
        bool(item.get('completed')),
        item.get('due_at') is None,
        item.get('due_at') or datetime.max.replace(tzinfo=timezone.utc),
        -(item.get('created_at', datetime.min.replace(tzinfo=timezone.utc)).timestamp()),
    )


def _stream_action_items_bounded(query: Any, *, max_docs: int) -> tuple[List[Dict[str, Any]], int]:
    """Stream at most max_docs Firestore documents; skip soft-deleted rows.

    Applies a field projection and a Firestore ``limit`` so the backend process
    never downloads full documents past the page budget (Python ``break`` alone
    still lets the client library buffer the rest of the stream).
    """
    action_items: List[Dict[str, Any]] = []
    document_count = 0
    if max_docs <= 0:
        return action_items, 0
    query = query.select(list(_ACTION_ITEMS_LIST_SELECT_FIELDS)).limit(max_docs)
    for doc in query.stream():
        document_count += 1
        data: Dict[str, Any] = _typed_doc(doc)
        if data.get('deleted'):
            if document_count >= max_docs:
                break
            continue
        data['id'] = doc.id
        action_items.append(_prepare_action_item_for_read(data))
        if document_count >= max_docs:
            break
    return action_items, document_count


def _apply_action_item_date_filters(
    query: Any,
    *,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    due_start_date: Optional[datetime],
    due_end_date: Optional[datetime],
) -> Any:
    due_at_filtering = due_start_date is not None or due_end_date is not None
    if due_at_filtering:
        if due_start_date is not None:
            query = query.where(filter=FieldFilter('due_at', '>=', due_start_date))
        if due_end_date is not None:
            query = query.where(filter=FieldFilter('due_at', '<=', due_end_date))
        # Soonest-due first so a bounded prefix matches product sort on due_at.
        query = query.order_by('due_at', direction=firestore.Query.ASCENDING)
        return query
    if start_date is not None:
        query = query.where(filter=FieldFilter('created_at', '>=', start_date))
    if end_date is not None:
        query = query.where(filter=FieldFilter('created_at', '<=', end_date))
    if start_date is not None or end_date is not None:
        query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
    return query


def get_action_items(
    uid: str,
    conversation_id: Optional[str] = None,
    completed: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    due_start_date: Optional[datetime] = None,
    due_end_date: Optional[datetime] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Get action items for a user with optional filters.

    Default (completed=None) lists preserve active-first product order by reading the
    incomplete bucket first, then the completed bucket — never a full-collection stream.
    Legacy documents with missing/null ``completed`` are harvested via a separate bounded
    unfiltered scan and treated as active after ``_prepare_action_item_for_read``.
    All paths are hard-capped so GET /v1/action-items cannot unbounded-scan under
    HTTP_GET_TIMEOUT. Pagination is applied after the product sort. When
    ``completed`` is set, the scan budget is the page plus deleted slack
    (not 2× the page). Offset is a live-item slice after that sort so it stays
    aligned with Windows ``offset += items.length`` — Firestore ``offset``
    counts deleted documents and would skip/duplicate across pages.
    """
    offset = max(0, int(offset or 0))
    if limit is None or limit <= 0:
        effective_limit = _ACTION_ITEMS_LIST_HARD_MAX
    else:
        effective_limit = min(int(limit), _ACTION_ITEMS_LIST_HARD_MAX)

    need = min(offset + effective_limit, _ACTION_ITEMS_LIST_HARD_MAX)
    total_docs = 0

    def _base_query() -> Any:
        user_ref = db.collection('users').document(uid)
        q = user_ref.collection(action_items_collection)
        if conversation_id is not None:
            q = q.where(filter=FieldFilter('conversation_id', '==', conversation_id))
        return _apply_action_item_date_filters(
            q,
            start_date=start_date,
            end_date=end_date,
            due_start_date=due_start_date,
            due_end_date=due_end_date,
        )

    def _fetch_filtered(completed_filter: Optional[bool], row_budget: int) -> List[Dict[str, Any]]:
        nonlocal total_docs
        if row_budget <= 0:
            return []
        q = _base_query()
        if completed_filter is not None:
            q = q.where(filter=FieldFilter('completed', '==', completed_filter))
        items, docs = _stream_action_items_bounded(q, max_docs=_list_scan_budget(row_budget))
        total_docs += docs
        items.sort(key=_action_item_list_sort_key)
        return items[:row_budget]

    if completed is not None:
        action_items = _fetch_filtered(completed, need)
    else:
        # Explicit incomplete first (server-side equality — excludes missing-field legacy docs).
        active = _fetch_filtered(False, need)
        seen = {item['id'] for item in active}
        # Legacy/partial docs: completed missing or null. Equality filters exclude them; harvest
        # with a bounded unfiltered scan and keep only those that prepare to active and are new.
        if len(active) < need:
            # Bound unfiltered scan generously enough to product-sort before capping:
            # early-stopping mid-stream would freeze Firestore order instead of due-date order.
            legacy_scan = min(
                _ACTION_ITEMS_LIST_HARD_MAX,
                max(need * 8, 128),
            )
            raw_legacy, docs = _stream_action_items_bounded(_base_query(), max_docs=legacy_scan)
            total_docs += docs
            for item in raw_legacy:
                if item['id'] in seen:
                    continue
                # Only pull true actives from the unfiltered scan into the active bucket.
                if item.get('completed'):
                    continue
                active.append(item)
                seen.add(item['id'])
            active.sort(key=_action_item_list_sort_key)
            active = active[:need]

        if len(active) >= need:
            action_items = active
        else:
            done = _fetch_filtered(True, need - len(active))
            # Drop any ids already present from legacy harvest
            done = [item for item in done if item['id'] not in seen]
            action_items = active + done

    record_firestore_read(
        FirestoreReadFamily.ACTION_ITEMS_LIST,
        FirestoreReadMode.BOUNDED,
        total_docs,
    )

    if offset > 0:
        action_items = action_items[offset:]
    return action_items[:effective_limit]


def _normalize_description(desc: Optional[str]) -> str:
    """Normalize a task description for case-insensitive duplicate matching.

    Strips whitespace + the legacy ``[screen]`` prefix/suffix marker that the
    AI promotion pipeline used to add to AI-generated tasks (still appears in
    historical data and on tasks that round-tripped through ``migrate_ai_tasks``).
    """
    if not desc:
        return ''
    s = desc.strip()
    if s.startswith('[screen] '):
        s = s[len('[screen] ') :]
    if s.endswith(' [screen]'):
        s = s[: -len(' [screen]')]
    return s.strip().lower()


def normalize_action_item_description(description: str) -> str:
    """Public normalization seam for cross-source idempotency keys."""
    return _normalize_description(description)


def get_active_action_item_by_description(uid: str, description: str) -> Optional[Dict[str, Any]]:
    """Find an active (not completed, not deleted) action_item with a matching
    description for the given user, or return None.

    Match is case-insensitive and ignores ``[screen]`` markers and surrounding
    whitespace, mirroring ``database.staged_tasks.create_staged_task``'s
    dedup logic so that the staged → action_item promotion path can avoid
    creating semantic duplicates.

    Streams active items (typically a small bounded set per user) rather than
    relying on a Firestore equality filter, because Firestore cannot do
    case-insensitive matching natively without a normalized companion field.
    """
    target = _normalize_description(description)
    if not target:
        return None

    user_ref = db.collection('users').document(uid)
    query = user_ref.collection(action_items_collection).where(filter=FieldFilter('completed', '==', False))

    for doc in query.stream():
        data: Dict[str, Any] = _typed_doc(doc)
        if data.get('deleted'):
            continue
        if _normalize_description(data.get('description')) == target:
            data['id'] = doc.id
            return _prepare_action_item_for_read(data)

    return None


def get_action_items_by_conversation(uid: str, conversation_id: str) -> List[Dict[str, Any]]:
    """
    Get all action items for a specific conversation.

    Args:
        uid: User ID
        conversation_id: Conversation ID

    Returns:
        List of action items for the conversation
    """
    return get_action_items(uid, conversation_id=conversation_id)


def get_action_items_count_by_conversation(uid: str, conversation_id: str) -> Dict[str, int]:
    """Return total / completed / incomplete action-item counts for one conversation.

    Uses Firestore count() aggregation with the same conversation_id predicate as
    get_action_items_by_conversation, so a client can render a task-progress badge
    (e.g. 2 of 3 done) without paging the items. Soft-retired items (``deleted: true``)
    are hidden from the list/read paths, so they are excluded here too; otherwise the
    badge would drift from what the client can list. incomplete = total - completed,
    clamped at 0 so the three values stay internally consistent.
    """
    base = (
        db.collection('users')
        .document(uid)
        .collection(action_items_collection)
        .where(filter=FieldFilter('conversation_id', '==', conversation_id))
    )
    total = int(base.count().get()[0][0].value)
    completed = int(base.where(filter=FieldFilter('completed', '==', True)).count().get()[0][0].value)

    # Exclude soft-retired items so the badge matches the visible list (get_action_items skips
    # data.get('deleted')). Deleted items are rare, so stream just that subset and subtract, rather
    # than requiring a filtered-aggregation composite index.
    deleted_total = 0
    deleted_completed = 0
    for doc in base.where(filter=FieldFilter('deleted', '==', True)).stream():
        deleted_total += 1
        if (doc.to_dict() or {}).get('completed'):
            deleted_completed += 1

    total = max(0, total - deleted_total)
    completed = max(0, completed - deleted_completed)
    # total and completed come from separate (non-atomic) count() aggregations, so a concurrent write
    # between them can leave completed > total. Cap it so the three values stay internally consistent.
    completed = min(completed, total)
    return {'total': total, 'completed': completed, 'incomplete': max(0, total - completed)}


def get_action_items_by_ids(uid: str, action_item_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Get multiple action items by their IDs in a single batch operation.

    Args:
        uid: User ID
        action_item_ids: List of action item IDs

    Returns:
        List of action items (only those that exist), in the same order as the input IDs
    """
    if not action_item_ids:
        return []

    user_ref = db.collection('users').document(uid)
    action_items_ref = user_ref.collection(action_items_collection)

    # Firestore batch get operation
    doc_refs = [action_items_ref.document(item_id) for item_id in action_item_ids]
    docs = db.get_all(doc_refs)

    # Create a map to preserve order
    action_items_map: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        if doc.exists:
            data: Dict[str, Any] = _typed_doc(doc)
            data['id'] = doc.id
            action_item = _prepare_action_item_for_read(data)
            action_items_map[doc.id] = action_item

    # Return in the same order as input IDs
    action_items: List[Dict[str, Any]] = []
    for item_id in action_item_ids:
        if item_id in action_items_map:
            action_items.append(action_items_map[item_id])

    return action_items


# *****************************
# ********** UPDATE ***********
# *****************************


def update_action_item(uid: str, action_item_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Update an action item.

    Args:
        uid: User ID
        action_item_id: Action item ID
        update_data: Fields to update

    Returns:
        True if updated successfully, False otherwise
    """
    # Prepare data
    update_data = _prepare_action_item_for_write(update_data, partial=True)

    user_ref = db.collection('users').document(uid)
    action_item_ref = user_ref.collection(action_items_collection).document(action_item_id)

    if 'goal_id' in update_data or 'workstream_id' in update_data:
        now = datetime.now(timezone.utc)

        @firestore.transactional
        def update_linked(write_transaction):
            snapshot = action_item_ref.get(transaction=write_transaction)
            if not snapshot.exists:
                return False
            current = _typed_doc(snapshot)
            goal_id = update_data.get('goal_id') if 'goal_id' in update_data else current.get('goal_id')
            workstream_id = (
                update_data.get('workstream_id') if 'workstream_id' in update_data else current.get('workstream_id')
            )
            validate_task_relationship_in_transaction(
                uid,
                goal_id=cast(Optional[str], goal_id),
                workstream_id=cast(Optional[str], workstream_id),
                transaction=write_transaction,
                firestore_client=db,
                allow_ended_goal=(goal_id, workstream_id) == (current.get('goal_id'), current.get('workstream_id')),
            )
            write_transaction.update(action_item_ref, {**update_data, 'updated_at': now})
            return True

        return bool(
            run_with_transaction_contention_retry(
                db.transaction,
                update_linked,
                operation_name="action_item_linked_update",
            )
        )

    # Check if exists
    if not action_item_ref.get().exists:
        return False

    # Add updated timestamp
    update_data['updated_at'] = datetime.now(timezone.utc)

    # Update the document
    action_item_ref.update(update_data)

    return True


def batch_update_action_items(uid: str, items: Iterable[_BatchUpdateEntry]) -> BatchMutationResult:
    """

    Missing IDs are returned explicitly. Each document update is applied
    independently so a concurrent delete cannot make Firestore reject an entire
    mutation after an earlier existence pre-read succeeded.
    """
    result = BatchMutationResult()
    if not items:
        return result

    user_ref = db.collection('users').document(uid)
    action_items_ref = user_ref.collection(action_items_collection)
    now = datetime.now(timezone.utc)

    for item in items:
        doc_ref = action_items_ref.document(item.id)
        update_data: Dict[str, Any] = {'updated_at': now}
        if item.sort_order is not None:
            update_data['sort_order'] = item.sort_order
        if item.indent_level is not None:
            update_data['indent_level'] = item.indent_level

        if len(update_data) == 1:
            result.noop_ids.append(item.id)
            continue

        try:
            doc_ref.update(update_data)
        except NotFound:
            result.missing_ids.append(item.id)
            continue
        result.updated_ids.append(item.id)

    return result


def mark_action_item_completed(uid: str, action_item_id: str, completed: bool = True) -> bool:
    """
    Mark an action item as completed or uncompleted.

    Args:
        uid: User ID
        action_item_id: Action item ID
        completed: Completion status

    Returns:
        True if updated successfully, False otherwise
    """
    update_data: Dict[str, Any] = {
        'completed': completed,
        'completed_at': datetime.now(timezone.utc) if completed else None,
    }
    return update_action_item(uid, action_item_id, update_data)


# *****************************
# ********** DELETE ***********
# *****************************


def delete_action_item(uid: str, action_item_id: str) -> bool:
    """
    Delete an action item.

    Args:
        uid: User ID
        action_item_id: Action item ID

    Returns:
        True if deleted successfully, False otherwise
    """
    user_ref = db.collection('users').document(uid)
    action_item_ref = user_ref.collection(action_items_collection).document(action_item_id)

    # Check if exists
    if not action_item_ref.get().exists:
        return False

    # Delete the document
    action_item_ref.delete()

    return True


def delete_action_items_batch(uid: str, action_item_ids: List[str]) -> List[str]:
    """
    Delete multiple action items by id, chunking into 500-op Firestore batches.

    Skips per-id existence reads: batch.delete() is a no-op for missing
    docs, and downstream vector + FCM cleanup are both idempotent for
    unknown ids.
    """
    if not action_item_ids:
        return []

    user_ref = db.collection('users').document(uid)
    action_items_ref = user_ref.collection(action_items_collection)

    batch = db.batch()
    count = 0

    for item_id in action_item_ids:
        batch.delete(action_items_ref.document(item_id))
        count += 1
        if count >= 499:  # Firestore batch limit is 500
            batch.commit()
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()

    return list(action_item_ids)


def delete_action_items_for_conversation(uid: str, conversation_id: str) -> int:
    """
    Delete all action items for a specific conversation.

    Args:
        uid: User ID
        conversation_id: Conversation ID

    Returns:
        Number of deleted items
    """
    user_ref = db.collection('users').document(uid)
    query = user_ref.collection(action_items_collection).where(
        filter=FieldFilter('conversation_id', '==', conversation_id)
    )

    docs = query.stream()
    batch = db.batch()
    count = 0

    for doc in docs:
        batch.delete(doc.reference)
        count += 1

    if count > 0:
        batch.commit()

    return count


def retire_action_items_for_conversation(
    uid: str,
    conversation_id: str,
    *,
    active_ids: List[str],
    replacements: Optional[Dict[str, str]] = None,
) -> int:
    """Soft-retire removed write-mode projections so accepted Candidate receipts keep a target."""
    active_id_set = set(active_ids)
    replacement_map = replacements or {}
    query = (
        db.collection('users')
        .document(uid)
        .collection(action_items_collection)
        .where(filter=FieldFilter('conversation_id', '==', conversation_id))
    )
    batch = db.batch()
    count = 0
    now = datetime.now(timezone.utc)
    for doc in query.stream():
        if doc.id in active_id_set:
            continue
        replacement_id = replacement_map.get(doc.id)
        batch.update(
            doc.reference,
            {
                'deleted': True,
                'status': 'superseded' if replacement_id else 'cancelled',
                'completed': False,
                'completed_at': None,
                'superseded_by': replacement_id,
                'updated_at': now,
            },
        )
        count += 1
    if count:
        batch.commit()
    return count


# *****************************
# ****** REMINDERS SYNC *******
# *****************************


def batch_set_sync_requested(uid: str, item_ids: List[str]) -> None:
    """Mark multiple action items as sync_requested in a single batch write."""
    if not item_ids:
        return

    user_ref = db.collection('users').document(uid)
    action_items_ref = user_ref.collection(action_items_collection)
    now = datetime.now(timezone.utc)

    batch = db.batch()
    for item_id in item_ids:
        doc_ref = action_items_ref.document(item_id)
        batch.update(doc_ref, {'sync_requested': True, 'updated_at': now})

    batch.commit()


def get_pending_apple_reminders_sync(uid: str) -> Dict[str, Any]:
    """
    Get items needing Apple Reminders sync:
    - pending_export: sync_requested=True but not yet exported (FCM missed items)
    - synced_items: exported to apple_reminders with apple_reminder_id (for bidirectional sync)
    """
    user_ref = db.collection('users').document(uid)
    items_ref = user_ref.collection(action_items_collection)

    # Pending export: sync_requested=True, filter exported!=True in Python
    # (avoids composite index + handles missing 'exported' field)
    pending_query = items_ref.where(filter=FieldFilter('sync_requested', '==', True)).limit(50)
    pending_docs = pending_query.stream()
    pending_export: List[Dict[str, Any]] = []
    for doc in pending_docs:
        data: Dict[str, Any] = _typed_doc(doc)
        if data.get('exported') is True:
            continue
        data['id'] = doc.id
        pending_export.append(_prepare_action_item_for_read(data))

    # Synced items: exported to apple_reminders (for bidirectional sync)
    # Uses only equality filters to avoid composite index requirement
    synced_query = (
        items_ref.where(filter=FieldFilter('export_platform', '==', 'apple_reminders'))
        .where(filter=FieldFilter('exported', '==', True))
        .limit(100)
    )
    synced_docs = synced_query.stream()
    synced_items: List[Dict[str, Any]] = []
    for doc in synced_docs:
        data = _typed_doc(doc)
        data['id'] = doc.id
        synced_items.append(_prepare_action_item_for_read(data))
    # Sort by updated_at desc in Python instead of Firestore (avoids composite index)
    synced_items.sort(key=lambda x: x.get('updated_at') or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    return {"pending_export": pending_export, "synced_items": synced_items}


def batch_sync_update_action_items(uid: str, updates: List[Dict[str, Any]]) -> BatchMutationResult:
    """
    Batch update action items during reminders sync.

    Missing IDs are returned explicitly; each document update is applied
    independently so a concurrent delete cannot fail the whole request after an
    existence pre-read. Callers should use only updated_ids for downstream
    vector/cache work.
    """
    result = BatchMutationResult()
    if not updates:
        return result

    user_ref = db.collection('users').document(uid)
    action_items_ref = user_ref.collection(action_items_collection)
    now = datetime.now(timezone.utc)

    for entry in updates:
        doc_ref = action_items_ref.document(entry['id'])
        update_data = _prepare_action_item_for_write(entry['data'], partial=True)
        update_data['updated_at'] = now
        # Clear sync_requested when item is successfully exported
        if update_data.get('exported') is True:
            update_data['sync_requested'] = False
        try:
            doc_ref.update(update_data)
        except NotFound:
            result.missing_ids.append(entry['id'])
            continue
        result.updated_ids.append(entry['id'])

    return result


def unlock_all_action_items(uid: str) -> None:
    """
    Finds all action items for a user with is_locked: True and updates them to is_locked = False.
    """
    action_items_ref = db.collection('users').document(uid).collection(action_items_collection)
    locked_items_query = action_items_ref.where(filter=FieldFilter('is_locked', '==', True))

    batch = db.batch()
    docs = locked_items_query.stream()
    count = 0
    for doc in docs:
        batch.update(doc.reference, {'is_locked': False})
        count += 1
        if count >= 499:  # Firestore batch limit is 500
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()
    logger.info(f"Unlocked all action items for user {uid}")


# ============================================================================
# DAILY SCORE — computed from action_items
# ============================================================================


def get_daily_score(uid: str, date: Optional[str] = None) -> Dict[str, Any]:
    """Compute productivity score for a single day from action_items."""
    if date:
        day = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    else:
        day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    day_end = day + timedelta(days=1)
    col = db.collection('users').document(uid).collection(action_items_collection)

    # Count tasks due today
    due_query = col.where(filter=FieldFilter('due_at', '>=', day)).where(filter=FieldFilter('due_at', '<', day_end))
    total = 0
    completed = 0
    for doc in due_query.stream():
        data: Dict[str, Any] = _typed_doc(doc)
        if data.get('deleted'):
            continue
        total += 1
        if data.get('completed'):
            completed += 1

    score = round((completed / total * 100) if total > 0 else 0)
    return {'date': day.strftime('%Y-%m-%d'), 'score': score, 'completed_tasks': completed, 'total_tasks': total}


def get_scores(uid: str, date: Optional[str] = None) -> Dict[str, Any]:
    """Compute daily, weekly, and overall scores (matching Rust backend behavior).

    Takes a single date (or defaults to today) and returns:
      daily  — tasks due on that date
      weekly — tasks due in the 7 days ending on that date
      overall — all non-deleted tasks
    """
    if date:
        day = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    else:
        day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    day_start = day
    day_end = day + timedelta(days=1)
    # "7 days ending on that date" is inclusive of `day`, so the window is
    # [day-6, day+1) — mirroring the one-day daily window [day, day+1). Using
    # day-7 spanned 8 calendar days and over-counted the weekly totals.
    week_start = day - timedelta(days=6)

    col = db.collection('users').document(uid).collection(action_items_collection)

    def _score(completed: int, total: int) -> float:
        return round((completed / total * 100) if total > 0 else 0, 1)

    # Daily: tasks due today
    daily_q = col.where(filter=FieldFilter('due_at', '>=', day_start)).where(filter=FieldFilter('due_at', '<', day_end))
    daily_completed = daily_total = 0
    for doc in daily_q.stream():
        data: Dict[str, Any] = _typed_doc(doc)
        if data.get('deleted'):
            continue
        daily_total += 1
        if data.get('completed'):
            daily_completed += 1

    # Weekly: tasks created in last 7 days (matches Rust backend which uses created_at)
    weekly_q = col.where(filter=FieldFilter('created_at', '>=', week_start)).where(
        filter=FieldFilter('created_at', '<', day_end)
    )
    weekly_completed = weekly_total = 0
    for doc in weekly_q.stream():
        data = _typed_doc(doc)
        if data.get('deleted'):
            continue
        weekly_total += 1
        if data.get('completed'):
            weekly_completed += 1

    # Overall: all non-deleted tasks
    overall_completed = overall_total = 0
    for doc in col.stream():
        data = _typed_doc(doc)
        if data.get('deleted'):
            continue
        overall_total += 1
        if data.get('completed'):
            overall_completed += 1

    daily: Dict[str, Any] = {
        'score': _score(daily_completed, daily_total),
        'completed_tasks': daily_completed,
        'total_tasks': daily_total,
    }
    weekly: Dict[str, Any] = {
        'score': _score(weekly_completed, weekly_total),
        'completed_tasks': weekly_completed,
        'total_tasks': weekly_total,
    }
    overall: Dict[str, Any] = {
        'score': _score(overall_completed, overall_total),
        'completed_tasks': overall_completed,
        'total_tasks': overall_total,
    }

    # Determine default tab (highest score, prefer daily > weekly > overall)
    if daily['total_tasks'] > 0 and daily['score'] >= weekly['score'] and daily['score'] >= overall['score']:
        default_tab = 'daily'
    elif weekly['score'] >= overall['score']:
        default_tab = 'weekly'
    else:
        default_tab = 'overall'

    return {
        'daily': daily,
        'weekly': weekly,
        'overall': overall,
        'default_tab': default_tab,
        'date': day.strftime('%Y-%m-%d'),
    }

"""Canonical goal persistence with explicit focus and relationship lifecycle."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from pydantic import ValidationError

from database import _client
from database.read_boundary import parse_snapshot_strict, parse_snapshots
from models.goal import (
    GoalMetric,
    GoalProgressEvent,
    GoalProgressEventCreate,
    GoalProgressEventKind,
    GoalRelationshipDisposition,
    GoalSource,
    GoalStatus,
    GoalType,
)
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode

logger = logging.getLogger(__name__)

goals_collection = 'goals'
goal_history_collection = 'goal_history'
goal_events_collection = 'events'
users_collection = 'users'
DEFAULT_FOCUS_CAP = 5
TASK_INTELLIGENCE_CONTROL_COLLECTION = 'task_intelligence_control'
TASK_INTELLIGENCE_CONTROL_DOCUMENT = 'state'
MUTATION_RECEIPTS_COLLECTION = 'workflow_mutation_receipts'
# Legacy test/call-site compatibility only; new persistence paths use _get_db().
db = _client.db


class GoalStoreError(RuntimeError):
    pass


class GoalNotFoundError(GoalStoreError):
    pass


class GoalConflictError(GoalStoreError):
    pass


def _get_db(firestore_client: Any = None) -> Any:
    if firestore_client is not None:
        return firestore_client
    getter = getattr(_client, 'get_firestore_client', None)
    return getter() if getter is not None else _client.db


def _goal_ref(uid: str, goal_id: str, *, firestore_client: Any = None):
    return (
        _get_db(firestore_client)
        .collection(users_collection)
        .document(uid)
        .collection(goals_collection)
        .document(goal_id)
    )


def goal_document_ref(uid: str, goal_id: str, *, firestore_client: Any = None):
    """Shared transaction seam for workflow relationship validation."""

    return _goal_ref(uid, goal_id, firestore_client=firestore_client)


def _goal_control_ref(uid: str, *, firestore_client: Any):
    return (
        _get_db(firestore_client)
        .collection(users_collection)
        .document(uid)
        .collection(TASK_INTELLIGENCE_CONTROL_COLLECTION)
        .document(TASK_INTELLIGENCE_CONTROL_DOCUMENT)
    )


def _validate_canonical_write(snapshot: Any, *, account_generation: int) -> None:
    control = TaskWorkflowControl()
    if snapshot.exists:
        control = parse_snapshot_strict(TaskWorkflowControl, snapshot)
    if control.account_generation != account_generation:
        raise GoalConflictError('account generation mismatch')
    if control.workflow_mode not in {TaskWorkflowMode.write, TaskWorkflowMode.read}:
        raise GoalConflictError('canonical goal writes are disabled')


def _goal_mutation_receipt_ref(
    uid: str,
    *,
    operation: str,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any,
):
    raw = f'{uid}\x1f{account_generation}\x1f{operation}\x1f{idempotency_key}'.encode('utf-8')
    receipt_id = f'mutation_{hashlib.sha256(raw).hexdigest()[:32]}'
    return (
        _get_db(firestore_client)
        .collection(users_collection)
        .document(uid)
        .collection(MUTATION_RECEIPTS_COLLECTION)
        .document(receipt_id)
    )


def _begin_goal_mutation(
    write_transaction: Any,
    *,
    uid: str,
    operation: str,
    idempotency_key: str,
    account_generation: int,
    request_payload: dict[str, Any],
    firestore_client: Any,
) -> tuple[Any, Optional[dict[str, Any]], str]:
    control_snapshot = _goal_control_ref(uid, firestore_client=firestore_client).get(transaction=write_transaction)
    _validate_canonical_write(control_snapshot, account_generation=account_generation)
    receipt_ref = _goal_mutation_receipt_ref(
        uid,
        operation=operation,
        idempotency_key=idempotency_key,
        account_generation=account_generation,
        firestore_client=firestore_client,
    )
    request_hash = hashlib.sha256(
        json.dumps(request_payload, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    ).hexdigest()
    snapshot = receipt_ref.get(transaction=write_transaction)
    if not snapshot.exists:
        return receipt_ref, None, request_hash
    receipt = _snapshot_dict(snapshot)
    if receipt.get('request_hash') != request_hash:
        raise GoalConflictError('idempotency key was reused with different content')
    result = receipt.get('result')
    if not isinstance(result, dict):
        raise GoalConflictError('idempotent goal mutation receipt is incomplete')
    return receipt_ref, cast(dict[str, Any], result), request_hash


def _finish_goal_mutation(
    write_transaction: Any,
    receipt_ref: Any,
    *,
    request_hash: str,
    result: dict[str, Any],
    now: datetime,
) -> None:
    write_transaction.create(
        receipt_ref,
        {'request_hash': request_hash, 'result': result, 'created_at': now},
    )


def _goal_dict(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    if not data.get('id'):
        data['id'] = doc.id
    data.setdefault('goal_id', doc.id)
    return data


def _snapshot_dict(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _coerce_created_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _goal_created_at_sort_key(goal: Dict[str, Any]) -> datetime:
    return _coerce_created_at(goal.get('created_at'))


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _metric_from_storage(data: dict[str, Any]) -> Optional[GoalMetric]:
    metric = data.get('metric')
    if isinstance(metric, dict):
        try:
            return GoalMetric.model_validate(metric)
        except ValidationError:
            return None
    if data.get('target_value') is None and data.get('goal_type') is None:
        return None
    # A drifted legacy row can carry a null/non-numeric current/target/min/max, a bad goal_type, or an
    # inconsistent min/max pair. Coerce each field defensively (the sibling min/max already None-guard) and
    # guard goal_type by set membership like status/source below; the ValidationError backstop degrades a
    # still-inconsistent metric to absent instead of 500ing every goal read.
    goal_type = data.get('goal_type', GoalType.scale.value)
    if goal_type not in {member.value for member in GoalType}:
        goal_type = GoalType.scale.value
    try:
        return GoalMetric(
            type=GoalType(goal_type),
            current=_safe_float(data.get('current_value'), 0.0),
            target=_safe_float(data.get('target_value'), 0.0),
            min=_safe_float(data.get('min_value'), 0.0) if data.get('min_value') is not None else None,
            max=_safe_float(data.get('max_value'), 10.0) if data.get('max_value') is not None else None,
            unit=data.get('unit'),
        )
    except ValidationError:
        return None


def _metric_aliases(metric: Optional[GoalMetric]) -> dict[str, Any]:
    """Released numeric aliases for metric-backed goals only.

    Qualitative goals omit tracker aliases so clients rely on ``metric=null``
    and canonical text fields instead of a fake 0-10 scale projection.
    """
    if metric is None:
        return {}
    return {
        'goal_type': metric.type.value,
        'current_value': metric.current,
        'target_value': metric.target,
        'min_value': metric.min if metric.min is not None else 0.0,
        'max_value': metric.max if metric.max is not None else max(metric.target, 10.0),
        'unit': metric.unit,
    }


def ensure_released_goal_aliases(goal: dict[str, Any]) -> dict[str, Any]:
    """Fill non-null released-client aliases for API responses without rewriting storage.

    Qualitative goals still expose inert numeric placeholders so older clients that
    require non-null ``goal_type`` / bounds keep decoding. New clients should prefer
    ``metric is None`` plus canonical text fields.
    """
    projected = dict(goal)
    metric = _metric_from_storage(projected)
    if metric is not None:
        projected.update(_metric_aliases(metric))
        return projected
    projected.setdefault('goal_type', 'scale')
    projected.setdefault('target_value', 0.0)
    projected.setdefault('current_value', 0.0)
    projected.setdefault('min_value', 0.0)
    projected.setdefault('max_value', 10.0)
    projected.setdefault('unit', None)
    return projected


def normalize_goal_storage(data: dict[str, Any], *, goal_id: Optional[str] = None) -> dict[str, Any]:
    """Project legacy rows into the canonical goal shape without changing authority."""

    normalized = dict(data)
    resolved_id = str(goal_id or normalized.get('goal_id') or normalized.get('id') or '')
    status_value = normalized.get('status')
    if status_value not in {status.value for status in GoalStatus}:
        status_value = GoalStatus.background.value if normalized.get('is_active', True) else GoalStatus.abandoned.value
    metric = _metric_from_storage(normalized)
    normalized.update(
        {
            'id': resolved_id,
            'goal_id': resolved_id,
            'title': str(normalized.get('title') or ''),
            'desired_outcome': str(normalized.get('desired_outcome') or normalized.get('title') or ''),
            'why_it_matters': normalized.get('why_it_matters'),
            'success_criteria': list(normalized.get('success_criteria') or []),
            'status': status_value,
            'focus_rank': normalized.get('focus_rank') if status_value == GoalStatus.focused.value else None,
            'metric': metric.model_dump(mode='python') if metric is not None else None,
            'source': (
                normalized.get('source')
                if normalized.get('source') in {source.value for source in GoalSource}
                else GoalSource.imported.value
            ),
            'latest_progress_sequence': _safe_int(normalized.get('latest_progress_sequence', 0), 0),
            'is_active': status_value not in {GoalStatus.achieved.value, GoalStatus.abandoned.value},
        }
    )
    normalized.update(_metric_aliases(metric))
    return normalized


def get_goal_by_id(uid: str, goal_id: str, *, firestore_client: Any = None) -> Optional[Dict[str, Any]]:
    snapshot = _goal_ref(uid, goal_id, firestore_client=firestore_client).get()
    if not snapshot.exists:
        return None
    return normalize_goal_storage(_goal_dict(snapshot), goal_id=goal_id)


def get_user_goal(uid: str, *, firestore_client: Any = None) -> Optional[Dict[str, Any]]:
    """Released compatibility projection: focused first, otherwise oldest non-terminal goal."""

    goals = get_user_goals(uid, limit=100, firestore_client=firestore_client)
    if not goals:
        return None
    goals.sort(
        key=lambda goal: (
            0 if goal.get('status') == GoalStatus.focused.value else 1,
            goal.get('focus_rank') if goal.get('focus_rank') is not None else DEFAULT_FOCUS_CAP,
            _goal_created_at_sort_key(goal),
        )
    )
    return goals[0]


def get_user_goals(uid: str, limit: int = 3, *, firestore_client: Any = None) -> List[Dict[str, Any]]:
    collection = _get_db(firestore_client).collection(users_collection).document(uid).collection(goals_collection)
    query = collection.where(filter=FieldFilter('is_active', '==', True)).limit(limit)
    goals = [normalize_goal_storage(_goal_dict(doc), goal_id=doc.id) for doc in query.stream()]
    goals = [goal for goal in goals if goal['status'] not in {GoalStatus.achieved.value, GoalStatus.abandoned.value}]
    goals.sort(key=_goal_created_at_sort_key)
    return goals[:limit]


def get_all_goals(
    uid: str,
    include_inactive: bool = False,
    *,
    limit: Optional[int] = None,
    firestore_client: Any = None,
) -> List[Dict[str, Any]]:
    """Fetch a user's goals, newest first.

    ``limit`` bounds the read at the query instead of in Python, so a caller that only needs a
    page cannot stream the whole collection. It is opt-in: every existing caller omits it and
    keeps the fetch-everything behaviour they rely on.

    The query orders by ``created_at`` descending so the bounded page is the newest ``limit``
    goals rather than an arbitrary slice that only looks sorted after the in-Python sort below.

    ``limit`` is only supported together with ``include_inactive=True``. That shape carries no
    equality filter, so ordering by ``created_at`` is served by Firestore's automatic
    single-field index. Combining a limit with the ``is_active`` filter would need a composite
    index that this project does not declare, and Firestore answers a missing composite index
    with an opaque 500, so the unsupported combination is rejected here rather than in
    production.
    """
    if limit is not None and not include_inactive:
        raise ValueError('get_all_goals(limit=...) is only supported with include_inactive=True')

    collection = _get_db(firestore_client).collection(users_collection).document(uid).collection(goals_collection)
    query = collection if include_inactive else collection.where(filter=FieldFilter('is_active', '==', True))
    if limit is not None:
        query = query.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
    goals = [normalize_goal_storage(_goal_dict(doc), goal_id=doc.id) for doc in query.stream()]
    if not include_inactive:
        goals = [goal for goal in goals if goal['is_active']]
    goals.sort(key=_goal_created_at_sort_key, reverse=True)
    return goals if limit is None else goals[:limit]


def create_goal(
    uid: str,
    goal_data: Dict[str, Any],
    max_goals: int = DEFAULT_FOCUS_CAP,
    *,
    firestore_client: Any = None,
) -> Dict[str, Any]:
    """Create a goal without implicitly changing any other goal's lifecycle."""

    del max_goals  # Kept only for released call-site compatibility.
    client = _get_db(firestore_client)
    now = datetime.now(timezone.utc)
    goal_id = str(goal_data.get('goal_id') or goal_data.get('id') or f'goal_{uuid4().hex[:12]}')
    user_ref = client.collection(users_collection).document(uid)
    goal_ref = user_ref.collection(goals_collection).document(goal_id)
    transaction = client.transaction()

    @firestore.transactional
    def create_in_generation(write_transaction):
        control_snapshot = (
            user_ref.collection(TASK_INTELLIGENCE_CONTROL_COLLECTION)
            .document(TASK_INTELLIGENCE_CONTROL_DOCUMENT)
            .get(transaction=write_transaction)
        )
        account_generation = (
            parse_snapshot_strict(TaskWorkflowControl, control_snapshot).account_generation
            if control_snapshot.exists
            else 0
        )
        payload = _new_goal_payload(
            goal_data,
            goal_id=goal_id,
            now=now,
            account_generation=account_generation,
        )
        write_transaction.create(goal_ref, payload)
        return normalize_goal_storage(payload, goal_id=goal_id)

    return create_in_generation(transaction)


def _new_goal_payload(
    goal_data: Dict[str, Any], *, goal_id: str, now: datetime, account_generation: int = 0
) -> dict[str, Any]:
    metric = _metric_from_storage(goal_data)
    status = GoalStatus(goal_data.get('status', GoalStatus.background.value))
    if status == GoalStatus.focused:
        raise GoalConflictError('use explicit focus management after creating a goal')
    payload = {
        'id': goal_id,
        'goal_id': goal_id,
        'title': str(goal_data.get('title') or '').strip(),
        'desired_outcome': str(goal_data.get('desired_outcome') or goal_data.get('title') or '').strip(),
        'why_it_matters': goal_data.get('why_it_matters'),
        'success_criteria': list(goal_data.get('success_criteria') or []),
        'horizon_at': goal_data.get('horizon_at'),
        'status': status.value,
        'focus_rank': None,
        'metric': metric.model_dump(mode='python') if metric is not None else None,
        'source': goal_data.get('source', GoalSource.user.value),
        'latest_progress_sequence': 0,
        'is_active': status not in {GoalStatus.achieved, GoalStatus.abandoned},
        'created_at': now,
        'updated_at': now,
        'account_generation': account_generation,
    }
    if not payload['title'] or not payload['desired_outcome']:
        raise ValueError('goal title and desired_outcome are required')
    payload.update(_metric_aliases(metric))
    return payload


def create_goal_idempotent(
    uid: str,
    goal_data: Dict[str, Any],
    *,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any = None,
) -> Dict[str, Any]:
    """Create one canonical goal for a generation-scoped UI occurrence."""

    client = _get_db(firestore_client)
    transaction = client.transaction()
    now = datetime.now(timezone.utc)
    raw_goal_id = f'{uid}\x1f{account_generation}\x1fgoal-create\x1f{idempotency_key}'.encode('utf-8')
    goal_id = f'goal_{hashlib.sha256(raw_goal_id).hexdigest()[:12]}'

    @firestore.transactional
    def apply(write_transaction):
        receipt_ref, stored_result, request_hash = _begin_goal_mutation(
            write_transaction,
            uid=uid,
            operation='goal-create',
            idempotency_key=idempotency_key,
            account_generation=account_generation,
            request_payload=goal_data,
            firestore_client=client,
        )
        if stored_result is not None:
            return normalize_goal_storage(stored_result, goal_id=goal_id)
        payload = _new_goal_payload(goal_data, goal_id=goal_id, now=now, account_generation=account_generation)
        goal_ref = _goal_ref(uid, goal_id, firestore_client=client)
        write_transaction.create(goal_ref, payload)
        result = normalize_goal_storage(payload, goal_id=goal_id)
        _finish_goal_mutation(
            write_transaction,
            receipt_ref,
            request_hash=request_hash,
            result=result,
            now=now,
        )
        return result

    return apply(transaction)


def update_goal(
    uid: str,
    goal_id: str,
    updates: Dict[str, Any],
    *,
    firestore_client: Any = None,
) -> Optional[Dict[str, Any]]:
    ref = _goal_ref(uid, goal_id, firestore_client=firestore_client)
    snapshot = ref.get()
    if not snapshot.exists:
        return None
    patch = dict(updates)
    patch.pop('status', None)
    patch.pop('focus_rank', None)
    clear_metric = bool(patch.pop('clear_metric', False))
    current = normalize_goal_storage(_goal_dict(snapshot), goal_id=goal_id)
    legacy_metric_keys = {'goal_type', 'current_value', 'target_value', 'min_value', 'max_value', 'unit'}
    if clear_metric:
        metric = None
    elif 'metric' in patch:
        metric_value = patch['metric']
        metric = GoalMetric.model_validate(metric_value) if metric_value is not None else None
    elif any(key in patch for key in legacy_metric_keys):
        current_metric = _metric_from_storage(current) or GoalMetric(type=GoalType.scale, current=0, target=0)
        metric = GoalMetric(
            type=GoalType(patch.get('goal_type', current_metric.type.value)),
            current=float(patch.get('current_value', current_metric.current)),
            target=float(patch.get('target_value', current_metric.target)),
            min=patch.get('min_value', current_metric.min),
            max=patch.get('max_value', current_metric.max),
            unit=patch.get('unit', current_metric.unit),
        )
    else:
        metric = _metric_from_storage(current)
    if 'metric' in patch or clear_metric or any(key in patch for key in legacy_metric_keys):
        patch['metric'] = metric.model_dump(mode='python') if metric is not None else None
        patch.update(_metric_aliases(metric))
    patch['updated_at'] = datetime.now(timezone.utc)
    ref.update(patch)
    return get_goal_by_id(uid, goal_id, firestore_client=firestore_client)


def focus_goal(
    uid: str,
    goal_id: str,
    *,
    idempotency_key: str,
    account_generation: int,
    replacement_goal_id: Optional[str] = None,
    focus_rank: Optional[int] = None,
    focus_cap: int = DEFAULT_FOCUS_CAP,
    firestore_client: Any = None,
) -> Dict[str, Any]:
    client = _get_db(firestore_client)
    target_ref = _goal_ref(uid, goal_id, firestore_client=client)
    collection = client.collection(users_collection).document(uid).collection(goals_collection)
    transaction = client.transaction()
    now = datetime.now(timezone.utc)

    @firestore.transactional
    def apply(write_transaction):
        receipt_ref, stored_result, request_hash = _begin_goal_mutation(
            write_transaction,
            uid=uid,
            operation=f'goal-focus:{goal_id}',
            idempotency_key=idempotency_key,
            account_generation=account_generation,
            request_payload={'replacement_goal_id': replacement_goal_id, 'focus_rank': focus_rank},
            firestore_client=client,
        )
        if stored_result is not None:
            return normalize_goal_storage(stored_result, goal_id=goal_id)
        target_snapshot = target_ref.get(transaction=write_transaction)
        if not target_snapshot.exists:
            raise GoalNotFoundError(goal_id)
        target = normalize_goal_storage(_goal_dict(target_snapshot), goal_id=goal_id)
        if target['status'] in {GoalStatus.achieved.value, GoalStatus.abandoned.value}:
            raise GoalConflictError('ended goals cannot be focused')
        focused_snapshots = list(
            collection.where(filter=FieldFilter('status', '==', GoalStatus.focused.value)).stream(
                transaction=write_transaction
            )
        )
        focused = [snapshot for snapshot in focused_snapshots if snapshot.id != goal_id]
        occupied = {
            rank for snapshot in focused for rank in [_goal_dict(snapshot).get('focus_rank')] if isinstance(rank, int)
        }
        if target['status'] == GoalStatus.focused.value and focus_rank in {None, target.get('focus_rank')}:
            _finish_goal_mutation(
                write_transaction,
                receipt_ref,
                request_hash=request_hash,
                result=target,
                now=now,
            )
            return target
        if len(focused) >= focus_cap:
            if replacement_goal_id is None:
                raise GoalConflictError('focus set is full; replacement_goal_id is required')
            replacement = next((snapshot for snapshot in focused if snapshot.id == replacement_goal_id), None)
            if replacement is None:
                raise GoalConflictError('replacement_goal_id must name a focused goal')
            previous_rank = _goal_dict(replacement).get('focus_rank')
            write_transaction.update(
                replacement.reference,
                {'status': GoalStatus.background.value, 'focus_rank': None, 'updated_at': now},
            )
            occupied.discard(int(previous_rank)) if isinstance(previous_rank, int) else None
        requested_rank = focus_rank
        if requested_rank is None:
            requested_rank = next((rank for rank in range(focus_cap) if rank not in occupied), 0)
        if requested_rank in occupied:
            raise GoalConflictError('focus_rank is already occupied')
        patch = {
            'status': GoalStatus.focused.value,
            'focus_rank': requested_rank,
            'is_active': True,
            'updated_at': now,
        }
        write_transaction.update(target_ref, patch)
        result = normalize_goal_storage({**target, **patch}, goal_id=goal_id)
        _finish_goal_mutation(
            write_transaction,
            receipt_ref,
            request_hash=request_hash,
            result=result,
            now=now,
        )
        return result

    return apply(transaction)


def unfocus_goal(
    uid: str,
    goal_id: str,
    *,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any = None,
) -> Dict[str, Any]:
    client = _get_db(firestore_client)
    goal_ref = _goal_ref(uid, goal_id, firestore_client=client)
    transaction = client.transaction()
    now = datetime.now(timezone.utc)

    @firestore.transactional
    def apply(write_transaction):
        receipt_ref, stored_result, request_hash = _begin_goal_mutation(
            write_transaction,
            uid=uid,
            operation=f'goal-unfocus:{goal_id}',
            idempotency_key=idempotency_key,
            account_generation=account_generation,
            request_payload={},
            firestore_client=client,
        )
        if stored_result is not None:
            return normalize_goal_storage(stored_result, goal_id=goal_id)
        snapshot = goal_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            raise GoalNotFoundError(goal_id)
        goal = normalize_goal_storage(_goal_dict(snapshot), goal_id=goal_id)
        if goal['status'] == GoalStatus.focused.value:
            patch = {'status': GoalStatus.background.value, 'focus_rank': None, 'updated_at': now}
            write_transaction.update(goal_ref, patch)
            goal = normalize_goal_storage({**goal, **patch}, goal_id=goal_id)
        _finish_goal_mutation(
            write_transaction,
            receipt_ref,
            request_hash=request_hash,
            result=goal,
            now=now,
        )
        return goal

    return apply(transaction)


def transition_goal_lifecycle(
    uid: str,
    goal_id: str,
    *,
    status: GoalStatus,
    relationship_disposition: GoalRelationshipDisposition,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any = None,
) -> Dict[str, Any]:
    if status not in {GoalStatus.paused, GoalStatus.achieved, GoalStatus.abandoned}:
        raise ValueError('invalid goal lifecycle target')
    client = _get_db(firestore_client)
    goal_ref = _goal_ref(uid, goal_id, firestore_client=client)
    transaction = client.transaction()
    now = datetime.now(timezone.utc)

    @firestore.transactional
    def apply(write_transaction):
        receipt_ref, stored_result, request_hash = _begin_goal_mutation(
            write_transaction,
            uid=uid,
            operation=f'goal-lifecycle:{goal_id}',
            idempotency_key=idempotency_key,
            account_generation=account_generation,
            request_payload={
                'status': status.value,
                'relationship_disposition': relationship_disposition.value,
            },
            firestore_client=client,
        )
        if stored_result is not None:
            return normalize_goal_storage(stored_result, goal_id=goal_id)
        goal_snapshot = goal_ref.get(transaction=write_transaction)
        if not goal_snapshot.exists:
            raise GoalNotFoundError(goal_id)
        if relationship_disposition == GoalRelationshipDisposition.detach:
            user_ref = client.collection(users_collection).document(uid)
            task_snapshots = list(
                user_ref.collection('action_items')
                .where(filter=FieldFilter('goal_id', '==', goal_id))
                .limit(450)
                .stream(transaction=write_transaction)
            )
            workstream_snapshots = list(
                user_ref.collection('workstreams')
                .where(filter=FieldFilter('goal_id', '==', goal_id))
                .limit(450)
                .stream(transaction=write_transaction)
            )
            if len(task_snapshots) + len(workstream_snapshots) >= 450:
                raise GoalConflictError('too many relationships to detach atomically')
            for snapshot in task_snapshots:
                write_transaction.update(snapshot.reference, {'goal_id': None, 'updated_at': now})
            for snapshot in workstream_snapshots:
                write_transaction.update(snapshot.reference, {'goal_id': None, 'updated_at': now})
        patch = {
            'status': status.value,
            'focus_rank': None,
            'is_active': status not in {GoalStatus.achieved, GoalStatus.abandoned},
            'relationship_disposition': relationship_disposition.value,
            'updated_at': now,
            'ended_at': now if status in {GoalStatus.achieved, GoalStatus.abandoned} else None,
        }
        write_transaction.update(goal_ref, patch)
        result = normalize_goal_storage({**_goal_dict(goal_snapshot), **patch}, goal_id=goal_id)
        _finish_goal_mutation(
            write_transaction,
            receipt_ref,
            request_hash=request_hash,
            result=result,
            now=now,
        )
        return result

    return apply(transaction)


def _append_goal_progress_event(
    uid: str,
    goal_id: str,
    event: GoalProgressEventCreate,
    *,
    idempotency_key: Optional[str],
    account_generation: Optional[int],
    firestore_client: Any = None,
) -> GoalProgressEvent:
    client = _get_db(firestore_client)
    goal_ref = _goal_ref(uid, goal_id, firestore_client=client)
    transaction = client.transaction()
    now = datetime.now(timezone.utc)
    event_id = (
        f'gpe_{hashlib.sha256(f"{uid}:{account_generation}:{goal_id}:{idempotency_key}".encode()).hexdigest()[:32]}'
        if idempotency_key is not None and account_generation is not None
        else f'gpe_{uuid4().hex}'
    )
    event_ref = goal_ref.collection(goal_events_collection).document(event_id)

    @firestore.transactional
    def apply(write_transaction):
        if account_generation is not None:
            control_snapshot = _goal_control_ref(uid, firestore_client=client).get(transaction=write_transaction)
            _validate_canonical_write(control_snapshot, account_generation=account_generation)
        goal_snapshot = goal_ref.get(transaction=write_transaction)
        if not goal_snapshot.exists:
            raise GoalNotFoundError(goal_id)
        existing = event_ref.get(transaction=write_transaction)
        if existing.exists:
            record = parse_snapshot_strict(GoalProgressEvent, existing)
            stored_proposal = GoalProgressEventCreate(
                kind=record.kind,
                summary=record.summary,
                evidence_refs=record.evidence_refs,
                metric=record.metric,
            )
            if stored_proposal != event:
                raise GoalConflictError('progress event idempotency key was reused with different content')
            return record
        goal = normalize_goal_storage(_goal_dict(goal_snapshot), goal_id=goal_id)
        sequence = int(goal.get('latest_progress_sequence', 0)) + 1
        record = GoalProgressEvent(
            event_id=event_id,
            goal_id=goal_id,
            sequence=sequence,
            kind=event.kind,
            summary=event.summary,
            evidence_refs=event.evidence_refs,
            metric=event.metric,
            created_at=now,
        )
        write_transaction.create(event_ref, record.model_dump(mode='python', exclude_none=True))
        goal_patch: dict[str, Any] = {'latest_progress_sequence': sequence, 'updated_at': now}
        if event.metric is not None:
            goal_patch['metric'] = event.metric.model_dump(mode='python')
            goal_patch.update(_metric_aliases(event.metric))
        write_transaction.update(goal_ref, goal_patch)
        return record

    return apply(transaction)


def append_goal_progress_event(
    uid: str,
    goal_id: str,
    event: GoalProgressEventCreate,
    *,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any = None,
) -> GoalProgressEvent:
    return _append_goal_progress_event(
        uid,
        goal_id,
        event,
        idempotency_key=idempotency_key,
        account_generation=account_generation,
        firestore_client=firestore_client,
    )


def list_goal_progress_events(
    uid: str,
    goal_id: str,
    *,
    limit: int = 100,
    firestore_client: Any = None,
) -> list[GoalProgressEvent]:
    query = (
        _goal_ref(uid, goal_id, firestore_client=firestore_client)
        .collection(goal_events_collection)
        .order_by('sequence', direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return parse_snapshots(GoalProgressEvent, query.stream())


def update_goal_progress(
    uid: str,
    goal_id: str,
    current_value: float,
    *,
    firestore_client: Any = None,
) -> Optional[Dict[str, Any]]:
    goal = get_goal_by_id(uid, goal_id, firestore_client=firestore_client)
    if goal is None:
        return None
    metric = _metric_from_storage(goal) or GoalMetric(type=GoalType.numeric, current=0, target=0)
    metric = metric.model_copy(update={'current': current_value})
    _append_goal_progress_event(
        uid,
        goal_id,
        GoalProgressEventCreate(
            kind=GoalProgressEventKind.metric_update,
            summary='Metric updated',
            metric=metric,
        ),
        idempotency_key=None,
        account_generation=None,
        firestore_client=firestore_client,
    )
    save_goal_progress_history(uid, goal_id, current_value, firestore_client=firestore_client)
    return get_goal_by_id(uid, goal_id, firestore_client=firestore_client)


def save_goal_progress_history(
    uid: str,
    goal_id: str,
    value: float,
    *,
    firestore_client: Any = None,
) -> None:
    now = datetime.now(timezone.utc)
    history_ref = _goal_ref(uid, goal_id, firestore_client=firestore_client).collection(goal_history_collection)
    history_ref.document(now.strftime('%Y-%m-%d')).set(
        {'date': now.strftime('%Y-%m-%d'), 'value': value, 'recorded_at': now}, merge=True
    )


def get_goal_history(
    uid: str,
    goal_id: str,
    days: int = 30,
    *,
    firestore_client: Any = None,
) -> List[Dict[str, Any]]:
    query = (
        _goal_ref(uid, goal_id, firestore_client=firestore_client)
        .collection(goal_history_collection)
        .order_by('date', direction=firestore.Query.DESCENDING)
        .limit(days)
    )
    return [
        cast(Dict[str, Any], snapshot.to_dict()) for snapshot in query.stream() if isinstance(snapshot.to_dict(), dict)
    ]


def delete_goal(uid: str, goal_id: str, *, firestore_client: Any = None) -> bool:
    """Released DELETE compatibility: soft-abandon and retain relationships."""

    ref = _goal_ref(uid, goal_id, firestore_client=firestore_client)
    if not ref.get().exists:
        return False
    now = datetime.now(timezone.utc)
    ref.update(
        {
            'status': GoalStatus.abandoned.value,
            'focus_rank': None,
            'is_active': False,
            'relationship_disposition': GoalRelationshipDisposition.retain.value,
            'updated_at': now,
            'ended_at': now,
        }
    )
    return True


__all__ = [
    'DEFAULT_FOCUS_CAP',
    'GoalConflictError',
    'GoalNotFoundError',
    'GoalStoreError',
    'append_goal_progress_event',
    'create_goal',
    'delete_goal',
    'ensure_released_goal_aliases',
    'focus_goal',
    'get_all_goals',
    'get_goal_by_id',
    'get_goal_history',
    'get_user_goal',
    'get_user_goals',
    'goal_document_ref',
    'list_goal_progress_events',
    'normalize_goal_storage',
    'save_goal_progress_history',
    'transition_goal_lifecycle',
    'unfocus_goal',
    'update_goal',
    'update_goal_progress',
]

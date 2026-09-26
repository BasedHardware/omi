import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

import pytz
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db
from .firestore_read_metrics import FirestoreReadFamily, FirestoreReadMode, record_firestore_read
from .llm_usage import resolve_usage_plan_id
from models.user_usage import UsageStats

logger = logging.getLogger(__name__)

# Firestore's document-id sentinel field path (`FieldPath.document_id()`), spelled
# literally: tests that stub `google.cloud.firestore_v1` as a plain module cannot
# import its `field_path` submodule.
_DOCUMENT_ID_FIELD = '__name__'
_UNATTRIBUTED_PLAN = '_unattributed'


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Typed adapter for a Firestore snapshot's `to_dict()` (SDK stub gap)."""
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _next_month(now: datetime) -> Tuple[int, int]:
    """(year, month) of the UTC month after ``now`` — the quota bucket boundary."""
    if now.month == 12:
        return now.year + 1, 1
    return now.year, now.month + 1


def _current_month_llm_usage_docs(llm_usage_ref: Any, now: datetime) -> Iterable[Any]:
    """Stream only the current month's `llm_usage/{YYYY-MM-DD}` docs.

    Bounded by document id, so the read stays at "days elapsed this month"
    regardless of how long the account has existed. Listing the whole
    collection and fetching the in-month days one at a time grew both the read
    count and the round-trips with account age, on the path every chat request
    takes through ``enforce_chat_quota``.
    """
    next_year, next_month = _next_month(now)
    start = llm_usage_ref.document(f'{now.year}-{now.month:02d}-01')
    end = llm_usage_ref.document(f'{next_year}-{next_month:02d}-01')
    return (
        llm_usage_ref.where(filter=FieldFilter(_DOCUMENT_ID_FIELD, '>=', start))
        .where(filter=FieldFilter(_DOCUMENT_ID_FIELD, '<', end))
        .stream()
    )


def get_monthly_bucket_call_count(
    uid: str, bucket: str, now: Optional[datetime] = None, *, firestore_client: Any | None = None
) -> int:
    """Sum one bucket's ``call_count`` over the current month's ``llm_usage`` docs.

    Bounded like :func:`get_monthly_chat_usage` (and recorded under its own
    ``FirestoreReadFamily`` so the read stays visible in the read metrics).
    Used by the realtime relay to bound how many Omi-paid provider responses a
    user may take in a month independently of the question counter, which only
    the chat request advances.
    """
    now = now or datetime.now(timezone.utc)
    llm_usage_ref = (firestore_client or db).collection('users').document(uid).collection('llm_usage')
    total = 0
    document_count = 0
    for snap in _current_month_llm_usage_docs(llm_usage_ref, now):
        document_count += 1
        data = _typed_doc(snap)
        value = data.get(bucket)
        if isinstance(value, dict):
            total += int(cast(Dict[str, Any], value).get('call_count', 0) or 0)
        flat = data.get(f'{bucket}.call_count')
        if isinstance(flat, (int, float)) and not isinstance(flat, bool):
            total += int(flat)
    record_firestore_read(
        FirestoreReadFamily.RELAY_RESPONSE_MONTHLY_COUNT,
        FirestoreReadMode.BOUNDED,
        document_count,
    )
    return total


def _merge_cost_status(existing: str | None, observed: str) -> str:
    statuses = {existing, observed} - {None}
    if statuses == {'complete'} or (statuses <= {'complete', 'excluded'} and 'complete' in statuses):
        return 'complete'
    if statuses == {'excluded'}:
        return 'excluded'
    if 'partial' in statuses:
        return 'partial'
    if 'missing' in statuses:
        return 'missing'
    return observed


def _plan_usage_row() -> Dict[str, Any]:
    return {
        'questions': 0,
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0,
        'transcription_seconds': 0,
        'words_transcribed': 0,
        'insights_gained': 0,
        'memories_created': 0,
        'speech_seconds': 0,
        'cost_usd': None,
        'cost_status': None,
        'cost_exclusions': {},
    }


def _plan_data_questions(value: Dict[str, Any]) -> int:
    """Questions a plan_usage subtree accounts for.

    Writers store questions at ``plan_usage.{plan}.{bucket}.quota_questions`` (and one
    level deeper for feature/model layouts). There is no top-level ``questions`` field,
    so this must recurse exactly like ``_accumulate_plan_data`` -- reading a flat
    ``questions`` key yields 0 for every real document and makes the residual below the
    document's entire count.
    """
    total = 0
    for key, child in value.items():
        if key == '_metadata':
            continue
        if isinstance(child, dict):
            total += _plan_data_questions(child)
        elif key == 'quota_questions':
            total += _safe_counter(child)
    return total


_HOURLY_COUNTER_KEYS = (
    'transcription_seconds',
    'words_transcribed',
    'insights_gained',
    'memories_created',
    'speech_seconds',
)
_HISTORY_COUNTER_KEYS = ('transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created')


def _unwrap_value(value: Any) -> Any:
    return getattr(value, '_value', getattr(value, 'value', value)) if value is not None else None


def _safe_counter(value: Any) -> int:
    raw = _unwrap_value(value)
    if raw is None or isinstance(raw, bool):
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _safe_bucket_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    raw = _unwrap_value(value)
    if raw is None or isinstance(raw, bool):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _history_zero_row() -> Dict[str, int]:
    return {key: 0 for key in _HISTORY_COUNTER_KEYS}


def _accumulate_plan_data(row: Dict[str, Any], value: Dict[str, Any]) -> None:
    """Collect metrics from both flat bucket and feature/model plan layouts."""
    for key, child in value.items():
        if key == '_metadata':
            continue
        if isinstance(child, dict):
            _accumulate_plan_data(row, child)
            continue
        raw = _unwrap_value(child)
        if key == 'quota_questions':
            row['questions'] += _safe_counter(raw)
        elif key == 'input_tokens':
            row['input_tokens'] += _safe_counter(raw)
        elif key == 'output_tokens':
            row['output_tokens'] += _safe_counter(raw)
        elif key == 'total_tokens':
            row['total_tokens'] += _safe_counter(raw)
        elif key == 'cost_usd' and raw is not None and not isinstance(raw, bool):
            row['cost_usd'] = (row['cost_usd'] or 0.0) + float(raw or 0.0)
        elif key in _HOURLY_COUNTER_KEYS:
            row[key] = row.get(key, 0) + _safe_counter(raw)


def _extract_plan_usage(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Reconstruct per-plan usage dicts from both nested `plan_usage` and flat `plan_usage.<plan>.*` keys."""
    extracted: Dict[str, Dict[str, Any]] = {}
    nested_plan_usage = data.get('plan_usage')
    if isinstance(nested_plan_usage, dict):
        for plan_id, plan_data in nested_plan_usage.items():
            if isinstance(plan_data, dict):
                extracted[str(plan_id)] = dict(plan_data)

    for key, raw_val in data.items():
        if not key.startswith('plan_usage.'):
            continue
        parts = [part for part in key.split('.')[1:] if part]
        if len(parts) < 2:
            continue
        plan_id, *subpath = parts
        cursor: Dict[str, Any] = extracted.setdefault(plan_id, {})
        for segment in subpath[:-1]:
            existing = cursor.get(segment)
            branch = dict(existing) if isinstance(existing, dict) else {}
            cursor[segment] = branch
            cursor = branch
        leaf = subpath[-1]
        val = _unwrap_value(raw_val)
        if leaf in cursor and isinstance(cursor[leaf], (int, float)) and isinstance(val, (int, float)):
            cursor[leaf] = cursor[leaf] + val
        else:
            cursor[leaf] = val
    return extracted


def _apply_plan_usage_entry(row: Dict[str, Any], plan_data: Dict[str, Any]) -> None:
    metadata = plan_data.get('_metadata')
    if isinstance(metadata, dict):
        status_counts = metadata.get('cost_status_counts')
        if isinstance(status_counts, dict):
            for status, count in status_counts.items():
                if _safe_counter(count) > 0:
                    row['cost_status'] = _merge_cost_status(row['cost_status'], str(status))
        exclusions = metadata.get('cost_exclusions')
        if isinstance(exclusions, dict):
            for exclusion, count in exclusions.items():
                key = str(exclusion)
                row['cost_exclusions'][key] = row['cost_exclusions'].get(key, 0) + _safe_counter(count)
    _accumulate_plan_data(row, plan_data)


def get_monthly_chat_usage(
    uid: str, now: Optional[datetime] = None, *, firestore_client: Any | None = None
) -> Dict[str, Any]:
    """Sum current-month chat usage from `users/{uid}/llm_usage/{YYYY-MM-DD}` docs."""
    now = now or datetime.now(timezone.utc)
    llm_usage_ref = (firestore_client or db).collection('users').document(uid).collection('llm_usage')
    questions = 0
    cost_usd = 0.0
    document_count = 0
    usage_by_plan: Dict[str, Dict[str, Any]] = {}
    for snap in _current_month_llm_usage_docs(llm_usage_ref, now):
        document_count += 1
        data: Dict[str, Any] = _typed_doc(snap)
        questions_before_document = questions
        plan_usage = _extract_plan_usage(data)
        plan_attributed_questions = 0
        for plan_id, plan_data in plan_usage.items():
            plan_attributed_questions += _plan_data_questions(plan_data)
            row = usage_by_plan.setdefault(str(plan_id), _plan_usage_row())
            _apply_plan_usage_entry(row, plan_data)

        has_desktop_realtime_quota_questions = 'desktop_chat_realtime.quota_questions' in data or (
            isinstance(data.get('desktop_chat_realtime'), dict) and 'quota_questions' in data['desktop_chat_realtime']
        )
        has_backend_quota_questions = any(
            (key == 'backend_chat' and isinstance(value, dict) and 'quota_questions' in value)
            or (key == 'backend_chat.quota_questions')
            for key, value in data.items()
        )
        for key, value in data.items():
            if isinstance(value, dict):
                value_dict = cast(Dict[str, Any], value)
                if key == 'desktop_chat':
                    questions += _safe_counter(value_dict.get('quota_questions', 0))
                    cost_usd += float(value_dict.get('cost_usd', 0) or 0)
                elif key == 'desktop_chat_realtime' and not has_desktop_realtime_quota_questions:
                    questions += _safe_counter(value_dict.get('call_count', 0))
                elif key == 'backend_chat':
                    questions += _safe_counter(value_dict.get('quota_questions', 0))
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            if key.startswith('desktop_chat'):
                if key == 'desktop_chat.quota_questions':
                    questions += int(value)
                elif key == 'desktop_chat_realtime.call_count' and not has_desktop_realtime_quota_questions:
                    questions += int(value)
                elif key.endswith('.cost_usd'):
                    cost_usd += float(value)
            elif key == 'backend_chat.quota_questions':
                questions += int(value)
            elif key.startswith('chat.') and key.endswith('.call_count') and not has_backend_quota_questions:
                questions += int(value)

        document_questions = questions - questions_before_document
        residual_questions = document_questions - plan_attributed_questions
        if residual_questions > 0:
            legacy_row = usage_by_plan.setdefault(_UNATTRIBUTED_PLAN, _plan_usage_row())
            legacy_row['questions'] += residual_questions
            legacy_row['cost_status'] = 'missing'
            legacy_row['cost_exclusions']['plan_snapshot_missing'] = (
                legacy_row['cost_exclusions'].get('plan_snapshot_missing', 0) + 1
            )

    record_firestore_read(FirestoreReadFamily.CHAT_QUOTA_MONTHLY_USAGE, FirestoreReadMode.BOUNDED, document_count)
    next_year, next_month = _next_month(now)
    reset_at = int(datetime(next_year, next_month, 1, tzinfo=timezone.utc).timestamp())

    return {
        'questions': questions,
        'cost_usd': round(cost_usd, 4),
        'usage_by_plan': usage_by_plan,
        'questions_by_plan': {plan_id: int(row['questions']) for plan_id, row in usage_by_plan.items()},
        'cost_by_plan': {plan_id: row['cost_usd'] for plan_id, row in usage_by_plan.items()},
        'cost_status_by_plan': {plan_id: row['cost_status'] or 'missing' for plan_id, row in usage_by_plan.items()},
        'reset_at': reset_at,
    }


def get_usage_by_plan(
    uid: str,
    now: Optional[datetime] = None,
    *,
    firestore_client: Any | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Join current-month chat and hourly usage under server-resolved plans."""
    now = now or datetime.now(timezone.utc)
    monthly = get_monthly_chat_usage(uid, now=now, firestore_client=firestore_client)
    report: Dict[str, Dict[str, Any]] = {plan_id: dict(row) for plan_id, row in monthly['usage_by_plan'].items()}
    hourly_ref = (firestore_client or db).collection('users').document(uid).collection('hourly_usage')
    query = hourly_ref.where(filter=FieldFilter('year', '==', now.year)).where(
        filter=FieldFilter('month', '==', now.month)
    )
    for snap in query.stream():
        data = _typed_doc(snap)
        plan_usage = _extract_plan_usage(data)
        if not plan_usage:
            row = report.setdefault(_UNATTRIBUTED_PLAN, _plan_usage_row())
            _accumulate_plan_data(row, data)
            row['cost_status'] = 'missing'
            row['cost_exclusions']['plan_snapshot_missing'] = row['cost_exclusions'].get('plan_snapshot_missing', 0) + 1
            continue
        attributed_counters = {key: 0 for key in _HOURLY_COUNTER_KEYS}
        for plan_id, plan_data in plan_usage.items():
            row = report.setdefault(str(plan_id), _plan_usage_row())
            before = {key: row.get(key, 0) for key in _HOURLY_COUNTER_KEYS}
            _apply_plan_usage_entry(row, plan_data)
            for key in _HOURLY_COUNTER_KEYS:
                attributed_counters[key] += row.get(key, 0) - before[key]
        residuals = {
            key: _safe_counter(data.get(key, 0)) - attributed_counters[key]
            for key in _HOURLY_COUNTER_KEYS
            if _safe_counter(data.get(key, 0)) > attributed_counters[key]
        }
        if residuals:
            legacy_row = report.setdefault(_UNATTRIBUTED_PLAN, _plan_usage_row())
            for key, diff in residuals.items():
                legacy_row[key] = legacy_row.get(key, 0) + diff
            legacy_row['cost_status'] = 'missing'
            legacy_row['cost_exclusions']['plan_snapshot_missing'] = (
                legacy_row['cost_exclusions'].get('plan_snapshot_missing', 0) + 1
            )

    for row in report.values():
        row['cost_status'] = row['cost_status'] or 'missing'
    return report


def _populate_hourly_plan_usage_increments(
    update_doc: Dict[str, Any],
    uid: str,
    updates: Dict[str, Any],
    *,
    cost_usd: float | None,
    cost_status: str,
    cost_exclusion: str | None,
    client: Any,
) -> None:
    plan_key = resolve_usage_plan_id(uid, firestore_client=client) or _UNATTRIBUTED_PLAN
    plan_prefix = f'plan_usage.{plan_key}'
    for key, value in updates.items():
        if (
            key in _HOURLY_COUNTER_KEYS
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > 0
        ):
            update_doc[f'{plan_prefix}.{key}'] = firestore.Increment(value)
    if cost_usd is not None:
        update_doc[f'{plan_prefix}.cost_usd'] = firestore.Increment(cost_usd)
    normalized_status = cost_status if cost_status in {'complete', 'partial', 'missing', 'excluded'} else 'missing'
    effective_exclusion = cost_exclusion or (
        'provider_cost_not_recorded' if normalized_status in {'missing', 'partial'} else None
    )
    update_doc[f'{plan_prefix}._metadata.cost_status_counts.{normalized_status}'] = firestore.Increment(1)
    update_doc[f'{plan_prefix}._metadata.last_cost_status'] = normalized_status
    if effective_exclusion:
        safe_exclusion = effective_exclusion.replace('.', '_').replace('/', '_')
        update_doc[f'{plan_prefix}._metadata.cost_exclusions.{safe_exclusion}'] = firestore.Increment(1)


def update_hourly_usage(
    uid: str,
    date: datetime,
    updates: Dict[str, Any],
    platform: Optional[str] = None,
    *,
    cost_usd: float | None = None,
    cost_status: str = 'missing',
    cost_exclusion: str | None = None,
    firestore_client: Any | None = None,
) -> None:
    """Updates or creates usage stats for a specific hour using Firestore atomic increments."""
    client = firestore_client or db
    user_ref = client.collection('users').document(uid)
    doc_id = f'{date.year}-{date.month:02d}-{date.day:02d}-{date.hour:02d}'
    hourly_usage_ref = user_ref.collection('hourly_usage').document(doc_id)

    update_doc: Dict[str, Any] = {'last_updated': datetime.now(timezone.utc)}
    has_increments = False
    for key, value in updates.items():
        if (
            key in _HOURLY_COUNTER_KEYS
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > 0
        ):
            update_doc[key] = firestore.Increment(value)
            has_increments = True
    if not has_increments:
        return

    _populate_hourly_plan_usage_increments(
        update_doc,
        uid,
        updates,
        cost_usd=cost_usd,
        cost_status=cost_status,
        cost_exclusion=cost_exclusion,
        client=client,
    )
    update_doc.update({'year': date.year, 'month': date.month, 'day': date.day, 'hour': date.hour, 'id': doc_id})
    if platform in ('desktop', 'mobile'):
        update_doc['platforms'] = firestore.ArrayUnion([platform])
    hourly_usage_ref.set(update_doc, merge=True)


@firestore.transactional
def _update_hourly_usage_once_transaction(
    transaction: Any,
    marker_ref: Any,
    usage_ref: Any,
    update_doc: Dict[str, Any],
) -> bool:
    marker_snapshot = marker_ref.get(transaction=transaction)
    marker_data = marker_snapshot.to_dict() or {} if marker_snapshot.exists else {}
    if marker_data.get('usage_committed_at') is not None:
        return False
    transaction.set(marker_ref, {'usage_committed_at': datetime.now(timezone.utc)}, merge=True)
    transaction.set(usage_ref, update_doc, merge=True)
    return True


def update_hourly_usage_once(
    uid: str,
    date: datetime,
    updates: Dict[str, Any],
    idempotency_key: str,
    *,
    cost_usd: float | None = None,
    cost_status: str = 'missing',
    cost_exclusion: str | None = None,
    firestore_client: Any | None = None,
) -> bool:
    """Atomically increment hourly usage once for a stable sync content key."""
    client = firestore_client or db
    user_ref = client.collection('users').document(uid)
    doc_id = f'{date.year}-{date.month:02d}-{date.day:02d}-{date.hour:02d}'
    usage_ref = user_ref.collection('hourly_usage').document(doc_id)
    marker_ref = user_ref.collection('sync_content_ledger').document(idempotency_key)
    update_doc: Dict[str, Any] = {
        'last_updated': datetime.now(timezone.utc),
        'year': date.year,
        'month': date.month,
        'day': date.day,
        'hour': date.hour,
        'id': doc_id,
    }
    for key, value in updates.items():
        if (
            key in _HOURLY_COUNTER_KEYS
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > 0
        ):
            update_doc[key] = firestore.Increment(value)
    if not any(key in _HOURLY_COUNTER_KEYS for key in update_doc):
        return False
    _populate_hourly_plan_usage_increments(
        update_doc,
        uid,
        updates,
        cost_usd=cost_usd,
        cost_status=cost_status,
        cost_exclusion=cost_exclusion,
        client=client,
    )
    return _update_hourly_usage_once_transaction(client.transaction(), marker_ref, usage_ref, update_doc)


def batch_update_hourly_usage(uid: str, hourly_updates: Dict[datetime, Dict[str, Any]]) -> None:
    """Batch updates or creates usage stats for multiple hours."""
    batch_size = 400
    items: List[Tuple[datetime, Dict[str, Any]]] = list(hourly_updates.items())

    for i in range(0, len(items), batch_size):
        batch = db.batch()
        chunk = items[i : i + batch_size]
        for date, updates in chunk:
            doc_id = f'{date.year}-{date.month:02d}-{date.day:02d}-{date.hour:02d}'
            hourly_usage_ref = db.collection('users').document(uid).collection('hourly_usage').document(doc_id)
            update_doc: Dict[str, Any] = updates.copy()
            update_doc.update(
                {
                    'year': date.year,
                    'month': date.month,
                    'day': date.day,
                    'hour': date.hour,
                    'id': doc_id,
                    'last_updated': datetime.now(timezone.utc),
                }
            )
            batch.set(hourly_usage_ref, update_doc, merge=True)
        batch.commit()


def get_today_usage_stats(uid: str, start: datetime, end: datetime) -> Dict[str, Any]:
    """Aggregates hourly usage stats for the UTC bucket range [start, end)."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    stats: Dict[str, Any] = {key: 0 for key in _HOURLY_COUNTER_KEYS}
    cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor < end:
        query = (
            hourly_usage_collection.where(filter=FieldFilter('year', '==', cursor.year))
            .where(filter=FieldFilter('month', '==', cursor.month))
            .where(filter=FieldFilter('day', '==', cursor.day))
        )
        for doc in query.stream():
            data = _typed_doc(doc)
            hour_val = _safe_bucket_int(data.get('hour', 0), default=0)
            if hour_val is None or not 0 <= hour_val <= 23:
                continue
            bucket_hour = cursor.replace(hour=hour_val)
            if start <= bucket_hour < end:
                for key in stats:
                    stats[key] += _safe_counter(data.get(key, 0))
        cursor += timedelta(days=1)
    return stats


def _aggregate_stats(query: Any) -> Dict[str, Any]:
    return _aggregate_stats_from_docs(query.stream())


def _aggregate_stats_from_docs(docs: Iterable[Any]) -> Dict[str, Any]:
    stats, _ = _aggregate_stats_with_count(docs)
    return stats


def _aggregate_stats_with_count(docs: Iterable[Any]) -> Tuple[Dict[str, Any], int]:
    stats: Dict[str, Any] = {key: 0 for key in _HOURLY_COUNTER_KEYS}
    document_count = 0
    for doc in docs:
        document_count += 1
        data: Dict[str, Any] = _typed_doc(doc)
        for key in _HOURLY_COUNTER_KEYS:
            stats[key] += _safe_counter(data.get(key, 0))
    return stats, document_count


def get_monthly_usage_stats(uid: str, date: datetime) -> Dict[str, Any]:
    """Aggregates hourly usage stats for a given month from Firestore."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    query = hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year)).where(
        filter=FieldFilter('month', '==', date.month)
    )
    return _aggregate_stats(query)


def get_monthly_usage_stats_since(uid: str, date: datetime, start_date: datetime) -> Dict[str, Any]:
    """Aggregates hourly usage stats for a given month from Firestore, starting from a specific date."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    start_doc_id = f'{start_date.year}-{start_date.month:02d}-{start_date.day:02d}-00'
    query = (
        hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year))
        .where(filter=FieldFilter('month', '==', date.month))
        .where(filter=FieldFilter('id', '>=', start_doc_id))
    )
    stats, document_count = _aggregate_stats_with_count(query.stream())
    record_firestore_read(FirestoreReadFamily.LISTEN_MONTHLY_USAGE, FirestoreReadMode.UNBOUNDED, document_count)
    return stats


def get_yearly_usage_stats(uid: str, date: datetime) -> Dict[str, Any]:
    """Aggregates hourly usage stats for a given year from Firestore."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    query = hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year))
    return _aggregate_stats(query)


def get_all_time_usage_stats(uid: str) -> Dict[str, Any]:
    """Aggregates all hourly usage stats for a user from Firestore."""
    stats, _ = _read_all_time_usage(uid)
    return stats


def get_hourly_history_for_today(uid: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Gets hourly usage for a specific day by aggregating hourly data."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    hourly_totals: Dict[datetime, Dict[str, int]] = {}
    cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor < end:
        query = (
            hourly_usage_collection.where(filter=FieldFilter('year', '==', cursor.year))
            .where(filter=FieldFilter('month', '==', cursor.month))
            .where(filter=FieldFilter('day', '==', cursor.day))
        )
        for doc in query.stream():
            data: Dict[str, Any] = _typed_doc(doc)
            hour_val = _safe_bucket_int(data.get('hour', 0), default=0)
            if hour_val is None or not 0 <= hour_val <= 23:
                continue
            bucket = cursor.replace(hour=hour_val)
            if not start <= bucket < end:
                continue
            row = hourly_totals.setdefault(bucket, _history_zero_row())
            for key in _HISTORY_COUNTER_KEYS:
                row[key] += _safe_counter(data.get(key, 0))
        cursor += timedelta(days=1)

    history: List[Dict[str, Any]] = [
        {'date': bucket.strftime('%Y-%m-%dT%H:00:00Z'), **stats} for bucket, stats in hourly_totals.items()
    ]
    history.sort(key=lambda x: cast(str, x['date']))
    return history


def get_daily_history_for_month(uid: str, date: datetime) -> List[Dict[str, Any]]:
    """Gets daily usage for a specific month by aggregating hourly data."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    query = hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year)).where(
        filter=FieldFilter('month', '==', date.month)
    )
    daily_totals: Dict[int, Dict[str, int]] = {}
    for doc in query.stream():
        data: Dict[str, Any] = _typed_doc(doc)
        day = _safe_bucket_int(data.get('day'))
        if day is None or not 1 <= day <= 31:
            continue
        row = daily_totals.setdefault(day, _history_zero_row())
        for key in _HISTORY_COUNTER_KEYS:
            row[key] += _safe_counter(data.get(key, 0))

    history: List[Dict[str, Any]] = [
        {'date': f"{date.year}-{date.month:02d}-{day:02d}", **stats} for day, stats in daily_totals.items()
    ]
    history.sort(key=lambda x: cast(str, x['date']))
    return history


def get_monthly_history_for_year(uid: str, date: datetime) -> List[Dict[str, Any]]:
    """Gets monthly usage for a specific year by aggregating hourly data."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    query = hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year))
    monthly_totals: Dict[int, Dict[str, int]] = {}
    for doc in query.stream():
        data: Dict[str, Any] = _typed_doc(doc)
        month = _safe_bucket_int(data.get('month'))
        if month is None or not 1 <= month <= 12:
            continue
        row = monthly_totals.setdefault(month, _history_zero_row())
        for key in _HISTORY_COUNTER_KEYS:
            row[key] += _safe_counter(data.get(key, 0))

    history: List[Dict[str, Any]] = [
        {'date': f"{date.year}-{month:02d}-01", **stats} for month, stats in monthly_totals.items()
    ]
    history.sort(key=lambda x: cast(str, x['date']))
    return history


def get_yearly_history(uid: str) -> List[Dict[str, Any]]:
    """Gets yearly usage for all time by aggregating hourly data."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    yearly_totals: Dict[int, Dict[str, int]] = {}
    for doc in hourly_usage_collection.stream():
        data: Dict[str, Any] = _typed_doc(doc)
        year = _safe_bucket_int(data.get('year'))
        if year is None or year <= 0:
            continue
        row = yearly_totals.setdefault(year, _history_zero_row())
        for key in _HISTORY_COUNTER_KEYS:
            row[key] += _safe_counter(data.get(key, 0))

    history: List[Dict[str, Any]] = [{'date': f"{year}-01-01", **stats} for year, stats in yearly_totals.items()]
    history.sort(key=lambda x: cast(str, x['date']))
    return history


def _read_all_time_usage(uid: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Read hourly usage once while building both the total and yearly history."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    stats: Dict[str, Any] = {key: 0 for key in _HOURLY_COUNTER_KEYS}
    yearly_totals: Dict[int, Dict[str, int]] = {}
    document_count = 0
    for doc in hourly_usage_collection.stream():
        document_count += 1
        data = _typed_doc(doc)
        for key in stats:
            stats[key] += _safe_counter(data.get(key, 0))
        year = _safe_bucket_int(data.get('year'))
        if year is None or year <= 0:
            continue
        year_stats = yearly_totals.setdefault(year, _history_zero_row())
        for key in _HISTORY_COUNTER_KEYS:
            year_stats[key] += _safe_counter(data.get(key, 0))

    record_firestore_read(FirestoreReadFamily.ALL_TIME_USAGE, FirestoreReadMode.UNBOUNDED, document_count)
    history = [{'date': f"{year}-01-01", **year_stats} for year, year_stats in yearly_totals.items()]
    history.sort(key=lambda x: cast(str, x['date']))
    return stats, history


def get_current_user_usage(
    uid: str, period: str, tz_name: Optional[str] = None, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """Gets usage for the current user for a specific period from Firestore.

    ``tz_name`` (IANA zone, e.g. "America/Los_Angeles") anchors period='today'
    to the caller's local calendar day instead of the UTC calendar day. Without
    it, users west of UTC see "today" reset hours before their real midnight,
    and users east of UTC see the tail of their local yesterday counted as
    "today" — since usage docs are written on UTC dates but this endpoint is
    read by a user thinking in their own timezone.
    """
    now = now or datetime.now(timezone.utc)
    response: Dict[str, Any] = {}

    if period == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        if tz_name:
            try:
                user_tz = pytz.timezone(tz_name)
                display_date = now.astimezone(user_tz).date()
                start = user_tz.localize(datetime.combine(display_date, time.min)).astimezone(timezone.utc)
                end = user_tz.localize(datetime.combine(display_date, time.max)).astimezone(timezone.utc)
            except Exception as e:
                # Keep serving the UTC day rather than failing the request, but say so: a stored
                # zone we cannot parse is a data problem worth seeing, not something to swallow.
                logger.error('usage today tz fallback to UTC uid=%s tz=%s: %s', uid, tz_name, e)
        response['today'] = UsageStats(**get_today_usage_stats(uid, start, end)).model_dump()
        response['history'] = get_hourly_history_for_today(uid, start, end)
    elif period == 'monthly':
        response['monthly'] = UsageStats(**get_monthly_usage_stats(uid, now)).model_dump()
        response['history'] = get_daily_history_for_month(uid, now)
    elif period == 'yearly':
        response['yearly'] = UsageStats(**get_yearly_usage_stats(uid, now)).model_dump()
        response['history'] = get_monthly_history_for_year(uid, now)
    elif period == 'all_time':
        all_time, history = _read_all_time_usage(uid)
        response['all_time'] = UsageStats(**all_time).model_dump()
        response['history'] = history

    return response

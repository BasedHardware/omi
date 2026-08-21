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
            total += int(child or 0)
    return total


def _accumulate_plan_data(row: Dict[str, Any], value: Dict[str, Any]) -> None:
    """Collect metrics from both flat bucket and feature/model plan layouts."""
    for key, child in value.items():
        if key == '_metadata':
            continue
        if isinstance(child, dict):
            _accumulate_plan_data(row, child)
            continue
        if key == 'quota_questions':
            row['questions'] += int(child or 0)
        elif key == 'input_tokens':
            row['input_tokens'] += int(child or 0)
        elif key == 'output_tokens':
            row['output_tokens'] += int(child or 0)
        elif key == 'total_tokens':
            row['total_tokens'] += int(child or 0)
        elif key == 'cost_usd':
            row['cost_usd'] = (row['cost_usd'] or 0.0) + float(child or 0.0)
        elif key in {
            'transcription_seconds',
            'words_transcribed',
            'insights_gained',
            'memories_created',
            'speech_seconds',
        }:
            row[key] = row.get(key, 0) + int(child or 0)


def get_monthly_chat_usage(
    uid: str, now: Optional[datetime] = None, *, firestore_client: Any | None = None
) -> Dict[str, Any]:
    """Sum current-month chat usage from `users/{uid}/llm_usage/{YYYY-MM-DD}` docs.

    Returns keys:
      - questions: total user-initiated chat calls (desktop/backend quota counters + legacy backend `chat.*`)
      - cost_usd:  legacy total desktop_chat* cost_usd for existing quota callers
      - usage_by_plan: catalog-plan rows; missing cost is ``None``, never a fake zero
      - reset_at:  unix seconds of the start of next UTC month (when the bucket resets)

    Proactive, memory-extraction, knowledge-graph, conversation-processing etc. are
    excluded on purpose — those are company-driven, not user-initiated questions.
    """
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
        plan_usage = data.get('plan_usage')
        plan_attributed_questions = 0
        if isinstance(plan_usage, dict):
            for plan_id, plan_data in plan_usage.items():
                if not isinstance(plan_data, dict):
                    continue
                plan_attributed_questions += _plan_data_questions(plan_data)
                row = usage_by_plan.setdefault(str(plan_id), _plan_usage_row())
                metadata = plan_data.get('_metadata')
                if isinstance(metadata, dict):
                    status_counts = metadata.get('cost_status_counts')
                    if isinstance(status_counts, dict):
                        for status, count in status_counts.items():
                            if int(count or 0) > 0:
                                row['cost_status'] = _merge_cost_status(row['cost_status'], str(status))
                    exclusions = metadata.get('cost_exclusions')
                    if isinstance(exclusions, dict):
                        for exclusion, count in exclusions.items():
                            key = str(exclusion)
                            row['cost_exclusions'][key] = row['cost_exclusions'].get(key, 0) + int(count or 0)
                _accumulate_plan_data(row, plan_data)

        has_desktop_realtime_quota_questions = 'desktop_chat_realtime.quota_questions' in data or (
            isinstance(data.get('desktop_chat_realtime'), dict) and 'quota_questions' in data['desktop_chat_realtime']
        )
        has_backend_quota_questions = any(
            (key == 'backend_chat' and isinstance(value, dict) and 'quota_questions' in value)
            or (key == 'backend_chat.quota_questions')
            for key, value in data.items()
        )
        for key, value in data.items():
            # The Rust desktop-backend commits desktop_chat usage via dotted Firestore
            # fieldPaths, which Firestore materializes as a NESTED map. Keep
            # `call_count` as internal generation telemetry; quota enforcement uses
            # `quota_questions`, incremented once per visible desktop user turn.
            if isinstance(value, dict):
                value_dict = cast(Dict[str, Any], value)
                if key == 'desktop_chat':
                    questions += int(value_dict.get('quota_questions', 0) or 0)
                    cost_usd += float(value_dict.get('cost_usd', 0) or 0)
                elif key == 'desktop_chat_realtime' and not has_desktop_realtime_quota_questions:
                    # Rollout bridge: old managed realtime turns only wrote
                    # call_count. New realtime writes both the grand-total
                    # desktop_chat.quota_questions counter and this breakdown's
                    # quota_questions, so only fall back when the breakdown is absent.
                    questions += int(value_dict.get('call_count', 0) or 0)
                elif key == 'backend_chat':
                    questions += int(value_dict.get('quota_questions', 0) or 0)
                continue
            if not isinstance(value, (int, float)):
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
                # Legacy user-initiated backend chat (any model). New writes use
                # backend_chat.quota_questions so LLM telemetry no longer drives quota.
                questions += int(value)

        # Anything the document's root counters report that `plan_usage` does not
        # account for is unattributed. Two cases reach here:
        #
        #  * No plan_usage at all -- a historical row written before attribution.
        #  * MIXED rows: the first post-deploy write adds plan_usage to a document
        #    that already carries pre-deploy root counters. Keying only on the
        #    absence of plan_usage would drop that residual entirely, so a user's
        #    earlier questions would silently vanish from per-plan reporting for
        #    the rest of the month.
        #
        # Reporting the residual as `_unattributed` keeps the totals honest. It is
        # never folded into a real plan, because we do not know which plan earned it.
        document_questions = questions - questions_before_document
        residual_questions = document_questions - plan_attributed_questions
        # A document with no plan_usage is entirely unattributed; one WITH plan_usage
        # contributes only what plan_usage fails to account for. Guard on the residual
        # in both cases so a fully attributed document creates no phantom row.
        if residual_questions > 0:
            legacy_row = usage_by_plan.setdefault(_UNATTRIBUTED_PLAN, _plan_usage_row())
            legacy_row['questions'] += residual_questions
            legacy_row['cost_status'] = 'missing'
            legacy_row['cost_exclusions']['plan_snapshot_missing'] = (
                legacy_row['cost_exclusions'].get('plan_snapshot_missing', 0) + 1
            )

    record_firestore_read(
        FirestoreReadFamily.CHAT_QUOTA_MONTHLY_USAGE,
        FirestoreReadMode.BOUNDED,
        document_count,
    )

    # Compute end-of-month boundary in UTC for the reset timestamp.
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
    """Join current-month chat and hourly usage under server-resolved plans.

    Rows are safe to join to the catalog by key. Historical rows without a
    plan snapshot use ``_unattributed`` and retain ``None`` for unmeasured
    cost, so this report cannot turn missing COGS into a free-looking zero.
    """
    now = now or datetime.now(timezone.utc)
    monthly = get_monthly_chat_usage(uid, now=now, firestore_client=firestore_client)
    report: Dict[str, Dict[str, Any]] = {plan_id: dict(row) for plan_id, row in monthly['usage_by_plan'].items()}
    hourly_ref = (firestore_client or db).collection('users').document(uid).collection('hourly_usage')
    query = hourly_ref.where(filter=FieldFilter('year', '==', now.year)).where(
        filter=FieldFilter('month', '==', now.month)
    )
    for snap in query.stream():
        data = _typed_doc(snap)
        plan_usage = data.get('plan_usage')
        if not isinstance(plan_usage, dict):
            row = report.setdefault(_UNATTRIBUTED_PLAN, _plan_usage_row())
            _accumulate_plan_data(row, data)
            row['cost_status'] = 'missing'
            row['cost_exclusions']['plan_snapshot_missing'] = row['cost_exclusions'].get('plan_snapshot_missing', 0) + 1
            continue
        for plan_id, plan_data in plan_usage.items():
            if not isinstance(plan_data, dict):
                continue
            row = report.setdefault(str(plan_id), _plan_usage_row())
            metadata = plan_data.get('_metadata')
            if isinstance(metadata, dict):
                counts = metadata.get('cost_status_counts')
                if isinstance(counts, dict):
                    for status, count in counts.items():
                        if int(count or 0) > 0:
                            row['cost_status'] = _merge_cost_status(row['cost_status'], str(status))
                exclusions = metadata.get('cost_exclusions')
                if isinstance(exclusions, dict):
                    for exclusion, count in exclusions.items():
                        key = str(exclusion)
                        row['cost_exclusions'][key] = row['cost_exclusions'].get(key, 0) + int(count or 0)
            _accumulate_plan_data(row, plan_data)

    for row in report.values():
        row['cost_status'] = row['cost_status'] or 'missing'
    return report


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
    """Updates or creates usage stats for a specific hour using Firestore atomic increments.

    Optional `platform` ('desktop' | 'mobile') is accumulated as an
    ArrayUnion so a single `hourly_usage/{date-hour}` doc can record activity
    from both platforms in the same hour without double-writing.
    """
    client = firestore_client or db
    user_ref = client.collection('users').document(uid)
    doc_id = f'{date.year}-{date.month:02d}-{date.day:02d}-{date.hour:02d}'
    hourly_usage_ref = user_ref.collection('hourly_usage').document(doc_id)

    update_doc: Dict[str, Any] = {'last_updated': datetime.now(timezone.utc)}
    has_increments = False

    for key, value in updates.items():
        if (
            key
            in ['transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds']
            and value > 0
        ):
            update_doc[key] = firestore.Increment(value)
            has_increments = True

    if not has_increments:
        return

    plan_key = resolve_usage_plan_id(uid, firestore_client=client) or _UNATTRIBUTED_PLAN
    plan_prefix = f'plan_usage.{plan_key}'
    for key, value in updates.items():
        if (
            key
            in {'transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds'}
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

    # Add year, month, day, hour fields for querying
    update_doc['year'] = date.year
    update_doc['month'] = date.month
    update_doc['day'] = date.day
    update_doc['hour'] = date.hour
    update_doc['id'] = doc_id
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
            key
            in {'transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds'}
            and value > 0
        ):
            update_doc[key] = firestore.Increment(value)
    has_increments = any(
        key in {'transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds'}
        for key in update_doc
    )
    if not has_increments:
        return False
    plan_key = resolve_usage_plan_id(uid, firestore_client=client) or _UNATTRIBUTED_PLAN
    plan_prefix = f'plan_usage.{plan_key}'
    for key, value in updates.items():
        if (
            key
            in {'transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds'}
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
            # Add year, month, day, hour fields for querying
            update_doc['year'] = date.year
            update_doc['month'] = date.month
            update_doc['day'] = date.day
            update_doc['hour'] = date.hour
            update_doc['id'] = doc_id
            update_doc['last_updated'] = datetime.now(timezone.utc)

            batch.set(hourly_usage_ref, update_doc, merge=True)
        batch.commit()


def get_today_usage_stats(uid: str, start: datetime, end: datetime) -> Dict[str, Any]:
    """Aggregates hourly usage stats for the UTC bucket range [start, end).

    The range may span two UTC calendar days when it represents the caller's
    local "today" rather than a UTC day (see get_current_user_usage) — hourly
    docs are written keyed by UTC date, so a user whose local midnight doesn't
    land on a UTC midnight has their day's buckets split across two UTC dates.
    """
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')

    stats: Dict[str, Any] = {
        'transcription_seconds': 0,
        'words_transcribed': 0,
        'insights_gained': 0,
        'memories_created': 0,
        'speech_seconds': 0,
    }
    cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor < end:
        query = (
            hourly_usage_collection.where(filter=FieldFilter('year', '==', cursor.year))
            .where(filter=FieldFilter('month', '==', cursor.month))
            .where(filter=FieldFilter('day', '==', cursor.day))
        )
        for doc in query.stream():
            data = _typed_doc(doc)
            bucket_hour = cursor.replace(hour=int(data.get('hour', 0)))
            if start <= bucket_hour < end:
                for key in stats:
                    stats[key] += data.get(key, 0)
        cursor += timedelta(days=1)
    return stats


def _aggregate_stats(query: Any) -> Dict[str, Any]:
    return _aggregate_stats_from_docs(query.stream())


def _aggregate_stats_from_docs(docs: Iterable[Any]) -> Dict[str, Any]:
    stats, _ = _aggregate_stats_with_count(docs)
    return stats


def _aggregate_stats_with_count(docs: Iterable[Any]) -> Tuple[Dict[str, Any], int]:
    stats: Dict[str, Any] = {
        'transcription_seconds': 0,
        'words_transcribed': 0,
        'insights_gained': 0,
        'memories_created': 0,
        'speech_seconds': 0,
    }
    document_count = 0
    for doc in docs:
        document_count += 1
        data: Dict[str, Any] = _typed_doc(doc)
        stats['transcription_seconds'] += data.get('transcription_seconds', 0)
        stats['words_transcribed'] += data.get('words_transcribed', 0)
        stats['insights_gained'] += data.get('insights_gained', 0)
        stats['memories_created'] += data.get('memories_created', 0)
        stats['speech_seconds'] += data.get('speech_seconds', 0)
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
    record_firestore_read(
        FirestoreReadFamily.LISTEN_MONTHLY_USAGE,
        FirestoreReadMode.UNBOUNDED,
        document_count,
    )
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


def get_hourly_history_for_today(uid: str, date: datetime) -> List[Dict[str, Any]]:
    """Gets hourly usage for a specific day by aggregating hourly data."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    query = (
        hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year))
        .where(filter=FieldFilter('month', '==', date.month))
        .where(filter=FieldFilter('day', '==', date.day))
    )
    docs = query.stream()
    hourly_totals: Dict[int, Dict[str, int]] = {}
    for doc in docs:
        data: Dict[str, Any] = _typed_doc(doc)
        hour = cast(int, data.get('hour', 0))
        if hour not in hourly_totals:
            hourly_totals[hour] = {
                'transcription_seconds': 0,
                'words_transcribed': 0,
                'insights_gained': 0,
                'memories_created': 0,
            }

        hourly_totals[hour]['transcription_seconds'] += cast(int, data.get('transcription_seconds', 0))
        hourly_totals[hour]['words_transcribed'] += cast(int, data.get('words_transcribed', 0))
        hourly_totals[hour]['insights_gained'] += cast(int, data.get('insights_gained', 0))
        hourly_totals[hour]['memories_created'] += cast(int, data.get('memories_created', 0))

    history: List[Dict[str, Any]] = [
        {'date': f"{date.year}-{date.month:02d}-{date.day:02d}T{hour:02d}:00:00Z", **stats}
        for hour, stats in hourly_totals.items()
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
    docs = query.stream()
    daily_totals: Dict[int, Dict[str, int]] = {}
    for doc in docs:
        data: Dict[str, Any] = _typed_doc(doc)
        day = cast(int, data.get('day', 0))
        if day not in daily_totals:
            daily_totals[day] = {
                'transcription_seconds': 0,
                'words_transcribed': 0,
                'insights_gained': 0,
                'memories_created': 0,
            }

        daily_totals[day]['transcription_seconds'] += cast(int, data.get('transcription_seconds', 0))
        daily_totals[day]['words_transcribed'] += cast(int, data.get('words_transcribed', 0))
        daily_totals[day]['insights_gained'] += cast(int, data.get('insights_gained', 0))
        daily_totals[day]['memories_created'] += cast(int, data.get('memories_created', 0))

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
    docs = query.stream()
    monthly_totals: Dict[int, Dict[str, int]] = {}
    for doc in docs:
        data: Dict[str, Any] = _typed_doc(doc)
        month = cast(int, data.get('month', 0))
        if month not in monthly_totals:
            monthly_totals[month] = {
                'transcription_seconds': 0,
                'words_transcribed': 0,
                'insights_gained': 0,
                'memories_created': 0,
            }

        monthly_totals[month]['transcription_seconds'] += cast(int, data.get('transcription_seconds', 0))
        monthly_totals[month]['words_transcribed'] += cast(int, data.get('words_transcribed', 0))
        monthly_totals[month]['insights_gained'] += cast(int, data.get('insights_gained', 0))
        monthly_totals[month]['memories_created'] += cast(int, data.get('memories_created', 0))

    history: List[Dict[str, Any]] = [
        {'date': f"{date.year}-{month:02d}-01", **stats} for month, stats in monthly_totals.items()
    ]
    history.sort(key=lambda x: cast(str, x['date']))
    return history


def get_yearly_history(uid: str) -> List[Dict[str, Any]]:
    """Gets yearly usage for all time by aggregating hourly data."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    docs = hourly_usage_collection.stream()
    yearly_totals: Dict[int, Dict[str, int]] = {}
    for doc in docs:
        data: Dict[str, Any] = _typed_doc(doc)
        year = cast(int, data.get('year', 0))
        if year not in yearly_totals:
            yearly_totals[year] = {
                'transcription_seconds': 0,
                'words_transcribed': 0,
                'insights_gained': 0,
                'memories_created': 0,
            }

        yearly_totals[year]['transcription_seconds'] += cast(int, data.get('transcription_seconds', 0))
        yearly_totals[year]['words_transcribed'] += cast(int, data.get('words_transcribed', 0))
        yearly_totals[year]['insights_gained'] += cast(int, data.get('insights_gained', 0))
        yearly_totals[year]['memories_created'] += cast(int, data.get('memories_created', 0))

    history: List[Dict[str, Any]] = [{'date': f"{year}-01-01", **stats} for year, stats in yearly_totals.items()]
    history.sort(key=lambda x: cast(str, x['date']))
    return history


def _read_all_time_usage(uid: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Read hourly usage once while building both the total and yearly history."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    stats: Dict[str, Any] = {
        'transcription_seconds': 0,
        'words_transcribed': 0,
        'insights_gained': 0,
        'memories_created': 0,
        'speech_seconds': 0,
    }
    yearly_totals: Dict[int, Dict[str, int]] = {}
    document_count = 0
    for doc in hourly_usage_collection.stream():
        document_count += 1
        data = _typed_doc(doc)
        for key in stats:
            stats[key] += data.get(key, 0)
        year = cast(int, data.get('year', 0))
        year_stats = yearly_totals.setdefault(
            year,
            {
                'transcription_seconds': 0,
                'words_transcribed': 0,
                'insights_gained': 0,
                'memories_created': 0,
            },
        )
        for key in year_stats:
            year_stats[key] += data.get(key, 0)

    record_firestore_read(
        FirestoreReadFamily.ALL_TIME_USAGE,
        FirestoreReadMode.UNBOUNDED,
        document_count,
    )
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
        response['history'] = get_hourly_history_for_today(uid, now)
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

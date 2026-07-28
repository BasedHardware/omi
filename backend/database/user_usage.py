import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

import pytz
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db
from .firestore_read_metrics import FirestoreReadFamily, FirestoreReadMode, record_firestore_read
from models.user_usage import UsageStats

logger = logging.getLogger(__name__)


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Typed adapter for a Firestore snapshot's `to_dict()` (SDK stub gap)."""
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def get_monthly_chat_usage(uid: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Sum current-month chat usage from `users/{uid}/llm_usage/{YYYY-MM-DD}` docs.

    Returns keys:
      - questions: total user-initiated chat calls (desktop/backend quota counters + legacy backend `chat.*`)
      - cost_usd:  total desktop_chat* cost_usd (backend GPT/Gemini chat has no cost field)
      - reset_at:  unix seconds of the start of next UTC month (when the bucket resets)

    Proactive, memory-extraction, knowledge-graph, conversation-processing etc. are
    excluded on purpose — those are company-driven, not user-initiated questions.
    """
    now = now or datetime.now(timezone.utc)
    month_prefix = f'{now.year}-{now.month:02d}-'

    llm_usage_ref = db.collection('users').document(uid).collection('llm_usage')
    questions = 0
    cost_usd = 0.0
    for doc in llm_usage_ref.list_documents():
        if not doc.id.startswith(month_prefix):
            continue
        snap = doc.get()
        if not snap.exists:
            continue
        data: Dict[str, Any] = _typed_doc(snap)
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

    # Compute end-of-month boundary in UTC for the reset timestamp.
    if now.month == 12:
        next_year, next_month = now.year + 1, 1
    else:
        next_year, next_month = now.year, now.month + 1
    reset_at = int(datetime(next_year, next_month, 1, tzinfo=timezone.utc).timestamp())

    return {
        'questions': questions,
        'cost_usd': round(cost_usd, 4),
        'reset_at': reset_at,
    }


def update_hourly_usage(uid: str, date: datetime, updates: Dict[str, Any], platform: Optional[str] = None) -> None:
    """Updates or creates usage stats for a specific hour using Firestore atomic increments.

    Optional `platform` ('desktop' | 'mobile') is accumulated as an
    ArrayUnion so a single `hourly_usage/{date-hour}` doc can record activity
    from both platforms in the same hour without double-writing.
    """
    user_ref = db.collection('users').document(uid)
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


def update_hourly_usage_once(uid: str, date: datetime, updates: Dict[str, Any], idempotency_key: str) -> bool:
    """Atomically increment hourly usage once for a stable sync content key."""
    user_ref = db.collection('users').document(uid)
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
    if len(update_doc) == 6:
        return False
    return _update_hourly_usage_once_transaction(db.transaction(), marker_ref, usage_ref, update_doc)


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
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    return _aggregate_stats(hourly_usage_collection)


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
        response['all_time'] = UsageStats(**get_all_time_usage_stats(uid)).model_dump()
        response['history'] = get_yearly_history(uid)

    return response

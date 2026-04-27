from calendar import monthrange
from datetime import datetime, timezone
from typing import Optional
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db
from models.user_usage import UsageStats


def get_monthly_chat_usage(uid: str, now: Optional[datetime] = None) -> dict:
    """Sum current-month chat usage from `users/{uid}/llm_usage/{YYYY-MM-DD}` docs.

    Returns keys:
      - questions: total user-initiated chat calls (desktop_chat* + backend `chat.*`)
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
        data = snap.to_dict() or {}
        for key, value in data.items():
            if not isinstance(value, (int, float)):
                continue
            if key.startswith('desktop_chat'):
                if key.endswith('.call_count'):
                    questions += int(value)
                elif key.endswith('.cost_usd'):
                    cost_usd += float(value)
            elif key.startswith('chat.') and key.endswith('.call_count'):
                # user-initiated backend chat (any model)
                questions += int(value)

    # Compute end-of-month boundary in UTC for the reset timestamp.
    last_day = monthrange(now.year, now.month)[1]
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


def update_hourly_usage(uid: str, date: datetime, updates: dict, platform: Optional[str] = None):
    """Updates or creates usage stats for a specific hour using Firestore atomic increments.

    Optional `platform` ('desktop' | 'mobile') is accumulated as an
    ArrayUnion so a single `hourly_usage/{date-hour}` doc can record activity
    from both platforms in the same hour without double-writing.
    """
    user_ref = db.collection('users').document(uid)
    doc_id = f'{date.year}-{date.month:02d}-{date.day:02d}-{date.hour:02d}'
    hourly_usage_ref = user_ref.collection('hourly_usage').document(doc_id)

    update_doc = {'last_updated': datetime.utcnow()}
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


def batch_update_hourly_usage(uid: str, hourly_updates: dict):
    """Batch updates or creates usage stats for multiple hours."""
    batch_size = 400
    items = list(hourly_updates.items())

    for i in range(0, len(items), batch_size):
        batch = db.batch()
        chunk = items[i : i + batch_size]
        for date, updates in chunk:
            doc_id = f'{date.year}-{date.month:02d}-{date.day:02d}-{date.hour:02d}'
            hourly_usage_ref = db.collection('users').document(uid).collection('hourly_usage').document(doc_id)

            update_doc = updates.copy()
            # Add year, month, day, hour fields for querying
            update_doc['year'] = date.year
            update_doc['month'] = date.month
            update_doc['day'] = date.day
            update_doc['hour'] = date.hour
            update_doc['id'] = doc_id
            update_doc['last_updated'] = datetime.utcnow()

            batch.set(hourly_usage_ref, update_doc, merge=True)
        batch.commit()


def get_today_usage_stats(uid: str, date: datetime) -> dict:
    """Aggregates hourly usage stats for a given day from Firestore."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')

    query = (
        hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year))
        .where(filter=FieldFilter('month', '==', date.month))
        .where(filter=FieldFilter('day', '==', date.day))
    )
    return _aggregate_stats(query)


def _aggregate_stats(query) -> dict:
    docs = query.stream()
    stats = {
        'transcription_seconds': 0,
        'words_transcribed': 0,
        'insights_gained': 0,
        'memories_created': 0,
        'speech_seconds': 0,
    }
    for doc in docs:
        data = doc.to_dict()
        stats['transcription_seconds'] += data.get('transcription_seconds', 0)
        stats['words_transcribed'] += data.get('words_transcribed', 0)
        stats['insights_gained'] += data.get('insights_gained', 0)
        stats['memories_created'] += data.get('memories_created', 0)
        stats['speech_seconds'] += data.get('speech_seconds', 0)
    return stats


def get_monthly_usage_stats(uid: str, date: datetime) -> dict:
    """Aggregates hourly usage stats for a given month from Firestore."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')

    query = hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year)).where(
        filter=FieldFilter('month', '==', date.month)
    )
    return _aggregate_stats(query)


def get_monthly_usage_stats_since(uid: str, date: datetime, start_date: datetime) -> dict:
    """Aggregates hourly usage stats for a given month from Firestore, starting from a specific date."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')

    start_doc_id = f'{start_date.year}-{start_date.month:02d}-{start_date.day:02d}-00'

    query = (
        hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year))
        .where(filter=FieldFilter('month', '==', date.month))
        .where(filter=FieldFilter('id', '>=', start_doc_id))
    )
    return _aggregate_stats(query)


def get_yearly_usage_stats(uid: str, date: datetime) -> dict:
    """Aggregates hourly usage stats for a given year from Firestore."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    query = hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year))
    return _aggregate_stats(query)


def get_all_time_usage_stats(uid: str) -> dict:
    """Aggregates all hourly usage stats for a user from Firestore."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    return _aggregate_stats(hourly_usage_collection)


def get_hourly_history_for_today(uid: str, date: datetime) -> list[dict]:
    """Gets hourly usage for a specific day by aggregating hourly data."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    query = (
        hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year))
        .where(filter=FieldFilter('month', '==', date.month))
        .where(filter=FieldFilter('day', '==', date.day))
    )
    docs = query.stream()
    hourly_totals = {}
    for doc in docs:
        data = doc.to_dict()
        hour = data.get('hour', 0)
        if hour not in hourly_totals:
            hourly_totals[hour] = {
                'transcription_seconds': 0,
                'words_transcribed': 0,
                'insights_gained': 0,
                'memories_created': 0,
            }

        hourly_totals[hour]['transcription_seconds'] += data.get('transcription_seconds', 0)
        hourly_totals[hour]['words_transcribed'] += data.get('words_transcribed', 0)
        hourly_totals[hour]['insights_gained'] += data.get('insights_gained', 0)
        hourly_totals[hour]['memories_created'] += data.get('memories_created', 0)

    history = [
        {'date': f"{date.year}-{date.month:02d}-{date.day:02d}T{hour:02d}:00:00Z", **stats}
        for hour, stats in hourly_totals.items()
    ]
    history.sort(key=lambda x: x['date'])
    return history


def get_daily_history_for_month(uid: str, date: datetime) -> list[dict]:
    """Gets daily usage for a specific month by aggregating hourly data."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    query = hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year)).where(
        filter=FieldFilter('month', '==', date.month)
    )
    docs = query.stream()
    daily_totals = {}
    for doc in docs:
        data = doc.to_dict()
        day = data.get('day', 0)
        if day not in daily_totals:
            daily_totals[day] = {
                'transcription_seconds': 0,
                'words_transcribed': 0,
                'insights_gained': 0,
                'memories_created': 0,
            }

        daily_totals[day]['transcription_seconds'] += data.get('transcription_seconds', 0)
        daily_totals[day]['words_transcribed'] += data.get('words_transcribed', 0)
        daily_totals[day]['insights_gained'] += data.get('insights_gained', 0)
        daily_totals[day]['memories_created'] += data.get('memories_created', 0)

    history = [{'date': f"{date.year}-{date.month:02d}-{day:02d}", **stats} for day, stats in daily_totals.items()]
    history.sort(key=lambda x: x['date'])
    return history


def get_monthly_history_for_year(uid: str, date: datetime) -> list[dict]:
    """Gets monthly usage for a specific year by aggregating hourly data."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    query = hourly_usage_collection.where(filter=FieldFilter('year', '==', date.year))
    docs = query.stream()
    monthly_totals = {}
    for doc in docs:
        data = doc.to_dict()
        month = data.get('month', 0)
        if month not in monthly_totals:
            monthly_totals[month] = {
                'transcription_seconds': 0,
                'words_transcribed': 0,
                'insights_gained': 0,
                'memories_created': 0,
            }

        monthly_totals[month]['transcription_seconds'] += data.get('transcription_seconds', 0)
        monthly_totals[month]['words_transcribed'] += data.get('words_transcribed', 0)
        monthly_totals[month]['insights_gained'] += data.get('insights_gained', 0)
        monthly_totals[month]['memories_created'] += data.get('memories_created', 0)

    history = [{'date': f"{date.year}-{month:02d}-01", **stats} for month, stats in monthly_totals.items()]
    history.sort(key=lambda x: x['date'])
    return history


def get_yearly_history(uid: str) -> list[dict]:
    """Gets yearly usage for all time by aggregating hourly data."""
    user_ref = db.collection('users').document(uid)
    hourly_usage_collection = user_ref.collection('hourly_usage')
    docs = hourly_usage_collection.stream()
    yearly_totals = {}
    for doc in docs:
        data = doc.to_dict()
        year = data.get('year', 0)
        if year not in yearly_totals:
            yearly_totals[year] = {
                'transcription_seconds': 0,
                'words_transcribed': 0,
                'insights_gained': 0,
                'memories_created': 0,
            }

        yearly_totals[year]['transcription_seconds'] += data.get('transcription_seconds', 0)
        yearly_totals[year]['words_transcribed'] += data.get('words_transcribed', 0)
        yearly_totals[year]['insights_gained'] += data.get('insights_gained', 0)
        yearly_totals[year]['memories_created'] += data.get('memories_created', 0)

    history = [{'date': f"{year}-01-01", **stats} for year, stats in yearly_totals.items()]
    history.sort(key=lambda x: x['date'])
    return history


def get_current_user_usage(uid: str, period: str) -> dict:
    """Gets usage for the current user for a specific period from Firestore."""
    now = datetime.utcnow()
    response = {}

    if period == 'today':
        response['today'] = UsageStats(**get_today_usage_stats(uid, now)).dict()
        response['history'] = get_hourly_history_for_today(uid, now)
    elif period == 'monthly':
        response['monthly'] = UsageStats(**get_monthly_usage_stats(uid, now)).dict()
        response['history'] = get_daily_history_for_month(uid, now)
    elif period == 'yearly':
        response['yearly'] = UsageStats(**get_yearly_usage_stats(uid, now)).dict()
        response['history'] = get_monthly_history_for_year(uid, now)
    elif period == 'all_time':
        response['all_time'] = UsageStats(**get_all_time_usage_stats(uid)).dict()
        response['history'] = get_yearly_history(uid)

    return response

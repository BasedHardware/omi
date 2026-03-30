"""
Desktop-specific Firestore CRUD operations.

Collections:
- users/{uid}/staged_tasks       — AI-generated tasks awaiting promotion
- users/{uid}/focus_sessions     — Focus/distraction tracking
- users/{uid}/advice             — Proactive coaching advice
- users/{uid}/chat_sessions      — Multi-session chat grouping (v2)

Also handles:
- Notification settings (user doc fields)
- Assistant settings (user doc nested map)
- AI user profile (user doc nested map)
- Daily score calculation from action_items
- Desktop LLM usage recording (per-query token tracking)
- Desktop chat message persistence (v2)
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# STAGED TASKS — users/{uid}/staged_tasks
# ============================================================================


def create_staged_task(uid: str, data: dict) -> dict:
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        'id': task_id,
        'description': data['description'],
        'completed': False,
        'created_at': now,
        'updated_at': now,
        'due_at': data.get('due_at'),
        'source': data.get('source'),
        'priority': data.get('priority'),
        'metadata': data.get('metadata'),
        'category': data.get('category'),
        'relevance_score': data.get('relevance_score'),
        'from_staged': True,
    }
    ref = db.collection('users').document(uid).collection('staged_tasks').document(task_id)
    ref.set(doc)
    return doc


def get_staged_tasks(uid: str, limit: int = 100, offset: int = 0) -> List[dict]:
    col = db.collection('users').document(uid).collection('staged_tasks')
    query = col.where(filter=FieldFilter('completed', '==', False))
    query = query.order_by('relevance_score', direction=firestore.Query.ASCENDING)
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
    if offset > 0:
        query = query.offset(offset)
    query = query.limit(limit)
    return [{**doc.to_dict(), 'id': doc.id} for doc in query.stream()]


def delete_staged_task(uid: str, task_id: str) -> bool:
    ref = db.collection('users').document(uid).collection('staged_tasks').document(task_id)
    doc = ref.get()
    if not doc.exists:
        return False
    ref.delete()
    return True


def batch_update_staged_scores(uid: str, scores: List[dict]) -> None:
    col = db.collection('users').document(uid).collection('staged_tasks')
    now = datetime.now(timezone.utc)
    batch = db.batch()
    count = 0
    for item in scores:
        ref = col.document(item['id'])
        batch.update(ref, {'relevance_score': item['relevance_score'], 'updated_at': now})
        count += 1
        if count >= 499:
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()


def get_active_ai_action_items(uid: str) -> List[dict]:
    """Get active AI action items (from_staged=true, not completed, not deleted)."""
    col = db.collection('users').document(uid).collection('action_items')
    query = col.where(filter=FieldFilter('from_staged', '==', True))
    query = query.where(filter=FieldFilter('completed', '==', False))
    items = []
    for doc in query.stream():
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        data['id'] = doc.id
        items.append(data)
    return items


def promote_staged_task(uid: str) -> dict:
    """Promote top-ranked staged task to action_items. Returns status dict."""
    active = get_active_ai_action_items(uid)
    if len(active) >= 5:
        return {'promoted': False, 'reason': f'Already have {len(active)} active AI tasks (max 5)'}

    existing_descs = {
        item['description'].strip().lower().removeprefix('[screen] ').removesuffix(' [screen]') for item in active
    }

    staged = get_staged_tasks(uid, limit=20, offset=0)
    if not staged:
        return {'promoted': False, 'reason': 'No staged tasks available'}

    selected = None
    duplicate_ids = []
    seen = set()
    for task in staged:
        norm = task['description'].strip().lower().removeprefix('[screen] ').removesuffix(' [screen]')
        if norm in existing_descs or norm in seen:
            duplicate_ids.append(task['id'])
            continue
        seen.add(norm)
        if selected is None:
            selected = task

    # Clean up duplicates
    for dup_id in duplicate_ids:
        delete_staged_task(uid, dup_id)

    if selected is None:
        return {'promoted': False, 'reason': 'All candidate staged tasks are duplicates'}

    # Create in action_items
    action_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    action_doc = {
        'id': action_id,
        'description': selected['description'],
        'completed': False,
        'created_at': now,
        'updated_at': now,
        'due_at': selected.get('due_at'),
        'source': selected.get('source'),
        'priority': selected.get('priority'),
        'metadata': selected.get('metadata'),
        'category': selected.get('category'),
        'relevance_score': selected.get('relevance_score'),
        'from_staged': True,
    }
    db.collection('users').document(uid).collection('action_items').document(action_id).set(action_doc)
    delete_staged_task(uid, selected['id'])

    return {'promoted': True, 'reason': None, 'promoted_task': action_doc}


def migrate_ai_tasks(uid: str) -> dict:
    """One-time migration: move excess AI tasks from action_items to staged_tasks."""
    col = db.collection('users').document(uid).collection('action_items')
    query = col.where(filter=FieldFilter('completed', '==', False))
    all_items = []
    for doc in query.stream():
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        data['id'] = doc.id
        all_items.append(data)

    ai_tasks = [item for item in all_items if item.get('source', '').find('screenshot') >= 0]
    if not ai_tasks:
        return {'status': 'ok'}

    ai_tasks.sort(key=lambda x: x.get('relevance_score') or 2147483647)

    # Tag top 5 with [screen] suffix
    for task in ai_tasks[:5]:
        desc = task['description']
        if not desc.endswith(' [screen]') and not desc.startswith('[screen] '):
            col.document(task['id']).update({'description': f'{desc} [screen]'})

    # Move the rest to staged_tasks
    to_move = ai_tasks[5:]
    if not to_move:
        return {'status': 'ok'}

    staged_col = db.collection('users').document(uid).collection('staged_tasks')
    batch = db.batch()
    count = 0
    for task in to_move:
        batch.set(staged_col.document(task['id']), task)
        batch.delete(col.document(task['id']))
        count += 1
        if count >= 249:
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()

    return {'status': 'ok'}


def migrate_conversation_items_to_staged(uid: str) -> dict:
    """Migrate action items from old conversation extraction to staged_tasks."""
    col = db.collection('users').document(uid).collection('action_items')
    query = col.where(filter=FieldFilter('completed', '==', False))

    migrated = 0
    deleted = 0
    staged_col = db.collection('users').document(uid).collection('staged_tasks')
    batch = db.batch()
    count = 0

    for doc in query.stream():
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        # Items with conversation_id but no source are from old conversation extraction
        if data.get('conversation_id') and not data.get('source'):
            data['id'] = doc.id
            data['source'] = 'conversation'
            batch.set(staged_col.document(doc.id), data)
            batch.delete(col.document(doc.id))
            migrated += 1
            count += 1
            if count >= 249:
                batch.commit()
                batch = db.batch()
                count = 0

    if count > 0:
        batch.commit()

    return {'status': 'ok', 'migrated': migrated, 'deleted': deleted}


# ============================================================================
# FOCUS SESSIONS — users/{uid}/focus_sessions
# ============================================================================


def create_focus_session(uid: str, data: dict) -> dict:
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        'id': session_id,
        'status': data['status'],
        'app_or_site': data['app_or_site'],
        'description': data['description'],
        'message': data.get('message'),
        'created_at': now,
        'duration_seconds': data.get('duration_seconds'),
    }
    ref = db.collection('users').document(uid).collection('focus_sessions').document(session_id)
    ref.set(doc)
    return doc


def get_focus_sessions(uid: str, limit: int = 100, offset: int = 0, date: str = None) -> List[dict]:
    col = db.collection('users').document(uid).collection('focus_sessions')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)

    if date:
        start = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1) - timedelta(milliseconds=1)
        query = query.where(filter=FieldFilter('created_at', '>=', start))
        query = query.where(filter=FieldFilter('created_at', '<=', end))

    if offset > 0:
        query = query.offset(offset)
    query = query.limit(limit)
    return [{**doc.to_dict(), 'id': doc.id} for doc in query.stream()]


def delete_focus_session(uid: str, session_id: str) -> bool:
    ref = db.collection('users').document(uid).collection('focus_sessions').document(session_id)
    doc = ref.get()
    if not doc.exists:
        return False
    ref.delete()
    return True


def get_focus_stats(uid: str, date: str = None) -> dict:
    if not date:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    sessions = get_focus_sessions(uid, limit=5000, offset=0, date=date)

    focused_seconds = 0
    distracted_seconds = 0
    focused_count = 0
    distracted_count = 0
    distraction_times: Dict[str, int] = {}

    for s in sessions:
        dur = s.get('duration_seconds') or 0
        if s.get('status') == 'focused':
            focused_seconds += dur
            focused_count += 1
        else:
            distracted_seconds += dur
            distracted_count += 1
            app = s.get('app_or_site', 'Unknown')
            distraction_times[app] = distraction_times.get(app, 0) + dur

    top_distractions = sorted(distraction_times.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        'focused_minutes': round(focused_seconds / 60, 1),
        'distracted_minutes': round(distracted_seconds / 60, 1),
        'session_count': len(sessions),
        'focused_count': focused_count,
        'distracted_count': distracted_count,
        'top_distractions': [{'app': app, 'minutes': round(secs / 60, 1)} for app, secs in top_distractions],
    }


# ============================================================================
# ADVICE — users/{uid}/advice
# ============================================================================


def create_advice(uid: str, data: dict) -> dict:
    advice_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        'id': advice_id,
        'content': data['content'],
        'category': data.get('category', 'other'),
        'reasoning': data.get('reasoning'),
        'source_app': data.get('source_app'),
        'confidence': data.get('confidence', 0.5),
        'context_summary': data.get('context_summary'),
        'current_activity': data.get('current_activity'),
        'created_at': now,
        'updated_at': now,
        'is_read': False,
        'is_dismissed': False,
    }
    ref = db.collection('users').document(uid).collection('advice').document(advice_id)
    ref.set(doc)
    return doc


def get_advice(
    uid: str, limit: int = 100, offset: int = 0, category: str = None, include_dismissed: bool = False
) -> List[dict]:
    col = db.collection('users').document(uid).collection('advice')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)

    if not include_dismissed:
        query = query.where(filter=FieldFilter('is_dismissed', '==', False))
    if category:
        query = query.where(filter=FieldFilter('category', '==', category))

    if offset > 0:
        query = query.offset(offset)
    query = query.limit(limit)
    return [{**doc.to_dict(), 'id': doc.id} for doc in query.stream()]


def update_advice(uid: str, advice_id: str, is_read: bool = None, is_dismissed: bool = None) -> Optional[dict]:
    ref = db.collection('users').document(uid).collection('advice').document(advice_id)
    doc = ref.get()
    if not doc.exists:
        return None
    update = {'updated_at': datetime.now(timezone.utc)}
    if is_read is not None:
        update['is_read'] = is_read
    if is_dismissed is not None:
        update['is_dismissed'] = is_dismissed
    ref.update(update)
    data = ref.get().to_dict()
    data['id'] = advice_id
    return data


def delete_advice(uid: str, advice_id: str) -> bool:
    ref = db.collection('users').document(uid).collection('advice').document(advice_id)
    doc = ref.get()
    if not doc.exists:
        return False
    ref.delete()
    return True


def mark_all_advice_read(uid: str) -> int:
    col = db.collection('users').document(uid).collection('advice')
    query = col.where(filter=FieldFilter('is_read', '==', False))
    count = 0
    batch = db.batch()
    for doc in query.stream():
        batch.update(col.document(doc.id), {'is_read': True, 'updated_at': datetime.now(timezone.utc)})
        count += 1
        if count % 499 == 0:
            batch.commit()
            batch = db.batch()
    if count % 499 != 0:
        batch.commit()
    return count


# ============================================================================
# CHAT SESSIONS v2 — users/{uid}/chat_sessions
# ============================================================================


def create_chat_session(uid: str, title: str = None, app_id: str = None) -> dict:
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        'id': session_id,
        'title': title or 'New Chat',
        'preview': None,
        'created_at': now,
        'updated_at': now,
        'app_id': app_id,
        'message_count': 0,
        'starred': False,
    }
    ref = db.collection('users').document(uid).collection('chat_sessions').document(session_id)
    ref.set(doc)
    return doc


def get_chat_sessions(
    uid: str, app_id: str = None, limit: int = 50, offset: int = 0, starred: bool = None
) -> List[dict]:
    col = db.collection('users').document(uid).collection('chat_sessions')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)

    if app_id is not None:
        query = query.where(filter=FieldFilter('app_id', '==', app_id))
    if starred is not None:
        query = query.where(filter=FieldFilter('starred', '==', starred))

    if offset > 0:
        query = query.offset(offset)
    query = query.limit(limit)
    return [{**doc.to_dict(), 'id': doc.id} for doc in query.stream()]


def get_chat_session(uid: str, session_id: str) -> Optional[dict]:
    ref = db.collection('users').document(uid).collection('chat_sessions').document(session_id)
    doc = ref.get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    data['id'] = doc.id
    return data


def update_chat_session(uid: str, session_id: str, title: str = None, starred: bool = None) -> Optional[dict]:
    ref = db.collection('users').document(uid).collection('chat_sessions').document(session_id)
    doc = ref.get()
    if not doc.exists:
        return None
    update = {'updated_at': datetime.now(timezone.utc)}
    if title is not None:
        update['title'] = title
    if starred is not None:
        update['starred'] = starred
    ref.update(update)
    data = ref.get().to_dict()
    data['id'] = session_id
    return data


def delete_chat_session(uid: str, session_id: str) -> bool:
    ref = db.collection('users').document(uid).collection('chat_sessions').document(session_id)
    doc = ref.get()
    if not doc.exists:
        return False
    # Cascade delete messages for this session
    msg_col = db.collection('users').document(uid).collection('messages')
    msgs = msg_col.where(filter=FieldFilter('chat_session_id', '==', session_id)).stream()
    batch = db.batch()
    count = 0
    for msg_doc in msgs:
        batch.delete(msg_col.document(msg_doc.id))
        count += 1
        if count >= 499:
            batch.commit()
            batch = db.batch()
            count = 0
    ref_delete = ref
    batch.delete(ref_delete)
    batch.commit()
    return True


# ============================================================================
# DESKTOP MESSAGES v2 — users/{uid}/messages (persistence layer)
# ============================================================================


def save_desktop_message(uid: str, data: dict) -> dict:
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        'id': msg_id,
        'text': data['text'],
        'created_at': now,
        'sender': data['sender'],
        'app_id': data.get('app_id'),
        'session_id': data.get('session_id'),
        'chat_session_id': data.get('session_id'),  # backward compat
        'rating': None,
        'reported': False,
        'metadata': data.get('metadata'),
    }
    ref = db.collection('users').document(uid).collection('messages').document(msg_id)
    ref.set(doc)

    # Update chat session message count and preview if session_id provided
    session_id = data.get('session_id')
    if session_id:
        session_ref = db.collection('users').document(uid).collection('chat_sessions').document(session_id)
        session_ref.update(
            {
                'updated_at': now,
                'message_count': firestore.Increment(1),
                'preview': data['text'][:100] if data['text'] else None,
            }
        )

    return {'id': msg_id, 'created_at': now.isoformat()}


def get_desktop_messages(
    uid: str, app_id: str = None, session_id: str = None, limit: int = 100, offset: int = 0
) -> List[dict]:
    col = db.collection('users').document(uid).collection('messages')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)

    if app_id is not None:
        query = query.where(filter=FieldFilter('app_id', '==', app_id))
    if session_id is not None:
        query = query.where(filter=FieldFilter('chat_session_id', '==', session_id))

    if offset > 0:
        query = query.offset(offset)
    query = query.limit(limit)
    return [{**doc.to_dict(), 'id': doc.id} for doc in query.stream()]


def delete_desktop_messages(uid: str, app_id: str = None) -> int:
    col = db.collection('users').document(uid).collection('messages')
    if app_id:
        query = col.where(filter=FieldFilter('app_id', '==', app_id))
    else:
        query = col

    count = 0
    batch = db.batch()
    for doc in query.stream():
        batch.delete(col.document(doc.id))
        count += 1
        if count % 499 == 0:
            batch.commit()
            batch = db.batch()
    if count % 499 != 0:
        batch.commit()
    return count


def rate_desktop_message(uid: str, message_id: str, rating: Optional[int]) -> bool:
    ref = db.collection('users').document(uid).collection('messages').document(message_id)
    doc = ref.get()
    if not doc.exists:
        return False
    ref.update({'rating': rating})
    return True


# ============================================================================
# NOTIFICATION SETTINGS — user document fields
# ============================================================================


def get_notification_settings(uid: str) -> dict:
    user_ref = db.collection('users').document(uid)
    doc = user_ref.get()
    if not doc.exists:
        return {'enabled': True, 'frequency': 3}
    data = doc.to_dict()
    return {
        'enabled': data.get('notifications_enabled', True),
        'frequency': data.get('notification_frequency', 3),
    }


def update_notification_settings(uid: str, enabled: bool = None, frequency: int = None) -> dict:
    user_ref = db.collection('users').document(uid)
    update = {}
    if enabled is not None:
        update['notifications_enabled'] = enabled
    if frequency is not None:
        update['notification_frequency'] = frequency
    if update:
        user_ref.update(update)
    return get_notification_settings(uid)


# ============================================================================
# ASSISTANT SETTINGS — user document nested map
# ============================================================================


def get_assistant_settings(uid: str) -> dict:
    user_ref = db.collection('users').document(uid)
    doc = user_ref.get()
    if not doc.exists:
        return {}
    data = doc.to_dict()
    settings = data.get('assistant_settings', {})
    result = dict(settings)
    if 'update_channel' in data:
        result['update_channel'] = data['update_channel']
    return result


def update_assistant_settings(uid: str, settings: dict) -> dict:
    user_ref = db.collection('users').document(uid)
    update = {}

    # Extract update_channel if present (top-level field)
    update_channel = settings.pop('update_channel', None)
    if update_channel is not None:
        update['update_channel'] = update_channel

    # Merge assistant_settings
    if settings:
        # Use dot-notation to merge nested fields without overwriting entire map
        for key, value in settings.items():
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    update[f'assistant_settings.{key}.{subkey}'] = subvalue
            else:
                update[f'assistant_settings.{key}'] = value

    if update:
        user_ref.set(update, merge=True)

    return get_assistant_settings(uid)


# ============================================================================
# AI USER PROFILE — user document nested map
# ============================================================================


def get_ai_user_profile(uid: str) -> Optional[dict]:
    user_ref = db.collection('users').document(uid)
    doc = user_ref.get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    return data.get('ai_user_profile')


def update_ai_user_profile(uid: str, profile: dict) -> dict:
    user_ref = db.collection('users').document(uid)
    user_ref.set({'ai_user_profile': profile}, merge=True)
    return profile


# ============================================================================
# DAILY SCORE — calculated from action_items
# ============================================================================


def get_daily_score(uid: str, date: str = None) -> dict:
    if not date:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    start = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1) - timedelta(milliseconds=1)

    col = db.collection('users').document(uid).collection('action_items')
    query = col.where(filter=FieldFilter('due_at', '>=', start))
    query = query.where(filter=FieldFilter('due_at', '<=', end))

    completed = 0
    total = 0
    for doc in query.stream():
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        total += 1
        if data.get('completed'):
            completed += 1

    score = (completed / total * 100.0) if total > 0 else 0.0
    return {'score': score, 'completed_tasks': completed, 'total_tasks': total, 'date': date}


def get_scores(uid: str, date: str = None) -> dict:
    if not date:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    today = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    today_end = today + timedelta(days=1) - timedelta(milliseconds=1)
    week_ago = today - timedelta(days=7)

    col = db.collection('users').document(uid).collection('action_items')

    # Daily: tasks due today
    daily_q = col.where(filter=FieldFilter('due_at', '>=', today))
    daily_q = daily_q.where(filter=FieldFilter('due_at', '<=', today_end))
    daily_completed = 0
    daily_total = 0
    for doc in daily_q.stream():
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        daily_total += 1
        if data.get('completed'):
            daily_completed += 1

    # Weekly: tasks created in last 7 days
    weekly_q = col.where(filter=FieldFilter('created_at', '>=', week_ago))
    weekly_q = weekly_q.where(filter=FieldFilter('created_at', '<=', today_end))
    weekly_completed = 0
    weekly_total = 0
    for doc in weekly_q.stream():
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        weekly_total += 1
        if data.get('completed'):
            weekly_completed += 1

    # Overall: all action items
    overall_completed = 0
    overall_total = 0
    for doc in col.stream():
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        overall_total += 1
        if data.get('completed'):
            overall_completed += 1

    def calc_score(c, t):
        return (c / t * 100.0) if t > 0 else 0.0

    daily = {
        'score': calc_score(daily_completed, daily_total),
        'completed_tasks': daily_completed,
        'total_tasks': daily_total,
    }
    weekly = {
        'score': calc_score(weekly_completed, weekly_total),
        'completed_tasks': weekly_completed,
        'total_tasks': weekly_total,
    }
    overall = {
        'score': calc_score(overall_completed, overall_total),
        'completed_tasks': overall_completed,
        'total_tasks': overall_total,
    }

    if daily['total_tasks'] > 0 and daily['score'] >= weekly['score'] and daily['score'] >= overall['score']:
        default_tab = 'daily'
    elif weekly['score'] >= overall['score']:
        default_tab = 'weekly'
    else:
        default_tab = 'overall'

    return {'daily': daily, 'weekly': weekly, 'overall': overall, 'default_tab': default_tab, 'date': date}


# ============================================================================
# DESKTOP LLM USAGE — users/{uid}/llm_usage (per-query recording)
# ============================================================================


def record_desktop_llm_usage(
    uid: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
    total_tokens: int,
    cost_usd: float,
    account: str = 'desktop_chat',
) -> None:
    now = datetime.now(timezone.utc)
    doc_id = now.strftime('%Y-%m-%d')
    ref = db.collection('users').document(uid).collection('llm_usage').document(doc_id)

    key = f'desktop_chat' if account == 'desktop_chat' else f'desktop_chat_{account}'
    update = {
        f'{key}.input_tokens': firestore.Increment(input_tokens),
        f'{key}.output_tokens': firestore.Increment(output_tokens),
        f'{key}.cache_read_tokens': firestore.Increment(cache_read_tokens),
        f'{key}.cache_write_tokens': firestore.Increment(cache_write_tokens),
        f'{key}.total_tokens': firestore.Increment(total_tokens),
        f'{key}.cost_usd': firestore.Increment(cost_usd),
        f'{key}.call_count': firestore.Increment(1),
        'date': doc_id,
        'last_updated': now,
    }
    ref.set(update, merge=True)


def get_total_desktop_llm_cost(uid: str) -> float:
    col = db.collection('users').document(uid).collection('llm_usage')
    total = 0.0
    for doc in col.stream():
        data = doc.to_dict()
        for key, value in data.items():
            if key.startswith('desktop_chat') and isinstance(value, dict):
                total += value.get('cost_usd', 0.0)
    return total


# ============================================================================
# CHAT MESSAGE COUNT — from PostHog or Firestore messages
# ============================================================================


def get_chat_message_count(uid: str) -> int:
    """Count messages in Firestore for the user."""
    col = db.collection('users').document(uid).collection('messages')
    count = 0
    for _ in col.select([]).stream():
        count += 1
    return count

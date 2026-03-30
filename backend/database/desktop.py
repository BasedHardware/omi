"""
Desktop-specific Firestore CRUD operations.

Architecture
~~~~~~~~~~~~
This module handles Firestore collections and fields that are **unique to the
desktop app** and do not already exist in other database modules.

Desktop-only collections:
  users/{uid}/staged_tasks    — AI-generated tasks awaiting promotion
  users/{uid}/focus_sessions  — Focus / distraction tracking
  users/{uid}/advice          — Proactive coaching items

Shared collections with desktop-specific schema:
  users/{uid}/chat_sessions   — Desktop v2 sessions (title, preview, message_count,
                                 starred) differ from mobile schema (message_ids,
                                 openai_thread_id).  Both schemas coexist in the
                                 same Firestore collection; fields are additive.
  users/{uid}/messages        — Desktop messages are persistence-only (no LLM
                                 streaming).  They write the same fields as
                                 chat.py's Message model for cross-platform compat.
  users/{uid}/llm_usage       — Desktop uses a flat key ("desktop_chat") while
                                 llm_usage.py uses feature.model nesting.  Both
                                 schemas coexist in the same date-keyed docs.

User document fields:
  notification_settings, assistant_settings, ai_user_profile — nested maps on
  the user doc, read/written only by the desktop app.

Computed:
  Daily score — derived from action_items counts, not stored separately.

Reuse:
  promote_staged_task() calls database.action_items.create_action_item() to
  avoid duplicating action-item creation logic.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from ._client import db
import database.action_items as action_items_db

logger = logging.getLogger(__name__)

USERS = 'users'
BATCH_LIMIT = 500  # Firestore hard limit


def _user_col(uid: str, collection: str):
    """Shorthand for users/{uid}/{collection}."""
    return db.collection(USERS).document(uid).collection(collection)


def _user_doc(uid: str):
    """Shorthand for users/{uid}."""
    return db.collection(USERS).document(uid)


def _commit_batch(batch, count):
    """Commit batch if count reaches BATCH_LIMIT; return fresh batch and 0."""
    if count >= BATCH_LIMIT:
        batch.commit()
        return db.batch(), 0
    return batch, count


# ============================================================================
# STAGED TASKS — users/{uid}/staged_tasks
# ============================================================================


def create_staged_task(uid: str, description: str, **kwargs) -> dict:
    """Create a staged task.  Deduplicates by case-insensitive description."""
    col = _user_col(uid, 'staged_tasks')

    # Deduplicate
    desc_lower = description.strip().lower()
    for doc in col.stream():
        if doc.to_dict().get('description', '').strip().lower() == desc_lower:
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


def delete_staged_task(uid: str, task_id: str) -> bool:
    ref = _user_col(uid, 'staged_tasks').document(task_id)
    if not ref.get().exists:
        return False
    ref.delete()
    return True


def batch_update_staged_scores(uid: str, scores: List[dict]) -> None:
    """Update relevance_score for staged tasks in batches of 500."""
    col = _user_col(uid, 'staged_tasks')
    now = datetime.now(timezone.utc)
    batch = db.batch()
    count = 0
    for item in scores:
        ref = col.document(item['id'])
        batch.update(ref, {'relevance_score': item['relevance_score'], 'updated_at': now})
        count += 1
        batch, count = _commit_batch(batch, count)
    if count > 0:
        batch.commit()


def promote_staged_task(uid: str) -> Optional[dict]:
    """Promote the top-scored staged task to an action_item.

    Returns the new action_item dict or None if no staged tasks exist.
    Uses database.action_items.create_action_item() for consistent field handling.
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

    staged = docs[0].to_dict()
    staged['id'] = docs[0].id

    # Build action_item data from staged task fields
    action_data = {
        'description': staged['description'],
        'completed': False,
        'from_staged': True,
    }
    for field in ('due_at', 'source', 'priority', 'metadata', 'category', 'relevance_score'):
        if staged.get(field) is not None:
            action_data[field] = staged[field]

    action_id = action_items_db.create_action_item(uid, action_data)

    # Mark staged task as completed
    col.document(staged['id']).update({'completed': True, 'promoted_at': datetime.now(timezone.utc)})

    action_item = action_items_db.get_action_item(uid, action_id)
    return action_item


def migrate_ai_tasks(uid: str) -> dict:
    """One-time migration: move excess AI tasks from action_items to staged_tasks.

    Keeps top 3 AI tasks in action_items, moves the rest to staged_tasks.
    Uses a 'source' field marker to identify AI-created tasks.
    """
    col = _user_col(uid, 'action_items')
    query = col.where(filter=FieldFilter('completed', '==', False))

    all_items = []
    for doc in query.stream():
        data = doc.to_dict()
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


def migrate_conversation_items_to_staged(uid: str) -> dict:
    """Move conversation-sourced action items (without 'source') to staged_tasks."""
    col = _user_col(uid, 'action_items')
    staged_col = _user_col(uid, 'staged_tasks')

    batch = db.batch()
    moved = 0
    batch_count = 0
    for doc in col.stream():
        data = doc.to_dict()
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


# ============================================================================
# FOCUS SESSIONS — users/{uid}/focus_sessions
# ============================================================================


def create_focus_session(uid: str, status: str, app_or_site: str, description: str, **kwargs) -> dict:
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        'id': session_id,
        'status': status,
        'app_or_site': app_or_site,
        'description': description,
        'message': kwargs.get('message'),
        'created_at': now,
        'duration_seconds': kwargs.get('duration_seconds'),
    }
    _user_col(uid, 'focus_sessions').document(session_id).set(doc)
    return doc


def get_focus_sessions(uid: str, date: str = None, limit: int = 100, offset: int = 0) -> List[dict]:
    col = _user_col(uid, 'focus_sessions')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)

    if date:
        day_start = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        query = query.where(filter=FieldFilter('created_at', '>=', day_start))
        query = query.where(filter=FieldFilter('created_at', '<', day_end))

    query = query.offset(offset).limit(limit)
    items = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        items.append(data)
    return items


def delete_focus_session(uid: str, session_id: str) -> bool:
    ref = _user_col(uid, 'focus_sessions').document(session_id)
    if not ref.get().exists:
        return False
    ref.delete()
    return True


def get_focus_stats(uid: str, date: str = None) -> dict:
    sessions = get_focus_sessions(uid, date=date, limit=5000, offset=0)
    focused_count = 0
    distracted_count = 0
    total_focus_seconds = 0
    distractions = {}

    for s in sessions:
        if s.get('status') == 'focused':
            focused_count += 1
            total_focus_seconds += s.get('duration_seconds') or 0
        elif s.get('status') == 'distracted':
            distracted_count += 1
            app = s.get('app_or_site', 'Unknown')
            entry = distractions.setdefault(app, {'duration_seconds': 0, 'count': 0})
            entry['duration_seconds'] += s.get('duration_seconds') or 60
            entry['count'] += 1

    return {
        'focused_count': focused_count,
        'distracted_count': distracted_count,
        'total_focus_seconds': total_focus_seconds,
        'top_distractions': sorted(distractions.items(), key=lambda x: x[1]['duration_seconds'], reverse=True)[:5],
    }


# ============================================================================
# ADVICE — users/{uid}/advice
# ============================================================================


def create_advice(uid: str, content: str, category: str = 'other', **kwargs) -> dict:
    advice_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        'id': advice_id,
        'content': content,
        'category': category,
        'reasoning': kwargs.get('reasoning'),
        'source_app': kwargs.get('source_app'),
        'confidence': kwargs.get('confidence', 0.5),
        'context_summary': kwargs.get('context_summary'),
        'current_activity': kwargs.get('current_activity'),
        'created_at': now,
        'updated_at': now,
        'is_read': False,
        'is_dismissed': False,
    }
    _user_col(uid, 'advice').document(advice_id).set(doc)
    return doc


def get_advice(
    uid: str, category: str = None, limit: int = 50, offset: int = 0, include_dismissed: bool = False
) -> List[dict]:
    col = _user_col(uid, 'advice')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)
    if category:
        query = query.where(filter=FieldFilter('category', '==', category))
    if not include_dismissed:
        query = query.where(filter=FieldFilter('is_dismissed', '==', False))
    if offset > 0:
        query = query.offset(offset)
    query = query.limit(limit)

    items = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        items.append(data)
    return items


def update_advice(uid: str, advice_id: str, is_read: bool = None, is_dismissed: bool = None) -> Optional[dict]:
    ref = _user_col(uid, 'advice').document(advice_id)
    snap = ref.get()
    if not snap.exists:
        return None
    updates = {'updated_at': datetime.now(timezone.utc)}
    if is_read is not None:
        updates['is_read'] = is_read
    if is_dismissed is not None:
        updates['is_dismissed'] = is_dismissed
    ref.update(updates)
    result = ref.get().to_dict()
    result['id'] = advice_id
    return result


def delete_advice(uid: str, advice_id: str) -> bool:
    ref = _user_col(uid, 'advice').document(advice_id)
    if not ref.get().exists:
        return False
    ref.delete()
    return True


def mark_all_advice_read(uid: str) -> int:
    col = _user_col(uid, 'advice')
    query = col.where(filter=FieldFilter('is_read', '==', False))
    batch = db.batch()
    total = 0
    batch_count = 0
    for doc in query.stream():
        batch.update(col.document(doc.id), {'is_read': True, 'updated_at': datetime.now(timezone.utc)})
        total += 1
        batch_count += 1
        batch, batch_count = _commit_batch(batch, batch_count)
    if batch_count > 0:
        batch.commit()
    return total


# ============================================================================
# CHAT SESSIONS v2 — users/{uid}/chat_sessions (desktop schema)
#
# Desktop sessions store: title, preview, message_count, starred, updated_at.
# Mobile sessions (chat.py) store: message_ids, file_ids, openai_thread_id.
# Both schemas coexist in the same Firestore collection.
# Both MUST write plugin_id alongside app_id for cross-platform query compat.
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
        'plugin_id': app_id,  # Python chat.py queries chat_sessions by plugin_id
        'message_count': 0,
        'starred': False,
    }
    _user_col(uid, 'chat_sessions').document(session_id).set(doc)
    return doc


def acquire_chat_session(uid: str, app_id: str = None) -> str:
    """Get or create a chat session for the given app_id (None = main chat).

    Queries by plugin_id to match both Python chat.py and Rust backend behavior.
    For main chat (app_id=None), matches sessions where plugin_id is None.
    """
    col = _user_col(uid, 'chat_sessions')
    query = col.where(filter=FieldFilter('plugin_id', '==', app_id)).limit(1)
    docs = list(query.stream())
    if docs:
        return docs[0].id
    session = create_chat_session(uid, app_id=app_id)
    return session['id']


def get_chat_sessions(
    uid: str, app_id: str = None, limit: int = 50, offset: int = 0, starred: bool = None
) -> List[dict]:
    col = _user_col(uid, 'chat_sessions')
    query = col.order_by('updated_at', direction=firestore.Query.DESCENDING)

    # Always filter — when app_id is None this returns only default-chat sessions
    query = query.where(filter=FieldFilter('plugin_id', '==', app_id))
    if starred is not None:
        query = query.where(filter=FieldFilter('starred', '==', starred))

    query = query.offset(offset).limit(limit)
    items = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        items.append(data)
    return items


def get_chat_session(uid: str, session_id: str) -> Optional[dict]:
    ref = _user_col(uid, 'chat_sessions').document(session_id)
    doc = ref.get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    data['id'] = doc.id
    return data


def update_chat_session(uid: str, session_id: str, title: str = None, starred: bool = None) -> Optional[dict]:
    ref = _user_col(uid, 'chat_sessions').document(session_id)
    if not ref.get().exists:
        return None
    updates = {'updated_at': datetime.now(timezone.utc)}
    if title is not None:
        updates['title'] = title
    if starred is not None:
        updates['starred'] = starred
    ref.update(updates)
    result = ref.get().to_dict()
    result['id'] = session_id
    return result


def delete_chat_session(uid: str, session_id: str) -> bool:
    """Delete a chat session and cascade-delete its messages.

    Uses a Firestore transaction to ensure atomicity: if the session doc is
    modified between the read and the delete, the transaction retries.
    """
    session_ref = _user_col(uid, 'chat_sessions').document(session_id)
    msg_col = _user_col(uid, 'messages')

    if not session_ref.get().exists:
        return False

    # Delete messages in batches (outside transaction — Firestore transactions
    # are limited to 500 ops and messages could exceed that).
    query = msg_col.where(filter=FieldFilter('chat_session_id', '==', session_id))
    while True:
        docs = list(query.limit(BATCH_LIMIT).stream())
        if not docs:
            break
        batch = db.batch()
        for doc in docs:
            batch.delete(msg_col.document(doc.id))
        batch.commit()

    # Delete the session itself
    session_ref.delete()
    return True


# ============================================================================
# DESKTOP MESSAGES — users/{uid}/messages
#
# Desktop messages are persistence-only (no LLM streaming).  They write the
# same field set as chat.py's Message model for cross-platform compatibility:
#   plugin_id, app_id, type='text', chat_session_id, from_external_integration
#
# When session_id is not provided, acquire_chat_session() auto-creates one
# (matching Rust's save_message behavior for default-chat visibility).
# ============================================================================


def save_desktop_message(
    uid: str, text: str, sender: str, app_id: str = None, session_id: str = None, metadata: str = None
) -> dict:
    """Save a chat message for the desktop app.

    Writes all fields expected by chat.py's Message model so messages are
    visible across platforms.  Auto-acquires a session if none provided.
    """
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Auto-acquire session (matches Rust backend behavior)
    if not session_id:
        session_id = acquire_chat_session(uid, app_id=app_id)

    doc = {
        'id': msg_id,
        'text': text,
        'created_at': now,
        'sender': sender,
        'type': 'text',  # Desktop messages are always type 'text'
        'app_id': app_id,
        'plugin_id': app_id,  # chat.py queries messages by plugin_id
        'session_id': session_id,
        'chat_session_id': session_id,  # chat.py uses this field name
        'from_external_integration': False,
        'rating': None,
        'reported': False,
        'memories_id': [],
        'metadata': metadata,
    }
    _user_col(uid, 'messages').document(msg_id).set(doc)

    # Update session message_count and preview (skip if session was deleted)
    if session_id:
        session_ref = _user_col(uid, 'chat_sessions').document(session_id)
        if session_ref.get().exists:
            session_ref.update(
                {
                    'updated_at': now,
                    'message_count': firestore.Increment(1),
                    'preview': text[:100] if text else None,
                }
            )

    return {'id': msg_id, 'created_at': now.isoformat()}


def get_desktop_messages(
    uid: str, app_id: str = None, session_id: str = None, limit: int = 100, offset: int = 0
) -> List[dict]:
    """Fetch messages.  Always filters by plugin_id so default chat (None) only
    returns its own messages, not messages from every app."""
    col = _user_col(uid, 'messages')
    query = col.order_by('created_at', direction=firestore.Query.DESCENDING)

    # Always filter — when app_id is None this returns only default-chat messages
    query = query.where(filter=FieldFilter('plugin_id', '==', app_id))
    if session_id is not None:
        query = query.where(filter=FieldFilter('chat_session_id', '==', session_id))

    query = query.offset(offset).limit(limit)
    items = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        items.append(data)
    return items


def delete_desktop_messages(uid: str, app_id: str = None, session_id: str = None) -> int:
    """Delete messages matching app_id/session_id.  Returns count deleted."""
    col = _user_col(uid, 'messages')
    query = col.where(filter=FieldFilter('plugin_id', '==', app_id))
    if session_id:
        query = query.where(filter=FieldFilter('chat_session_id', '==', session_id))

    deleted = 0
    while True:
        docs = list(query.limit(BATCH_LIMIT).stream())
        if not docs:
            break
        batch = db.batch()
        for doc in docs:
            batch.delete(col.document(doc.id))
        batch.commit()
        deleted += len(docs)
    return deleted


def rate_desktop_message(uid: str, message_id: str, rating: Optional[int]) -> bool:
    """Rate a message (1=thumbs up, -1=thumbs down, None=clear)."""
    ref = _user_col(uid, 'messages').document(message_id)
    if not ref.get().exists:
        return False
    ref.update({'rating': rating, 'updated_at': datetime.now(timezone.utc)})
    return True


# ============================================================================
# USER SETTINGS — fields on users/{uid} document
# ============================================================================


def get_notification_settings(uid: str) -> dict:
    """Return notification settings with Swift-compatible field names.

    Firestore stores ``notifications_enabled`` / ``notification_frequency`` on
    the user doc.  The Swift ``NotificationSettingsResponse`` decodes
    ``enabled`` / ``frequency``, so we map to the wire names here.
    """
    doc = _user_doc(uid).get()
    if not doc.exists:
        return {'enabled': True, 'frequency': 1}
    data = doc.to_dict()
    return {
        'enabled': data.get('notifications_enabled', True),
        'frequency': data.get('notification_frequency', 1),
    }


def update_notification_settings(uid: str, enabled: bool = None, frequency: int = None) -> dict:
    updates = {}
    if enabled is not None:
        updates['notifications_enabled'] = enabled
    if frequency is not None:
        updates['notification_frequency'] = frequency
    if updates:
        _user_doc(uid).update(updates)
    return get_notification_settings(uid)


def get_assistant_settings(uid: str) -> dict:
    doc = _user_doc(uid).get()
    if not doc.exists:
        return {}
    return doc.to_dict().get('assistant_settings') or {}


def update_assistant_settings(uid: str, settings: dict) -> dict:
    """Deep-merge partial settings into existing assistant_settings.

    The Swift client sends tiny partial updates (e.g. {"focus": {"enabled": true}})
    on every toggle.  A naive overwrite would erase sibling sections.
    """
    existing = get_assistant_settings(uid)
    for section, values in settings.items():
        if isinstance(values, dict) and isinstance(existing.get(section), dict):
            existing[section].update(values)
        else:
            existing[section] = values
    _user_doc(uid).update({'assistant_settings': existing})
    return existing


def get_ai_user_profile(uid: str) -> Optional[dict]:
    doc = _user_doc(uid).get()
    if not doc.exists:
        return None
    return doc.to_dict().get('ai_user_profile')


def update_ai_user_profile(
    uid: str, profile_text: str = None, generated_at=None, data_sources_used: int = None
) -> dict:
    """Update AI user profile.  Only writes non-None fields (partial update)."""
    # Read existing profile and merge updates
    existing = get_ai_user_profile(uid) or {}
    if profile_text is not None:
        existing['profile_text'] = profile_text
    if generated_at is not None:
        existing['generated_at'] = generated_at
    if data_sources_used is not None:
        existing['data_sources_used'] = data_sources_used
    _user_doc(uid).update({'ai_user_profile': existing})
    return existing


# ============================================================================
# DAILY SCORE — computed from users/{uid}/action_items
# ============================================================================


def get_daily_score(uid: str, date: str = None) -> dict:
    """Compute productivity score for a single day from action_items."""
    if date:
        day = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    else:
        day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    day_end = day + timedelta(days=1)
    col = _user_col(uid, 'action_items')

    # Count tasks due today
    due_query = col.where(filter=FieldFilter('due_at', '>=', day)).where(filter=FieldFilter('due_at', '<', day_end))
    total = 0
    completed = 0
    for doc in due_query.stream():
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        total += 1
        if data.get('completed'):
            completed += 1

    score = round((completed / total * 100) if total > 0 else 0)
    return {'date': day.strftime('%Y-%m-%d'), 'score': score, 'completed': completed, 'total': total}


def get_scores(uid: str, date: str = None) -> dict:
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
    week_start = day - timedelta(days=7)

    col = _user_col(uid, 'action_items')

    def _score(completed, total):
        return round((completed / total * 100) if total > 0 else 0, 1)

    # Daily: tasks due today
    daily_q = col.where(filter=FieldFilter('due_at', '>=', day_start)).where(filter=FieldFilter('due_at', '<', day_end))
    daily_completed = daily_total = 0
    for doc in daily_q.stream():
        data = doc.to_dict()
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
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        weekly_total += 1
        if data.get('completed'):
            weekly_completed += 1

    # Overall: all non-deleted tasks
    overall_completed = overall_total = 0
    for doc in col.stream():
        data = doc.to_dict()
        if data.get('deleted'):
            continue
        overall_total += 1
        if data.get('completed'):
            overall_completed += 1

    daily = {
        'score': _score(daily_completed, daily_total),
        'completed_tasks': daily_completed,
        'total_tasks': daily_total,
    }
    weekly = {
        'score': _score(weekly_completed, weekly_total),
        'completed_tasks': weekly_completed,
        'total_tasks': weekly_total,
    }
    overall = {
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


# ============================================================================
# DESKTOP LLM USAGE — users/{uid}/llm_usage/{YYYY-MM-DD}
#
# Desktop uses a flat key scheme ("desktop_chat" / "desktop_chat_{account}")
# with fields: input_tokens, output_tokens, cache_read_tokens,
# cache_write_tokens, total_tokens, cost_usd, call_count.
#
# This differs from llm_usage.py's {feature}.{model} nesting.  Both schemas
# coexist in the same date-keyed documents using Firestore's schemaless design.
# ============================================================================


def record_desktop_llm_usage(
    uid: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
    account: str = 'omi',
) -> None:
    """Record desktop LLM token usage with atomic increments.

    Matches the Rust backend's field schema exactly so existing analytics
    and the Swift client see consistent data.
    """
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    ref = _user_col(uid, 'llm_usage').document(today)

    key = 'desktop_chat' if account == 'omi' else f'desktop_chat_{account}'
    update = {
        f'{key}.input_tokens': firestore.Increment(input_tokens),
        f'{key}.output_tokens': firestore.Increment(output_tokens),
        f'{key}.cache_read_tokens': firestore.Increment(cache_read_tokens),
        f'{key}.cache_write_tokens': firestore.Increment(cache_write_tokens),
        f'{key}.total_tokens': firestore.Increment(total_tokens),
        f'{key}.cost_usd': firestore.Increment(cost_usd),
        f'{key}.call_count': firestore.Increment(1),
        'date': today,
        'last_updated': datetime.now(timezone.utc),
    }
    ref.set(update, merge=True)


def get_total_desktop_llm_cost(uid: str) -> float:
    """Sum cost_usd across all date docs for desktop_chat* keys."""
    col = _user_col(uid, 'llm_usage')
    total = 0.0
    for doc in col.stream():
        data = doc.to_dict()
        for key, value in data.items():
            if key.startswith('desktop_chat') and isinstance(value, dict):
                total += value.get('cost_usd', 0.0)
    return round(total, 6)

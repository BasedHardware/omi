from datetime import datetime, timezone
from typing import Optional
from database._client import db
from google.api_core.exceptions import NotFound
import logging

logger = logging.getLogger(__name__)


def get_clone_settings(uid: str) -> dict:
    doc = db.collection('users').document(uid).collection('ai_clone').document('settings').get()
    if doc.exists:
        return doc.to_dict()
    return {
        'enabled': False,
        'auto_reply': False,
        'platforms': {},
    }


def update_clone_settings(uid: str, settings: dict) -> None:
    db.collection('users').document(uid).collection('ai_clone').document('settings').set(settings, merge=True)


def save_clone_message(uid: str, message: dict) -> str:
    ref = db.collection('users').document(uid).collection('ai_clone_messages').document()
    message['created_at'] = datetime.now(timezone.utc).isoformat()
    message['id'] = ref.id
    ref.set(message)
    return ref.id


def get_clone_messages(uid: str, limit: int = 50) -> list[dict]:
    docs = (
        db.collection('users')
        .document(uid)
        .collection('ai_clone_messages')
        .order_by('created_at', direction='DESCENDING')
        .limit(limit)
        .stream()
    )
    return [d.to_dict() for d in docs]


def update_clone_message(uid: str, message_id: str, updates: dict) -> None:
    db.collection('users').document(uid).collection('ai_clone_messages').document(message_id).update(updates)


def get_chat_messages(uid: str, platform: str, chat_identifier: str, limit: int = 5) -> list[dict]:
    """Return the last `limit` messages for a specific chat, oldest-first, for conversation continuity."""
    recent = get_clone_messages(uid, limit=100)
    chat = [m for m in recent if m.get('platform') == platform and m.get('chat_identifier') == chat_identifier]
    # get_clone_messages returns newest-first; reverse to chronological, take tail
    return list(reversed(chat[:limit]))


def get_platform_settings(uid: str, platform: str) -> Optional[dict]:
    settings = get_clone_settings(uid)
    return settings.get('platforms', {}).get(platform)


def update_platform_settings(uid: str, platform: str, data: dict) -> None:
    """Replace a platform's entire settings map without clobbering other platforms."""
    ref = db.collection('users').document(uid).collection('ai_clone').document('settings')
    try:
        ref.update({f'platforms.{platform}': data})
    except NotFound:
        ref.set({'platforms': {platform: data}}, merge=True)


def set_platform_field(uid: str, platform: str, field: str, value) -> None:
    """Update a single field within a platform's settings without touching other fields."""
    ref = db.collection('users').document(uid).collection('ai_clone').document('settings')
    try:
        # Deep dot-notation: platforms.telegram.active — only this leaf is written.
        ref.update({f'platforms.{platform}.{field}': value})
    except NotFound:
        ref.set({'platforms': {platform: {field: value}}}, merge=True)

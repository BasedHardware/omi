from datetime import datetime, timezone
from typing import Optional
from database._client import db
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


def get_platform_settings(uid: str, platform: str) -> Optional[dict]:
    settings = get_clone_settings(uid)
    return settings.get('platforms', {}).get(platform)

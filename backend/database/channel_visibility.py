"""First-party session-list opt-in. Channel histories remain hidden by default."""

from __future__ import annotations

import logging
from typing import Any, Optional

from config.messaging import cohort_enabled
from database._client import get_firestore_client

_LOGGER = logging.getLogger(__name__)


def visible_sessions(uid: str, *, firestore_client: Optional[Any] = None) -> list[dict[str, Any]]:
    cleaned_uid = uid.strip() if uid else ''
    if not cleaned_uid:
        return []
    if not cohort_enabled(cleaned_uid):
        return []
    db = firestore_client if firestore_client is not None else get_firestore_client()
    if db is None:
        return []
    try:
        user = db.collection('users').document(cleaned_uid)
        visible: set[str] = set()
        for d in user.collection('channel_links').stream():
            data = d.to_dict()
            if isinstance(data, dict) and data.get('visible_in_app'):
                visible.add(d.id)
        if not visible:
            return []

        results: list[dict[str, Any]] = []
        for d in user.collection('chat_sessions').stream():
            data = d.to_dict()
            if isinstance(data, dict) and data.get('channel_link_id') in visible:
                session_dict = dict(data)
                session_dict['id'] = d.id
                results.append(session_dict)
        return results
    except Exception as e:
        _LOGGER.warning('Failed to fetch visible sessions for uid %s: %s', cleaned_uid, e)
        return []

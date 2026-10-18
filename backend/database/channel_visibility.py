"""First-party session-list opt-in. Channel histories remain hidden by default."""

import logging
from typing import Any, Optional

from google.api_core.exceptions import GoogleAPICallError

from config.messaging import cohort_enabled
from database._client import get_firestore_client

logger = logging.getLogger(__name__)


def visible_sessions(uid: str, *, firestore_client: Optional[Any] = None) -> list[dict[str, Any]]:
    """Chat sessions linked to channels the caller opted into.

    A whitespace-carrying uid would read an orphaned document path; a
    transient Firestore failure must not break the caller's session list —
    both collapse to an empty list rather than an exception.
    """
    uid = uid.strip()
    if not uid:
        return []
    if not cohort_enabled(uid):
        return []
    try:
        db = firestore_client if firestore_client is not None else get_firestore_client()
        if db is None:
            return []
        user = db.collection('users').document(uid)
        visible = set()
        for d in user.collection('channel_links').stream():
            data = d.to_dict()
            if isinstance(data, dict) and data.get('visible_in_app'):
                visible.add(d.id)
        if not visible:
            return []
        sessions = []
        for d in user.collection('chat_sessions').stream():
            data = d.to_dict()
            if isinstance(data, dict) and data.get('channel_link_id') in visible:
                sessions.append(dict(data, id=d.id))
        return sessions
    except (GoogleAPICallError, OSError, TimeoutError):
        logger.warning('channel_visibility read failed', exc_info=True)
        return []

"""First-party session-list opt-in. Channel histories remain hidden by default."""

from database._client import get_firestore_client
from config.messaging import cohort_enabled


def visible_sessions(uid, *, firestore_client=None):
    if not cohort_enabled(uid):
        return []
    db = firestore_client if firestore_client is not None else get_firestore_client()
    user = db.collection('users').document(uid)
    visible = {d.id for d in user.collection('channel_links').stream() if d.to_dict().get('visible_in_app')}
    if not visible:
        return []
    return [
        dict(d.to_dict(), id=d.id)
        for d in user.collection('chat_sessions').stream()
        if d.to_dict().get('channel_link_id') in visible
    ]

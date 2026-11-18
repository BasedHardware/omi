"""Indexed read of a user's recent v3 windows for GET /v1/conversations/live.

It uses the existing ``v3_derived, finished_at, started_at`` index (the derived-window
read in ``conversations_v3``), so legacy in-progress rows never enter the scan however many
exist. The field mask is unconditional and carries no transcript: the live tile needs only
its identity, title, times, state and the visibility flags.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.conversations import conversations_collection, prepare_conversation_for_read

LIVE_FIELDS = [
    'id',
    'structured',
    'user_title',
    'data_protection_level',
    'started_at',
    'created_at',
    'finished_at',
    'status',
    'tile_state',
    'v3_derived',
    'recording',
    'home_hidden',
    'deleted',
    'discarded',
]
# Windows that spoke inside the idle cap. Ascending by finished_at (the index order), so a
# busy account pages forward to reach the newest; four pages bound the read.
PAGE = 20
MAX_PAGES = 4
# Clock skew allowance for a window that started a moment "in the future".
START_SKEW = timedelta(minutes=5)


def recent_windows(
    uid: str, *, now: datetime, max_idle: timedelta, firestore_client: Any = None
) -> List[Dict[str, Any]]:
    """v3 windows whose last speech is inside ``max_idle``, projected to the live fields."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection('users')
        .document(uid)
        .collection(conversations_collection)
        .where(filter=FieldFilter('v3_derived', '==', True))
        .where(filter=FieldFilter('finished_at', '>=', now - max_idle))
        .where(filter=FieldFilter('started_at', '<=', now + START_SKEW))
        .select(LIVE_FIELDS)
    )
    rows: List[Dict[str, Any]] = []
    last: Optional[Any] = None
    for _ in range(MAX_PAGES):
        page = (query.start_after(last) if last is not None else query).limit(PAGE)
        snapshots = list(page.stream())
        for snapshot in snapshots:
            row = prepare_conversation_for_read(dict(snapshot.to_dict() or {}, id=snapshot.id), uid)
            if row is not None:
                rows.append(row)
        if len(snapshots) < PAGE:
            break
        last = snapshots[-1]
    return rows

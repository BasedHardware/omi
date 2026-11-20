"""Indexed read of a user's recent v3 windows for GET /v1/conversations/live.

It uses the existing ``v3_derived, finished_at, started_at`` index (the derived-window
read in ``conversations_v3``), so legacy in-progress rows never enter the scan however many
exist. The field mask is unconditional and carries no transcript: the live tile needs only
its identity, title, times, state and the visibility flags.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.conversations import conversations_collection, prepare_conversation_for_read

logger = logging.getLogger(__name__)

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
    'is_locked',
    'v3_recording_ids',
]
# The index is ascending by finished_at, so the newest window comes last and a read cannot
# stop early once it finds the open one; a reverse-order read would need a new descending
# index. The live tile is polled, so the read goes in two bands instead. An open window's
# finished_at is its latest speech, so it is almost always in the recent band, which holds
# only a few rows. The full idle window is read only when the recent band has no live
# window. READ_CAP bounds the rows one call reads across both bands; reaching it is logged.
RECENT_BAND = timedelta(minutes=10)
PAGE = 50
READ_CAP = 200
# Clock skew allowance for a window that started a moment "in the future".
START_SKEW = timedelta(minutes=5)


def recent_windows(
    uid: str,
    *,
    now: datetime,
    max_idle: timedelta,
    finished_before: Optional[datetime] = None,
    max_rows: int = READ_CAP,
    firestore_client: Any = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """v3 windows whose last speech is inside ``max_idle``, projected to the live fields.

    ``finished_before`` excludes windows whose last speech is at or after it, so a wider band
    does not re-read a narrower one. Returns the prepared rows and the number of
    documents read (at most ``max_rows``).
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection('users')
        .document(uid)
        .collection(conversations_collection)
        .where(filter=FieldFilter('v3_derived', '==', True))
        .where(filter=FieldFilter('finished_at', '>=', now - max_idle))
        .where(filter=FieldFilter('started_at', '<=', now + START_SKEW))
    )
    if finished_before is not None:
        query = query.where(filter=FieldFilter('finished_at', '<', finished_before))
    # Explicit, so pages run oldest to newest whatever the implicit order of the two range
    # fields; the v3 window index (finished_at ASC, started_at ASC) serves it.
    query = query.order_by('finished_at').select(LIVE_FIELDS)
    rows: List[Dict[str, Any]] = []
    read = 0
    last: Optional[Any] = None
    while read < max_rows:
        size = min(PAGE, max_rows - read)
        snapshots = list((query.start_after(last) if last is not None else query).limit(size).stream())
        read += len(snapshots)
        for snapshot in snapshots:
            row = prepare_conversation_for_read(dict(snapshot.to_dict() or {}, id=snapshot.id), uid)
            if row is not None:
                rows.append(row)
        if len(snapshots) < size:
            return rows, read
        last = snapshots[-1]
    logger.warning('v3 live read stopped at its bound of %d windows', max_rows)
    return rows, read


def live_window(
    uid: str,
    *,
    now: datetime,
    max_idle: timedelta,
    pick: Callable[[Sequence[Mapping[str, Any]], datetime], Optional[Mapping[str, Any]]],
    firestore_client: Any = None,
) -> Optional[Mapping[str, Any]]:
    """The window ``pick`` chooses, reading the recent band first and widening only if needed."""
    left = READ_CAP
    recent = min(RECENT_BAND, max_idle)
    # The bands are disjoint, so the wider one never re-reads the recent one.
    for band, finished_before in ((recent, None), (max_idle, now - recent)):
        rows, read = recent_windows(
            uid,
            now=now,
            max_idle=band,
            finished_before=finished_before,
            max_rows=left,
            firestore_client=firestore_client,
        )
        row = pick(rows, now)
        left -= read
        if row is not None or left <= 0:
            return row
    return None

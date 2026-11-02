"""Bounded, content-free counts of noise/media captures hidden from Home."""

from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client

HIDDEN_NOISE_ROW_CAP = 1000
HIDDEN_NOISE_FIELDS = (
    'created_at',
    'discarded',
    'content_kind',
    'sync_relevance_user_kept',
    'deleted',
    'sync_merged_into',
    'status',
)


def count_hidden_noise_by_day(
    uid: str, start_date: datetime, end_date: datetime, tz: ZoneInfo, *, firestore_client=None
) -> dict:
    """Read at most 1000 discarded rows; counts are lower bounds when truncated.

    Dream duplicates count: the include_discarded list that reveals a day shows
    them too, and the badge must match that reveal.

    No MEDIA_NOISE_MODE gate: previously hidden rows remain countable after the
    mode is disabled. Locked rows remain eligible, just as on the Home list.
    The descending order reuses the existing conversations_discarded_created index.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection('users')
        .document(uid)
        .collection('conversations')
        .where(filter=FieldFilter('discarded', '==', True))
        .where(filter=FieldFilter('created_at', '>=', start_date))
        .where(filter=FieldFilter('created_at', '<=', end_date))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .select(HIDDEN_NOISE_FIELDS)
        .limit(HIDDEN_NOISE_ROW_CAP + 1)
    )
    counts = Counter()
    scanned = 0
    for doc in query.stream():
        scanned += 1
        if scanned > HIDDEN_NOISE_ROW_CAP:
            break
        row = doc.to_dict() or {}
        if (
            row.get('discarded') is True
            and row.get('content_kind') in ('media', 'noise')
            and not row.get('sync_relevance_user_kept')
            and not row.get('deleted')
            and not row.get('sync_merged_into')
            and row.get('status') in ('completed', 'processing')
        ):
            counts[row['created_at'].astimezone(tz).date().isoformat()] += 1
    return {
        'days': [{'date': day, 'count': counts[day]} for day in sorted(counts)],
        'total': sum(counts.values()),
        'truncated': scanned > HIDDEN_NOISE_ROW_CAP,
    }

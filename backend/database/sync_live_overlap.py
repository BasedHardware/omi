"""Bounded metadata discovery for the sync/live assignment transaction."""

import logging

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from utils.sync.live_overlap import discoverable_live_overlap
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def find_sync_live_overlap_candidates(user_ref, incoming: dict) -> tuple[str, ...]:
    """Bounded metadata discovery using the existing temporal lookup index.

    No plaintext is read here. The assignment transaction rechecks the full row.
    Discovery failure restores normal visible sync intake immediately; it never
    creates a hidden row or waits for another upload to publish captured speech.
    """
    fields = [
        'id',
        'started_at',
        'finished_at',
        'source',
        'client_device_id',
        'capture_evidence',
        'external_data',
        'recording_session_id',
        'sync_clock_run',
        'is_locked',
        'deleted',
        'sync_merged_into',
        'status',
    ]
    try:
        query = (
            user_ref.collection('conversations')
            .where(filter=FieldFilter('finished_at', '>=', incoming['started_at']))
            .where(filter=FieldFilter('started_at', '<=', incoming['finished_at']))
            .order_by('created_at', direction=firestore.Query.DESCENDING)
            .select(fields)
            .limit(128)
        )
        rows = [dict(doc.to_dict(), id=doc.id) for doc in query.stream(timeout=10)]
        # Keep every same-partition overlapping live hint — including a stub
        # whose first transcript write has not landed yet — so the assignment
        # transaction reads that document and Firestore commit contention can
        # fence a listen writer adding content concurrently. The transaction's
        # revalidation stays authoritative; a still-empty stub is not adopted.
        return tuple(row['id'] for row in rows if discoverable_live_overlap(row, incoming))
    except Exception:
        logger.warning('event=sync_live_overlap outcome=lookup_failed')
        record_fallback(
            component='sync_dispatch',
            from_mode='live_overlap',
            to_mode='temporal_assignment',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return ()

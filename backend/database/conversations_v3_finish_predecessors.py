"""The sealed recordings before a fresh manual-end cut whose batch transcript has not landed yet."""

from datetime import datetime, timedelta, timezone

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config.conversations_v3 import capture_continuity_enabled
from utils.conversations.v3 import policy
from utils.conversations.v3.outline import FINISH_PREDECESSORS

# A manual-end cut looks back this far for a preceding recording whose batch transcript is still
# pending (a rotated or reconnected recording is at most an hour long), nearest first.
FINISH_PREDECESSOR_LOOKBACK = timedelta(hours=1)
FINISH_PREDECESSOR_LIMIT = 8
FINISH_PREDECESSOR_FIELDS = [
    'started_at',
    'finished_at',
    'status',
    'recording',
    'deleted',
    'discarded',
    'sync_merged_into',
    'data_protection_level',
    'record_lane_owner',
    'record_projection_revision',
    'record_upload_failed',
    'record_sealed_at',
    'finalization_status',
    'external_data.recording_origin_id',
]


def attach(coll, recordings):
    """Name the sealed recordings before a fresh manual-end cut whose batch transcript has not landed.

    Only while the cut can still wait (``policy.FINISH_WAIT`` after it): one bounded read of at most
    ``FINISH_PREDECESSOR_LIMIT`` metadata-only documents per such cut. The planner holds the cut
    while one of them is in the finished speech's capture (``outline._held_cuts``); they never become
    sources here, so a pass without speech from them commits nothing for them.
    """
    if not capture_continuity_enabled():
        return
    now = datetime.now(timezone.utc)
    for row in list(recordings.values()):
        cut, start = row.get('finished_at'), row.get('started_at')
        if not row.get('v3_manual_end') or not cut or not start or now - cut >= policy.FINISH_WAIT:
            continue
        query = (
            coll.where(filter=FieldFilter('started_at', '>=', start - FINISH_PREDECESSOR_LOOKBACK))
            .where(filter=FieldFilter('started_at', '<', start))
            .order_by('started_at', direction=firestore.Query.DESCENDING)
            .limit(FINISH_PREDECESSOR_LIMIT)
            .select(FINISH_PREDECESSOR_FIELDS)
        )
        found = []
        for doc in query.stream():
            raw = doc.to_dict() or {}
            if doc.id not in recordings and policy.awaiting_batch_transcript(raw):
                found.append({**raw, 'id': doc.id})
        row[FINISH_PREDECESSORS] = found

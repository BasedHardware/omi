"""The sealed recordings before a fresh manual-end cut whose batch transcript has not landed yet."""

from datetime import datetime, timezone

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config.conversations_v3 import capture_continuity_enabled
from database.firestore_index_registry import SYNC_RECORDING_LINEAGE_QUERY
from utils.conversations.v3 import policy
from utils.conversations.v3.outline import CAPTURE_GAP_LIMIT, FINISH_PREDECESSORS, capture_origin

# Nearest generations of the Finish recording's capture origin that end within the reconnect bound of
# its start. The read is scoped by the origin and both time bounds (the existing sync lineage index),
# so generations that cannot join the finished speech never take a slot; a pending predecessor can
# only be crowded out by eight newer generations of the same capture, each nearer the Finish.
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
    'client_device_id',
    'record_lane_owner',
    'record_projection_revision',
    'record_upload_failed',
    'record_sealed_at',
    'finalization_status',
    'external_data.recording_origin_id',
    'external_data.recording_session_id',
]


def _cut_applied(row, existing):
    """A locked manual-end conversation already holds this recording: its Finish is settled."""
    return any(
        row['id'] in (done.get('v3_recording_ids') or ())
        and done.get('manual_end')
        and done.get('status') != 'in_progress'
        and not done.get('v3_unlocked')
        for done in existing.values()
    )


def attach(coll, recordings, existing):
    """Name the earlier generations of a fresh Finish's capture whose batch transcript has not landed.

    Runs only for a loaded manual-end recording that has a capture origin, whose cut is within
    its applicable wait and not yet settled into a locked conversation: one read of at most
    ``FINISH_PREDECESSOR_LIMIT`` metadata-only documents per such recording and pass. The planner holds
    the cut only for those that join the finished speech (``outline._held_cuts``); they never become
    sources here.
    """
    if not capture_continuity_enabled():
        return
    now = datetime.now(timezone.utc)
    for row in list(recordings.values()):
        cut, start, origin = row.get('finished_at'), row.get('started_at'), capture_origin(row)
        if (
            not row.get('v3_manual_end')
            or not cut
            or not start
            or origin is None
            or now - cut >= policy.finish_wait(row)
            or _cut_applied(row, existing)
        ):
            continue
        query = (
            SYNC_RECORDING_LINEAGE_QUERY.build(
                coll,
                {
                    'recording_origin_id': origin,
                    'started_before': start,
                    'finished_after': start - CAPTURE_GAP_LIMIT,
                },
                field_filter_factory=FieldFilter,
            )
            .order_by('started_at', direction=firestore.Query.DESCENDING)
            .order_by('finished_at', direction=firestore.Query.DESCENDING)
            .select(FINISH_PREDECESSOR_FIELDS)
            .limit(FINISH_PREDECESSOR_LIMIT)
        )
        found = []
        for doc in query.stream():
            raw = doc.to_dict() or {}
            if doc.id == row['id'] or doc.id in recordings or not raw.get('started_at') or raw['started_at'] >= start:
                continue
            if policy.awaiting_batch_transcript(raw):
                found.append({**raw, 'id': doc.id})
        row[FINISH_PREDECESSORS] = found

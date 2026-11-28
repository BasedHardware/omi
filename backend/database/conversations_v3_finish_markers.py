"""Finish marker reads for the v3 builder's fast Finish re-wake: marker fields only, a bounded id set."""

from database._client import get_firestore_client
from database.conversations_v3 import user_conversations
from utils.conversations.v3.finish_stamp import FINISH_STAMP_FIELD

# Only what the builder needs to tell a recent Finish from live speech; one document read per id.
FINISH_MARKER_FIELDS = (
    'v3_manual_end',
    'v3_manual_end_requested',
    'v3_pending',
    'finished_at',
    FINISH_STAMP_FIELD,
    'deleted',
    'discarded',
)
FINISH_MARKER_LIMIT = 8


def finish_markers(uid, ids, *, firestore_client=None):
    """The Finish marker fields of the first ``FINISH_MARKER_LIMIT`` of ``ids`` (caller's order: likeliest
    Finishes first), keyed by id; absent rows are omitted."""
    chosen = list(dict.fromkeys(ids))[:FINISH_MARKER_LIMIT]
    if not chosen:
        return {}
    client = firestore_client or get_firestore_client()
    coll = user_conversations(client, uid)
    snapshots = client.get_all([coll.document(rid) for rid in chosen], field_paths=list(FINISH_MARKER_FIELDS))
    return {snapshot.id: snapshot.to_dict() or {} for snapshot in snapshots if snapshot.exists}

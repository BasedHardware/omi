"""Finish marker reads for the v3 builder's fast Finish re-wake: marker fields only, a bounded id set."""

from database._client import get_firestore_client
from database.conversations_v3 import user_conversations

# Only what the builder needs to tell a recent Finish from live speech; one document read per id.
FINISH_MARKER_FIELDS = ('v3_manual_end', 'v3_manual_end_requested', 'v3_pending', 'finished_at', 'deleted', 'discarded')
FINISH_MARKER_LIMIT = 8


def finish_markers(uid, ids, *, firestore_client=None):
    """The Finish marker fields of at most ``FINISH_MARKER_LIMIT`` recordings, keyed by id (absent rows omitted)."""
    chosen = sorted(ids)[:FINISH_MARKER_LIMIT]
    if not chosen:
        return {}
    client = firestore_client or get_firestore_client()
    coll = user_conversations(client, uid)
    snapshots = client.get_all([coll.document(rid) for rid in chosen], field_paths=list(FINISH_MARKER_FIELDS))
    return {snapshot.id: snapshot.to_dict() or {} for snapshot in snapshots if snapshot.exists}

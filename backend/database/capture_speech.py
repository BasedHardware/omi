"""Single-snapshot immutable transcript reads for deterministic capture grouping."""

from copy import deepcopy

from database._client import get_firestore_client
from database.capture_groups import transcript_fingerprint
from database import conversations as conversations_db


def get_shared_speech_snapshot(uid: str, conversation_id: str, *, firestore_client=None):
    """Never project mutable correction overlays or perform their additional reads.

    Corrected captures retain their metadata and abstain before decoding. The
    matcher and commit guard both reject corrections, including concurrent edits.
    """
    client = firestore_client or get_firestore_client()
    snapshot = client.collection('users').document(uid).collection('conversations').document(conversation_id).get()
    raw = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
    if not raw:
        return None, None
    fingerprint = transcript_fingerprint(raw)
    row = dict(raw)
    if raw.get('has_transcript_corrections') or raw.get('transcript_correction_overlay') is not None:
        row['transcript_segments'] = []
    else:
        row['transcript_segments'] = conversations_db.decode_transcript_segments_verified(
            uid, deepcopy(raw.get('transcript_segments') or []), bool(raw.get('transcript_segments_compressed'))
        )
    return row, fingerprint

"""Composite (Firestore + GCS + cache) operations for screen frames.

The Firestore-only CRUD lives in database/screen_frames.py, mirroring the
photos subcollection exactly (contract §8). This module is the layer above
it that also touches GCS — the same split as delete_conversation_audio_files
(GCS, utils/other/storage.py) being called alongside
database.conversations.delete_conversation (Firestore-only) from the router,
rather than folding the GCS call into the DB layer.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import database.screen_frames as screen_frames_db
import utils.other.storage as storage
from utils.screen_frames.environment import frame_storage_bucket

logger = logging.getLogger(__name__)


def persist_screen_frame_docs(uid: str, conversation_id: str, frame_docs: List[Dict[str, Any]]) -> bool:
    """Upsert already role/rank-assigned frame Firestore docs.

    Returns False if the parent conversation no longer exists (mirrors
    store_conversation_photos' check-parent-exists behavior) — callers must
    treat that as "nothing was persisted," including not counting the
    corresponding writer-side GCS objects as reachable content anymore.
    """
    if not frame_docs:
        return True
    return screen_frames_db.store_conversation_screen_frames(uid, conversation_id, frame_docs)


def delete_screen_frame(uid: str, conversation_id: str, frame_id: str) -> bool:
    """Delete one frame's Firestore doc, both GCS objects, and cached signed
    URLs. Returns whether the Firestore doc existed. GCS/cache deletion runs
    unconditionally either way — contract §8: a delete that leaves bytes in
    the bucket is a bug, not a partial success.

    A frame another environment wrote (its doc records a different bucket) is
    not this environment's to delete: it is reported as absent and untouched.
    """
    bucket = storage.configured_screen_frames_bucket()
    doc = screen_frames_db.get_conversation_screen_frame_doc(uid, conversation_id, frame_id)
    if doc is not None and frame_storage_bucket(doc) != bucket:
        return False
    existed = screen_frames_db.delete_conversation_screen_frame_doc(uid, conversation_id, frame_id)
    storage.delete_screen_frame_blobs(uid, conversation_id, frame_id)
    return existed


def delete_conversation_screen_frames(uid: str, conversation_id: str) -> int:
    """Delete every screen frame for a conversation: Firestore docs + both GCS
    objects each + cached signed URLs each.

    This is the function wired into the conversation-delete path (contract
    §8). It must run before the parent conversation doc is deleted —
    Firestore does not cascade subcollection deletes.

    The conversation is going away, so every frame doc goes with it. Bytes in
    another environment's bucket are deleted best-effort from that bucket:
    this environment may lack access, and that must not block the delete.
    """
    bucket = storage.configured_screen_frames_bucket()
    frames = screen_frames_db.get_conversation_screen_frames(uid, conversation_id)
    for frame in frames:
        frame_id = frame.get('id')
        if not frame_id:
            continue
        frame_bucket = frame_storage_bucket(frame)
        if frame_bucket == bucket:
            storage.delete_screen_frame_blobs(uid, conversation_id, frame_id)
            continue
        try:
            storage.delete_screen_frame_blobs(uid, conversation_id, frame_id, bucket=frame_bucket)
        except Exception as error:  # noqa: BLE001 - another environment's bucket is best effort
            logger.warning(
                "screen_frame foreign-bucket delete failed uid=%s conversation_id=%s frame_id=%s error_type=%s",
                uid,
                conversation_id,
                frame_id,
                type(error).__name__,
            )
    return screen_frames_db.delete_conversation_screen_frame_docs(uid, conversation_id)

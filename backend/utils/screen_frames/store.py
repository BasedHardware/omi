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
    """
    existed = screen_frames_db.delete_conversation_screen_frame_doc(uid, conversation_id, frame_id)
    storage.delete_screen_frame_blobs(uid, conversation_id, frame_id)
    return existed


def delete_conversation_screen_frames(uid: str, conversation_id: str) -> int:
    """Delete every screen frame for a conversation: Firestore docs + both GCS
    objects each + cached signed URLs each.

    This is the function wired into the conversation-delete path (contract
    §8). It must run before the parent conversation doc is deleted —
    Firestore does not cascade subcollection deletes.
    """
    frames = screen_frames_db.get_conversation_screen_frames(uid, conversation_id)
    for frame in frames:
        frame_id = frame.get('id')
        if frame_id:
            storage.delete_screen_frame_blobs(uid, conversation_id, frame_id)
    return screen_frames_db.delete_conversation_screen_frame_docs(uid, conversation_id)

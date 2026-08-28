"""Conversation-lifetime frame evidence reads and deletion convergence."""

from __future__ import annotations

from collections.abc import Callable

import database.conversations as conversations_db
import database.frame_requests as frame_requests_db
from utils.retrieval.frame_request_storage import (
    delete_frame_request_pixels_for_user,
    download_frame_request_pixels,
)


def read_conversation_frame(
    uid: str,
    conversation_id: str,
    photo_id: str,
) -> tuple[bytes, str]:
    if not conversations_db.get_conversation(uid, conversation_id):
        raise KeyError("conversation frame not found")
    photos = conversations_db.get_conversation_photos(uid, conversation_id) or []
    photo = next(
        (item for item in photos if item.get("id") == photo_id and item.get("storage_id")),
        None,
    )
    if not photo:
        raise KeyError("conversation frame not found")
    payload = download_frame_request_pixels(uid, str(photo["storage_id"]))
    return payload, str(photo.get("content_type") or "image/jpeg")


def delete_conversation_and_frame_evidence(
    uid: str,
    conversation_id: str,
    *,
    delete_conversation: Callable[[str, str], object] = conversations_db.delete_conversation,
) -> None:
    """Outbox objects before metadata deletion, then converge best-effort."""

    photo_storage_ids = [
        str(photo.get("storage_id"))
        for photo in (conversations_db.get_conversation_photos(uid, conversation_id) or [])
        if isinstance(photo, dict) and isinstance(photo.get("storage_id"), str) and photo.get("storage_id")
    ]
    request_storage_ids = frame_requests_db.list_all_frame_request_storage_ids(
        uid,
        conversation_id=conversation_id,
    )
    storage_ids = list(dict.fromkeys(photo_storage_ids + request_storage_ids))
    frame_requests_db.persist_conversation_frame_deletion_outbox(uid, conversation_id, storage_ids)
    delete_conversation(uid, conversation_id)
    for storage_id in storage_ids:
        try:
            delete_frame_request_pixels_for_user(uid, [storage_id])
        except Exception:
            continue
        frame_requests_db.acknowledge_conversation_frame_deletion(uid, conversation_id, storage_id)
    frame_requests_db.delete_frame_requests_for_conversation(uid, conversation_id)


__all__ = ["delete_conversation_and_frame_evidence", "read_conversation_frame"]

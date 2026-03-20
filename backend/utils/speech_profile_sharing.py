from __future__ import annotations

import json
import logging
from typing import Optional

import numpy as np
from google.cloud import firestore, storage

from database._client import db
from database.redis_db import r

logger = logging.getLogger(__name__)

_SHARES_COLLECTION = "speech_profile_shares"
_SHARE_CHANNEL_PREFIX = "speech_profile_share:"
_BUCKET_SPEECH_PROFILES = "speech-profiles"  # matches env BUCKET_SPEECH_PROFILES


# ──────────────────────────────────────────────────────────────
# Channel helpers (pure functions, zero I/O)
# ──────────────────────────────────────────────────────────────

def share_redis_channel(recipient_uid: str) -> str:
    return f"{_SHARE_CHANNEL_PREFIX}{recipient_uid}"


def shared_profile_key(sharer_uid: str) -> str:
    """Namespace shared profiles to avoid collision with own profile key."""
    return f"shared_{sharer_uid}"


# ──────────────────────────────────────────────────────────────
# GCS helpers
# ──────────────────────────────────────────────────────────────

def _embedding_blob_path(uid: str) -> str:
    return f"{uid}/speech_profile.npy"


def load_embedding_from_gcs(uid: str) -> Optional[np.ndarray]:
    """Download and deserialise a user's speech-profile embedding from GCS.

    Returns ``None`` if the blob does not exist or cannot be read.
    """
    try:
        bucket = storage.Client().bucket(_BUCKET_SPEECH_PROFILES)
        blob = bucket.blob(_embedding_blob_path(uid))
        if not blob.exists():
            logger.debug("No speech profile blob for uid=%s", uid)
            return None
        raw = blob.download_as_bytes()
        return np.frombuffer(raw, dtype=np.float32)
    except Exception:
        logger.exception("Failed to load speech profile embedding for uid=%s", uid)
        return None


# ──────────────────────────────────────────────────────────────
# Firestore CRUD
# ──────────────────────────────────────────────────────────────

def get_user_by_email(email: str) -> Optional[dict]:
    """Return ``{"uid": ..., ...}`` for the first user with *email*, or ``None``."""
    docs = (
        db.collection("users")
        .where("email", "==", email)
        .limit(1)
        .stream()
    )
    for doc in docs:
        return {"uid": doc.id, **doc.to_dict()}
    return None


def create_share(sharer_uid: str, recipient_uid: str, display_name: str) -> str:
    """Persist a share record. Returns the new Firestore document ID."""
    ref = db.collection(_SHARES_COLLECTION).document()
    ref.set(
        {
            "sharer_uid": sharer_uid,
            "recipient_uid": recipient_uid,
            "display_name": display_name,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )
    logger.info(
        "Share created: sharer=%s recipient=%s name=%r doc=%s",
        sharer_uid,
        recipient_uid,
        display_name,
        ref.id,
    )
    return ref.id


def delete_share(sharer_uid: str, recipient_uid: str) -> bool:
    """Delete share record(s). Returns ``True`` if at least one was removed."""
    docs = (
        db.collection(_SHARES_COLLECTION)
        .where("sharer_uid", "==", sharer_uid)
        .where("recipient_uid", "==", recipient_uid)
        .stream()
    )
    deleted = False
    for doc in docs:
        doc.reference.delete()
        deleted = True
    if deleted:
        logger.info("Share revoked: sharer=%s recipient=%s", sharer_uid, recipient_uid)
    return deleted


def get_shares_for_recipient(recipient_uid: str) -> list[dict]:
    """Return all active share records where the current user is the recipient."""
    docs = (
        db.collection(_SHARES_COLLECTION)
        .where("recipient_uid", "==", recipient_uid)
        .stream()
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


def share_exists(sharer_uid: str, recipient_uid: str) -> bool:
    docs = (
        db.collection(_SHARES_COLLECTION)
        .where("sharer_uid", "==", sharer_uid)
        .where("recipient_uid", "==", recipient_uid)
        .limit(1)
        .stream()
    )
    return any(True for _ in docs)


# ──────────────────────────────────────────────────────────────
# Redis pub/sub
# ──────────────────────────────────────────────────────────────

def publish_share_event(
    recipient_uid: str, action: str, sharer_uid: str, display_name: str
) -> None:
    """Publish a share/revoke event to the recipient's Redis channel."""
    channel = share_redis_channel(recipient_uid)
    payload = json.dumps(
        {"action": action, "sharer_uid": sharer_uid, "display_name": display_name}
    )
    r.publish(channel, payload)
    logger.info("Redis event published: channel=%s action=%s", channel, action)


# ──────────────────────────────────────────────────────────────
# Bulk loader for /v4/listen session startup
# ──────────────────────────────────────────────────────────────

def load_shared_profiles(uid: str) -> dict[str, tuple[np.ndarray, str]]:
    """Load all shared embeddings for *uid*.

    Returns a dict of ``{shared_{sharer_uid}: (embedding, display_name)}``.
    Called once when a /v4/listen WebSocket session opens.
    """
    shares = get_shares_for_recipient(uid)
    result: dict[str, tuple[np.ndarray, str]] = {}
    for share in shares:
        sharer_uid = share["sharer_uid"]
        display_name = share.get("display_name", sharer_uid)
        embedding = load_embedding_from_gcs(sharer_uid)
        if embedding is not None:
            key = shared_profile_key(sharer_uid)
            result[key] = (embedding, display_name)
            logger.info(
                "Shared profile loaded: sharer=%s label=%r for_uid=%s",
                sharer_uid,
                display_name,
                uid,
            )
        else:
            logger.warning(
                "Shared profile sharer=%s has no embedding; skipping for uid=%s",
                sharer_uid,
                uid,
            )
    return result

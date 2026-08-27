"""The writer boundary (contract §5).

This module is the ONLY code path in the codebase allowed to write
BUCKET_SCREEN_FRAMES. It:

1. Verifies the approval (signature, structure, expiry) via `approval.verify_approval`.
2. Re-derives the digest over the exact bytes handed to it and checks it against
   the approval's claimed canonical_sha256 — the approval binds to specific
   bytes, not to "a frame that was approved at some point."
3. Atomically consumes the approval's jti (Redis SETNX with TTL) BEFORE writing,
   so a replayed approval can never write twice.
4. Only then calls the storage layer to write the bucket.

DEPLOY PREREQUISITE (contract §5): this function must run under a separate
service account with write access to BUCKET_SCREEN_FRAMES only, granted only
to the writer's execution identity. This module cannot provision that IAM
split — it is infrastructure that must exist before this code is trusted
with real traffic, not something a PR can create.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from uuid import uuid4

import database.redis_db as redis_db
import utils.other.storage as storage
from utils.screen_frames.approval import ApprovalSignatureError, verify_approval

logger = logging.getLogger(__name__)


class ScreenFrameWriteError(Exception):
    """The approval could not be used to write anything.

    Every raise site here happens strictly before any bytes reach GCS,
    except upload_failed (raised only after the jti is already consumed —
    burning a jti on a failed upload is safe: it just makes that specific
    approval unusable, which is the fail-closed direction).
    """


@dataclass(frozen=True)
class WrittenScreenFrame:
    frame_id: str
    uid: str
    conversation_id: str


def write_screen_frame(
    approval_token: str,
    *,
    jpeg_bytes: bytes,
    thumbnail_jpeg_bytes: bytes,
) -> WrittenScreenFrame:
    """Verify, then write. Raises ScreenFrameWriteError and writes nothing on
    any failure: expired/malformed/tampered approval, wrong-digest bytes, or a
    replayed jti.
    """
    try:
        claims = verify_approval(approval_token)
    except ApprovalSignatureError as error:
        raise ScreenFrameWriteError(f"invalid_approval:{error}") from error

    actual_digest = hashlib.sha256(jpeg_bytes).hexdigest()
    if not hmac.compare_digest(actual_digest, claims.canonical_sha256):
        raise ScreenFrameWriteError("digest_mismatch")

    if not redis_db.try_consume_screen_frame_jti(str(claims.jti)):
        raise ScreenFrameWriteError("jti_already_consumed")

    frame_id = str(uuid4())
    try:
        storage.upload_screen_frame_blobs(claims.uid, claims.subject_id, frame_id, jpeg_bytes, thumbnail_jpeg_bytes)
    except Exception as error:
        logger.error(
            "screen_frame writer upload failed uid=%s conversation_id=%s error_type=%s",
            claims.uid,
            claims.subject_id,
            type(error).__name__,
        )
        raise ScreenFrameWriteError("upload_failed") from error

    return WrittenScreenFrame(frame_id=frame_id, uid=claims.uid, conversation_id=claims.subject_id)

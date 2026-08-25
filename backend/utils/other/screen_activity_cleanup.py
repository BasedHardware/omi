"""Fleet cleanup for the retired screen-activity cloud copies.

Screen-activity sync was retired: the write route is a tombstone and the
desktop no longer uploads OCR rows. Users who synced before that rollout
still hold historical copies in the cloud — ``users/{uid}/screen_activity``
documents in Firestore and their embeddings in Pinecone — and account
deletion was the only path that removed them. This module drains both stores
for every affected user, in bounded passes, so the user-facing promise
("captures stay on this Mac") becomes true for pre-existing data too.

Ordering matters and is deliberate: a user's Pinecone vectors are deleted
FIRST, and the Firestore documents are deleted only if that succeeded. If
vector deletion fails, the documents survive as the durable to-do list and
the next hourly pass retries the same user. Deleting in the other order
would orphan the vectors forever.

Runs from the notifications-job cron lane (``utils.other.jobs.start_job``).
"""

from __future__ import annotations

import logging
import os

from database._client import get_firestore_client
from database.screen_activity import delete_screen_activity, get_screen_activity_ids
from database.vector_db import delete_screen_activity_vectors
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)

DEFAULT_USERS_PER_RUN = 200


def _users_per_run() -> int:
    raw = os.getenv("SCREEN_ACTIVITY_CLOUD_PURGE_USERS_PER_RUN", str(DEFAULT_USERS_PER_RUN))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("SCREEN_ACTIVITY_CLOUD_PURGE_USERS_PER_RUN must be an integer") from exc
    return max(0, value)


async def purge_retired_screen_activity_copies() -> dict[str, int]:
    """Delete historical screen-activity Firestore rows + Pinecone vectors.

    Bounded per run so the hourly cron lane drains the fleet gradually without
    monopolizing its budget. Returns counters for logging/tests. Set
    ``SCREEN_ACTIVITY_CLOUD_PURGE_USERS_PER_RUN=0`` to disable the pass.
    """
    users_limit = _users_per_run()
    result = {"users_scanned": 0, "docs_deleted": 0, "vectors_deleted": 0, "users_failed": 0}
    if users_limit == 0:
        logger.info("Screen-activity cloud purge disabled by configuration")
        return result

    def _discover_owners() -> list[str]:
        client = get_firestore_client()
        owners: list[str] = []
        # A bare collection-group scan needs no composite index; only IDs are read.
        for doc in client.collection_group("screen_activity").select([]).stream():
            parent = doc.reference.parent.parent
            uid = str(parent.id) if parent is not None else None
            if not uid:
                continue
            result["users_scanned"] += 1
            if uid not in owners:
                owners.append(uid)
            if len(owners) >= users_limit:
                break
        return owners

    owners = await run_blocking(db_executor, _discover_owners)
    for owner_uid in owners:

        def _purge_user(uid: str = owner_uid) -> tuple[int, int]:
            ids = get_screen_activity_ids(uid)
            if not ids:
                return 0, 0
            # Vectors first: the surviving Firestore docs are the retry list.
            delete_screen_activity_vectors(uid, ids)
            deleted = delete_screen_activity(uid, ids)
            return len(ids), deleted

        try:
            vector_count, doc_count = await run_blocking(db_executor, _purge_user)
            result["vectors_deleted"] += vector_count
            result["docs_deleted"] += doc_count
        except Exception as exc:
            result["users_failed"] += 1
            # Exception type only; row content must never reach logs.
            logger.warning(
                "screen_activity purge deferred for one owner (%s); documents retained as retry list",
                type(exc).__name__,
            )
    logger.info("Screen-activity cloud purge pass complete: %s", result)
    return result

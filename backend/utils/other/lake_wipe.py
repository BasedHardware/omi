"""Required lake erasure steps, outside database transactions and behind owner fences."""

import hashlib
import math
import os
import time
from datetime import datetime, timezone

from google.cloud import firestore

from config import object_lake as config
from database import users as users_db
from database.account_deletion_policy import account_deletion_blocks_access
from utils.other import object_lake, space_keys
from utils.cloud_tasks import enqueue_named_task


def purge_owner_lake_content(uid: str) -> dict:
    """Fence, drain in-flight writers, then purge with verified absence."""
    if not config.bucket():
        return {'status': 'noop'}
    status = users_db.get_user_deletion_wipe_status(uid)
    if status != 'running':
        raise RuntimeError('lake purge requires a running account wipe')
    if not account_deletion_blocks_access(status):
        raise RuntimeError('lake purge requires a blocking deletion marker')
    drain = config.wipe_drain_seconds()
    if drain:
        time.sleep(drain)
    count = object_lake.delete_space_prefix(uid)
    # Keep discovery through all intervening wipe steps: an admitted upload can
    # land after this listing and lose its worker before its post-put check.
    return {'status': 'purged', 'objects_deleted': count, 'candidates_deleted': 0}


def destroy_owner_lake_keys(uid: str, *, now: datetime | None = None) -> dict:
    """LAST destructive wipe step, including when bucket configuration is absent."""
    if users_db.get_user_deletion_wipe_status(uid) != 'running':
        raise RuntimeError('lake key destroy requires a running account wipe')
    object_lake.assert_space_uploads_quiescent(uid, now=now)
    # Re-list and verify absence at the last possible point, before erasing the
    # discovery rows and then key authority. Any failure retains keys for retry.
    if config.bucket():
        object_lake.delete_space_prefix(uid)
    # An absent bucket must not strand existing owner-derived Firestore intents.
    object_lake.delete_space_upload_candidates(uid, now=now)
    count = space_keys.destroy_space_keys(uid)
    return {'status': 'destroyed', 'versions_destroyed': count}


def purge_conversation_lake_objects(uid: str, conversation_id: str, source_ids=()) -> int:
    """Purge the conversation and merge donors before deleting their documents."""
    entity_ids = [entity_id for entity_id in dict.fromkeys([conversation_id, *source_ids]) if entity_id]
    # With no current bucket, only recorded former-bucket candidates need work;
    # skip the fence write entirely when none exist (the usual unconfigured case).
    if not config.bucket() and not any(
        object_lake.entity_upload_candidates_exist(uid, entity_id) for entity_id in entity_ids
    ):
        return 0
    # Fence every donor before the first listing, including callers that do not
    # record the public route's intent. Preserve existing tombstone bindings.
    for entity_id in entity_ids:
        _fence_conversation_uploads(uid, entity_id)
    count = 0
    for entity_id in entity_ids:
        if config.bucket():
            count += object_lake.delete_space_entity(uid, entity_id)
        object_lake.delete_entity_upload_candidates(
            uid, entity_id, schedule_repurge=lambda due: schedule_conversation_lake_repurge(uid, entity_id, due)
        )
    return count


def schedule_conversation_lake_repurge(uid: str, entity_id: str, due: datetime) -> None:
    """Reuse the existing sync task queue/identity; no new infrastructure bindings."""
    handler = os.getenv('SYNC_TASKS_HANDLER_URL', '').strip()
    suffix = '/v2/sync-jobs/run'
    if not handler.endswith(suffix):
        raise object_lake.LakeFetchError('Lake re-purge requires the configured sync task handler')
    # Strictly older than 24 hours, including fractional admission timestamps.
    schedule_at = max(math.floor(due.timestamp()) + 1, math.floor(time.time()) + 1)
    digest = hashlib.sha256(f'{uid}/{entity_id}/{schedule_at}'.encode()).hexdigest()
    try:
        enqueue_named_task(
            os.getenv('SYNC_TASKS_QUEUE', ''),
            handler.removesuffix(suffix) + '/internal/lake/conversation-repurge',
            f'lake-repurge-{digest}',
            {'space_id': uid, 'entity_id': entity_id},
            audience=os.getenv('SYNC_TASKS_OIDC_AUDIENCE') or handler,
            schedule_at=schedule_at,
        )
    except Exception:
        raise object_lake.LakeFetchError('Lake delayed re-purge scheduling unavailable') from None


def repurge_conversation_lake_objects(uid: str, entity_id: str, *, now: datetime | None = None) -> int:
    """Delayed retry: re-delete recorded buckets before expiring lost attempts."""

    # Early deliveries must retry, not acknowledge a task whose work is pending.
    def still_pending(_due: datetime) -> None:
        raise object_lake.LakeFetchError('Lake uploads still in flight; retry re-purge later')

    # Require the durable deletion fence even on duplicate/early task deliveries.
    return object_lake.delete_entity_upload_candidates(
        uid,
        entity_id,
        now=now,
        erase_expired=True,
        schedule_repurge=still_pending,
    )


def _fence_conversation_uploads(uid: str, conversation_id: str) -> None:
    try:
        client = space_keys.space_key_firestore_client()
        tombstone = (
            client.collection('users').document(uid).collection('deleted_conversations').document(conversation_id)
        )

        @firestore.transactional
        def fence(transaction):
            if not tombstone.get(transaction=transaction).exists:
                transaction.create(
                    tombstone, {'conversation_id': conversation_id, 'deleted_at': datetime.now(timezone.utc)}
                )

        fence(client.transaction())
    except Exception:
        raise object_lake.LakeFetchError('Lake conversation deletion fence unavailable') from None

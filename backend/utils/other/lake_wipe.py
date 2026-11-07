"""Required lake erasure steps, outside database transactions and behind owner fences."""

import time

from config import object_lake as config
from database import users as users_db
from database.account_deletion_policy import account_deletion_blocks_access
from utils.other import object_lake, space_keys


def purge_owner_lake_content(uid: str) -> dict:
    """Fence, drain in-flight writers, then purge with verified absence."""
    if not config.bucket():
        return {'status': 'noop'}
    if users_db.get_user_deletion_wipe_status(uid) != 'running':
        raise RuntimeError('lake purge requires a running account wipe')
    if not account_deletion_blocks_access(users_db.get_user_deletion_wipe_status(uid)):
        raise RuntimeError('lake purge requires a blocking deletion marker')
    time.sleep(config.wipe_drain_seconds())
    count = object_lake.delete_space_prefix(uid)
    return {'status': 'purged', 'objects_deleted': count}


def destroy_owner_lake_keys(uid: str) -> dict:
    """LAST destructive wipe step, including when bucket configuration is absent."""
    if users_db.get_user_deletion_wipe_status(uid) != 'running':
        raise RuntimeError('lake key destroy requires a running account wipe')
    count = space_keys.destroy_space_keys(uid)
    return {'status': 'destroyed', 'versions_destroyed': count}


def purge_conversation_lake_objects(uid: str, conversation_id: str, source_ids=()) -> int:
    """Purge the conversation and merge donors before deleting their documents."""
    if not config.bucket():
        return 0
    count = 0
    for entity_id in dict.fromkeys([conversation_id, *source_ids]):
        if entity_id:
            count += object_lake.delete_space_entity(uid, entity_id)
    return count

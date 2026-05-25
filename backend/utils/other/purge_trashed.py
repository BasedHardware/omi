import logging
import uuid
from datetime import datetime, timedelta, timezone

import database.action_items as action_items_db
import database.conversations as conversations_db
import database.memories as memories_db
from database.vector_db import delete_memory_vector, delete_vector
from utils.log_sanitizer import sanitize_pii
from utils.other.storage import delete_conversation_audio_files

logger = logging.getLogger(__name__)

RETENTION_DAYS = 30
PURGE_HOUR_UTC = 3


def should_run_purge_trashed_job(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now.hour == PURGE_HOUR_UTC


def purge_expired_trashed_conversations(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    batch_id = str(uuid.uuid4())
    purged_count = 0

    for uid, conversation_id in conversations_db.list_expired_trashed(cutoff):
        safe_uid = sanitize_pii(uid)
        safe_conversation_id = sanitize_pii(conversation_id)
        try:
            conversations_db.delete_conversation(uid, conversation_id)
            delete_vector(uid, conversation_id)
            delete_conversation_audio_files(uid, conversation_id)

            memory_ids = memories_db.get_memory_ids_for_conversation(uid, conversation_id)
            memories_db.delete_memories_for_conversation(uid, conversation_id)
            for memory_id in memory_ids:
                delete_memory_vector(uid, memory_id)

            action_items_db.delete_action_items_for_conversation(uid, conversation_id)
            purged_count += 1
        except Exception as e:
            logger.exception(
                'purge_trashed failed batch_id=%s uid=%s conversation_id=%s error=%s',
                batch_id,
                safe_uid,
                safe_conversation_id,
                sanitize_pii(str(e)),
            )

    logger.info('purge_trashed completed count=%s batch_id=%s', purged_count, batch_id)
    return purged_count

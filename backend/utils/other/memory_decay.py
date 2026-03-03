"""
Daily memory decay job.

Recalculates scoring for all non-manually-added memories using the exponential decay formula:
  relevance = exp(-0.03 * days_since_last_access) * log2(access_count + 2) * type_weight

Manually-added memories are vaulted (never decay). The job batches Firestore writes to stay
within rate limits and skips memories whose score hasn't changed.
"""

import logging
from datetime import datetime, timezone

from google.cloud import firestore

from database._client import db
from models.memories import MemoryDB, MemoryCategory

logger = logging.getLogger(__name__)

_USERS_COLLECTION = 'users'
_MEMORIES_COLLECTION = 'memories'
_BATCH_SIZE = 400  # Firestore batch limit is 500; stay conservative


def should_run_job() -> bool:
    """Run once per day — always true; caller decides scheduling frequency."""
    return True


async def start_cron_job():
    """Entry point called from jobs.py. Recalculates decay scores for all users."""
    logger.info('memory_decay_job: starting')
    total_users = 0
    total_updated = 0

    try:
        users_ref = db.collection(_USERS_COLLECTION).stream()
        for user_doc in users_ref:
            uid = user_doc.id
            updated = _recalculate_scores_for_user(uid)
            total_updated += updated
            total_users += 1

    except Exception as e:
        logger.error(f'memory_decay_job: error iterating users: {e}')

    logger.info(f'memory_decay_job: done — {total_users} users, {total_updated} scores updated')


def _recalculate_scores_for_user(uid: str) -> int:
    """Recalculate decay scores for a single user. Returns count of updated memories."""
    memories_ref = db.collection(_USERS_COLLECTION).document(uid).collection(_MEMORIES_COLLECTION)

    try:
        docs = list(memories_ref.stream())
    except Exception as e:
        logger.warning(f'memory_decay_job: failed to fetch memories for {uid}: {e}')
        return 0

    batch = db.batch()
    batch_count = 0
    total_updated = 0

    for doc in docs:
        data = doc.to_dict()
        if not data:
            continue

        # Skip deleted memories
        if data.get('deleted', False):
            continue

        try:
            # Build a minimal MemoryDB object to reuse calculate_score
            memory = _dict_to_memory_db(data)
            if memory is None:
                continue

            new_score = MemoryDB.calculate_score(memory)

            # Only write if score actually changed
            if new_score == data.get('scoring'):
                continue

            batch.update(
                doc.reference,
                {
                    'scoring': new_score,
                    'updated_at': datetime.now(timezone.utc),
                },
            )
            batch_count += 1
            total_updated += 1

            # Commit when approaching batch limit
            if batch_count >= _BATCH_SIZE:
                batch.commit()
                batch = db.batch()
                batch_count = 0

        except Exception as e:
            logger.warning(f'memory_decay_job: error processing memory {doc.id} for {uid}: {e}')
            continue

    # Commit remaining writes
    if batch_count > 0:
        try:
            batch.commit()
        except Exception as e:
            logger.error(f'memory_decay_job: batch commit failed for {uid}: {e}')

    return total_updated


def _dict_to_memory_db(data: dict) -> 'MemoryDB | None':
    """Convert a Firestore dict to a MemoryDB instance for score calculation."""
    try:
        # Ensure required fields exist
        if not data.get('id') or not data.get('uid'):
            return None

        # Resolve category — default to 'system' for unknown/missing
        raw_cat = data.get('category', 'system')
        try:
            category = MemoryCategory(raw_cat)
        except ValueError:
            category = MemoryCategory.system

        created_at = data.get('created_at')
        if created_at is None:
            return None
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        last_accessed_at = data.get('last_accessed_at')
        if last_accessed_at is not None:
            if isinstance(last_accessed_at, str):
                last_accessed_at = datetime.fromisoformat(last_accessed_at)
            if last_accessed_at.tzinfo is None:
                last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)

        return MemoryDB(
            id=data['id'],
            uid=data['uid'],
            content=data.get('content', ''),
            category=category,
            created_at=created_at,
            updated_at=data.get('updated_at', created_at),
            manually_added=data.get('manually_added', False),
            access_count=data.get('access_count', 0),
            last_accessed_at=last_accessed_at,
        )
    except Exception as e:
        logger.debug(f'memory_decay_job: _dict_to_memory_db failed: {e}')
        return None

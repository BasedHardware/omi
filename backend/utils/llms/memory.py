import threading
from typing import Any, Dict, List, Optional, Tuple

from cachetools import TTLCache

from database._client import db as firestore_db
from database.auth import get_user_name
from models.memories import Memory, MemoryDB
from utils.memory.memory_service import MemoryService
import logging

logger = logging.getLogger(__name__)

# Prompt context is a bounded default-visible intake — never a full account export.
PROMPT_MEMORY_LIMIT = 1000

_PROMPT_DATA_CACHE_MAX_SIZE = 1024
_PROMPT_DATA_CACHE_TTL_SECONDS = 30
_prompt_data_cache: TTLCache[str, Tuple[Optional[str], List[MemoryDB], List[MemoryDB], List[MemoryDB]]] = TTLCache(
    maxsize=_PROMPT_DATA_CACHE_MAX_SIZE, ttl=_PROMPT_DATA_CACHE_TTL_SECONDS
)
_prompt_data_cache_lock = threading.Lock()


def clear_prompt_data_cache(uid: Optional[str] = None) -> None:
    """Drop cached prompt context for one user (or all users when uid is None)."""
    with _prompt_data_cache_lock:
        if uid is None:
            _prompt_data_cache.clear()
        else:
            _prompt_data_cache.pop(uid, None)


def get_prompt_memories(uid: str) -> Tuple[Any, str]:
    user_name, baseline_memories, user_made_memories, generated_memories = get_prompt_data(uid)
    memories_str = ''
    if baseline_memories:
        memories_str += (
            f'you already know the following baseline facts about {user_name} (always in context):'
            f' \n{Memory.get_memories_as_str(baseline_memories)}.\n'
        )
    memories_str += (
        f'you already know the following facts about {user_name}: \n{Memory.get_memories_as_str(generated_memories)}.'
    )
    if user_made_memories:
        memories_str += (
            f'\n\n{user_name} also shared the following about self: \n{Memory.get_memories_as_str(user_made_memories)}'
        )
    return user_name, memories_str + '\n'


def safe_create_memory(memory_data: Dict[str, Any]) -> MemoryDB:
    """Safely create a MemoryDB instance handling legacy categories"""
    try:
        return MemoryDB(**memory_data)
    except Exception as e:
        # Handle legacy category conversion if needed
        if 'category' in memory_data and isinstance(memory_data['category'], str):
            # Make a copy to avoid modifying the original data
            fixed_data: Dict[str, Any] = dict(memory_data)
            # Set a default/fallback category if the category is causing issues
            if 'category' in str(e):
                # Use a safe default category
                if memory_data['category'] in [
                    'core',
                    'hobbies',
                    'lifestyle',
                    'interests',
                    'work',
                    'skills',
                    'learnings',
                ]:
                    fixed_data['category'] = 'interesting'
                else:
                    fixed_data['category'] = 'system'
                return MemoryDB(**fixed_data)
        # If we couldn't fix it, re-raise the exception
        raise


def _is_prompt_visible(memory: MemoryDB) -> bool:
    """Rejected, pending-review, locked, and invalidated rows stay out of prompts."""
    if memory.is_locked:
        return False
    if memory.user_review is False:
        return False
    if memory.invalid_at is not None:
        return False
    return True


def get_prompt_data(
    uid: str,
) -> Tuple[Optional[str], List[MemoryDB], List[MemoryDB], List[MemoryDB]]:
    with _prompt_data_cache_lock:
        cached = _prompt_data_cache.get(uid)
    if cached is not None:
        user_name, baseline, user_made, generated = cached
        return user_name, list(baseline), list(user_made), list(generated)

    # Use the default-visible list surface (processed, non-archive) with a hard
    # page cap. Account export is intentionally not used for prompt intake.
    existing_memories = MemoryService(db_client=firestore_db).read(
        uid,
        limit=PROMPT_MEMORY_LIMIT,
        offset=0,
        include_pending_processing=False,
    )

    baseline: List[MemoryDB] = []
    user_made: List[MemoryDB] = []
    generated: List[MemoryDB] = []

    for memory_obj in existing_memories:
        try:
            if not _is_prompt_visible(memory_obj):
                continue
            if memory_obj.is_baseline:
                baseline.append(memory_obj)
            elif memory_obj.manually_added:
                user_made.append(memory_obj)
            else:
                generated.append(memory_obj)
        except Exception as e:
            logger.error(f"Error routing memory into prompt buckets: {e}")

    user_name = get_user_name(uid)
    result = (user_name, baseline, user_made, generated)
    with _prompt_data_cache_lock:
        _prompt_data_cache[uid] = result
    return result

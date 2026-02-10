import hashlib
import json
from typing import List, Tuple, Optional

import database.memories as memories_db
import database.redis_db as redis_db
from database.auth import get_user_name
from models.memories import Memory, MemoryCategory

# Redis cache TTL for prompt data (seconds)
_PROMPT_DATA_CACHE_TTL = 300  # 5 minutes


def get_prompt_memories(uid: str, context: str = None, k: int = 50) -> Tuple[str, str, str]:
    """
    Get formatted memory string for prompt injection.

    Args:
        uid: User ID
        context: Optional conversation context for semantic retrieval via Pinecone.
                 When provided, uses vector similarity to find relevant memories.
                 When None, uses Firestore scoring (importance + recency).
        k: Number of memories to retrieve (default 50)

    Returns:
        (user_name, memories_str, version_hash)
        version_hash is a deterministic 8-char hex string for cache key routing.
    """
    user_name, user_made_memories, generated_memories = get_prompt_data(uid, context=context, k=k)
    memories_str = (
        f'you already know the following facts about {user_name}: \n{Memory.get_memories_as_str(generated_memories)}.'
    )
    if user_made_memories:
        memories_str += (
            f'\n\n{user_name} also shared the following about self: \n{Memory.get_memories_as_str(user_made_memories)}'
        )
    version = _compute_version_hash(user_made_memories, generated_memories)
    return user_name, memories_str + '\n', version


def safe_create_memory(memory_data):
    """Safely create a Memory instance handling legacy categories"""
    try:
        return Memory(**memory_data)
    except Exception as e:
        # Handle legacy category conversion if needed
        if 'category' in memory_data and isinstance(memory_data['category'], str):
            # Make a copy to avoid modifying the original data
            fixed_data = dict(memory_data)
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
                return Memory(**fixed_data)
        # If we couldn't fix it, re-raise the exception
        raise


def get_prompt_data(uid: str, context: str = None, k: int = 50) -> Tuple[str, List[Memory], List[Memory]]:
    """
    Fetch top-K memories for a user.

    When context is provided, uses Pinecone semantic search for relevance-ranked memories.
    Otherwise, uses Firestore scoring (importance + recency).
    Scoring-based results are cached in Redis for 5 minutes.
    """
    # Try Redis cache for scoring-based path (no context dependency)
    if context is None:
        cached = _get_cached_prompt_data(uid, k)
        if cached is not None:
            return cached

    # Fetch memories
    if context:
        existing_memories = _fetch_memories_by_context(uid, context, k)
    else:
        existing_memories = memories_db.get_memories(uid, limit=k)

    # Separate into user_made and generated
    user_made = []
    generated = []
    for memory in existing_memories:
        try:
            m = safe_create_memory(memory)
            if memory.get('manually_added', False):
                user_made.append(m)
            else:
                generated.append(m)
        except Exception as e:
            print(f"Error creating memory: {e}")

    user_name = get_user_name(uid)

    # Cache scoring-based results only (context-specific results vary per query)
    if context is None:
        _cache_prompt_data(uid, k, user_name, existing_memories)

    return user_name, user_made, generated


def _fetch_memories_by_context(uid: str, context: str, k: int) -> List[dict]:
    """Fetch semantically relevant memories using Pinecone vector search."""
    try:
        from database.vector_db import search_memories_by_vector

        memory_ids = search_memories_by_vector(uid, context, limit=k)
        if memory_ids:
            return memories_db.get_memories_by_ids(uid, memory_ids)
    except Exception as e:
        print(f"Semantic memory search failed, falling back to scoring: {e}")

    # Fallback to scoring-based retrieval
    return memories_db.get_memories(uid, limit=k)


def _compute_version_hash(user_made: List[Memory], generated: List[Memory]) -> str:
    """Compute deterministic version hash from memory content for cache key routing."""
    all_content = sorted([m.content for m in user_made + generated])
    hash_input = '|'.join(all_content)
    return hashlib.md5(hash_input.encode()).hexdigest()[:8]


def _cache_prompt_data(uid: str, k: int, user_name: str, raw_memories: List[dict]):
    """Cache raw memory dicts in Redis."""
    try:
        data = json.dumps({'user_name': user_name, 'memories': raw_memories}, default=str)
        redis_db.r.setex(f'prompt_data:{uid}:{k}', _PROMPT_DATA_CACHE_TTL, data)
    except Exception as e:
        print(f"Failed to cache prompt data: {e}")


def _get_cached_prompt_data(uid: str, k: int) -> Optional[Tuple[str, List[Memory], List[Memory]]]:
    """Retrieve cached prompt data from Redis."""
    try:
        cached = redis_db.r.get(f'prompt_data:{uid}:{k}')
        if cached:
            data = json.loads(cached)
            user_name = data['user_name']
            user_made = []
            generated = []
            for memory in data['memories']:
                try:
                    m = safe_create_memory(memory)
                    if memory.get('manually_added', False):
                        user_made.append(m)
                    else:
                        generated.append(m)
                except Exception as e:
                    print(f"Error creating cached memory: {e}")
            return user_name, user_made, generated
    except Exception as e:
        print(f"Failed to read prompt data cache: {e}")
    return None

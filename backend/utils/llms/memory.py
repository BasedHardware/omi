from typing import List, Tuple, Optional

import database.memories as memories_db
from database.auth import get_user_name
from models.memories import Memory, MemoryCategory, MemoryDB
import logging

logger = logging.getLogger(__name__)


def get_prompt_memories(uid: str) -> str:
    user_name, baseline_memories, user_made_memories, generated_memories = get_prompt_data(uid)
    memories_str = ''
    if baseline_memories:
        memories_str += f'you already know the following baseline facts about {user_name} (always in context): \n{Memory.get_memories_as_str(baseline_memories)}.\n'
    
    memories_str += f'you also know the following facts about {user_name}: \n{Memory.get_memories_as_str(generated_memories)}.'
    if user_made_memories:
        memories_str += (
            f'\n\n{user_name} also shared the following about self: \n{Memory.get_memories_as_str(user_made_memories)}'
        )
    return user_name, memories_str + '\n'


def safe_create_memory(memory_data):
    """Safely create a Memory instance handling legacy categories"""
    try:
        return MemoryDB(**memory_data)
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
                return MemoryDB(**fixed_data)
        # If we couldn't fix it, re-raise the exception
        raise


def get_prompt_data(uid: str) -> Tuple[str, List[MemoryDB], List[MemoryDB], List[MemoryDB]]:
    # TODO: cache this
    existing_memories = [m for m in memories_db.get_memories(uid, limit=1000) if not m.get('is_locked')]

    baseline = []
    user_made = []
    generated = []
    
    for memory in existing_memories:
        try:
            memory_obj = safe_create_memory(memory)
            if memory_obj.is_baseline:
                baseline.append(memory_obj)
            elif memory_obj.manually_added:
                user_made.append(memory_obj)
            else:
                generated.append(memory_obj)
        except Exception as e:
            logger.error(f"Error creating memory from memory: {e}")

    user_name = get_user_name(uid)
    return user_name, baseline, user_made, generated

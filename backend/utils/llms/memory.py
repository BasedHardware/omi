from typing import List, Tuple, Optional

import database.memories as memories_db
from database.auth import get_user_name
from models.memories import Memory, MemoryCategory


def get_prompt_memories(uid: str) -> str:
    user_name, user_made_memories, generated_memories = get_prompt_data(uid)
    memories_str = (
        f'you already know the following facts about {user_name}: \n{Memory.get_memories_as_str(generated_memories)}.'
    )
    if user_made_memories:
        memories_str += (
            f'\n\n{user_name} also shared the following about self: \n{Memory.get_memories_as_str(user_made_memories)}'
        )
    return user_name, memories_str + '\n'


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


def get_prompt_data(uid: str) -> Tuple[str, List[Memory], List[Memory]]:
    # TODO: cache this
    existing_memories = memories_db.get_memories(uid, limit=100)

    # Use a safer approach to create Memory objects from existing memories
    user_made = []
    for memory in existing_memories:
        if memory['manually_added']:
            try:
                user_made.append(safe_create_memory(memory))
            except Exception as e:
                print(f"Error creating memory from user-made memory: {e}")

    # Similarly for generated memories
    generated = []
    for memory in existing_memories:
        if not memory['manually_added']:
            try:
                generated.append(safe_create_memory(memory))
            except Exception as e:
                print(f"Error creating memory from generated memory: {e}")

    user_name = get_user_name(uid)
    # print('get_prompt_data', user_name, len(user_made), len(generated))
    return user_name, user_made, generated

from typing import List, Tuple, Optional

import database.memories as memories_db
from database.auth import get_user_name
from models.memories import Memory


def get_prompt_memories(uid: str) -> str:
    user_name, user_made_memories, generated_memories = get_prompt_data(uid)
    memories_str = f'you already know the following facts about {user_name}: \n{Memory.get_memories_as_str(generated_memories)}.'
    if user_made_memories:
        memories_str += f'\n\n{user_name} also shared the following about self: \n{Memory.get_memories_as_str(user_made_memories)}'
    return user_name, memories_str + '\n'


def get_prompt_data(uid: str) -> Tuple[str, List[Memory], List[Memory]]:
    # TODO: cache this
    existing_memories = memories_db.get_memories(uid, limit=100)
    user_made = [Memory(**memory) for memory in existing_memories if memory['manually_added']]
    # TODO: filter only reviewed True
    generated = [Memory(**memory) for memory in existing_memories if not memory['manually_added']]
    user_name = get_user_name(uid)
    # print('get_prompt_data', user_name, len(user_made), len(generated))
    return user_name, user_made, generated

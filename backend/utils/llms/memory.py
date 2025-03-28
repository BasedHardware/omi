from typing import List, Tuple, Optional

import database.memories as memories_db
from database.auth import get_user_name
from models.memories import Memory


def get_prompt_memories(uid: str) -> str:
    user_name, user_made_facts, generated_facts = get_prompt_data(uid)
    facts_str = f'you already know the following facts about {user_name}: \n{Memory.get_memories_as_str(generated_facts)}.'
    if user_made_facts:
        facts_str += f'\n\n{user_name} also shared the following about self: \n{Memory.get_memories_as_str(user_made_facts)}'
    return user_name, facts_str + '\n'


def get_prompt_data(uid: str) -> Tuple[str, List[Memory], List[Memory]]:
    # TODO: cache this
    existing_facts = memories_db.get_memories(uid, limit=100)
    user_made = [Memory(**fact) for fact in existing_facts if fact['manually_added']]
    # TODO: filter only reviewed True
    generated = [Memory(**fact) for fact in existing_facts if not fact['manually_added']]
    user_name = get_user_name(uid)
    # print('get_prompt_data', user_name, len(user_made), len(generated))
    return user_name, user_made, generated

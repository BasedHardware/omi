from typing import List, Tuple

import database.facts as facts_db
from database.auth import get_user_name
from models.facts import Fact


def get_prompt_facts(uid: str) -> str:
    user_name, user_made_facts, generated_facts = get_prompt_data(uid)
    facts_str = f'you already know the following facts about {user_name}: \n{Fact.get_facts_as_str(generated_facts)}.'
    if user_made_facts:
        facts_str += f'\n\n{user_name} also shared the following about self: \n{Fact.get_facts_as_str(user_made_facts)}'
    return user_name, facts_str + '\n'


def get_prompt_data(uid: str) -> Tuple[str, List[Fact], List[Fact]]:
    # TODO: cache this
    existing_facts = facts_db.get_facts(uid)
    user_made = [Fact(**fact) for fact in existing_facts if fact['manually_added']]
    # TODO: filter only reviewed True
    generated = [Fact(**fact) for fact in existing_facts if not fact['manually_added']]
    user_name = get_user_name(uid)
    print('get_prompt_data', user_name, len(user_made), len(generated))
    return user_name, user_made, generated

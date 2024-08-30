from typing import List, Tuple

import database.facts as facts_db
from database.auth import get_user_name
from models.facts import Fact


def get_prompt_data(uid: str, existing_facts: List[Fact] = None) -> Tuple[str, List[Fact]]:
    if not existing_facts:
        # TODO: cache this
        existing_facts = facts_db.get_facts(uid)  # TODO: use filter_only_true
        existing_facts = [Fact(**fact) for fact in existing_facts]

    user_name = get_user_name(uid)
    return user_name, existing_facts

from datetime import datetime
from typing import Tuple

import firebase_admin

from _shared import *
from database._client import document_id_from_seed
from models.facts import Fact, FactDB

firebase_admin.initialize_app()
from database.auth import get_user_name
from utils.llm import new_facts_extractor


def get_preferences_from_memory(memories: List[dict], uid: str) -> List[Tuple[str, List[Fact]]]:
    all_facts: List[Tuple[str, List[Fact]]] = []
    only_facts: List[Fact] = []
    user_name = get_user_name(uid)
    print('User:', user_name)
    for i, memory in enumerate(memories):
        data = Memory(**memory)
        try:
            new_facts = new_facts_extractor(data.transcript_segments, user_name, only_facts)
        except Exception as e:
            # LLM failed to parse output, we can skip 1 or 2, every 200.
            continue
        all_facts.append([memory['id'], new_facts])
        only_facts.extend(new_facts)

        print('Memory #', i + 1, 'retrieved', len(new_facts), 'facts')

    for fact in only_facts:
        print(fact.category.value.upper(), '~', fact.content)
    return all_facts


def script_migrate_users():
    # uids = memories_db.get_users_uid()
    uids = ['DX8n89KAmUaG9O7Qvj8xTi81Zu12']
    for uid in uids:
        memories = memories_db.get_memories(uid, limit=2000)
        data: List[Tuple[str, List[Fact]]] = get_preferences_from_memory(memories, uid)
        parsed_facts = []
        for item in data:
            memory_id, facts = item
            for fact in facts:
                parsed_facts.append(FactDB(
                    id=document_id_from_seed(fact.content),
                    uid=uid,
                    content=fact.content,
                    category=fact.category,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    memory_id=memory_id,
                    # memory_category=,
                ))

        facts_db.save_facts(uid, [fact.dict() for fact in parsed_facts])


if __name__ == '__main__':
    # get_preferences_from_memory()
    script_migrate_users()

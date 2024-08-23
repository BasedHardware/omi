import threading
from typing import Tuple

import firebase_admin

from _shared import *
from database._client import *
from models.facts import Fact, FactDB

firebase_admin.initialize_app()
from database.auth import get_user_name
from utils.llm import new_facts_extractor


def get_facts_from_memory(memories: List[dict], uid: str) -> List[Tuple[str, List[Fact]]]:
    all_facts: List[Tuple[str, List[Fact]]] = []
    only_facts: List[Fact] = []
    user_name = get_user_name(uid)
    print('User:', user_name)
    for i, memory in enumerate(memories):
        data = Memory(**memory)
        new_facts = new_facts_extractor(data.transcript_segments, user_name, only_facts)
        if not new_facts:
            continue
        all_facts.append([memory['id'], new_facts])
        only_facts.extend(new_facts)

        print(uid, 'Memory #', i + 1, 'retrieved', len(new_facts), 'facts')

    return all_facts


def execute_for_user(uid: str):
    facts_db.delete_facts(uid)

    memories = memories_db.get_memories(uid, limit=2000)
    data: List[Tuple[str, List[Fact]]] = get_facts_from_memory(memories, uid)
    parsed_facts = []
    for item in data:
        memory_id, facts = item
        memory = next((m for m in memories if m['id'] == memory_id), None)
        for fact in facts:
            parsed_facts.append(FactDB.from_fact(fact, uid, memory['id'], memory['structured']['category']))
        facts_db.save_facts(uid, [fact.dict() for fact in parsed_facts])


def script_migrate_users():
    uids = get_users_uid()
    # uids = ['DX8n89KAmUaG9O7Qvj8xTi81Zu12']

    threads = []
    for uid in uids:
        t = threading.Thread(target=execute_for_user, args=(uid,))
        threads.append(t)

    chunk_size = 10
    chunks = [threads[i:i + chunk_size] for i in range(0, len(threads), chunk_size)]
    for chunk in chunks:
        [t.start() for t in chunk]
        [t.join() for t in chunk]


if __name__ == '__main__':
    # get_preferences_from_memory()
    script_migrate_users()

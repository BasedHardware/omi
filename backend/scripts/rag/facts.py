import threading
from typing import Tuple

import firebase_admin

from _shared import *
from database.auth import get_user_name
from models.facts import Fact, FactDB

firebase_admin.initialize_app()
from utils.llm import new_facts_extractor
import database.facts as facts_db


def get_facts_from_memories(
        memories: List[dict], uid: str, user_name: str, existing_facts: List[Fact]
) -> List[Tuple[str, List[Fact]]]:
    print('get_facts_from_memories', len(memories), user_name, len(existing_facts))

    all_facts = {}

    def execute(memory):
        data = Memory(**memory)
        new_facts = new_facts_extractor(uid, data.transcript_segments, user_name, Fact.get_facts_as_str(existing_facts))
        if not new_facts:
            return
        all_facts[memory['id']] = new_facts

    threads = []
    for memory in memories:
        t = threading.Thread(target=execute, args=(memory,))
        threads.append(t)

    [t.start() for t in threads]
    [t.join() for t in threads]

    response = []
    for key, value in all_facts.items():
        memory_id, facts = key, value
        memory = next((m for m in memories if m['id'] == memory_id), None)
        parsed_facts = []
        response += facts
        for fact in facts:
            parsed_facts.append(FactDB.from_fact(fact, uid, memory['id'], memory['structured']['category']))
        facts_db.save_facts(uid, [fact.dict() for fact in parsed_facts])

    return response


def execute_for_user(uid: str):
    facts_db.delete_facts(uid)
    print('execute_for_user', uid, 'deleted facts')
    memories = memories_db.get_memories(uid, limit=2000)
    print('execute_for_user', uid, 'found memories', len(memories))
    user_name = get_user_name(uid)
    facts = []
    chunk_size = 10
    for i in range(0, len(memories), chunk_size):
        new_facts = get_facts_from_memories(memories[i:i + chunk_size], uid, user_name, facts)
        facts += new_facts


def script_migrate_users():
    # uids = get_users_uid()
    # print('Migrating', len(uids), 'users')
    uids = ['viUv7GtdoHXbK1UBCDlPuTDuPgJ2']

    threads = []
    for uid in uids:
        t = threading.Thread(target=execute_for_user, args=(uid,))
        threads.append(t)

    chunk_size = 1
    chunks = [threads[i:i + chunk_size] for i in range(0, len(threads), chunk_size)]
    for i, chunk in enumerate(chunks):
        # print('STARTING CHUNK', i + 1)
        [t.start() for t in chunk]
        [t.join() for t in chunk]


if __name__ == '__main__':
    script_migrate_users()

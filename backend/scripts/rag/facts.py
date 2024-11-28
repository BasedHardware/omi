import threading
from typing import Tuple

import firebase_admin

from _shared import *
from models.facts import Fact, FactDB

firebase_admin.initialize_app()
from utils.llm import new_facts_extractor
import database.facts as facts_db


def get_facts_from_memories(memories: List[dict], uid: str) -> List[Tuple[str, List[Fact]]]:
    all_facts = {}
    chunks = [memories[i:i + 25] for i in range(0, len(memories), 25)]

    def execute(chunk):
        only_facts: List[Fact] = []
        for i, memory in enumerate(chunk):
            data = Memory(**memory)
            new_facts = new_facts_extractor(uid, data.transcript_segments)
            if not new_facts:
                continue
            all_facts[memory['id']] = new_facts
            only_facts.extend(new_facts)

            print(uid, 'Memory #', i + 1, 'retrieved', len(new_facts), 'facts')

    threads = []
    for chunk in chunks:
        t = threading.Thread(target=execute, args=(chunk,))
        threads.append(t)

    [t.start() for t in threads]
    [t.join() for t in threads]

    for key, value in all_facts.items():
        memory_id, facts = key, value
        memory = next((m for m in memories if m['id'] == memory_id), None)
        parsed_facts = []
        for fact in facts:
            parsed_facts.append(FactDB.from_fact(fact, uid, memory['id'], memory['structured']['category']))
        facts_db.save_facts(uid, [fact.dict() for fact in parsed_facts])



def execute_for_user(uid: str):
    facts_db.delete_facts(uid)

    memories = memories_db.get_memories(uid, limit=2000)
    get_facts_from_memories(memories, uid)


def script_migrate_users():
    # uids = get_users_uid()
    # print('Migrating', len(uids), 'users')
    uids = ['yOnlnL4a3CYHe6Zlfotrngz9T3w2']
    execute_for_user(uids[0])

    # threads = []
    # for uid in uids:
    #     t = threading.Thread(target=execute_for_user, args=(uid,))
    #     threads.append(t)

    # chunk_size = 1
    # chunks = [threads[i:i + chunk_size] for i in range(0, len(threads), chunk_size)]
    # for i, chunk in enumerate(chunks):
    #     print('STARTING CHUNK', i + 1)
    #     [t.start() for t in chunk]
    #     [t.join() for t in chunk]


if __name__ == '__main__':
    script_migrate_users()

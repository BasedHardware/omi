import database.facts as facts_db
from utils.llm import new_facts_extractor, new_learnings_extractor
import threading
from typing import Tuple

import firebase_admin

from scripts.rag._shared import *
from database.auth import get_user_name
from database._client import get_users_uid
from models.facts import Fact, FactDB

firebase_admin.initialize_app()


def get_facts_from_memories(
        memories: List[dict], uid: str, user_name: str, existing_facts: List[Fact]
) -> List[Tuple[str, List[Fact]]]:
    print('get_facts_from_memories', len(memories), user_name, len(existing_facts))

    # learning_facts = list(filter(lambda x: x.category == 'learnings', existing_facts))
    all_facts = {}

    def execute(memory):
        data = Memory(**memory)
        new_facts = new_facts_extractor(uid, data.transcript_segments, user_name, Fact.get_facts_as_str(existing_facts))
        # new_learnings = new_learnings_extractor(
        #     uid, data.transcript_segments, user_name,
        #     Fact.get_facts_as_str(learning_facts)
        # )
        # print('Found', len(new_facts), 'new facts and', len(new_learnings), 'new learnings')
        # new_facts += new_learnings
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
            parsed_facts.append(FactDB.from_fact(fact, uid, memory['id'], memory['structured']['category'],False))
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


# migrate scoring for facts
def migration_fact_scoring_for_user(uid: str):
    print('migration_fact_scoring_for_user', uid)
    offset = 0
    while True:
        facts_data = facts_db.get_non_filtered_facts(uid, limit=400, offset=offset)
        facts = [FactDB(**d) for d in facts_data]
        if not facts or len(facts) == 0:
            break

        print('execute_for_user', uid, 'found facts', len(facts))
        for fact in facts:
            fact.scoring = FactDB.calculate_score(fact)
        facts_db.save_facts(uid, [fact.dict() for fact in facts])
        offset += len(facts)

def script_migrate_fact_scoring_users(uids: [str]):
    threads = []
    for uid in uids:
        t = threading.Thread(target=migration_fact_scoring_for_user, args=(uid,))
        threads.append(t)

    chunk_size = 1
    chunks = [threads[i:i + chunk_size] for i in range(0, len(threads), chunk_size)]
    for i, chunk in enumerate(chunks):
        [t.start() for t in chunk]
        [t.join() for t in chunk]

def script_migrate_fact_scoring():
    uids = get_users_uid()
    print(f"script_migrate_fact_scoring {len(uids)} users")
    chunk_size = 10
    for i in range(0, len(uids), chunk_size):
        script_migrate_fact_scoring_users(uids[i: i + chunk_size])
        print(f"[progress] migrating {i+1}/{len(uids)}...")


if __name__ == '__main__':
    script_migrate_users()

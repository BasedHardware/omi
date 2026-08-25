import threading
from typing import Any, Dict, List, Optional, cast

import firebase_admin

import database.memories as memories_db
from database._client import get_users_uid
from database.auth import get_user_name
from models.conversation import Conversation
from models.memories import Memory, MemoryDB
from utils.llm.memories import new_memories_extractor
from utils.log_sanitizer import sanitize_pii

from scripts.rag._shared import *

# firebase_admin's initialize_app ships with partially-unknown parameter types.
cast(Any, firebase_admin).initialize_app()


def get_memories_from_conversations(
    conversations: List[Dict[str, Any]], uid: str, user_name: Optional[str], existing_memories: List[Memory]
) -> List[Memory]:
    print('get_memories_from_conversations', len(conversations), sanitize_pii(user_name), len(existing_memories))

    # learning_facts = list(filter(lambda x: x.category == 'learnings', existing_facts))
    all_memories: Dict[Any, List[Memory]] = {}

    def execute(conversation: Dict[str, Any]) -> None:
        data = Conversation(**conversation)
        new_memories = new_memories_extractor(
            uid, data.transcript_segments, user_name, Memory.get_memories_as_str(existing_memories)
        )
        # new_learnings = new_learnings_extractor(
        #     uid, data.transcript_segments, user_name,
        #     Fact.get_facts_as_str(learning_facts)
        # )
        # print('Found', len(new_facts), 'new facts and', len(new_learnings), 'new learnings')
        # new_facts += new_learnings
        if not new_memories:
            return
        all_memories[conversation['id']] = new_memories

    threads: List[threading.Thread] = []
    for conversation in conversations:
        t = threading.Thread(target=execute, args=(conversation,))
        threads.append(t)

    [t.start() for t in threads]
    [t.join() for t in threads]

    response: List[Memory] = []
    for key, value in all_memories.items():
        conversation_id, memories = key, value
        conversation = next((m for m in conversations if m['id'] == conversation_id), None)
        if conversation is None:
            continue
        parsed_memories: List[MemoryDB] = []
        response += memories
        for memory in memories:
            parsed_memories.append(MemoryDB.from_memory(memory, uid, conversation['id'], False))
        memories_db.save_memories(uid, [memory.dict() for memory in parsed_memories])

    return response


def execute_for_user(uid: str) -> None:
    memories_db.delete_memories(uid)
    print('execute_for_user', uid, 'deleted memories')
    conversations = conversations_db.get_conversations(uid, limit=2000)
    print('execute_for_user', uid, 'found conversations', len(conversations))
    user_name = get_user_name(uid)
    memories: List[Memory] = []
    chunk_size = 10
    for i in range(0, len(conversations), chunk_size):
        new_memories = get_memories_from_conversations(conversations[i : i + chunk_size], uid, user_name, memories)
        memories += new_memories


def script_migrate_users() -> None:
    # uids = get_users_uid()
    # print('Migrating', len(uids), 'users')
    uids = ['viUv7GtdoHXbK1UBCDlPuTDuPgJ2']

    threads: List[threading.Thread] = []
    for uid in uids:
        t = threading.Thread(target=execute_for_user, args=(uid,))
        threads.append(t)

    chunk_size = 1
    chunks = [threads[i : i + chunk_size] for i in range(0, len(threads), chunk_size)]
    for _i, chunk in enumerate(chunks):
        # print('STARTING CHUNK', _i + 1)
        [t.start() for t in chunk]
        [t.join() for t in chunk]


# migrate scoring for facts
def migration_fact_scoring_for_user(uid: str) -> None:
    print('migration_fact_scoring_for_user', uid)
    offset = 0
    while True:
        facts_data = memories_db.get_non_filtered_memories(uid, limit=400, offset=offset)
        facts = [MemoryDB(**d) for d in facts_data]
        if not facts or len(facts) == 0:
            break

        print('execute_for_user', uid, 'found facts', len(facts))
        for fact in facts:
            fact.scoring = MemoryDB.calculate_score(fact)
        memories_db.save_memories(uid, [fact.dict() for fact in facts])
        offset += len(facts)


def script_migrate_fact_scoring_users(uids: List[str]) -> None:
    threads: List[threading.Thread] = []
    for uid in uids:
        t = threading.Thread(target=migration_fact_scoring_for_user, args=(uid,))
        threads.append(t)

    chunk_size = 1
    chunks = [threads[i : i + chunk_size] for i in range(0, len(threads), chunk_size)]
    for _i, chunk in enumerate(chunks):
        [t.start() for t in chunk]
        [t.join() for t in chunk]


def script_migrate_fact_scoring() -> None:
    uids = get_users_uid()
    print(f"script_migrate_fact_scoring {len(uids)} users")
    chunk_size = 10
    for i in range(0, len(uids), chunk_size):
        script_migrate_fact_scoring_users(uids[i : i + chunk_size])
        print(f"[progress] migrating {i+1}/{len(uids)}...")


if __name__ == '__main__':
    script_migrate_users()

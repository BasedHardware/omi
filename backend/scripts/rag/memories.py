import threading
from typing import Any, Dict, List, Optional, cast

import firebase_admin

from models.conversation import Conversation
from models.memories import Memory, MemoryDB
from utils.llm.memories import new_memories_extractor
from utils.log_sanitizer import sanitize_pii
from utils.memory.memory_service import MemoryService

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
        MemoryService().write_batch(uid, [memory.model_dump(mode='python') for memory in parsed_memories])

    return response

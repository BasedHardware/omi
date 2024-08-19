from typing import List, Tuple

from database.memories import filter_memories_by_date, get_memories_by_id
from database.vector_db import query_vectors
from models.chat import Message
from models.memory import Memory
from utils.llm import determine_requires_context


def retrieve_rag_context(uid: str, prev_messages: List[Message]) -> Tuple[str, List[Memory]]:
    context = determine_requires_context(prev_messages)
    if not context or (not context[0] and not context[1]):
        return '', []

    topics = context[0]
    dates_range = context[1]
    start_timestamp = dates_range[0].timestamp() if dates_range else None
    end_timestamp = dates_range[1].timestamp() if dates_range else None

    def retrieve_for_topic(topic: str) -> List[str]:
        return query_vectors(topic, uid, starts_at=start_timestamp, ends_at=end_timestamp)

    memories_id = []
    if topics:
        for topic in topics:
            memories_id.extend(retrieve_for_topic(topic))
        memories = get_memories_by_id(uid, memories_id)
    else:
        memories = filter_memories_by_date(uid, dates_range[0], dates_range[1])
    print('Found', len(memories), 'memories for context')
    memories = [Memory(**memory) for memory in memories]

    return Memory.memories_to_string(memories), memories

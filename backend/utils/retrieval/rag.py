import threading
from collections import Counter, defaultdict
from typing import List, Tuple

from database.memories import filter_memories_by_date, get_memories_by_id
from database.vector_db import query_vectors
from models.chat import Message
from models.memory import Memory
from utils.llm import requires_context, retrieve_context_params, retrieve_context_dates


def retrieve_rag_context(uid: str, prev_messages: List[Message]) -> Tuple[str, List[Memory]]:
    requires = requires_context(prev_messages)
    if not requires:
        return '', []

    topics = retrieve_context_params(prev_messages)
    dates_range = retrieve_context_dates(prev_messages)
    print('retrieve_rag_context', topics, dates_range)
    if not topics and not dates_range:
        return '', []

    if len(topics) > 5:
        topics = topics[:5]

    def retrieve_for_topic(topic: str, start_timestamp, end_timestamp, memories_id) -> List[str]:
        result = query_vectors(topic, uid, starts_at=start_timestamp, ends_at=end_timestamp)
        print('retrieve_for_topic', topic, len(result))
        for memory_id in result:
            memories_id[memory_id] += 1
        return result

    start_timestamp = dates_range[0].timestamp() if dates_range else None
    end_timestamp = dates_range[1].timestamp() if dates_range else None

    if topics:
        memories_id = defaultdict(int)
        threads = []
        for topic in topics:
            t = threading.Thread(target=retrieve_for_topic, args=(topic, start_timestamp, end_timestamp, memories_id))
            threads.append(t)
        [t.start() for t in threads]
        [t.join() for t in threads]

        # FIXME, fix the source of the issue, not this patch
        if not memories_id and dates_range:
            threads = []
            for topic in topics:
                t = threading.Thread(target=retrieve_for_topic, args=(topic, None, None, memories_id))
                threads.append(t)
            [t.start() for t in threads]
            [t.join() for t in threads]

        memories = get_memories_by_id(uid, memories_id)
    else:
        memories = filter_memories_by_date(uid, dates_range[0], dates_range[1])

    print('Found', len(memories), 'memories for context')
    id_counter = Counter(memory['id'] for memory in memories)
    sorted_memories = sorted(memories, key=lambda x: id_counter[x['id']], reverse=True)
    sorted_memory_objects = [Memory(**memory) for memory in sorted_memories]

    if len(sorted_memory_objects) > 10:
        sorted_memory_objects = sorted_memory_objects[:10]

    return Memory.memories_to_string(sorted_memory_objects), sorted_memory_objects

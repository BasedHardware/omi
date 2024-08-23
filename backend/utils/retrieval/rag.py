import threading
from collections import Counter, defaultdict
from typing import List, Tuple

from database.memories import filter_memories_by_date, get_memories_by_id
from database.vector_db import query_vectors
from models.chat import Message
from models.memory import Memory
from models.transcript_segment import TranscriptSegment
from utils.llm import requires_context, retrieve_context_params, retrieve_context_dates, chunk_extraction, \
    num_tokens_from_string, retrieve_memory_context_params


def retrieve_for_topic(uid: str, topic: str, start_timestamp, end_timestamp, k: int, memories_id) -> List[str]:
    result = query_vectors(topic, uid, starts_at=start_timestamp, ends_at=end_timestamp, k=k)
    print('retrieve_for_topic', topic, [start_timestamp, end_timestamp], 'found:', len(result), 'vectors')
    for memory_id in result:
        memories_id[memory_id].append(topic)
    return result


def retrieve_memories_for_topics(uid: str, topics: List[str], dates_range: List):
    start_timestamp = dates_range[0].timestamp() if dates_range else None
    end_timestamp = dates_range[1].timestamp() if dates_range else None

    memories_id = defaultdict(list)
    threads = []
    top_k = 10 if len(topics) == 1 else 5
    for topic in topics:
        t = threading.Thread(target=retrieve_for_topic,
                             args=(uid, topic, start_timestamp, end_timestamp, top_k, memories_id))
        threads.append(t)
    [t.start() for t in threads]
    [t.join() for t in threads]

    # FIXME, fix the source of the issue, not this patch
    if not memories_id and dates_range:
        threads = []
        for topic in topics:
            t = threading.Thread(target=retrieve_for_topic, args=(uid, topic, None, None, top_k, memories_id))
            threads.append(t)
        [t.start() for t in threads]
        [t.join() for t in threads]

    return memories_id, get_memories_by_id(uid, memories_id.keys())


def get_better_memory_chunk(memory: Memory, topics: List[str], context_data: dict) -> str:
    print('get_better_memory_chunk', memory.id, topics)
    conversation = TranscriptSegment.segments_as_string(memory.transcript_segments, include_timestamps=True)
    if num_tokens_from_string(conversation) < 250:
        return Memory.memories_to_string([memory])
    chunk = chunk_extraction(memory.transcript_segments, topics)
    if not chunk or len(chunk) < 10:
        return
    context_data[memory.id] = chunk


def retrieve_rag_context(
        uid: str, prev_messages: List[Message], return_context_params: bool = False
) -> Tuple[str, List[Memory]]:
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

    memories_id_to_topics = {}
    memories = None
    if topics:
        memories_id_to_topics, memories = retrieve_memories_for_topics(uid, topics, dates_range)
        id_counter = Counter(memory['id'] for memory in memories)
        memories = sorted(memories, key=lambda x: id_counter[x['id']], reverse=True)

    if not memories and dates_range:
        memories_id_to_topics = {}
        memories = filter_memories_by_date(uid, dates_range[0], dates_range[1])

    memories = [Memory(**memory) for memory in memories]
    if len(memories) > 10:
        memories = memories[:10]

    # not performing as expected
    if memories_id_to_topics:
        context_data = {}
        threads = []
        for memory in memories:
            m_topics = memories_id_to_topics.get(memory.id, [])
            t = threading.Thread(target=get_better_memory_chunk, args=(memory, m_topics, context_data))
            threads.append(t)
        [t.start() for t in threads]
        [t.join() for t in threads]
        memories = list(filter(lambda x: x.id in context_data, memories))
        context_str = '\n\n---------------------\n\n'.join(context_data.values()).strip()
    else:
        context_str = Memory.memories_to_string(memories)

    if return_context_params:
        return context_str, (memories if context_str else []), topics, dates_range

    return context_str, (memories if context_str else [])


def retrieve_rag_memory_context(uid: str, memory: Memory) -> Tuple[str, List[Memory]]:
    topics = retrieve_memory_context_params(memory)
    print('retrieve_memory_rag_context', topics)
    if not topics:
        return '', []

    if len(topics) > 5:
        topics = topics[:5]

    memories_id_to_topics = {}
    if topics:
        memories_id_to_topics, memories = retrieve_memories_for_topics(uid, topics, [])
        id_counter = Counter(memory['id'] for memory in memories)
        memories = sorted(memories, key=lambda x: id_counter[x['id']], reverse=True)

    memories = [Memory(**memory) for memory in memories]
    if len(memories) > 10:
        memories = memories[:10]

    if memories_id_to_topics:
        # TODO: restore sorthing here
        context_data = {}
        threads = []
        for memory in memories:
            topics = memories_id_to_topics.get(memory.id, [])
            t = threading.Thread(target=get_better_memory_chunk, args=(memory, topics, context_data))
            threads.append(t)
        [t.start() for t in threads]
        [t.join() for t in threads]
        context_str = '\n'.join(context_data.values()).strip()
    else:
        context_str = Memory.memories_to_string(memories)

    return context_str, (memories if context_str else [])

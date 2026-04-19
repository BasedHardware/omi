from collections import Counter, defaultdict
from typing import List, Tuple

import database.users as users_db
from database.auth import get_user_name
from database.conversations import get_conversations_by_id
from database.vector_db import query_vectors
from models.conversation import Conversation
from models.other import Person
from utils.conversations.factory import deserialize_conversations
from utils.conversations.render import conversations_to_string
from models.transcript_segment import TranscriptSegment
from utils.llm.chat import chunk_extraction, retrieve_memory_context_params
from utils.llm.clients import num_tokens_from_string
from utils.executors import critical_executor
import logging

logger = logging.getLogger(__name__)


def retrieve_for_topic(uid: str, topic: str, start_timestamp, end_timestamp, k: int, memories_id) -> List[str]:
    result = query_vectors(topic, uid, starts_at=start_timestamp, ends_at=end_timestamp, k=k)
    logger.info(f'retrieve_for_topic {topic} {[start_timestamp, end_timestamp]} found: {len(result)} vectors')
    for memory_id in result:
        memories_id[memory_id].append(topic)
    return result


def retrieve_memories_for_topics(uid: str, topics: List[str], dates_range: List):
    start_timestamp = dates_range[0].timestamp() if len(dates_range) == 2 else None
    end_timestamp = dates_range[1].timestamp() if len(dates_range) == 2 else None

    memories_id = defaultdict(list)
    top_k = 10 if len(topics) == 1 else 5
    futures = [
        critical_executor.submit(retrieve_for_topic, uid, topic, start_timestamp, end_timestamp, top_k, memories_id)
        for topic in topics
    ]
    for f in futures:
        f.result()

    # FIXME, fix the source of the issue, not this patch
    if not memories_id and len(dates_range) == 2:
        futures = [
            critical_executor.submit(retrieve_for_topic, uid, topic, None, None, top_k, memories_id) for topic in topics
        ]
        for f in futures:
            f.result()

    return memories_id, get_conversations_by_id(uid, memories_id.keys())


def get_better_conversation_chunk(
    memory: Conversation, topics: List[str], context_data: dict, people: List[Person] = None, user_name: str = None
) -> str:
    logger.info(f'get_better_memory_chunk {memory.id} {topics}')
    conversation = TranscriptSegment.segments_as_string(
        memory.transcript_segments, include_timestamps=True, people=people, user_name=user_name
    )
    if num_tokens_from_string(conversation) < 250:
        return conversations_to_string([memory], people=people, user_name=user_name)
    chunk = chunk_extraction(memory.transcript_segments, topics, people=people, user_name=user_name)
    if not chunk or len(chunk) < 10:
        return
    context_data[memory.id] = chunk


def retrieve_rag_conversation_context(uid: str, memory: Conversation) -> Tuple[str, List[Conversation]]:
    topics = retrieve_memory_context_params(uid, memory.transcript_segments, memory.get_person_ids())
    logger.info(f'retrieve_memory_rag_context {topics}')
    if not topics:
        return '', []

    if len(topics) > 5:
        topics = topics[:5]

    memories_id_to_topics = {}
    if topics:
        memories_id_to_topics, memories = retrieve_memories_for_topics(uid, topics, [])
        id_counter = Counter(memory['id'] for memory in memories)
        memories = sorted(memories, key=lambda x: id_counter[x['id']], reverse=True)

    memories = deserialize_conversations(memories)
    if len(memories) > 10:
        memories = memories[:10]

    all_person_ids = []
    for m in memories:
        all_person_ids.extend(m.get_person_ids())

    people = []
    if all_person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(all_person_ids)))
        people = [Person(**p) for p in people_data]

    user_name = get_user_name(uid, use_default=False)

    if memories_id_to_topics:
        # TODO: restore sorting here
        context_data = {}
        futures = [
            critical_executor.submit(
                get_better_conversation_chunk, m, memories_id_to_topics.get(m.id, []), context_data, people, user_name
            )
            for m in memories
        ]
        for f in futures:
            f.result()
        context_str = '\n'.join(context_data.values()).strip()
    else:
        context_str = conversations_to_string(memories, people=people, user_name=user_name)

    return context_str, (memories if context_str else [])

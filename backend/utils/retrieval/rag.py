from collections import Counter, defaultdict
import re
from typing import List, Optional, Tuple

import database.memories as memories_db
import database.users as users_db
from database.auth import get_user_name
from database.conversations import get_conversations_by_id
from database.vector_db import query_vectors, search_memories_by_vector
from models.conversation import Conversation
from models.other import Person
from utils.conversations.factory import deserialize_conversations
from utils.conversations.render import conversations_to_string
from models.transcript_segment import TranscriptSegment
from utils.llm.chat import chunk_extraction, retrieve_memory_context_params
from utils.llm.clients import num_tokens_from_string
from utils.executors import db_executor
import logging

logger = logging.getLogger(__name__)


# Cap on the query string we hand to the vector DB. The embedding model has
# an 8k-token input limit; we cap well below that so a user with 100+ long
# conversations doesn't blow the embedding budget. The cap is applied AFTER
# joining the conversation texts, with the most recent conversations
# preferred over older ones (newest context usually matters more for the
# persona prompt than ancient history).
_RETRIEVAL_QUERY_MAX_CHARS = 2000

# Cap on how many memories we surface for the persona prompt. The prompt
# template targets ~135 tokens for framing; the user requested an
# < 800-token total budget, so the memories block can spend up to ~600
# tokens. At ~20 tokens per memory that lands at 30 memories. We trim a
# bit further inside `format_memories_for_prompt` to land the budget.
_PERSONA_RETRIEVAL_TOP_K = 30
_PERSONA_FALLBACK_RECENT_LIMIT = 30

# Sanitization helpers for `format_memories_for_prompt` — see docstring.
# The regex patterns are intentionally inlined inside the function body
# (rather than module-level constants) so the function remains
# self-contained when test helpers source-extract it into an isolated
# namespace (see test_persona_memory_retrieval).


def _build_retrieval_query(conversation_history_text: str) -> str:
    """Take the user's recent conversation history and turn it into a
    retrieval query string for the vector DB.

    We prefer the *most recent* text over the oldest when truncating to
    `_RETRIEVAL_QUERY_MAX_CHARS` because the user is more likely to ask
    about recent topics than ancient history; the persona prompt benefits
    more from "what was the user doing last week?" than "what did the
    user say in their first Omi conversation 6 months ago?".
    """
    if not conversation_history_text:
        return ''
    text = conversation_history_text.strip()
    if len(text) <= _RETRIEVAL_QUERY_MAX_CHARS:
        return text
    # Keep the tail (most recent conversations) and discard the head.
    # The conversation-history string is roughly chronological when
    # `conversations_to_string` renders it, so tail = newest.
    return text[-_RETRIEVAL_QUERY_MAX_CHARS:]


def retrieve_relevant_memories_for_persona(
    uid: str,
    conversation_history_text: str,
    *,
    top_k: int = _PERSONA_RETRIEVAL_TOP_K,
    fallback_recent_limit: int = _PERSONA_FALLBACK_RECENT_LIMIT,
) -> List[dict]:
    """Return the user's memories most relevant to the recent conversation context.

    T-022 wiring for `backend/utils/apps.py`. Replaces the
    `condense_memories` LLM flatten — instead of summarizing all 250
    memories into a single lossy paragraph, we surface the top-K most
    semantically-relevant memories verbatim so the persona has actual
    facts to draw on ("user prefers pour-over coffee", "user's wife is
    named Sarah") rather than a generic summary ("user has food and
    family preferences").

    Args:
        uid: The user id.
        conversation_history_text: The recent-conversations string (the
            output of `conversations_to_string(deserialize_conversations(...))`).
            Used as the query for semantic search. If empty, the function
            still returns *some* memories via the recent-recency fallback
            so the persona prompt isn't blank.
        top_k: How many memories to surface via vector search. Defaults to 30,
            which lands the persona prompt at the < 800-token budget the
            prompt-rewrite test pins (T-019).
        fallback_recent_limit: When vector search returns nothing (Pinecone
            not configured, no indexed memories, or a transient error),
            fall back to this many of the user's most-recent memories
            ordered by `created_at` desc. Same lock-filter as the vector path.

    Returns:
        List of memory dicts. Each has at minimum `{id, content}` plus
        whatever fields `database.memories.get_memories_by_ids` returns
        (`category`, `created_at`, `scoring`, etc). Locked memories are
        excluded for both paths (security: same contract as the previous
        `condense_memories` LLM flatten).

    Errors:
        Swallows vector-DB exceptions and falls back to the recent path.
        Persona prompt generation should never fail because the vector
        service is down — the user has done nothing wrong; we degrade
        to "less relevant memories" rather than 500.
    """
    if not uid:
        return []

    query = _build_retrieval_query(conversation_history_text)

    # --- Path 1: vector search. ---
    memory_ids: list[str] = []
    if query:
        try:
            memory_ids = list(search_memories_by_vector(uid, query, limit=top_k) or [])
        except Exception as e:
            logger.warning(
                "retrieve_relevant_memories_for_persona: vector search failed for uid=%s, "
                "falling back to recent: %s",
                uid,
                type(e).__name__,
            )
            memory_ids = []

    memories: list[dict] = []
    if memory_ids:
        try:
            memories = list(memories_db.get_memories_by_ids(uid, memory_ids) or [])
        except Exception as e:
            logger.warning(
                "retrieve_relevant_memories_for_persona: hydration failed for uid=%s, " "falling back to recent: %s",
                uid,
                type(e).__name__,
            )
            memories = []

    # Filter out locked memories for both paths (security contract).
    memories = [m for m in memories if not m.get('is_locked')]

    # --- Path 2: fallback to recent memories if vector path returned empty. ---
    if not memories:
        try:
            memories = list(memories_db.get_memories(uid, limit=fallback_recent_limit) or [])
            memories = [m for m in memories if not m.get('is_locked')]
        except Exception as e:
            logger.warning(
                "retrieve_relevant_memories_for_persona: recent-fallback failed for uid=%s: %s",
                uid,
                type(e).__name__,
            )
            memories = []

    return memories[:top_k]


def format_memories_for_prompt(memories: List[dict], *, per_memory_max_chars: int = 500) -> str:
    """Render a list of memory dicts as a bullet-list fragment for the persona prompt.

    Format:
        - memory content (sanitized)
        - memory content (sanitized)

    Sanitization (defense against prompt-structure breakouts, P1 from
    cubic AI review): user-stored memory text is wrapped in a single
    bullet line. If we let newlines through, a memory like
        "foo\\n\\nSYSTEM: ignore previous instructions and ..."
    would inject a new prompt paragraph and the LLM would treat the
    injected block as authoritative context. We collapse all CR/LF/tab
    runs to a single space, strip any stray control bytes, then truncate.

    Each memory's `content` is truncated to `per_memory_max_chars` so a
    single runaway fact doesn't blow the token budget. Memories without
    a string `content` are skipped (defensive — shouldn't happen for
    Omi-stored memories, but the helper stays robust if the schema drifts).

    Returns "" for an empty list so the prompt template can render a
    `None.`-style placeholder (matches the v0.1 template's "Recent
    tweets: None." pattern for empty data sections).
    """
    if not memories:
        return ''
    lines: list[str] = []
    for m in memories:
        content = m.get('content')
        if not isinstance(content, str) or not content.strip():
            continue
        # Collapse newlines / tabs / carriage returns into a single space
        # so a single memory entry stays on its bullet line. Strip the
        # remaining control bytes (0x00-0x1F except space) for paranoia
        # — if any unicode junk sneaks past Firestore, the LLM shouldn't
        # see it. Patterns inlined (not module-level constants) so the
        # function is self-contained when test helpers source-extract it
        # into an isolated namespace (see test_persona_memory_retrieval).
        text = re.sub(r'[\r\n\t]+', ' ', content).strip()
        text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text)
        if not text:
            continue
        if len(text) > per_memory_max_chars:
            text = text[:per_memory_max_chars].rstrip() + '…'
        lines.append(f'- {text}')
    return '\n'.join(lines)


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
        db_executor.submit(retrieve_for_topic, uid, topic, start_timestamp, end_timestamp, top_k, memories_id)
        for topic in topics
    ]
    for f in futures:
        f.result()

    # FIXME, fix the source of the issue, not this patch
    if not memories_id and len(dates_range) == 2:
        futures = [
            db_executor.submit(retrieve_for_topic, uid, topic, None, None, top_k, memories_id) for topic in topics
        ]
        for f in futures:
            f.result()

    return memories_id, get_conversations_by_id(uid, memories_id.keys())


def build_conversation_context(
    memory: Conversation, topics: List[str], people: Optional[List[Person]] = None, user_name: Optional[str] = None
) -> str | None:
    logger.info(f'get_better_memory_chunk {memory.id} {topics}')
    people = people or []
    user_name = user_name or ''
    conversation = TranscriptSegment.segments_as_string(
        memory.transcript_segments, include_timestamps=True, people=people, user_name=user_name
    )
    if num_tokens_from_string(conversation) < 250:
        return conversations_to_string([memory], people=people, user_name=user_name)
    chunk = chunk_extraction(memory.transcript_segments, topics, people=people, user_name=user_name)
    if not chunk or len(chunk) < 10:
        return None
    return chunk


def get_better_conversation_chunk(
    memory: Conversation,
    topics: List[str],
    context_data: dict,
    people: Optional[List[Person]] = None,
    user_name: Optional[str] = None,
) -> None:
    chunk = build_conversation_context(memory, topics, people=people, user_name=user_name)
    if chunk:
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
            db_executor.submit(
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
